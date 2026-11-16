import json
from typing import Any, Dict, List, AsyncGenerator
import asyncio

import pandas as pd
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from beeflow.nodes.base_node import END, INPUT, OUTPUT, START
from beeflow.nodes.flow.branch_node import BranchNode
from beeflow.nodes.graph.graph_node import GraphNode
from beeflow.nodes.primitives.ai.llm_node import LLMNode
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beeflow.nodes.templates.basic_chain_node import BasicChainNode
from beeflow.nodes.templates.retriever_node_v2 import RetrieverNode
from beeflow.nodes.primitives.data.redis_node import RedisNode, RedisOperation

from beeflow.workflow import WorkflowEngine
from beeflow.utils.streaming import STREAM_SERVICE
from beegen.loggings.loggers import LOGGER
from beegen.registry.resource_hub import ResourceHub
from beegen.utils.common import fake_chunk_from, transform_bot_id
from beeportal.beecrm.services.hierarchy import hierarchy
from beeportal.beecrm.services.redis_sv import manage_session_hierarchy_with_comparison
from beeportal.beecrm.services.scoring import run_query_industry
from beeportal.beecrm.utils import *
from beeportal.utils import PROMPTS


class BeeCRMBot:
    def __init__(self, bot_id: str):
        self.bot_id = bot_id
        mongo_engine = ResourceHub.self().sync_mongo("aicenter-chatbot")
        bot_info = mongo_engine._find_one(collection_name="botinfo", query={"_id": self.bot_id})
        self.name = bot_info.get("data", {}).get("name")
        self.config = bot_info.get("data", {}).get("metadata", {})
        self._build_flow()

    def _build_flow(self) -> None:
        with WorkflowEngine(
            name="beecrm",
            description="BeeCRM skeleton flow",
        ) as beecrm:
            
            code_init_query = CodeNode(
                name="code_init_query",
                code_fn=init_query,
                inputs={"messages": INPUT},
                return_keys=["origin_query: str", "conversation: List[Dict[str, Any]]"],
            )

            code_verify_workflow = CodeNode(
                name="code_verify_workflow",
                code_fn=verify_workflow_type,
                inputs={"metadata": INPUT},
                return_keys=["workflow: str"],
            )

            with GraphNode(
                name="graph_get_cache",
                description="Get cache in session",
                inputs={
                    "session_id": INPUT,
                },
            ) as graph_get_cache:

                redis_get_cache_template = RedisNode(
                    name="redis_get_template",
                    resource_key="aicenter-chatbot",
                    operation=RedisOperation.GET,
                    inputs={
                        "key": {INPUT: "session_id"}
                    },
                )

                code_postprocess_redis = CodeNode(
                    name="postprocess_redis",
                    code_fn=postprocess_redis_value,
                    inputs={"redis_output": {redis_get_cache_template: "value"}},  
                    return_keys=["values: Dict[str, Any]"],
                    outputs=OUTPUT
                    )

                START >> redis_get_cache_template >> code_postprocess_redis >> END
            
            code_select_template = CodeNode(
                name="code_select_template",
                code_fn= select_template,
                inputs={
                    "cached": {graph_get_cache: "values"},
                },
                return_keys=["template_askback: str", "template_rcm: str"],
                outputs = {"template_askback": OUTPUT, "template_rcm": OUTPUT}
            )

            # region ===== Flow GPT =====
            with GraphNode(
                name="graph_gpt_flow",
                description="Handle GPT workflow routing",
                inputs={
                    "origin_query": code_init_query,
                    "metadata": INPUT,
                    "cached": {graph_get_cache: "values"},
                    "username": INPUT,
                    "conversation": code_init_query,
                    "template_askback": code_select_template,
                    "template_rcm": code_select_template,
                },
            ) as graph_gpt_flow:
                
                code_check_switch = CodeNode(
                    name="code_check_switch",
                    code_fn=check_switch_state,
                    inputs={
                        "metadata": {INPUT: "metadata"},
                        "cached": INPUT,
                    },
                    return_keys=["switch_route: str", "updated_metadata: Dict[str, Any]"],
                )


                # region =============== Flow Askback =======================
                with GraphNode(
                    name="graph_askback_flow",
                    description="Ask back to get personal info",
                    inputs={
                        "template_askback": INPUT,
                        "updated_metadata": code_check_switch
                    },
                    ) as graph_askback_flow:

                    llm_GPT_ASKBACK = LLMNode(
                        name="llm_GPT_ASKBACK",
                        resource_key="fake",
                        instant_response=True,
                        inputs={
                            "response": {INPUT: "template_askback"},
                            "custom_data": {INPUT: "updated_metadata"}                            
                            },
                        stream=True
                    )
                    START >> llm_GPT_ASKBACK >> END

                # endregion =============== Flow Askback =======================

                # region =============== Flow Recommend =======================
                with GraphNode(
                    name="graph_recommend_flow",
                    description="recommend the scenarios",
                    inputs={
                        "template_rcm": code_select_template,
                        "origin_query": INPUT,
                        "username": INPUT,
                        "updated_metadata": code_check_switch, 
                        "template_rcm": INPUT,
                        "cached": INPUT,
                    },
                ) as graph_recommend_flow:
                    
                    code_get_user_info = CodeNode(
                        name = "code_get_user_info",
                        code_fn= get_user_info_by_username,
                        inputs = {
                            "username": INPUT
                        },
                        return_keys=["user_info: str"]
                    )

                    llm_GPT_RCM = BasicChainNode(
                        name="llm_GPT_RCM",
                        resource_key="gpt-5.1-chat",
                        llm_configs= {"max_tokens": 16348},
                        user_prompt=PROMPTS["BEECRM:WRAPPER"],
                        inputs={ 
                                "prompt_rcm": {INPUT: "template_rcm"},
                                "query": {INPUT: "origin_query"},
                                "rm_info": {code_get_user_info: "user_info"},
                                "cached": INPUT,
                                "conversation": INPUT,
                                "custom_data": {INPUT: "updated_metadata"}},
                        stream=True
                    )

                    # --- Routing ---
                    START >> code_get_user_info >> llm_GPT_RCM >> END

                # endregion =============== Flow Recommend =======================


                llm_standard_flow = BasicChainNode(
                    name="llm_standard_flow",
                    resource_key="gpt-5.1-chat",
                    llm_configs= {"max_tokens": 16348},
                    user_prompt=PROMPTS["BEECRM:STANDARD_GPT"],
                    inputs={"origin_query": INPUT,
                            "conversation": INPUT,
                            "custom_data": {code_check_switch: "updated_metadata"}
                    },
                    stream=True
                )

                # Update routing logic
                branch_routing_switch = BranchNode(
                    name="routing_switch",
                    cases={
                        "switch_route == 'askback'": "graph_askback_flow",
                        "switch_route == 'recommend'": "graph_recommend_flow",
                    },
                    default="llm_standard_flow",
                    inputs={"switch_route": {code_check_switch: "switch_route"}},
                )


                START >>  code_check_switch >> branch_routing_switch >> [graph_askback_flow,
                                                                        graph_recommend_flow,
                                                                        llm_standard_flow] >> END
            # endregion ===== Flow GPT =====      

            # region ===== Flow Internal =====
            with GraphNode(
                name="graph_internal_flow",
                description="Handle internal workflow routing",
                inputs={
                    "origin_query": code_init_query,
                    "conversation": code_init_query,
                    "metadata": INPUT,
                    "cached": {graph_get_cache: "values"},
                    "session_id": INPUT,
                    "username": INPUT,
                    "template_rcm": code_select_template,
                },
                ) as graph_internal_flow:
                
                # region ================ button flow =======================
                with GraphNode(
                    name="graph_button_flow",
                    description="Recommend scenarios with qa cache",
                    inputs={
                        "origin_query": INPUT,
                        "username": INPUT,
                        "session_id": INPUT,
                        "cached": INPUT,
                        "metadata": INPUT,
                    },
                ) as graph_button_flow:
                    
                    retrieve_qa = RetrieverNode(
                        embedding="qwen-embedding-chat",
                        name="retrieve_qa",
                        inputs={
                            "query": {INPUT: "origin_query"},
                            "collection": custom_transform_bot_id(self.bot_id),
                            "top_k": 5,
                            "rerank_top_k": 1,
                            "output_fields": ["chunk_id"],
                            "allowed_roles": ["L1"],
                            "bot_id": self.bot_id,
                            "threshold": 0.95
                        }
                    )
                    
                    code_route_qa_flow = CodeNode(
                        name= "code_route_qa_flow",
                        code_fn= route_qa_flow,
                        inputs={
                            "docs": retrieve_qa,
                            "query": {INPUT: "origin_query"}
                            },
                        return_keys=["is_sub_category: bool", "is_rcm_business_industry: bool", "is_viewmore: bool", "is_rcm_standard: bool", "qa_cache: str"],
                    )

                    # region ============== L2 and rcm with L1 =================
                    with GraphNode(
                        name="graph_fake_chunk_qa",
                        description="graph_fake_chunk_qa",
                        inputs={
                            "qa_cache": code_route_qa_flow,
                            "session_id": INPUT,
                            "cached": INPUT,
                            "origin_query": INPUT,
                        },
                    ) as graph_fake_chunk_qa:
                        
                        code_extract_answer = CodeNode(
                            name="extract_answer",
                            code_fn=extract_answer_from_qa,
                            inputs={
                                "qa_content": {INPUT: "qa_cache"}  
                            },
                            return_keys=["answer_qa: str"],
                        )
                        
                        llm_response_qa = LLMNode(
                            name="llm_response_qa",
                            resource_key="fake",
                            instant_response=True,
                            inputs={"response": {code_extract_answer: "answer_qa"},
                                     },
                            stream=True,
                            )
                        
                        # region ================ cache ==================
                        with GraphNode(
                            name="graph_update_cache_fake_chunk",
                            description="Updated cache with session id",
                            inputs={
                                "origin_query": INPUT,
                                "cached": INPUT,
                                "session_id": INPUT,
                            },
                        ) as graph_update_cache_fake_chunk:
                            
                            code_manage_hierarchy = CodeNode(
                                name="manage_hierarchy",
                                code_fn=manage_session_hierarchy_with_comparison,
                                inputs={
                                    "cached": {INPUT: "cached"}, 
                                    "L1": {INPUT: "origin_query"},  
                                    "L2": "",  
                                    "L3": "",  
                                },
                                return_keys=["updated_cache: str"],
                            )

                            redis_set_node = RedisNode(
                                name="redis_set",
                                resource_key="aicenter-chatbot",             
                                operation=RedisOperation.SET,
                                inputs={
                                    "key": {INPUT: "session_id"},
                                    "value": {code_manage_hierarchy: "updated_cache"}
                                },
                                outputs=OUTPUT
                            )
                            
                            START >> code_manage_hierarchy >> redis_set_node >> END
                        # endregion ================ cache ==================
                        
                        START >> [code_extract_answer,
                                  graph_update_cache_fake_chunk] >> llm_response_qa >> END

                    # region ============== rcm with L1 ====================
                    with GraphNode(
                        name="graph_recommend_scenarios_with_qa",
                        description="graph_recommend_scenarios_with_qa",
                        inputs={
                            "origin_query": INPUT,
                            "metadata": INPUT,
                            "session_id": INPUT,
                            "cached": INPUT,
                        },
                    ) as graph_recommend_scenarios_with_qa:

                        code_fake_cache_qa = CodeNode(
                            name="code_fake_cache_qa",
                            code_fn= set_hierarchy_in_cache,
                            inputs={
                                "category": {INPUT: "origin_query"},
                            },
                            return_keys=["fake_cache: Dict"],
                        )

                        code_select_template_qa = CodeNode(
                            name="code_select_template_qa",
                            code_fn= select_template,
                            inputs={
                                "cached": {code_fake_cache_qa: "fake_cache"},
                            },
                            return_keys=["template_askback: str", "template_rcm: str"],
                        )
                            
                        llm_GPT_ASKBACK_QA = LLMNode(
                            name="llm_GPT_ASKBACK_QA",
                            resource_key="fake",
                            instant_response=True,
                            inputs={
                                "response": {code_select_template_qa: "template_askback"},
                                "custom_data": {INPUT: "metadata"}                            
                                },
                            stream=True
                        )

                        # region ================ cache ==================
                        with GraphNode(
                            name="graph_update_cache_with_rcm",
                            description="Updated cache with session id",
                            inputs={
                                "origin_query": INPUT,
                                "cached": INPUT,
                                "session_id": INPUT,
                            },
                        ) as graph_update_cache_with_rcm:
                            
                            code_format_input_count_scenarios = CodeNode(
                                name= "code_format_input_count_scenarios",
                                code_fn= format_filter_input,
                                inputs= {
                                    "L1": {INPUT: "origin_query"}
                                },
                                return_keys=["input_data: Dict[str, Any]"]
                            )

                            code_count_scenarios_qa = CodeNode(
                                name= "code_count_scenarios_qa",
                                code_fn= get_number_of_scenarios,
                                inputs= {
                                    "input_data": code_format_input_count_scenarios
                                },
                                return_keys=["count_scenario: int"]
                            )
                            
                            code_manage_hierarchy = CodeNode(
                                name="manage_hierarchy",
                                code_fn=manage_session_hierarchy_with_comparison,
                                inputs={
                                    "cached": {INPUT: "cached"}, 
                                    "L1": {INPUT: "origin_query"},  
                                    "L2": "",  
                                    "L3": "",
                                    "count_scenario": code_count_scenarios_qa,
                                },
                                return_keys=["updated_cache: str"],
                            )

                            redis_set_node = RedisNode(
                                name="redis_set",
                                resource_key="aicenter-chatbot",             
                                operation=RedisOperation.SET,
                                inputs={
                                    "key": {INPUT: "session_id"},
                                    "value": {code_manage_hierarchy: "updated_cache"}
                                },
                                outputs=OUTPUT
                            )
                            
                            START >> code_format_input_count_scenarios >> code_count_scenarios_qa >> code_manage_hierarchy >> redis_set_node >> END
                        # endregion ================ cache ==================
                        
                        START >> [code_fake_cache_qa,
                                  graph_update_cache_with_rcm] 
                        
                        code_fake_cache_qa >> code_select_template_qa >> llm_GPT_ASKBACK_QA >> END
                        graph_update_cache_with_rcm >> END

                    # endregion ============== rcm with L1 ====================
                    
                    # endregion ============== L2 and rcm with L1 =================

                    # region =============== rcm 5 bi =======================
                    with GraphNode(
                        name="graph_response_suggest",
                        description="recommend 5 BI",
                        inputs={
                            "username": INPUT,
                            "session_id": INPUT,
                            "cached": INPUT
                        },
                    ) as graph_response_suggest:
                        # rcm 5 nganh con
                        code_create_chunk_response_suggest = CodeNode(
                            name= "code_create_chunk_response_suggest",
                            code_fn=create_chunk_for_suggest,
                            inputs= {
                                "content": "Dưới đây là các ngành được gợi ý xem kịch bản bán hàng. Trường hợp ngành bạn cần không nằm trong danh sách, vui lòng nhập tên ngành cụ thể để tìm kịch bản phù hợp.",
                                "username": INPUT,
                            },
                            return_keys=["contents: str", "docs: List", "metadata: Dict"],
                        )

                        llm_fake_response_suggest = LLMNode(
                            name="llm_fake_response_suggest",
                            resource_key="fake",
                            instant_response=True,
                            inputs={
                                "response": {code_create_chunk_response_suggest: "contents"},
                                "custom_data": {code_create_chunk_response_suggest: "metadata"}                            
                                },
                            stream=True,
                            )
                        
                        with GraphNode(
                            name="graph_update_cache_non_chitchat",
                            description="Updated cache with session id",
                            inputs={
                                "session_id": INPUT,
                                "cached": INPUT
                            },
                        ) as graph_update_cache_non_chitchat:
                            
                            code_manage_hierarchy = CodeNode(
                                name="manage_hierarchy",
                                code_fn=manage_session_hierarchy_with_comparison,
                                inputs={
                                    "cached": {INPUT: "cached"}, 
                                    "L1": "Tín dụng",  
                                    "L2": "SXKD",  
                                    "L3": "",  
                                },
                                return_keys=["updated_cache: str"],
                            )

                            redis_set_node = RedisNode(
                                name="redis_set",
                                resource_key="aicenter-chatbot",             
                                operation=RedisOperation.SET,
                                inputs={
                                    "key": {INPUT: "session_id"},
                                    "value": {code_manage_hierarchy: "updated_cache"}
                                },
                                outputs=OUTPUT
                            )
                            
                            START >> code_manage_hierarchy >> redis_set_node >> END
                        
                        START >> code_create_chunk_response_suggest >> [llm_fake_response_suggest,
                                                                        graph_update_cache_non_chitchat] >> END

                    # endregion =============== rcm 5 bi =======================
                    
                    # region =============== viewmore ==================
                    with GraphNode(
                        name="graph_viewmore_flow",
                        description="graph_viewmore_flow",
                        inputs={
                            "username": INPUT,
                            "cached": INPUT,
                        },
                    ) as graph_viewmore_flow:
                        
                        code_extract_cache = CodeNode(
                                name="code_extract_cache",
                                code_fn=extract_cached,
                                inputs={"cached": INPUT
                                        },
                                return_keys=["L1_cache: str", "L2_cache: str", "L3_cache: str"],
                            )

                        branch_routing_viewmore = BranchNode(
                            name="branch_routing_viewmore",
                            cases={
                                "L3_cache == True": "graph_business_industry_in_viewmore",
                            },
                            default="graph_standard_business_industry_in_viewmore",
                            inputs={"L3_cache": code_extract_cache},
                        )

                        code_format_input_count_scenarios = CodeNode(
                            name= "code_format_input_count_scenarios",
                            code_fn= format_filter_input,
                            inputs= {
                                "L1": {code_extract_cache: "L1_cache"},
                                "L2": {code_extract_cache: "L2_cache"},
                                "L3": {code_extract_cache: "L3_cache"},
                            },
                            return_keys=["input_data: Dict[str, Any]"]
                        )

                        code_count_scenarios_qa = CodeNode(
                            name= "code_count_scenarios_qa",
                            code_fn= get_number_of_scenarios,
                            inputs= {
                                "input_data": code_format_input_count_scenarios
                            },
                            return_keys=["count_scenario: int"]
                        )

                        with GraphNode(
                            name="graph_business_industry_in_viewmore",
                            description="graph_business_industry_in_viewmore",
                            inputs={
                                "username": INPUT,
                                "L3_cache": code_extract_cache,
                                "count_scenario": code_count_scenarios_qa,
                            },
                        ) as graph_business_industry_in_viewmore:
                            
                            code_run_business_industry_in_viewmore = CodeNode(
                                name="code_run_business_industry_flow",
                                code_fn=run_business_industry_flow,
                                inputs={"username": INPUT,
                                        "businessIndustryId": "",
                                        "businessIndustryName": {INPUT: "L3_cache"},
                                        "count_scenario": INPUT
                                        },
                                return_keys=["contents: str", "docs: List", "metadata: Dict"],
                            )

                            llm_fake_response_rcm_business_industry_in_viewmore = LLMNode(
                                name="llm_fake_response_rcm_business_industry",
                                resource_key="fake",
                                instant_response=True,
                                inputs={
                                    "response": {code_run_business_industry_in_viewmore: "contents"},
                                    "custom_data": {code_run_business_industry_in_viewmore: "metadata"}                            
                                    },
                                outputs= OUTPUT,
                                stream = True
                                )
                            
                            START >> code_run_business_industry_in_viewmore >> llm_fake_response_rcm_business_industry_in_viewmore >> END

                        with GraphNode(
                            name="graph_standard_business_industry_in_viewmore",
                            description=" Default flow business industry in standard flow",
                            inputs={
                                "username": INPUT,
                                "L1_cache": code_extract_cache,
                                "L2_cache": code_extract_cache,
                                "count_scenario": code_count_scenarios_qa
                            },
                        ) as graph_standard_business_industry_in_viewmore:

                            code_recommend_scenarios_standard= CodeNode(
                                name="code_recommend_scenarios_standard",
                                code_fn=recommend_scenarios_standard,
                                inputs={"username": INPUT,
                                        "category": {INPUT: "L1_cache"},
                                        "sub_category": {INPUT: "L2_cache"},
                                        "count_scenario": INPUT
                                        },
                                return_keys=["contents: str", "docs: List", "metadata: Dict"],
                            )

                            llm_fake_response_recommend_scenarios_standard = LLMNode(
                                name="llm_fake_response_recommend_scenarios_standard",
                                resource_key="fake",
                                instant_response=True,
                                inputs={
                                    "response": {code_recommend_scenarios_standard: "contents"},
                                    "custom_data": {code_recommend_scenarios_standard: "metadata"}                            
                                    },
                                stream=True,
                                )
                            
                            START >> code_recommend_scenarios_standard >> llm_fake_response_recommend_scenarios_standard >> END


                        START >> code_extract_cache >> code_format_input_count_scenarios >> code_count_scenarios_qa >> branch_routing_viewmore >> [graph_business_industry_in_viewmore,
                                                                                                                                                    graph_standard_business_industry_in_viewmore] >> END
                    
                    # endregion =============== viewmore ==================

                    # region ================ recommend L1, L2 ===================
                    with GraphNode(
                        name="graph_standard_business_industry",
                        description=" Default flow business industry in standard flow",
                        inputs={
                            "origin_query": {INPUT: "origin_query"},
                            "session_id": INPUT,
                            "cached": INPUT,
                            "metadata": INPUT,
                        },
                    ) as graph_standard_business_industry:
                        
                        code_prepare_input = CodeNode(
                            name= "code_prepare_input",
                            code_fn= prepare_input,
                            inputs= {
                                "cached": INPUT,
                                "sub_category": {INPUT: "origin_query"},
                            },
                            return_keys=["L1: str", "L2: str"]
                        )

                        code_fake_cache_standard = CodeNode(
                            name="code_fake_cache_standard",
                            code_fn= set_hierarchy_in_cache,
                            inputs={
                                "category": {code_prepare_input: "L1"},
                                "sub_category": {code_prepare_input: "L2"},
                                "cached": INPUT,
                            },
                            return_keys=["fake_cache: Dict"],
                        )

                        code_select_template_standard = CodeNode(
                            name="code_select_template_standard",
                            code_fn= select_template,
                            inputs={
                                "cached": {code_fake_cache_standard: "fake_cache"},
                            },
                            return_keys=["template_askback: str", "template_rcm: str"],
                        )
                            
                        llm_GPT_ASKBACK = LLMNode(
                            name="llm_GPT_ASKBACK",
                            resource_key="fake",
                            instant_response=True,
                            inputs={
                                "response": {code_select_template_standard: "template_askback"},
                                "custom_data":  {INPUT: "metadata"}                          
                                },
                            stream=True
                        )

                        with GraphNode(
                            name="graph_update_cache_standard",
                            description="Updated cache with session id",
                            inputs={
                                "L1": code_prepare_input,
                                "L2": code_prepare_input,
                                "session_id": INPUT,
                                "cached": INPUT
                            },
                        ) as graph_update_cache_standard:
                            
                            code_format_input_count_scenarios = CodeNode(
                                name= "code_format_input_count_scenarios",
                                code_fn= format_filter_input,
                                inputs= {
                                    "L1": INPUT,
                                    "L2": INPUT,
                                },
                                return_keys=["input_data: Dict[str, Any]"]
                            )

                            code_count_scenarios_qa = CodeNode(
                                name= "code_count_scenarios_qa",
                                code_fn= get_number_of_scenarios,
                                inputs= {
                                    "input_data": code_format_input_count_scenarios
                                },
                                return_keys=["count_scenario: int"]
                            )
                            
                            code_manage_hierarchy = CodeNode(
                                name="manage_hierarchy",
                                code_fn=manage_session_hierarchy_with_comparison,
                                inputs={
                                    "cached": {INPUT: "cached"}, 
                                    "L1": {INPUT: "L1"},  
                                    "L2": {INPUT: "L2"},  
                                    "L3": "",  
                                    "count_scenario": code_count_scenarios_qa
                                },
                                return_keys=["updated_cache: str"],
                            )

                            redis_set_node = RedisNode(
                                name="redis_set",
                                resource_key="aicenter-chatbot",             
                                operation=RedisOperation.SET,
                                inputs={
                                    "key": {INPUT: "session_id"},
                                    "value": {code_manage_hierarchy: "updated_cache"}
                                },
                                outputs=OUTPUT
                            )
                            
                            START >> code_format_input_count_scenarios >> code_count_scenarios_qa >> code_manage_hierarchy >> redis_set_node >> END

                        START  >> code_prepare_input >> [code_fake_cache_standard,
                                                         graph_update_cache_standard] 
                        code_fake_cache_standard >> code_select_template_standard >> llm_GPT_ASKBACK >> END
                        graph_update_cache_standard >> END

                # endregion ================ recommend L1, L2 ===================

                    branch_routing_qa_flow = BranchNode(
                        name="branch_routing_qa_flow",
                        cases={
                            "is_sub_category": "graph_fake_chunk_qa",
                            "is_rcm_business_industry": "graph_response_suggest",
                            "is_viewmore": "graph_viewmore_flow",
                            "is_rcm_standard": "graph_standard_business_industry",
                        },
                        default="graph_recommend_scenarios_with_qa",
                        inputs={
                            "is_sub_category": code_route_qa_flow,
                            "is_rcm_business_industry": code_route_qa_flow,
                            "is_viewmore": code_route_qa_flow,
                            "is_rcm_standard": code_route_qa_flow,
                        },
                    )

                    START >> retrieve_qa >> code_route_qa_flow >> branch_routing_qa_flow >> [graph_fake_chunk_qa,
                                                                                            graph_response_suggest,
                                                                                            graph_viewmore_flow,
                                                                                            graph_standard_business_industry,
                                                                                            graph_recommend_scenarios_with_qa] >> END

                # endregion ================== button Flow =====================================

                # region ================ business industry flow ================

                code_business_industry_route_decision = CodeNode(
                        name= "code_business_industry_route_decision",
                        code_fn= business_industry_route_decision,
                        inputs= {
                            "metadata": INPUT
                        },
                        return_keys=["business_industry_flow: bool",
                                    "businessIndustryId: Optional[str]",
                                    "businessIndustryName: Optional[str]"] ,
                    )
                
                with GraphNode(
                    name="graph_business_industry_flow",
                    description="graph_business_industry_flow",
                    inputs={
                        "session_id": INPUT,
                        "cached": INPUT,
                        "metadata": INPUT,
                        "businessIndustryName": code_business_industry_route_decision
                    },
                ) as graph_business_industry_flow:
                    
                    code_fake_cache_semantic_search = CodeNode(
                        name="code_fake_cache_semantic_search",
                        code_fn= set_hierarchy_in_cache,
                        inputs={
                            "category": "Tín dụng",
                            "sub_category": "SXKD"
                        },
                        return_keys=["fake_cache: Dict"],
                    )

                    code_select_template_semantic_search = CodeNode(
                        name="code_select_template_semantic_search",
                        code_fn= select_template,
                        inputs={
                            "cached": {code_fake_cache_semantic_search: "fake_cache"},
                        },
                        return_keys=["template_askback: str", "template_rcm: str"],
                    )
                    
                    llm_GPT_ASKBACK = LLMNode(
                        name="llm_GPT_ASKBACK",
                        resource_key="fake",
                        instant_response=True,
                        inputs={
                            "response": {code_select_template_semantic_search: "template_askback"},
                            "custom_data": {INPUT: "metadata"}                            
                            },
                        stream=True
                    )

                    with GraphNode(
                        name="graph_update_cache_business_industry_flow",
                        description="Updated cache with session id",
                        inputs={
                            "session_id": INPUT,
                            "cached": INPUT,
                            "businessIndustryName": code_business_industry_route_decision,
                        },
                    ) as graph_update_cache_business_industry_flow:
                        
                        code_format_input_count_scenarios = CodeNode(
                            name= "code_format_input_count_scenarios",
                            code_fn= format_filter_input,
                            inputs= {
                                "L3": {INPUT: "businessIndustryName"}
                            },
                            return_keys=["input_data: Dict[str, Any]"]
                        )

                        code_count_scenarios_qa = CodeNode(
                            name= "code_count_scenarios_qa",
                            code_fn= get_number_of_scenarios,
                            inputs= {
                                "input_data": code_format_input_count_scenarios
                            },
                            return_keys=["count_scenario: int"]
                        )
                        
                        code_manage_hierarchy = CodeNode(
                            name="manage_hierarchy",
                            code_fn=manage_session_hierarchy_with_comparison,
                            inputs={
                                "cached": {INPUT: "cached"}, 
                                "L1": "",  
                                "L2": "",  
                                "L3": {INPUT: "businessIndustryName"},
                                "count_scenario": code_count_scenarios_qa,
                            },
                            return_keys=["updated_cache: str"],
                        )

                        redis_set_node = RedisNode(
                            name="redis_set",
                            resource_key="aicenter-chatbot",             
                            operation=RedisOperation.SET,
                            inputs={
                                "key": {INPUT: "session_id"},
                                "value": {code_manage_hierarchy: "updated_cache"}
                            },
                            outputs=OUTPUT
                        )
                        
                        START >> code_format_input_count_scenarios >> code_count_scenarios_qa >> code_manage_hierarchy >> redis_set_node >> END

                    START >> [graph_update_cache_business_industry_flow,
                              code_fake_cache_semantic_search]
                    
                    graph_update_cache_business_industry_flow >> END
                    code_fake_cache_semantic_search >> code_select_template_semantic_search >> llm_GPT_ASKBACK >> END

                # endregion ================ business industry flow ================

                
                # region ================== chat flow ==========================
                with GraphNode(
                    name="graph_chat_flow",
                    description="Standard flow routing",
                    inputs={
                        "origin_query": INPUT,
                        "conversation": INPUT,
                        "username": INPUT,
                        "session_id": INPUT,
                        "cached": INPUT,
                        "metadata": INPUT,
                        "template_rcm": INPUT,
                    },
                ) as graph_chat_flow:
                    
                    # region ================ rewrite ================          
                    with GraphNode(
                        name="graph_rewrite_query",
                        description="Rewrite flow",
                        inputs={
                            "origin_query": INPUT,
                            "conversation": INPUT,
                        },
                    ) as graph_rewrite_query:

                        llm_rewrite_query = BasicChainNode(
                            name="rewrite_query",
                            resource_key="gpt-4o",
                            user_prompt=PROMPTS["BEECRM:REWRITE_PROMPT"],
                            inputs={
                                "query": {INPUT: "origin_query"},
                                "conversation": {INPUT: "conversation"},
                                "hierarchy": hierarchy
                            },
                        )

                        code_postprocess_rewrite = CodeNode(
                            name= "postprocess_rewrite",
                            code_fn=postprocess_rewrite,
                            inputs= {
                                "query": {llm_rewrite_query: "content"},
                                "origin_query": INPUT
                            },
                            return_keys= ["rewrited_query: Dict[str, str]"],
                            outputs= {"rewrited_query": OUTPUT}
                        )

                        START >> llm_rewrite_query >> code_postprocess_rewrite >> END


                    # endregion ================ rewrite ================

                    # region ================ cls ================
                    with GraphNode(
                        name="graph_classify_question",
                        description="classify question flow",
                        inputs={
                            "rewrited_query": graph_rewrite_query,
                        },
                    ) as graph_classify_question:

                        llm_classify_question = BasicChainNode(
                            name="classify_question",
                            resource_key="gpt-4.1",
                            user_prompt=PROMPTS["BEECRM:CLS_QUESTION"],
                            inputs={
                                "query": {INPUT: "rewrited_query"},
                                "hierarchy": hierarchy,
                            },
                        )

                        code_postprocess_cls_question = CodeNode(
                            name= "postprocess_cls_question",
                            code_fn=postprocess_cls_question,
                            inputs= {
                                "query": {llm_classify_question: "content"},
                            },
                            return_keys= ["intent_question: str"],
                            outputs= {"intent_question": OUTPUT}
                        )
                        START >> llm_classify_question >> code_postprocess_cls_question >> END

                    # endregion ================ cls ================

                    # region =========================== retrieva chunk =====================================
                    with GraphNode(
                        name="graph_semantic_search_scenarios",
                        description=" Search scenarios with query",
                        inputs={
                            "origin_query": INPUT,
                            "session_id": INPUT,
                            "rewrited_query": graph_rewrite_query,
                            "username": INPUT,
                            "cached": INPUT,
                            "metadata": INPUT,
                            "template_rcm": INPUT,
                            "conversation": INPUT,
                        },
                    ) as graph_semantic_search_scenarios:
                                        
                        retrieve_scenarios = RetrieverNode(
                            embedding="qwen-embedding-chat",
                            name="retrieve_scenarios",
                            inputs={
                                "query": {INPUT: "rewrited_query"},
                                "collection": custom_transform_bot_id(self.bot_id),
                                "top_k": 5,
                                "rerank_top_k": 1,
                                "output_fields": ["chunk_id"],
                                "allowed_roles": ["L1"],
                                "bot_id": self.bot_id,
                                "threshold": 0.9,
                                "rerank_threshold": 0.99
                            }
                        )  

                        code_recommend_scenarios_by_semantic_search = CodeNode(
                            name="code_recommend_scenarios_by_semantic_search",
                            code_fn=recommend_scenario_with_chunk,
                            inputs={"docs": retrieve_scenarios,
                                    "username": INPUT},
                            return_keys=["contents: str", "docs_chunk: List", "metadata: Dict", "crm_category_name: str", "crm_sub_category_name: str", "business_industry_name: str"],
                        )

                        llm_fake_response_recommend_scenarios_by_semantic_search = LLMNode(
                            name="llm_fake_response_recommend_scenarios_by_semantic_search",
                            resource_key="fake",
                            instant_response=True,
                            inputs={
                                "response": {code_recommend_scenarios_by_semantic_search: "contents"},
                                "custom_data": {code_recommend_scenarios_by_semantic_search: "metadata"}                            
                                },
                            stream=True,
                            )
                        
                        # region ======================= rcm with gpt =========================
                        with GraphNode(
                            name="graph_recommend_semantic_search_with_gpt",
                            description="graph_recommend_semantic_search_with_gpt",
                            inputs={
                                "origin_query": INPUT,
                                "metadata": INPUT,
                                "cached": INPUT,
                                "template_rcm": INPUT,
                                "username": INPUT,
                                "conversation": INPUT,
                                "rewrited_query": INPUT,
                                "session_id": INPUT,
                            },
                        ) as graph_recommend_semantic_search_with_gpt:
                            
                            code_update_metadata_gpt = CodeNode(
                                name = "code_update_metadata_gpt",
                                code_fn= add_is_crmind_metadata,
                                inputs= {
                                    "metadata": INPUT,
                                    "cached": INPUT,
                                },
                                return_keys= ["rcm_metadata: Dict", "is_classify: bool"]
                            )

                            code_get_user_info = CodeNode(
                                name = "code_get_user_info",
                                code_fn= get_user_info_by_username,
                                inputs = {
                                    "username": INPUT
                                },
                                return_keys=["user_info: str"]
                            )

                            llm_GPT_RCM_standard = BasicChainNode(
                                name="llm_GPT_RCM_standard",
                                resource_key="gpt-5.1-chat",
                                llm_configs= {"max_tokens": 16348},
                                user_prompt=PROMPTS["BEECRM:WRAPPER"],
                                inputs={                                    
                                        "prompt_rcm": {INPUT: "template_rcm"},
                                        "query": {INPUT: "origin_query"},
                                        "rm_info": {code_get_user_info: "user_info"},
                                        "cached": INPUT,
                                        "conversation": INPUT,
                                        "custom_data": {code_update_metadata_gpt: "rcm_metadata"}},
                                stream=True
                            )

                            # region ============= non category ==================
                            with GraphNode(
                                name="graph_rcm_non_category",
                                description="graph_rcm_non_category",
                                inputs={
                                    "session_id": INPUT,
                                    "cached": INPUT,
                                    "origin_query": INPUT,
                                    "conversation": INPUT,
                                    "rewrited_query": INPUT,
                                    "user_info": code_get_user_info,
                                    "rcm_metadata": code_update_metadata_gpt,
                                },
                            ) as graph_rcm_non_category:

                                llm_classify_category = BasicChainNode(
                                    name="llm_classify_category",
                                    resource_key="gpt-4o",
                                    user_prompt=PROMPTS["BEECRM:EXTRACT_QUERY"],
                                    inputs={"hierarchy": hierarchy,
                                            "query": {INPUT: "rewrited_query"}},
                                )

                                code_postprocess_extract_query = CodeNode(
                                    name= "code_postprocess_extract_query",
                                    code_fn= postprocess_extract_query,
                                    inputs= {
                                        "query": {llm_classify_category: "content"}
                                    },
                                    return_keys= ["L1: str", "L2: str", "relation: str"]
                                )

                                code_format_input_count_scenarios_non_category = CodeNode(
                                    name= "code_format_input_count_scenarios_non_category",
                                    code_fn= format_filter_input,
                                    inputs= {
                                        "L1": code_postprocess_extract_query,
                                        "L2": code_postprocess_extract_query,
                                    },
                                    return_keys=["input_data: Dict[str, Any]"]
                                )

                                code_count_scenarios_qa_non_category = CodeNode(
                                    name= "code_count_scenarios_qa",
                                    code_fn= get_number_of_scenarios,
                                    inputs= {
                                        "input_data": code_format_input_count_scenarios_non_category
                                    },
                                    return_keys=["count_scenario: int"]
                                )

                                code_update_metadata = CodeNode(
                                    name= "code_update_metadata",
                                    code_fn= update_metadata_with_classification,
                                    inputs= {
                                        "L1": code_postprocess_extract_query,
                                        "L2": code_postprocess_extract_query,
                                        "metadata": {INPUT: "rcm_metadata"},
                                        "count_scenario": code_count_scenarios_qa_non_category
                                    },
                                    return_keys= ["updated_metadata: Dict", "template_askback: str", "template_rcm: str"]
                                )

                                llm_GPT_RCM = BasicChainNode(
                                    name="llm_GPT_RCM",
                                    resource_key="gpt-5.1-chat",
                                    llm_configs= {"max_tokens": 16348},
                                    user_prompt=PROMPTS["BEECRM:WRAPPER"],
                                    inputs={
                                            "prompt_rcm": {code_update_metadata: "template_rcm"},
                                            "query": {INPUT: "origin_query"},
                                            "rm_info": {INPUT: "user_info"},
                                            "cached": INPUT,
                                            "conversation": INPUT,
                                            "custom_data": {code_update_metadata: "updated_metadata"}},
                                    stream=True
                                )

                                with GraphNode(
                                    name="graph_update_cache_semantic_search",
                                    description="Updated cache with session id",
                                    inputs={
                                        "crm_category_name": {code_postprocess_extract_query: "L1"},
                                        "crm_sub_category_name": {code_postprocess_extract_query: "L2"},
                                        "session_id": INPUT,
                                        "cached": INPUT
                                    },
                                ) as graph_update_cache_semantic_search:
                                    
                                    code_format_input_count_scenarios = CodeNode(
                                        name= "code_format_input_count_scenarios",
                                        code_fn= format_filter_input,
                                        inputs= {
                                            "L1": {INPUT: "crm_category_name"},
                                            "L2": {INPUT: "crm_sub_category_name"},
                                        },
                                        return_keys=["input_data: Dict[str, Any]"]
                                    )

                                    code_count_scenarios_qa = CodeNode(
                                        name= "code_count_scenarios_qa",
                                        code_fn= get_number_of_scenarios,
                                        inputs= {
                                            "input_data": code_format_input_count_scenarios
                                        },
                                        return_keys=["count_scenario: int"]
                                    )
                                    
                                    code_manage_hierarchy_semantic_search = CodeNode(
                                        name="manage_hierarchy",
                                        code_fn=manage_session_hierarchy_with_comparison,
                                        inputs={
                                            "cached": {INPUT: "cached"}, 
                                            "count_scenario": code_count_scenarios_qa,
                                            "L1": {INPUT: "crm_category_name"},
                                            "L2": {INPUT: "crm_sub_category_name"},
                                        },
                                        return_keys=["updated_cache: str"],
                                    )

                                    redis_set_node_semantic_search = RedisNode(
                                        name="redis_set",
                                        resource_key="aicenter-chatbot",             
                                        operation=RedisOperation.SET,
                                        inputs={
                                            "key": {INPUT: "session_id"},
                                            "value": {code_manage_hierarchy_semantic_search: "updated_cache"}
                                        },
                                        outputs=OUTPUT
                                    )
                                    
                                    START >> code_format_input_count_scenarios >> code_count_scenarios_qa >> code_manage_hierarchy_semantic_search >> redis_set_node_semantic_search >> END

                                START >> llm_classify_category >> code_postprocess_extract_query >> [code_format_input_count_scenarios_non_category,
                                                                                                     graph_update_cache_semantic_search] 
                                code_format_input_count_scenarios_non_category >> code_count_scenarios_qa_non_category >> code_update_metadata >> llm_GPT_RCM >> END
                                graph_update_cache_semantic_search >> END

                            # endregion ============= non category ==================

                            # --- Routing ---
                            branch_routing_category = BranchNode(
                                name="branch_routing_category",
                                cases={
                                    "is_classify": "code_get_user_info",
                                },
                                default="graph_rcm_non_category",
                                inputs={"is_classify": code_update_metadata_gpt},
                            )

                            START >> code_update_metadata_gpt >> branch_routing_category >> [code_get_user_info,
                                                                                             graph_rcm_non_category] 
                            code_get_user_info >> llm_GPT_RCM_standard >> END
                            graph_rcm_non_category >> END
                        # endregion ======================= rcm with gpt =========================

                        
                        code_extract_metadata_semantic_search= CodeNode(
                            name="code_extract_metadata_semantic_search",
                            code_fn=is_scenarios_empty,
                            inputs={"metadata": code_recommend_scenarios_by_semantic_search,
                                    },
                            return_keys=["is_scenarios: bool"],
                        )

                        with GraphNode(
                            name="graph_update_cache_semantic_search",
                            description="Updated cache with session id",
                            inputs={
                                "crm_category_name": code_recommend_scenarios_by_semantic_search,
                                "crm_sub_category_name": code_recommend_scenarios_by_semantic_search,
                                "business_industry_name": code_recommend_scenarios_by_semantic_search,
                                "session_id": INPUT,
                                "cached": INPUT
                            },
                        ) as graph_update_cache_semantic_search:
                            
                            code_format_input_count_scenarios = CodeNode(
                                name= "code_format_input_count_scenarios",
                                code_fn= format_filter_input,
                                inputs= {
                                    "L1": {INPUT: "crm_category_name"},
                                    "L2": {INPUT: "crm_sub_category_name"},
                                    "L3": {INPUT: "business_industry_name"}
                                },
                                return_keys=["input_data: Dict[str, Any]"]
                            )

                            code_count_scenarios_qa = CodeNode(
                                name= "code_count_scenarios_qa",
                                code_fn= get_number_of_scenarios,
                                inputs= {
                                    "input_data": code_format_input_count_scenarios
                                },
                                return_keys=["count_scenario: int"]
                            )
                            
                            code_manage_hierarchy_semantic_search = CodeNode(
                                name="manage_hierarchy",
                                code_fn=manage_session_hierarchy_with_comparison,
                                inputs={
                                    "cached": {INPUT: "cached"}, 
                                    "count_scenario": code_count_scenarios_qa,
                                    "L1": {INPUT: "crm_category_name"},
                                    "L2": {INPUT: "crm_sub_category_name"},
                                    "L3": {INPUT: "business_industry_name"},  
                                },
                                return_keys=["updated_cache: str"],
                            )

                            redis_set_node_semantic_search = RedisNode(
                                name="redis_set",
                                resource_key="aicenter-chatbot",             
                                operation=RedisOperation.SET,
                                inputs={
                                    "key": {INPUT: "session_id"},
                                    "value": {code_manage_hierarchy_semantic_search: "updated_cache"}
                                },
                                outputs=OUTPUT
                            )
                            
                            START >> code_format_input_count_scenarios >> code_count_scenarios_qa >> code_manage_hierarchy_semantic_search >> redis_set_node_semantic_search >> END

                        branch_routing_semantic_search_gpt= BranchNode(
                            name="branch_routing_semantic_search_gpt",
                            cases={
                                "is_scenarios": "graph_recommend_semantic_search_with_gpt",
                            },
                            default="graph_update_cache_semantic_search",
                            inputs={"is_scenarios": code_extract_metadata_semantic_search},
                        )

                        START >> retrieve_scenarios >> code_recommend_scenarios_by_semantic_search >> code_extract_metadata_semantic_search >> branch_routing_semantic_search_gpt 
                        
                        branch_routing_semantic_search_gpt >> [ graph_update_cache_semantic_search,
                                                                graph_recommend_semantic_search_with_gpt] >> END
                        
                        graph_update_cache_semantic_search >> llm_fake_response_recommend_scenarios_by_semantic_search >> END

                    # endregion =========================== retrieva chunk ===================================
                                            
                    llm_chitchat = BasicChainNode(
                        name="llm_chitchat",
                        resource_key="gpt-4.1",
                        user_prompt=PROMPTS["BEECRM:REJECT_CHITCHAT"],
                        inputs={"definition": "bot này là bot của crm (Customer Relation Management)",
                        },
                        stream = True
                    )
                   
    
                    branch_routing_chitchat = BranchNode(
                        name="branch_routing_chitchat",
                        cases={
                            "intent_question == 'false'": "llm_chitchat",
                        },
                        default="graph_semantic_search_scenarios",
                        inputs={"intent_question": {graph_classify_question: "intent_question"}}
                    )


                    START >> graph_rewrite_query >> graph_classify_question >> branch_routing_chitchat
                    branch_routing_chitchat >> [graph_semantic_search_scenarios,
                                                llm_chitchat] >> END
                    
                # endregion ========================= chat flow =============================


                code_check_button_flow = CodeNode(
                    name="code_check_button_flow",
                    code_fn=check_button_flow,
                    inputs={
                        "metadata": INPUT,
                    },
                    return_keys=["is_button_flow: bool"],
                ) 

                branch_routing_qa = BranchNode(
                    name="branch_routing_qa",
                    cases={
                           "business_industry_flow == True": "graph_business_industry_flow",
                           "is_button_flow == True": "graph_button_flow",
                           },
                    default="graph_chat_flow",
                    inputs={"is_button_flow": code_check_button_flow,
                            "business_industry_flow": code_business_industry_route_decision},
                )

                START >>  [ code_check_button_flow,
                            code_business_industry_route_decision] >> branch_routing_qa

                branch_routing_qa >> [graph_button_flow,
                                      graph_business_industry_flow,
                                      graph_chat_flow] >> END
            # endregion ===== Flow Internal =====

            branch_routing_flow = BranchNode(
                name="branch_routing_flow",
                cases={
                    "workflow == 'gpt'": "graph_gpt_flow",
                    "workflow == 'internal'": "graph_internal_flow",
                },
                default="graph_internal_flow",
                inputs={"workflow": {code_verify_workflow: "workflow"}},
            )

            START >> [code_init_query, graph_get_cache] >> code_verify_workflow >> code_select_template >> branch_routing_flow

            branch_routing_flow >> [graph_gpt_flow, graph_internal_flow]

            graph_gpt_flow >> END
            graph_internal_flow >> END

        beecrm.compile()
        self.workflow = beecrm

    async def run(
        self,
        messages: List[Dict[str, Any]],
        session_id: str,
        client_message_id: str,
        username: str,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[Any, None]:
        try:
            asyncio.create_task( self.workflow.run(
                    request_id=client_message_id,
                    inputs={
                        "messages": messages,
                        "metadata": metadata or {},
                        "session_id": session_id,
                        "username": username,
                    },
                )
            )
            async for channel_name in STREAM_SERVICE.get_channels(client_message_id):
                async for chunk in STREAM_SERVICE.get(client_message_id, channel_name, json_mode=False):
                    yield chunk
        except Exception:
            import traceback
            LOGGER.error(traceback.format_exc())
            default_answers = "Xin loi, hien tai he thong gap loi. Vui long thu lai sau."
            yield fake_chunk_from(content=default_answers, model="error")


async def main():


    bot = BeeCRMBot(bot_id="ae5e0fb7-7db6-42fa-8024-ee133a116cd0")
    dialogue_id = "be9678da-32fd-456e-a24f-bed6f0d56c84"

    import uuid
    client_message_id = str(uuid.uuid4())

    username = "dungdd2"


    async for chunk in bot.run(
        messages=[
    {
        "role": "assistant",
        "content": "Chào bạn! Mình là Trợ lý bán hàng thông minh. Hãy chọn sản phẩm để mình gợi ý các kịch bản bán hàng hiệu quả nhé!  <Button: Tín dụng> <Button: Huy động vốn> <Button: CDs> <Button: Bancas><Button: Thẻ><Button: SP Đầu tư><Button: Kiều hối>"
    },
    {
        "role": "user",
        "content": "Tín dụng"
    },
    {
        "role": "assistant",
        "content": "Bạn hãy chọn sản phẩm con để mình hiển thị kịch bản bán phù hợp nhé!\n<Button: Nhà đất>\n<Button: Nhà dự án>\n<Button: Ô tô>\n<Button: SXKD>\n<Button: TD có TSBĐ>"
    },
    {
        "role": "user",
        "content": "Nhà đất"
    },
    {
        "role": "assistant",
        "content": "Để xây dựng kịch bản bán hàng bám sát đặc điểm và nhu cầu của Khách hàng, bạn vui lòng cung cấp bổ sung các thông tin sau:\n\n 1. **Chân dung khách hàng:** phân khúc, giới tính, độ tuổi, nghề nghiệp...\n 2. **Mục đích vay vốn cụ thể:** mua nhà đất để ở; mua nhà đất để đầu tư, cho thuê; xây mới hoặc sửa chữa nhà...\n 3. **Điểm chạm khách hàng (nếu có):** được chị Thảo giới thiệu, được sale bất động sản giới thiệu...\n 4. **Tình huống bán:** KH từ chối do lãi suất cao; thủ tục phức tạp; đang quen dùng ngân hàng khác; chưa có nhu cầu..."
    },
    {
        "role": "user",
        "content": "khách hàng thuộc phân khúc private, giới tính nam, 45 tuổi, sở hữu doanh nghiệp, mục đích vay mua nhà dự án vin ocean park 2, được bên sale giới thiệu"
    },
    {
        "role": "assistant",
        "content": "## **PHẦN DẪN DẮT (Dữ kiện → Suy luận chính → Kết luận)**\n- **Dữ kiện:** KH **nam 45 tuổi**, phân khúc **Private**, **chủ doanh nghiệp**; nhu cầu **vay mua nhà dự án Vin Ocean Park 2**; **được bên sale giới thiệu**; chưa có tình huống bán cụ thể.  \n- **Suy luận chính:** KH Private thường ưu tiên **tốc độ phê duyệt**, **hạn mức/tỷ lệ vay tối ưu**, **phương án dòng tiền linh hoạt theo doanh thu DN**, và **trải nghiệm dịch vụ gọn**; lead từ sale cần **tận dụng “niềm tin chuyển giao”** để chốt lịch tư vấn nhanh.  \n- **Kết luận:** Dùng kịch bản **gọi điện theo lead giới thiệu**, tập trung **cá nhân hóa theo dòng tiền**, nhấn **ưu đãi – tốc độ – hỗ trợ hồ sơ/pháp lý**, mục tiêu **chốt hẹn** và **chốt checklist hồ sơ** ngay trong cuộc gọi.\n\n---\n\n# ## **KỊCH BẢN BÁN: _“AN CƯ VIN OCEAN PARK 2 – DUYỆT NHANH CHO KH PRIVATE”_** 🏡⚡\n\n---\n\n## **1. Chuẩn bị trước khi tiếp cận (RM cần tìm hiểu gì)** 🗂️\n- **Tìm hiểu khách hàng (trong hệ thống MB):**  \n  **Thông tin định danh cơ bản** (không nhắc dữ liệu nhạy cảm); lịch sử quan hệ (đã có CASA/thẻ/tín dụng chưa); **dòng tiền vào tài khoản**; hành vi giao dịch; sản phẩm đang dùng; lịch sử tín dụng nội bộ (nếu có); hạn mức/điểm tín nhiệm nội bộ; ghi chú chăm sóc trước đây (nếu có).\n- **Tìm hiểu khách hàng (từ bên ngoài):**  \n  Thông tin doanh nghiệp (ngành, quy mô, thời gian hoạt động, tính mùa vụ dòng tiền); **nguồn thu chính/phụ**; tình trạng tài sản hiện có (BĐS/xe/đầu tư); mức độ “chắc” của giao dịch tại Vin Ocean Park 2 (đã chọn căn/chưa, booking/chưa).\n- **Xác định nhu cầu tiềm năng:**  \n  **Mục đích vay:** mua nhà dự án Vin Ocean Park 2; **khoản cần vay dự kiến**; **timeline ký HĐ/đóng tiền** theo tiến độ CĐT; **khả năng trả nợ:** dựa trên doanh thu DN + thu nhập cá nhân; **nguồn trả nợ chính:** dòng tiền kinh doanh hay lương/cổ tức; **khả năng chứng minh tài chính:** sao kê, BCTC/thuế, hợp đồng kinh tế (nếu có), tài sản bổ trợ.\n- **Chuẩn bị tài liệu/phương án tư vấn:**  \n  Bảng **so sánh lãi suất/ưu đãi theo kỳ**; 2–3 **kịch bản trả nợ** (gốc đều/gốc giảm dần/linh hoạt theo dòng tiền); phương án **ân hạn gốc** (nếu phù hợp); checklist hồ sơ **cá nhân + doanh nghiệp**; gói tiện ích: **bảo hiểm**, miễn/giảm phí dịch vụ theo phân khúc, **hỗ trợ thẩm định/giấy tờ dự án** theo quy trình; khung thời gian xử lý: tiếp nhận hồ sơ → phê duyệt → ký → giải ngân theo tiến độ.\n- **Xác định mục tiêu tiếp cận:**  \n  **Chốt lịch hẹn tư vấn 30 phút** (online/offline) + **chốt danh sách giấy tờ** cần gửi trước; mục tiêu kế tiếp: **đặt phương án vay cá nhân hóa** và “giữ suất” tiến độ ký/giải ngân đúng lịch của dự án.\n\n---\n\n## **2. Kịch bản tiếp cận và bán hàng** (Mục đích vay: **Vay mua nhà dự án Vin Ocean Park 2**; Điểm chạm: **Được bên sale giới thiệu**) 📞\n\n### **Kịch bản tiếp cận qua điện thoại** ☎️  \n**RM (MB):** Chào anh [Tên KH], em là **[Tên RM]** từ **MB Bank**. Em được bạn **bên sale Vin Ocean Park 2** giới thiệu anh đang cân nhắc phương án **vay mua căn** tại dự án, nên em gọi nhanh để mình **chốt hướng tài chính** cho kịp tiến độ, anh tiện nghe máy 2 phút chứ ạ?  \n**KH:** (Đồng ý/Đang bận)  \n**RM:** Dạ em hỏi rất nhanh 3 ý để tư vấn đúng: **(1)** Anh dự kiến chốt căn loại nào và **khi nào** ký/đóng tiền đợt gần nhất? **(2)** Anh muốn vay khoảng **bao nhiêu %** giá trị căn? **(3)** Nguồn trả nợ chính của mình là **dòng tiền kinh doanh** hay có thêm nguồn khác ạ?  \n**KH:** (Trả lời)  \n**RM (khơi gợi & xác nhận nhu cầu):** Em hiểu rồi ạ; với khách **chủ doanh nghiệp** như anh, điểm quan trọng nhất thường là **(i) duyệt nhanh đúng tiến độ CĐT**, **(ii) phương án trả nợ linh hoạt theo dòng tiền**, và **(iii) hồ sơ gọn để không mất thời gian**—đúng ưu tiên của anh không ạ?  \n**KH:** (Xác nhận/điều chỉnh)  \n**RM (đề xuất giá trị – nói ngắn, đúng “điểm đau”):** Với nhu cầu mua Vin Ocean Park 2, bên em có thể thiết kế **phương án vay mua nhà dự án** theo 3 lợi ích chính: **✅ Tỷ lệ tài trợ & thời hạn vay phù hợp** để giảm áp lực dòng tiền; **✅ Có thể cân nhắc ân hạn gốc thời gian đầu** (tùy hồ sơ) để anh tối ưu vốn cho kinh doanh; **✅ Quy trình xử lý hồ sơ gọn**—em sẽ **đồng hành checklist** và bám tiến độ phê duyệt/giải ngân theo lịch đóng tiền của dự án. Ngoài ra em gửi anh **2 phương án trả nợ** để anh chọn mức an toàn nhất.  \n**KH:** Lãi suất bên MB thế nào? / Tôi đang hỏi ngân hàng khác.  \n**RM (neo giá trị trước – rồi mới chốt hẹn):** Dạ phần lãi suất em sẽ gửi anh **bảng so sánh theo kỳ ưu đãi** và tính thử **tiền phải trả/tháng** theo đúng khoản vay của anh để mình nhìn bằng con số. Quan trọng là em sẽ tối ưu để anh thấy **tổng chi phí – sự thuận tiện – tốc độ xử lý** cái nào lợi nhất.  \n**RM (chốt hẹn rõ ràng):** Anh cho em xin **20–30 phút** hôm nay hoặc ngày mai: **(A)** em qua chỗ anh/ở văn phòng sales, hoặc **(B)** mình call online. Em sẽ chuẩn bị sẵn **2 kịch bản vay** (an toàn & tối ưu dòng tiền). Anh tiện khung **11:30–12:00** hay **17:30–18:00** ạ?  \n**KH:** (Chọn thời gian)  \n**RM (chốt “hành động nhỏ” ngay trong cuộc gọi):** Tuyệt vời ạ. Để buổi hẹn hiệu quả, anh giúp em trước **3 thông tin**: **giá căn dự kiến**, **khoản anh muốn vay**, và **thời điểm đóng tiền đợt gần nhất**; em sẽ gửi lại anh **bảng tính** ngay sau khi nhận. Em cảm ơn anh!\n\n---\n\n## **3. Tips bán hàng hiệu quả** 🎯\n- **Key selling point (keyword):** **“Giải pháp tài chính dài hạn – lãi suất linh hoạt – thủ tục gọn nhanh – RM bám sát tiến độ dự án & hỗ trợ hồ sơ.”**\n- **Tips bán hàng hiệu quả (áp cho KH Private, chủ DN):**  \n  1) **Bám “tiến độ đóng tiền”** của dự án để tạo urgency hợp lý: “đúng lịch – không lỡ căn/đợt thanh toán”.  \n  2) Tư vấn bằng **con số/tháng** (cashflow) thay vì chỉ nói lãi suất: đưa **2 kịch bản** “an toàn” vs “tối ưu vốn”.  \n  3) Nhấn mạnh **trải nghiệm**: “anh chỉ cần cung cấp đầu vào, phần còn lại em bám và cập nhật”.  \n  4) Khai thác tâm lý **an cư – giữ tài sản – tối ưu vốn kinh doanh**: “mua nhà nhưng vẫn giữ dòng tiền cho DN”.\n\n---\n\n## **4. Tips xử lý từ chối** 🛡️  \n*(Do **sales_situation = None**, áp dụng bộ xử lý mặc định dưới đây.)*\n\n- **Từ chối về lãi suất cao:**  \n  **RM:** Em hiểu anh quan tâm tổng chi phí. Lãi vay thường có **giai đoạn ưu đãi cố định ban đầu**, sau đó điều chỉnh theo thị trường; em sẽ so cho anh **2 phương án**: (1) ưu đãi mạnh đầu kỳ để giảm áp lực, (2) phương án cân bằng để ổn định lâu dài. Ngoài lãi suất, anh cân nhắc thêm **tốc độ duyệt – phí – hỗ trợ hồ sơ/tiến độ giải ngân**, vì nó ảnh hưởng trực tiếp việc chốt căn và kế hoạch vốn của anh.\n- **Từ chối do đã có ngân hàng khác:**  \n  **RM:** Dạ rất hợp lý khi anh so sánh. Em xin phép làm “**bài toán đối chiếu**” 10 phút: cùng khoản vay–kỳ hạn–cách trả nợ, em sẽ chỉ ra **khác biệt về tổng tiền/tháng + điều kiện giải ngân + mức linh hoạt hồ sơ**. Nếu bên kia tốt hơn, em cũng nói thẳng để anh chọn tối ưu; còn nếu MB lợi hơn ở **tiến độ & dịch vụ bám sát**, mình chốt phương án phù hợp ạ.\n- **Từ chối vì thủ tục phức tạp:**  \n  **RM:** Em cam kết phần thủ tục anh **không phải tự xoay**; em gửi **checklist đúng 1 lần**, hướng dẫn điền biểu mẫu, và em bám tiến độ xử lý để rút ngắn thời gian. Mục tiêu là anh chỉ cần tập trung công việc, còn hồ sơ vay em theo đến khi **phê duyệt & giải ngân đúng lịch**.\n- **Các tình huống khác:**  \n  + **“Tôi không có nhu cầu” →** **RM:** Dạ em hiểu. Cho em xin 1 phút: anh dự kiến 6–12 tháng tới có kế hoạch **đổi nhà/nâng cấp chỗ ở/mua thêm BĐS giữ tài sản** không ạ? Nếu có, em gửi anh trước **bảng nguyên tắc** để mình chủ động khi cần.  \n  + **“Tôi không có ấn tượng tốt về MB” →** **RM:** Em ghi nhận thẳng thắn của anh. Điều em có thể làm ngay là cho anh trải nghiệm **tư vấn minh bạch bằng con số**, timeline rõ ràng, cập nhật tiến độ chủ động. Anh cho em một cơ hội **30 phút**, nếu không phù hợp mình dừng, không làm phiền anh thêm ạ.  \n  + **“Tôi bận không có thời gian” →** **RM:** Dạ em linh hoạt theo lịch anh: mình có thể **call online 15–20 phút** ngoài giờ, hoặc em chỉ cần anh gửi 3 thông tin (giá căn–khoản vay–mốc đóng tiền), em làm sẵn **bảng tính** để anh xem khi rảnh; sau đó mình chốt 1 cuộc hẹn ngắn.\n\n--- \n\nNếu bạn cho mình thêm **[Vùng/Miền RM] + giới tính/tuổi RM** và KH đang ở bước **(đã booking/đã ký HĐMB/chưa chọn căn)**, mình sẽ tinh chỉnh ngôn từ vùng miền và “điểm chốt” sát tiến độ hơn."
    },
    {
        "role": "user",
        "content": "Cho mình xem thêm KBB này"
    },
    {
        "role": "assistant",
        "content": "Dưới đây là **một số KBB bổ sung** cho cùng bối cảnh: **KH Private – nam 45 – chủ DN – vay mua nhà dự án Vin Ocean Park 2 – lead từ sale**. Bạn có thể chọn theo kênh/điểm chạm.\n\n---\n\n## 1) KBB nhắn Zalo/SMS (sau khi sale giới thiệu)\n**RM:** Chào anh [Tên], em [Tên RM] – MB. Em được bạn [Tên sale] giới thiệu anh đang xem căn tại **Vinhomes Ocean Park 2**.  \nĐể em làm nhanh **2 phương án vay** (an toàn & tối ưu dòng tiền DN), anh cho em xin 3 thông tin: **giá căn**, **mức vay dự kiến (%/số tiền)**, **mốc đóng tiền gần nhất** ạ.  \nNếu tiện, mình hẹn **15–20’** call/online hôm nay **11:30–12:00** hoặc **17:30–18:00** anh chọn giúp em khung giờ nhé.\n\n**KH:** (trả lời)  \n**RM:** Em cảm ơn anh. Em gửi lại anh **bảng tính tiền/tháng + timeline phê duyệt** ngay trong hôm nay để kịp tiến độ dự án.\n\n---\n\n## 2) KBB gọi “chốt hẹn nhanh” (khi KH bận)\n**RM:** Em chào anh [Tên], em [Tên RM] MB – lead từ [sale]. Em xin đúng **60 giây**:  \n1) Đợt gần nhất anh cần đóng tiền khi nào?  \n2) Anh muốn vay khoảng bao nhiêu?  \n3) Anh ưu tiên **duyệt nhanh** hay **tối ưu chi phí** hơn ạ?\n\n**Nếu KH nói bận:**  \n**RM:** Dạ em hiểu. Anh cho em xin **1 khung giờ 10–15’** (trưa/ngoài giờ đều được). Em sẽ gửi trước **2 phương án** để anh xem nhanh, cuộc gọi mình chỉ chốt phương án và checklist hồ sơ.\n\n---\n\n## 3) KBB tư vấn tại chỗ (gặp ở sàn/sales gallery)\n**RM:** Em chào anh [Tên], em là RM MB. Em sẽ đi thẳng vào 3 thứ anh quan tâm nhất khi vay mua nhà dự án:  \n- **Đúng tiến độ đóng tiền** (không lỡ lịch)  \n- **Phương án trả nợ theo dòng tiền DN**  \n- **Hồ sơ gọn – một đầu mối xử lý**\n\n**RM (khai thác nhu cầu):** Anh dự kiến giữ căn để ở hay đầu tư? Anh muốn “nhẹ gốc” giai đoạn đầu để ưu tiên vốn kinh doanh không ạ?\n\n**RM (đề xuất 2 lựa chọn):**  \n- **PA1 An toàn:** trả đều, tỷ lệ vay vừa phải, tiền/tháng ổn định.  \n- **PA2 Tối ưu dòng tiền:** cân nhắc ân hạn gốc/thiết kế lịch trả theo mùa vụ (tùy hồ sơ).\n\n**RM (chốt bước tiếp):** Nếu anh đồng ý, mình chốt luôn: **mốc đóng tiền**, **mức vay**, và em gửi **checklist hồ sơ** để bắt đầu thẩm định trong ngày.\n\n---\n\n## 4) KBB gửi báo giá/lãi suất (tránh “nói miệng”)\n**RM:** Em gửi anh 2 phương án theo đúng **giá căn – số vay – kỳ hạn**. Anh xem giúp em 3 dòng:  \n1) **Tiền phải trả/tháng** giai đoạn ưu đãi  \n2) **Tiền phải trả/tháng** sau ưu đãi (ước tính)  \n3) **Tổng chi phí dự kiến** + các điều kiện kèm theo\n\nAnh muốn em tối ưu theo hướng **giảm tiền/tháng** hay **giảm tổng chi phí** ạ? (em sẽ chỉnh ngay theo ưu tiên của anh)\n\n---\n\n## 5) KBB follow-up sau khi gửi phương án (24–48h)\n**RM:** Chào anh [Tên], em follow-up nhanh phần bảng tính hôm qua:  \n- Phương án nào “khớp” nhất với dòng tiền DN của anh: **PA1** hay **PA2** ạ?  \nNếu anh chốt, em xin phép nhận trước **3 hồ sơ tối thiểu** để vào luồng duyệt sớm: (1) giấy tờ cá nhân, (2) hồ sơ chứng minh thu nhập/dòng tiền, (3) thông tin căn/tiến độ thanh toán.  \nAnh muốn em qua lấy hồ sơ hay anh gửi bản chụp trước qua Zalo/email ạ?\n\n---\n\n## 6) KBB xử lý từ chối “lãi suất cao” theo phong cách Private\n**KH:** Lãi suất bên em cao.  \n**RM:** Em hiểu. Với KH Private, mình nên nhìn **tổng bài toán**:  \n- **tiền/tháng** theo dòng tiền DN,  \n- **phí/điều kiện giải ngân đúng tiến độ**,  \n- và **độ chắc chắn phê duyệt**.  \nAnh cho em xin báo giá bên khác (chỉ cần lãi + kỳ ưu đãi + phí chính). Em làm bảng **so sánh cùng một khoản vay** và chỉ ra điểm chênh đúng/sai. Nếu MB không tốt hơn, em nói thẳng để anh khỏi mất thời gian.\n\n---\n\nNếu bạn muốn, mình có thể viết thêm **KBB “chốt hồ sơ trong 1 cuộc hẹn”** (kèm checklist theo nhóm giấy tờ) hoặc **KBB xử lý tình huống KH đã có ngân hàng A nhưng muốn giữ bí mật dòng tiền DN**. Bạn cho mình biết KH đang ở bước: **đã booking/đã ký HĐMB/chưa chọn căn** và **mốc đóng tiền gần nhất** nhé."
    },
    {
        "role": "user",
        "content": "Xem thêm"
    },
    {
        "role": "assistant",
        "content": "Bạn quả là người ham học hỏi vì đã tham khảo toàn bộ những kịch bản bán hàng hiệu quả mà tôi phải vắt óc để nghĩ ra. Hãy cho tôi thêm thời gian để suy nghĩ ra những kịch bản mới nhé. Vui lòng tham khảo lại 1 kịch bản hấp dẫn mà tôi đã từng chia sẻ cho bạn"
    },
    {
        "role": "user",
        "content": "Sản phẩm khác"
    },
    {
        "role": "assistant",
        "content": "Chào bạn! Mình là Trợ lý bán hàng thông minh. Hãy chọn sản phẩm để mình gợi ý các kịch bản bán hàng hiệu quả nhé!  <Button: Tín dụng> <Button: Huy động vốn> <Button: CDs> <Button: Bancas><Button: Thẻ><Button: SP Đầu tư><Button: Kiều hối>"
    },
    {
        "role": "user",
        "content": "khách hàng vay 32 tuổi  vừa giải ngân 3 tỷ, khách hàng kinh doanh bia, nước ngọt, lợi nhuận 150 triệu đồng/ tháng nên tư vấn gói bảo hiểm nào là phù hợp và giá trị là bao nhiêu"
    },
] 
 ,
        metadata={  "workflow": "internal",
                    # "switched": "standard",
                    # "share_scenarios": "false",
                    # "scenarios": [],
                    # "messageType": "button",
                    # "crmBusinessIndustry": {
                    #     "businessIndustryId": "3e1c7997-58ec-4461-952c-34df5b5140ee",
                    #     "businessIndustryName": "46323-Bán buôn rau, quả",
                    # },
                },

        session_id = dialogue_id,
        client_message_id=client_message_id,
        username = username
    ):
        print(f"chunk: {chunk}")

    await asyncio.sleep(4)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())



__all__ = ["BeeCRMBotV2"]




