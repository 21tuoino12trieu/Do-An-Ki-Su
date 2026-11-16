from datetime import datetime
from typing import Dict, List
import asyncio

from beeflow.nodes import EmbeddingNode, MilvusNode
from beeflow.nodes.base_node import END, INPUT, OUTPUT, START
from beeflow.nodes.flow.branch_node import BranchNode
from beeflow.nodes.flow.for_loop_node import ForLoopNode
from beeflow.nodes.graph.graph_node import GraphNode
from beeflow.nodes.primitives.ai.llm_node import LLMNode
from beeflow.nodes.primitives.ai.rerank_node import RerankNode
from beeflow.nodes.primitives.data.mongo_node import MongoNode
from beeflow.nodes.primitives.data.sql_node import SQLNode
from beeflow.nodes.primitives.memory.mem0_node import Mem0Node
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beeflow.nodes.templates.basic_chain_node import BasicChainNode
from beeflow.nodes.templates.retriever_node_v2 import RetrieverNode
from beeflow.workflow import WorkflowEngine
from beeflow.utils.streaming import STREAM_SERVICE
from beegen.configs.memory.mem0_config import Mem0Operation
from beegen.loggings.loggers import LOGGER
from beegen.registry.resource_hub import ResourceHub
from beegen.utils.common import fake_chunk_from, transform_bot_id
from beeportal.bot_bee247.bee247.functions import *
from beeportal.bot_bee247.bee247.mapping_prompt import get_topic_prompt
from beeportal.utils import PROMPTS, annotate_query, get_cache_qa, init_query, post_process_mem0_search_results

from beegen.configs.storage.sql_config import (
    SQLOperation,
    SQL_OPERATION_INPUTS,
    SQL_OPERATION_OUTPUTS,
)


class Bee247Bot:
    def __init__(self, bot_id: str):
        self.bot_id = bot_id
        mongo_engine = ResourceHub.self().sync_mongo("aicenter-chatbot")
        bot_info = mongo_engine._find_one(collection_name="botinfo", query={"_id": self.bot_id})
        self.name = bot_info.get('data', {'name': {}}).get('name', None)
        self.config = bot_info.get('data', {'metadata': {}}).get('metadata', {})
        self.DOCUMENT_TEXT_CACHING = {}
        self.cep_account_mapping = load_STK_mapping()
        self.cep_mapping = load_cep_mapping()

        self._build_flow()

    def _build_flow(self):
        with WorkflowEngine(
            name="bee247",
            description="đây là chatbot của 247"
        ) as bee247:
            # region ===== rewrite query =====
            with GraphNode(
                name="rewrite_query",
                description="luồng rewrite query",
                inputs={"messages": INPUT},
            ) as rewrite_query:
                init_query_fn = CodeNode(
                    name="init_query_fn",
                    code_fn=init_query,
                    inputs={"messages": INPUT},
                    return_keys=["origin_query: str", "conversation: List[str]"],
                    outputs={"conversation": OUTPUT}
                )
                
                annotate_query_fn = CodeNode(
                    name="annotate_query_fn",
                    code_fn=annotate_query,
                    inputs={"origin_query": init_query_fn},
                    return_keys=["query: str"],
                    outputs={"query": OUTPUT}
                )
                
                enhanced_query = BasicChainNode(
                    name="enhanced_query",
                    resource_key="gemini-2.5-flash-chat",
                    llm_configs= {"reasoning_effort": "none"},
                    user_prompt=PROMPTS["BEE247:ENHANCED_CONVERSATION_WITH_FLOW_PROMPT"],
                    inputs={
                        "current_user_message": {annotate_query_fn: "query"},
                        "full_conversation": {init_query_fn: "conversation"}
                    },
                    outputs={"content": {OUTPUT: "enhanced_query"}}
                )

                START >> init_query_fn >> annotate_query_fn >> enhanced_query >> END
            # endregion ===== rewrite query =====

            # region ===== check cached qa =====
            with GraphNode(
                name="qa_cached",
                description="streaming cached qa if match",
                inputs={
                    # "query": rewrite_query,
                    "enhanced_query": {rewrite_query: "query"}, 
                    "role_ids": INPUT
                }
            ) as qa_cached:
                qa_retriever = RetrieverNode(
                    name="qa_retriever",
                    inputs={
                        "query": {INPUT: "enhanced_query"},
                        "collection": transform_bot_id(self.bot_id),
                        "partition_names": ["QA"],
                        "top_k": 5, "rerank_top_k": 1,
                        "output_fields": ["chunk_id"],
                        "allowed_roles": {INPUT: "role_ids"},
                        "bot_id": self.bot_id,
                    }
                )

                get_cached_qa_fn = CodeNode(
                    name="get_cached_qa_fn",
                    code_fn=get_cache_qa,
                    inputs={"docs": qa_retriever},
                    return_keys=["cache_qa: Optional[str]", "ids: Optional[List[Dict[str, Any]]]"],
                    outputs=OUTPUT,
                )
                
                qa_filter = BasicChainNode(
                    name="qa_filter", 
                    resource_key="gpt-4o",
                    parser="yaml",
                    user_prompt=PROMPTS["BEE247:QA_FILTER_PROMPT"],
                    inputs={
                        "question": {INPUT: "enhanced_query"},
                        "document": {get_cached_qa_fn: "cache_qa"}
                    },
                    extract_schema=["result: str"],
                    outputs={"result": OUTPUT}
                )

                START >> qa_retriever >> get_cached_qa_fn >> qa_filter >> END
            # endregion ===== check cached qa =====

            stream_cached_qa_answer = BasicChainNode(
                name="stream_cached_qa_answer",
                resource_key="gpt-4o",
                user_prompt=PROMPTS["BEE247:NORMAL_RAG_ANSWER_PROMPT"],
                inputs={
                    "question": {rewrite_query: "query"},
                    "final_documents": {qa_cached: "cache_qa"},
                    "docs": {qa_cached: "ids"}
                },
                stream=True
            )
            
            post_process_stream_cached_qa_answer_fn = CodeNode(
                name="post_process_stream_cached_qa_answer_fn",
                code_fn=post_process_stream_cached_qa_answer,
                inputs={
                    "query": {rewrite_query: "query"},
                    "content": stream_cached_qa_answer,
                },
                return_keys=["dialogue: Dict[str, List[Dict[str, str]]]", "output_response: str"],
            )
            
            cached_qa_add_session_memory = Mem0Node(
                name="cached_qa_add_session_memory",
                resource_key="mem0",
                operation=Mem0Operation.ADD,
                inputs={
                    "messages": {post_process_stream_cached_qa_answer_fn: "dialogue"},
                    "session_id": INPUT,
                    "custom_fact_extraction_prompt": PROMPTS["BEE247:CUSTOM_FACT_EXTRACTION_PROMPT"],
                }
            )
            
            llm_check_intent_khcn_khdn = BasicChainNode(
                name="llm_check_intent_khcn_khdn",
                resource_key="gemini-2.5-flash-chat",
                llm_configs= {"reasoning_effort": "none"},
                user_prompt=PROMPTS["BEE247:CHECK_INTENT_KHCN_KHDN"],
                inputs={
                    "question": {rewrite_query: "enhanced_query"},
                }
            )
            
            llm_ask_back_khcn_khdn = LLMNode(
                name="llm_ask_back_khcn_khdn",
                resource_key="fake",
                instant_response=True,
                inputs={"response": f"Chào bạn, vấn đề này bạn đang quan tâm đến thông tin sản phẩm dành cho đối tượng Khách hàng cá nhân (KHCN) hay Khách hàng doanh nghiệp (KHDN)?"},
                outputs={"content": OUTPUT},
                stream=True
            )
            
            search_session_memory = Mem0Node(
                name="search_session_memory",
                resource_key="mem0",
                operation=Mem0Operation.SEARCH,
                inputs={
                    "query": {rewrite_query: "enhanced_query"},
                    "session_id": INPUT,
                }
            )
            
            postprocess_mem0_results_fn = CodeNode(
                name="postprocess_mem0_results_fn",
                code_fn=post_process_mem0_search_results,
                inputs={
                    "mem0_response": {search_session_memory: "results"}
                },
                return_keys=["memory_context: str"]
            )

            topic_classifier = BasicChainNode(
                name="topic_classifier",
                resource_key="gemini-2.5-flash-chat",
                llm_configs= {"reasoning_effort": "none"},
                parser="yaml",
                user_prompt=PROMPTS["BEE247:TOPIC_CLASSIFY_PROMPT"],
                inputs={
                    "question": {rewrite_query: "enhanced_query"},
                },
                extract_schema=["topic: str"],
            )
            
            routing_ask_back = BranchNode(
                name="routing_ask_back",
                cases={
                    "'sản phẩm thẻ' in topic and 'no' in content": llm_ask_back_khcn_khdn,
                    "'vay' in topic and 'no' in content": llm_ask_back_khcn_khdn,
                    "'ngân hàng điện tử' in topic and 'no' in content": llm_ask_back_khcn_khdn,
                    "'tài khoản thanh toán' in topic and 'no' in content": llm_ask_back_khcn_khdn,
                    "'chuyển tiền' in topic and 'no' in content": llm_ask_back_khcn_khdn,
                },
                default="search_session_memory",
                inputs={
                    "topic": topic_classifier,
                    "content": llm_check_intent_khcn_khdn
                },
            )
            
            routing_qa_flow = BranchNode(
                name="routing_qa_flow",
                cases={
                    "'có' in result.lower()": stream_cached_qa_answer, 
                },
                default=routing_ask_back,
                inputs={
                    "result": qa_cached
                }
            )
            
            routing_main_flow = BranchNode(
                name="routing_main_flow",
                cases={
                    "'sản phẩm thẻ' in topic": "card_response",
                    "'chi nhánh' in topic": "location_response",
                    "'phòng giao dịch' in topic": "location_response",
                    "'atm' in topic": "location_response",
                    "'cdm' in topic": "location_response",
                    "'crm' in topic": "location_response",
                    "'smart bank' in topic": "location_response"
                },
                default="standard_response",
                inputs={"topic": topic_classifier}
            )

            # region ===== standard =====
            with GraphNode(
                name="standard_response",
                description="streaming standard response",
                inputs={
                    # "query": rewrite_query, 
                    "enhanced_query": rewrite_query, 
                    "conversation": rewrite_query, 
                    "memory_context": postprocess_mem0_results_fn, 
                    "role_ids": INPUT
                }
            ) as standard_response:
                master_retriever = RetrieverNode(
                    name="master_retriever",
                    inputs={
                        "query": {INPUT: "enhanced_query"},
                        "collection": transform_bot_id(self.bot_id),
                        "top_k": 16,
                        "rerank_top_k": 3,
                        "partition_names": ['document'],
                        "output_fields": ["chunk_id"],
                        "allowed_roles": {INPUT: "role_ids"},
                        "bot_id": self.bot_id
                    }
                )

                qa_retriever = RetrieverNode(
                    name="qa_retriever",
                    inputs={
                        "query": {INPUT: "enhanced_query"},
                        "collection": transform_bot_id(self.bot_id),
                        "top_k": 16,
                        "rerank_top_k": 2,
                        "partition_names": ['QA'],
                        "output_fields": ["chunk_id"],
                        "allowed_roles": {INPUT: "role_ids"},
                        "bot_id": self.bot_id
                    }
                )

                gw_retriever = RetrieverNode(
                    name="gw_retriever",
                    inputs={
                        "query": {INPUT: "enhanced_query"},
                        "collection": f"{transform_bot_id(self.bot_id)}_gwcode",
                        "top_k": 16,
                        "rerank_top_k": 2,
                        "output_fields": ["chunk_id"],
                        "allowed_roles": {INPUT: "role_ids"},
                        "bot_id": self.bot_id
                    }
                )

                fee_retriever = RetrieverNode(
                    name="fee_retriever",
                    inputs={
                        "query": {INPUT: "enhanced_query"},
                        "collection": f"{transform_bot_id(self.bot_id)}_BIEUPHI",
                        "top_k": 16,
                        "rerank_top_k": 2,
                        "output_fields": ["chunk_id"],
                        "allowed_roles": {INPUT: "role_ids"},
                        "bot_id": self.bot_id
                    }
                )

                promotion_retriever = RetrieverNode(
                    name="promotion_retriever",
                    inputs={
                        "query": {INPUT: "enhanced_query"},
                        "collection": f"{transform_bot_id(self.bot_id)}_UUDAI",
                        "top_k": 6,
                        "rerank_top_k": 2,
                        "output_fields": ["chunk_id"],
                        "allowed_roles": {INPUT: "role_ids"},
                        "bot_id": self.bot_id
                    }
                )

                format_retrieved_docs_fn = CodeNode(
                    name="format_retrieved_docs_fn",
                    code_fn=format_retrieved_docs,
                    inputs={
                        "master_docs": {master_retriever: "docs"},
                        "master_qa": {qa_retriever: "docs"},
                        "gw_docs": {gw_retriever: "docs"},
                        "fee_docs": {fee_retriever: "docs"},
                        "promotion_docs": {promotion_retriever: "docs"}
                    },
                    return_keys=["doc_contents: List[str]", "doc_ids: List[str]", "ids: List[Dict[str, Any]]", "lengths: int"]
                )

                standard_rerank = RerankNode(
                    name="standard_rerank",
                    resource_key="bge-m3",
                    inputs={
                        "query": {INPUT: "enhanced_query"},
                        "documents": {format_retrieved_docs_fn: "doc_contents"},
                        "top_k": {format_retrieved_docs_fn: "lengths"}
                    }
                )

                cep_mapping_of_fn = CodeNode(
                    name="cep_mapping_of_fn",
                    code_fn=cep_mapping_of,
                    inputs={
                        "query": {INPUT: "enhanced_query"},
                        "cep_account_mapping": self.cep_account_mapping,
                        "cep_mapping": self.cep_mapping
                    },
                    return_keys=["cep_result: Dict[str, Any]"]
                )

                format_final_docs_fn = CodeNode(
                    name="format_final_docs_fn",
                    code_fn=format_final_docs,
                    inputs={
                        "cep_mapping_result": {cep_mapping_of_fn: "cep_result"},
                        "retrieved_docs": {standard_rerank: "reranks"}
                    },
                    return_keys=["template: str", "documents_text: str"]
                )

                routing_template_flow = BranchNode(
                    name="routing_template_flow",
                    cases={
                        "template == 'EMB_RAG_ANSWER_PROMPT'": "emb_rag_answer",
                        "template == 'EKYC_RAG_ANSWER_PROMPT'": "ekyc_rag_answer"
                    },
                    default="normal_rag_answer",
                    inputs={
                        "template": format_final_docs_fn
                    }
                )

                normal_rag_answer = BasicChainNode(
                    name="normal_rag_answer",
                    resource_key="gpt-4o",
                    user_prompt=PROMPTS["BEE247:NORMAL_RAG_ANSWER_PROMPT"],
                    inputs={
                        "date": datetime.now().date().strftime("%d/%m/%Y"),
                        "final_documents": {format_final_docs_fn: "documents_text"},
                        "question": {INPUT: "enhanced_query"},
                        "conversation": INPUT,
                        "memory_context": INPUT,
                        "docs": {format_retrieved_docs_fn: "ids"}
                    },
                    outputs={"content": OUTPUT},
                    stream=True
                )

                emb_rag_answer = BasicChainNode(
                    name="emb_rag_answer",
                    resource_key="gpt-4o",
                    user_prompt=PROMPTS["BEE247:EMB_RAG_ANSWER_PROMPT"],
                    inputs={
                        "final_documents": {format_final_docs_fn: "documents_text"},
                        "question": {INPUT: "enhanced_query"},
                        "memory_context": INPUT,
                        "conversation": INPUT,
                        "docs": {format_retrieved_docs_fn: "ids"}
                    },
                    outputs={"content": OUTPUT},
                    stream=True
                )

                ekyc_rag_answer = BasicChainNode(
                    name="ekyc_rag_answer",
                    resource_key="gpt-4o",
                    user_prompt=PROMPTS["BEE247:EKYC_RAG_ANSWER_PROMPT"],
                    inputs={
                        "final_documents": {format_final_docs_fn: "documents_text"},
                        "question": {INPUT: "enhanced_query"},
                        "memory_context": INPUT,
                        "conversation": INPUT,
                        "docs": {format_retrieved_docs_fn: "ids"}
                    },
                    outputs={"content": OUTPUT},
                    stream=True
                )

                START >> [master_retriever, 
                          qa_retriever, 
                          gw_retriever, 
                          fee_retriever, 
                          promotion_retriever] >> format_retrieved_docs_fn
                format_retrieved_docs_fn >> [cep_mapping_of_fn, 
                                             standard_rerank] >> format_final_docs_fn >> routing_template_flow
                routing_template_flow >> [normal_rag_answer, 
                                          emb_rag_answer, 
                                          ekyc_rag_answer] >> END
            # endregion ===== standard =====
            
            post_process_standard_response_fn = CodeNode(
                name="post_process_standard_response_fn",
                code_fn=post_process_standard_response,
                inputs={
                    "query": {rewrite_query: "enhanced_query"},
                    "content": standard_response,
                },
                return_keys=["dialogue: Dict[str, List[Dict[str, str]]]", "output_standard_response: str"]
            )
            
            standard_add_session_memory = Mem0Node(
                name="standard_add_session_memory",
                resource_key="mem0",
                operation=Mem0Operation.ADD,
                inputs={
                    "messages": {post_process_standard_response_fn: "dialogue"},
                    "session_id": INPUT,
                    "custom_fact_extraction_prompt": PROMPTS["BEE247:CUSTOM_FACT_EXTRACTION_PROMPT"],
                }
            )
            
            # region ===== card =====
            with GraphNode(
                name="card_response",
                description="streaming card response",
                inputs={
                    # "query": rewrite_query, 
                    "memory_context": postprocess_mem0_results_fn, 
                    "enhanced_query": rewrite_query, 
                    "conversation": rewrite_query,
                    "role_ids": INPUT
                },
                outputs=OUTPUT
            ) as card_response:
                # region ===== card extract keywords =====
                with GraphNode(
                    name="card_extract_keywords",
                    description="extract keywords card flow",
                    inputs={
                        "enhanced_query": INPUT,
                    }
                ) as card_extract_keywords:
                    get_card_keywords_data = MongoNode(
                        name="get_card_keywords_data",
                        resource_key="aicenter-chatbot",
                        operation="find",
                        inputs={
                            "collection_name": "filename_mapping",
                            "query": {"type": "card_keyword"},
                            "projection": {"mapping": 1, "_id": 0}
                        }
                    )

                    post_process_card_keywords_data_fn = CodeNode(
                        name="post_process_card_keywords_data_fn",
                        code_fn=post_process_card_keywords_data,
                        inputs={
                            "data": get_card_keywords_data,
                        },
                        return_keys=["card_keywords_data_unique: List[str]", "card_keywords_data: Dict[str, Any]"]
                    )

                    card_keywords_extractor = BasicChainNode(
                        name="card_keywords_extractor",
                        resource_key="gemini-2.5-flash-chat",
                        user_prompt=PROMPTS["BEE247:CARD_KEYWORD_EXTRACT_PROMPT"],
                        inputs={
                            "question": {INPUT: "enhanced_query"},
                            "keywords": {post_process_card_keywords_data_fn: "card_keywords_data_unique"}
                        },
                    )

                    get_card_filename_data = MongoNode(
                        name="get_card_filename_data",
                        resource_key="aicenter-chatbot",
                        operation="find",
                        inputs={
                            "collection_name": "filename_mapping",
                            "query": {"type": "card_filename"},
                            "projection": {"mapping": 1, "_id": 0}
                        }
                    )

                    post_process_card_keywords_query_fn = CodeNode(
                        name="post_process_card_keywords_query_fn",
                        code_fn=post_process_card_keywords_query,
                        inputs={
                            "query": {card_keywords_extractor: "content"},
                        },
                        return_keys=["query_keywords: List[str]"]
                    )

                    post_process_card_filename_data_fn = CodeNode(
                        name="post_process_card_filename_data_fn",
                        code_fn=post_process_card_filename_data,
                        inputs={
                            "data": get_card_filename_data,
                        },
                        return_keys=["card_filename_data: Dict[str, str]"],
                        outputs=OUTPUT
                    )

                    extract_matching_card_ids_fn = CodeNode(
                        name="extract_matching_card_ids_fn",
                        code_fn=extract_matching_card_ids,
                        inputs={
                            "all_keywords": {post_process_card_keywords_data_fn: "card_keywords_data"},
                            "extracted_keywords": {post_process_card_keywords_query_fn: "query_keywords"},
                            "unique_keywords": {post_process_card_keywords_data_fn: "card_keywords_data_unique"}
                        },
                        return_keys=["card_ids: List[str]"],
                        outputs=OUTPUT
                    )
                    
                    START >> [get_card_keywords_data, 
                            get_card_filename_data]
                    
                    get_card_keywords_data >> post_process_card_keywords_data_fn >> card_keywords_extractor >> post_process_card_keywords_query_fn
                    
                    get_card_filename_data >> post_process_card_filename_data_fn
                    
                    [post_process_card_keywords_data_fn, 
                    post_process_card_keywords_query_fn] >> extract_matching_card_ids_fn >> END
                # endregion ===== card extract keywords =====
                
                # region ===== card stream response =====
                with GraphNode(
                    name="card_stream_response",
                    description="extract keywords card flow",
                    inputs={
                        # "query": INPUT, 
                        "memory_context": INPUT, 
                        "enhanced_query": INPUT, 
                        "conversation": INPUT,
                        "role_ids": INPUT,
                        "card_ids": card_extract_keywords,
                        "card_filename_data": card_extract_keywords
                    },
                    outputs=OUTPUT
                ) as card_stream_response:
                    card_ids_batch_inputs_create_fn = CodeNode(
                        name="card_ids_batch_inputs_create_fn",
                        code_fn=create_card_ids_batch_inputs,
                        inputs={
                            "card_ids": INPUT,
                            "enhanced_query": INPUT,
                            "role_ids": INPUT
                        },
                        return_keys=[
                            "batch_data: List[Dict[str, Any]]"
                        ]
                    )
                    
                    with ForLoopNode(
                        name="card_batch_retriever",
                        inputs={
                            "batch_data": card_ids_batch_inputs_create_fn
                        },
                    ) as card_batch_retriever:
                        card_retriever = RetrieverNode(
                            name="card_retriever",
                            inputs={
                                "query": {INPUT: "enhanced_query"},
                                "collection": transform_bot_id(self.bot_id) + "_THE",
                                "top_k": 10,
                                "rerank_top_k": 3,
                                "partition_names": INPUT,
                                "output_fields": ["chunk_id"],
                                "allowed_roles": {INPUT: "role_ids"},
                                "bot_id": self.bot_id
                            }
                        )
                        
                        format_retrieved_card_documents_fn = CodeNode(
                            name="format_retrieved_card_documents_fn",
                            code_fn=format_retrieved_card_documents,
                            inputs={
                                "docs": card_retriever
                            },
                            return_keys=["document_contents: List[str]", "ids: List[Dict[str, Any]]"],
                            outputs=OUTPUT
                        )
                        
                        START >> card_retriever >> format_retrieved_card_documents_fn >> END                  

                    create_stream_local_card_batch_inputs_create_fn = CodeNode(
                        name="create_stream_local_card_batch_inputs_create_fn",
                        code_fn=create_stream_local_card_batch_inputs,
                        inputs={
                            "enhanced_query": INPUT,
                            "card_ids": INPUT,
                            "card_filenames": {INPUT: "card_filename_data"},
                            "memory_context": INPUT,
                            "batch_retrieved_results": {card_batch_retriever: "batch_result"}
                        },
                        return_keys=[
                            "batch_data: List[Dict[str, Any]]",
                            "ids: List[Dict[str, Any]]"
                        ]
                    )
                    
                    card_topic_synthesize = BasicChainNode(
                        name="card_topic_synthesize",
                        resource_key="gpt-4o",
                        user_prompt=PROMPTS["BEE247:TOPIC_SYNTHESIZE_INTRODUCTION_PROMPT"],
                        inputs={
                            "question": {INPUT: "enhanced_query"},
                            "topics": {INPUT: "card_ids"},
                            "conversation": INPUT,
                            "memory_context": INPUT,
                            "docs": {create_stream_local_card_batch_inputs_create_fn: "ids"}
                        },
                        outputs={"content": {OUTPUT: "synthesize_content"}},
                        stream=True
                    )

                    # region ===== card iteration =====
                    with ForLoopNode(
                        name="stream_local_card",
                        inputs={
                            "batch_data": {create_stream_local_card_batch_inputs_create_fn: "batch_data"},
                        },
                        outputs={"batch_result": {OUTPUT: "local_content"}},
                    ) as stream_local_card:
                        stream_card_document = BasicChainNode(
                            name="stream_card_document",
                            resource_key="gpt-4o",
                            user_prompt=PROMPTS["BEE247:TOPIC_SYNTHESIZE_LOCAL_PROMPT"],
                            inputs={
                                "topic": INPUT,
                                "topics": INPUT,
                                "topic_documents": {INPUT: "contents"},
                                "question": {INPUT: "enhanced_query"},
                                "conversation": INPUT,
                                "memory_context": INPUT,
                                "docs": {INPUT: "ids"}
                            },
                            outputs={"content": OUTPUT},
                            stream=True
                        )

                        START >> stream_card_document >> END
                        # endregion ===== card iteration =====
                
                    START >> card_ids_batch_inputs_create_fn >> card_batch_retriever >> create_stream_local_card_batch_inputs_create_fn >> card_topic_synthesize >> stream_local_card >> END
                # endregion ===== card stream response =====

                # region ===== standard stream response callback =====
                with GraphNode(
                    name="card_callback_standard_response",
                    description="callback streaming standard response",
                    inputs={
                        # "query": INPUT, 
                        "enhanced_query": INPUT, 
                        "conversation": rewrite_query, 
                        "memory_context": INPUT, 
                        "role_ids": INPUT
                    },
                    outputs=OUTPUT
                ) as card_callback_standard_response:
                    master_retriever = RetrieverNode(
                        name="master_retriever",
                        inputs={
                            "query": {INPUT: "enhanced_query"},
                            "collection": transform_bot_id(self.bot_id),
                            "top_k": 20,
                            "rerank_top_k": 16,
                            "partition_names": ['document'],
                            "output_fields": ["chunk_id"],
                            "allowed_roles": {INPUT: "role_ids"},
                            "bot_id": self.bot_id
                        }
                    )

                    qa_retriever = RetrieverNode(
                        name="qa_retriever",
                        inputs={
                            "query": {INPUT: "enhanced_query"},
                            "collection": transform_bot_id(self.bot_id),
                            "top_k": 20,
                            "rerank_top_k": 4,
                            "partition_names": ['QA'],
                            "output_fields": ["chunk_id"],
                            "allowed_roles": {INPUT: "role_ids"},
                            "bot_id": self.bot_id
                        }
                    )

                    gw_retriever = RetrieverNode(
                        name="gw_retriever",
                        inputs={
                            "query": {INPUT: "enhanced_query"},
                            "collection": f"{transform_bot_id(self.bot_id)}_gwcode",
                            "top_k": 16,
                            "rerank_top_k": 0,
                            "output_fields": ["chunk_id"],
                            "allowed_roles": {INPUT: "role_ids"},
                            "bot_id": self.bot_id
                        }
                    )

                    fee_retriever = RetrieverNode(
                        name="fee_retriever",
                        inputs={
                            "query": {INPUT: "enhanced_query"},
                            "collection": f"{transform_bot_id(self.bot_id)}_BIEUPHI",
                            "top_k": 16,
                            "rerank_top_k": 0,
                            "output_fields": ["chunk_id"],
                            "allowed_roles": {INPUT: "role_ids"},
                            "bot_id": self.bot_id
                        }
                    )

                    promotion_retriever = RetrieverNode(
                        name="promotion_retriever",
                        inputs={
                            "query": {INPUT: "enhanced_query"},
                            "collection": f"{transform_bot_id(self.bot_id)}_UUDAI",
                            "top_k": 6,
                            "rerank_top_k": 0,
                            "output_fields": ["chunk_id"],
                            "allowed_roles": {INPUT: "role_ids"},
                            "bot_id": self.bot_id
                        }
                    )

                    format_retrieved_docs_fn = CodeNode(
                        name="format_retrieved_docs_fn",
                        code_fn=format_retrieved_docs,
                        inputs={
                            "master_docs": {master_retriever: "docs"},
                            "master_qa": {qa_retriever: "docs"},
                            "gw_docs": {gw_retriever: "docs"},
                            "fee_docs": {fee_retriever: "docs"},
                            "promotion_docs": {promotion_retriever: "docs"}
                        },
                        return_keys=["doc_contents: List[str]", "doc_ids: List[str]", "ids: List[Dict[str, Any]]", "lengths: int"]
                    )

                    standard_rerank = RerankNode(
                        name="standard_rerank",
                        resource_key="bge-m3",
                        inputs={
                            "query": {INPUT: "enhanced_query"},
                            "documents": {format_retrieved_docs_fn: "doc_contents"},
                            "top_k": {format_retrieved_docs_fn: "lengths"}
                        }
                    )

                    cep_mapping_of_fn = CodeNode(
                        name="cep_mapping_of_fn",
                        code_fn=cep_mapping_of,
                        inputs={
                            "query": {INPUT: "enhanced_query"},
                            "cep_account_mapping": self.cep_account_mapping,
                            "cep_mapping": self.cep_mapping
                        },
                        return_keys=["cep_result: Dict[str, Any]"]
                    )

                    format_final_docs_fn = CodeNode(
                        name="format_final_docs_fn",
                        code_fn=format_final_docs,
                        inputs={
                            "cep_mapping_result": {cep_mapping_of_fn: "cep_result"},
                            "retrieved_docs": {standard_rerank: "reranks"}
                        },
                        return_keys=["template: str", "documents_text: str"]
                    )

                    routing_template_flow = BranchNode(
                        name="routing_template_flow",
                        cases={
                            "template == 'EMB_RAG_ANSWER_PROMPT'": "emb_rag_answer",
                            "template == 'EKYC_RAG_ANSWER_PROMPT'": "ekyc_rag_answer"
                        },
                        default="normal_rag_answer",
                        inputs={
                            "template": format_final_docs_fn
                        }
                    )

                    normal_rag_answer = BasicChainNode(
                        name="normal_rag_answer",
                        resource_key="gpt-4o",
                        user_prompt=PROMPTS["BEE247:NORMAL_RAG_ANSWER_PROMPT"],
                        inputs={
                            "date": datetime.now().date().strftime("%d/%m/%Y"),
                            "final_documents": {format_final_docs_fn: "documents_text"},
                            "question": {INPUT: "enhanced_query"},
                            "conversation": INPUT,
                            "memory_context": INPUT,
                            "docs": {format_retrieved_docs_fn: "ids"}
                        },
                        outputs={"content": {OUTPUT: "synthesize_content"}},
                        stream=True
                    )

                    emb_rag_answer = BasicChainNode(
                        name="emb_rag_answer",
                        resource_key="gpt-4o",
                        user_prompt=PROMPTS["BEE247:EMB_RAG_ANSWER_PROMPT"],
                        inputs={
                            "final_documents": {format_final_docs_fn: "documents_text"},
                            "question": {INPUT: "enhanced_query"},
                            "memory_context": INPUT,
                            "conversation": INPUT,
                            "docs": {format_retrieved_docs_fn: "ids"}
                        },
                        outputs={"content": {OUTPUT: "synthesize_content"}},
                        stream=True
                    )

                    ekyc_rag_answer = BasicChainNode(
                        name="ekyc_rag_answer",
                        resource_key="gpt-4o",
                        user_prompt=PROMPTS["BEE247:EKYC_RAG_ANSWER_PROMPT"],
                        inputs={
                            "final_documents": {format_final_docs_fn: "documents_text"},
                            "question": {INPUT: "enhanced_query"},
                            "memory_context": INPUT,
                            "conversation": INPUT,
                            "docs": {format_retrieved_docs_fn: "ids"}
                        },
                        outputs={"content": {OUTPUT: "synthesize_content"}},
                        stream=True
                    )

                    START >> [master_retriever, 
                            qa_retriever, 
                            gw_retriever, 
                            fee_retriever, 
                            promotion_retriever] >> format_retrieved_docs_fn
                    format_retrieved_docs_fn >> [cep_mapping_of_fn, 
                                                standard_rerank] >> format_final_docs_fn >> routing_template_flow
                    routing_template_flow >> [normal_rag_answer, 
                                            emb_rag_answer, 
                                            ekyc_rag_answer] >> END
                # endregion ===== standard stream response callback =====
            
                routing_card_flow = BranchNode(
                    name="routing_card_flow",
                    cases={
                        "card_ids != []": card_stream_response,
                    },
                    default=card_callback_standard_response,
                    inputs={
                        "card_ids": card_extract_keywords
                    }
                )
                                
                START >> card_extract_keywords >> routing_card_flow >> [card_stream_response, card_callback_standard_response] >> END

                
            # endregion ===== card =====
            
            post_process_card_response_fn = CodeNode(
                name="post_process_card_response_fn",
                code_fn=post_process_card_response,
                inputs={
                    "query": {rewrite_query: "enhanced_query"},
                    "synthesize_content": card_response,
                    "local_content": card_response
                },
                return_keys=["dialogue: Dict[str, List[Dict[str, str]]]", "output_card_response: str"],
            )
            
            card_add_session_memory = Mem0Node(
                name="card_add_session_memory",
                resource_key="mem0",
                operation=Mem0Operation.ADD,
                inputs={
                    "messages": {post_process_card_response_fn: "dialogue"},
                    "session_id": INPUT,
                    "custom_fact_extraction_prompt": PROMPTS["BEE247:CUSTOM_FACT_EXTRACTION_PROMPT"],
                }
            )

                    
      

            # region ===== location =====
            with GraphNode(
                name="location_response",
                description="streaming location response",
                inputs={
                    # "query": rewrite_query, 
                    "topic": topic_classifier, 
                    "memory_context": postprocess_mem0_results_fn, 
                    "enhanced_query": rewrite_query, 
                    "conversation": rewrite_query
                }
            ) as location_response:
                get_location_doc_id_fn = CodeNode(
                    name="get_location_doc_id_fn",
                    code_fn=get_location_doc_id,
                    inputs={"topic_category": {topic_classifier: "topic"}},
                    return_keys=["location_doc_id: Optional[str]", "prompt_key: Optional[str]"]
                )

                create_location_mongo_query_fn = CodeNode(
                    name="create_location_mongo_query_fn",
                    code_fn=create_location_mongo_query,
                    inputs={
                        "location_doc_id": {get_location_doc_id_fn: "location_doc_id"},
                    },
                    return_keys=["query: Dict[str, Any]"]
                )

                get_location_data_from_mongo = MongoNode(
                    name="get_location_data_from_mongo",
                    resource_key="aicenter-chatbot",
                    operation="find",
                    inputs={
                        "collection_name": "document_text",
                        "query": {create_location_mongo_query_fn: "query"},
                        "projection": {"text": 1, "updated_time": 1, "_id": 0}
                    }
                )

                check_location_cache_fn = CodeNode(
                    name="check_location_cache_fn",
                    code_fn=check_location_cache,
                    inputs={
                        "document_text_caching": self.DOCUMENT_TEXT_CACHING,
                        "doc_data": {get_location_data_from_mongo: "data"}
                    },
                    return_keys=["overwrite_document_text_caching: Dict[str, Any]"]
                )

                extract_location_terms = BasicChainNode(
                    name="extract_location_terms",
                    resource_key="gemini-2.5-flash-chat",
                    llm_configs= {"reasoning_effort": "none"},
                    user_prompt=PROMPTS["BEE247:DOCUMENT_TEXT_KEYWORD_EXTRACT_PROMPT"],
                    inputs={
                        "message": {INPUT: "enhanced_query"}
                    }
                )

                post_process_extracted_location_terms_fn = CodeNode(
                    name="post_process_extracted_location_terms_fn",
                    code_fn=post_process_extracted_location_terms,
                    inputs={
                        "keywords_text": {extract_location_terms: "content"}
                    },
                    return_keys=["keywords: List[str]"]
                )

                post_process_location_data_fn = CodeNode(
                    name="post_process_location_data_fn",
                    code_fn=post_process_location_data,
                    inputs={
                        "document_texts": {check_location_cache_fn: "overwrite_document_text_caching"},
                        "keywords": post_process_extracted_location_terms_fn
                    },
                    return_keys=["doc_data: str"]
                )

                branch_loc_data = BranchNode(
                    name="check_no_loc_data",
                    cases={
                        "doc_data and location_doc_id == 'atm'": "atm_response",
                        "doc_data and location_doc_id != 'atm'": "loc_response"
                    },
                    default="no_loc_response",
                    inputs={
                        "doc_data": post_process_location_data_fn,
                        "location_doc_id": {get_location_doc_id_fn: "location_doc_id"}
                    }
                )
                
                no_loc_response = LLMNode(
                    name="no_loc_response",
                    resource_key="fake",
                    instant_response=True,
                    inputs={"response": "Xin lỗi, tôi không tìm thấy thông tin về địa điểm bạn yêu cầu."},
                    outputs={"content": OUTPUT},
                    stream=True
                )

                loc_response = BasicChainNode(
                    name="loc_response",
                    resource_key="gpt-4o",
                    user_prompt=PROMPTS["BEE247:DOCUMENT_TEXT_PROMPT"],
                    inputs={
                        "question": {INPUT: "enhanced_query"},
                        "document_text": {post_process_location_data_fn: "doc_data"},
                        "memory_context": INPUT,
                        "conversation": INPUT,
                    },
                    outputs={"content": OUTPUT},
                    stream=True,
                )
                atm_response = BasicChainNode(
                    name="atm_response",
                    resource_key="gpt-4o",
                    user_prompt=PROMPTS["BEE247:ATM_TEXT_PROMPT"],
                    inputs={
                        "question": {INPUT: "enhanced_query"},
                        "document_text": {post_process_location_data_fn: "doc_data"},
                        "memory_context": INPUT,
                        "conversation": INPUT,
                    },
                    outputs={"content": OUTPUT},
                    stream=True,
                )

                START >> [get_location_doc_id_fn, extract_location_terms]
                get_location_doc_id_fn >> create_location_mongo_query_fn >> get_location_data_from_mongo >> check_location_cache_fn
                extract_location_terms >> post_process_extracted_location_terms_fn
                [check_location_cache_fn, post_process_extracted_location_terms_fn] >> post_process_location_data_fn >> branch_loc_data
                branch_loc_data >> [atm_response, loc_response, no_loc_response] >> END
            # endregion ===== location =====

            post_process_location_response_fn = CodeNode(
                name="post_process_location_response_fn",
                code_fn=post_process_location_response,
                inputs={
                    "query": {rewrite_query: "enhanced_query"},
                    "content": location_response,
                },
                return_keys=["dialogue: Dict[str, List[Dict[str, str]]]", "output_location_response: str"]
            )
            
            location_add_session_memory = Mem0Node(
                name="location_add_session_memory",
                resource_key="mem0",
                operation=Mem0Operation.ADD,
                inputs={
                    "messages": {post_process_location_response_fn: "dialogue"},
                    "session_id": INPUT,
                    "custom_fact_extraction_prompt": PROMPTS["BEE247:CUSTOM_FACT_EXTRACTION_PROMPT"],
                }
            )


            code_merge_node_response = CodeNode(
                name="code_merge_node_response",
                code_fn=merge_node,
                inputs={
                    "output_card_response": post_process_card_response_fn,
                    "output_location_response": post_process_location_response_fn,
                    "output_standard_response": post_process_standard_response_fn,
                },
                return_keys=["output_response: str"],
            )

            select_prompt_topic_standard = CodeNode(
                name= "select_prompt_topic_standard",
                code_fn= get_topic_prompt,
                inputs={
                    "topic": "standard",
                },
                return_keys=["template: str"]
            )
        
            llm_classify_issue_standard= BasicChainNode(
                name="llm_classify_issue_standard",
                resource_key="gemini-2.5-flash-chat",
                llm_configs= {"reasoning_effort": "none"},
                parser="json",
                user_prompt= PROMPTS["BEE247:CLASSIFY_TOPIC_ISSUE"],
                inputs={
                    "template": select_prompt_topic_standard,
                    "question": {rewrite_query: "enhanced_query"},
                },
                extract_schema=["classifications: List[dict]"],
            )

            code_process_classifications = CodeNode(
                name="code_process_classifications",
                code_fn=process_multiple_classifications,
                inputs={
                    "classifications": {llm_classify_issue_standard: "classifications"},
                    "question": {rewrite_query: "enhanced_query"},
                    "output_response": code_merge_node_response,
                },
                return_keys=["processed_items: List[dict]"],  # Mỗi item có {topic, issue, query}
            )

            # region ===== log isues iteration =====
            with ForLoopNode(
                name="logging_issues",
                inputs={
                    "batch_data": {code_process_classifications: "processed_items"},
                },
            ) as forloop_logging_issues:

                # region ================= issues report =====================

                with GraphNode(
                    name="graph_issues_log",
                    description="card logging question with issue",
                    inputs={
                        "question": INPUT,
                        "output_response": INPUT,
                        "topic": INPUT,
                        "issue": INPUT,
                        "query": INPUT,
                    }
                ) as graph_issues_log:

                    embedding_question = EmbeddingNode(
                        name="embedding_question",
                        resource_key="bge-m3",
                        inputs={"texts": INPUT["question"]}
                    )

                    milvus_search_issue = MilvusNode(
                        name="milvus_search_issue",
                        resource_key="chatbot-libra",
                        operation="search",
                        inputs={
                            "query_vectors": embedding_question["embeddings"],
                            "output_fields": ['chunk_id', 'question'],
                            "partition_names": ["issues_log"],
                            "top_k": 1,
                            "threshold": 0,
                            "collection_name": f"{transform_bot_id(self.bot_id)}_ISSUES",
                            "expr":  {INPUT: "query"},
                        }
                    )

                    code_collect_milvus_chunk_id = CodeNode(
                        name="code_collect_milvus_chunk_id",
                        code_fn=extract_single_chunk_id,
                        inputs={"milvus_chunks": milvus_search_issue["results"]},
                        return_keys=["chunk_id: List[str]", "question: str"]
                    )

                    llm_check_relevant_question = BasicChainNode(
                        name="llm_check_relevant_question",
                        resource_key="gpt-5.1-chat",
                        llm_configs= {"reasoning_effort": "none"},
                        user_prompt= PROMPTS["BEE247:CHECK_RELEVANT_QUESTION"],
                        inputs={
                            "main_question": {code_collect_milvus_chunk_id: "question"},
                            "new_question": {INPUT: "question"},
                        },
                    )

                    branch_logger_issues= BranchNode(
                        name="branch_logger_issues",
                        cases={
                            "'yes' in content": "graph_update_log_issues",
                        },
                        default= "graph_insert_new_question",
                        inputs= {
                            "content": llm_check_relevant_question,
                        }
                    )

                    # region ============== insert new issue ===============
                    with GraphNode(
                        name="graph_insert_new_question",
                        description="insert new question to mongo and milvus",
                        inputs={
                            "question": INPUT,
                            "topic": INPUT,
                            "issue": INPUT,
                            "output_response": INPUT,
                            "embeddings": embedding_question
                        }
                    ) as graph_insert_new_question:                        
                        
                        # 1. Prepare insert data
                        code_preprocess_data_milvus = CodeNode(
                            name="code_preprocess_data_milvus",
                            code_fn=prepare_insert_milvus,
                            inputs={
                                "embeddings": INPUT,
                                "topic": INPUT,
                                "issue": INPUT,
                                "question": INPUT,
                            },
                            return_keys=["data_milvus: Any", "chunk_id: Any"]
                        )
                        
                        # 2. Insert to Milvus
                        milvus_insert_issues_log = MilvusNode(
                            name="milvus_insert_issues_log",
                            resource_key="chatbot-libra",
                            operation="insert",
                            inputs={
                                "data": code_preprocess_data_milvus["data_milvus"],
                                "collection_name": f"{transform_bot_id(self.bot_id)}_ISSUES",
                                "partition_name": "issues_log",
                            }
                        )
                        

                        # insert to postgreSQL
                        code_prepare_insert_postgre = CodeNode(
                            name="code_prepare_insert_postgre",
                            code_fn= prepare_insert_postgre,
                            inputs={
                                "issue": INPUT,
                                "question": INPUT,
                                "output_response": INPUT,
                                "topic": INPUT,
                                "chunk_id": code_preprocess_data_milvus["chunk_id"],
                            },
                            return_keys=["query: str", "params: Any"]
                        )

                        sql_insert_issues_postgre = SQLNode(
                            name="sql_insert_issues_postgre",
                            resource_key="anapp",               
                            operation=SQLOperation.EXECUTE,
                            inputs={
                                "query": code_prepare_insert_postgre,
                                "params": code_prepare_insert_postgre,           
                            },
                            outputs=OUTPUT
                        )


                        START >> code_preprocess_data_milvus >> [milvus_insert_issues_log,
                                                                code_prepare_insert_postgre] >> END
                        
                        milvus_insert_issues_log >> END
                        code_prepare_insert_postgre >> sql_insert_issues_postgre >> END
                    
                    # endregion ============== insert new issue ===============
                    
                    # region ============== update issue ===============
                    with GraphNode(
                        name="graph_update_log_issues",
                        description="insert old question to mongo",
                        inputs={
                            "chunk_id": code_collect_milvus_chunk_id,
                        }
                    ) as graph_update_log_issues:
                        
                        code_prepare_query_postgre = CodeNode(
                            name="code_prepare_query_postgre",
                            code_fn= prepare_query_postgre,
                            inputs={
                                "chunk_id": INPUT,
                            },
                            return_keys=["query: str", "params: tuple"]
                        )
                        
                        sql_query_issues_postgre = SQLNode(
                            name="sql_query_issues_postgre",
                            resource_key="anapp",               
                            operation=SQLOperation.QUERY,
                            inputs={
                                "query": code_prepare_query_postgre,
                                "params": code_prepare_query_postgre,           
                            },
                        )
                        
                        code_prepare_update_question = CodeNode(
                            name= "code_prepare_update_question",
                            code_fn= prepare_update_or_insert_relevant,
                            inputs= {
                                "data": sql_query_issues_postgre,
                            },
                            return_keys=["query: str", "params: tuple"]
                        )

                        sql_excuse_issues_postgre = SQLNode(
                            name="sql_excuse_issues_postgre",
                            resource_key="anapp",               
                            operation=SQLOperation.EXECUTE,
                            inputs={
                                "query": code_prepare_update_question,
                                "params": code_prepare_update_question,           
                            },
                        )

                        START >> code_prepare_query_postgre >> sql_query_issues_postgre >> code_prepare_update_question >> sql_excuse_issues_postgre >> END
                    # endregion ============== update issue ===============


                    START >> embedding_question >>  milvus_search_issue >> code_collect_milvus_chunk_id >> llm_check_relevant_question >> branch_logger_issues >> [ graph_update_log_issues,
                                                                                                                                                                    graph_insert_new_question] >> END
                # endregion ================ issues report ========================


                START >> graph_issues_log >> END
            # endregion ===== log isues iterationn =====

                    
            
            # region ================= issues report cached =====================

            with GraphNode(
                name="graph_issues_log_cached",
                description="logging question with issue",
                inputs={
                    "question": {rewrite_query: "query"},
                    "output_response": post_process_stream_cached_qa_answer_fn,
                    "ids": qa_cached,
                }
            ) as graph_issues_log_cached:
                
                code_create_get_qa_mongo_query = CodeNode(
                    name="code_create_get_qa_mongo_query",
                    code_fn=create_get_qa_mongo_query,
                    inputs={
                        "ids": INPUT,
                    },
                    return_keys=["query: Dict[str, Any]"]
                )
                
                mongo_get_qa = MongoNode(
                    name="mongo_get_qa",
                    resource_key="aicenter-chatbot",
                    operation="find",
                    inputs={
                        "collection_name": "dialogue",
                        "query": {code_create_get_qa_mongo_query: "query"},
                        "projection": {"tags": 1}
                    }
                )

                code_create_get_document_mongo_query = CodeNode(
                    name="code_create_get_document_mongo_query",
                    code_fn=create_get_document_mongo_query,
                    inputs={
                        "data": mongo_get_qa,
                    },
                    return_keys=["query: Dict[str, Any]"]
                )

                mongo_get_topic_id = MongoNode(
                    name="mongo_get_topic_id",
                    resource_key="aicenter-chatbot",
                    operation="find",
                    inputs={
                        "collection_name": "documents",
                        "query": {code_create_get_document_mongo_query: "query"},
                        "projection": {"category_id": 1}
                    }
                )

                code_create_get_topic_mongo_query = CodeNode(
                    name="code_create_get_topic_mongo_query",
                    code_fn=create_get_topic_mongo_query,
                    inputs={
                        "data": mongo_get_topic_id,
                    },
                    return_keys=["query: Dict[str, Any]"]
                )

                mongo_get_topic_name = MongoNode(
                    name="mongo_get_topic_name",
                    resource_key="aicenter-chatbot",
                    operation="find",
                    inputs={
                        "collection_name": "category",
                        "query": {code_create_get_topic_mongo_query: "query"},
                        "projection": {"name": 1}
                    }
                )

                code_postprocess_topic = CodeNode(
                    name="code_postprocess_topic",
                    code_fn=postprocess_topic,
                    inputs={
                        "data": mongo_get_topic_name,
                    },
                    return_keys=["topic: str"]
                )
                
                select_prompt_topic = CodeNode(
                    name= "select_prompt_topic",
                    code_fn= get_topic_prompt,
                    inputs={
                        "topic": code_postprocess_topic
                    },
                    return_keys=["template: str"]
                )
            
                llm_classify_issue= BasicChainNode(
                    name="llm_classify_issue",
                    resource_key="gemini-2.5-flash-chat",
                    llm_configs= {"reasoning_effort": "none"},
                    parser="yaml",
                    user_prompt= PROMPTS["BEE247:ISSUES_CLASSIFY"],
                    inputs={
                        "template": select_prompt_topic,
                        "question": INPUT,
                    },
                    extract_schema=["topic: str" , "issue: str"],
                )

                code_create_query_topic_milvus = CodeNode(
                    name= "code_create_query_topic_milvus",
                    code_fn= create_topic_query,
                    inputs= {
                        "topic": {llm_classify_issue: "topic"},
                    },
                    return_keys= ["query: str"],
                )

                embedding_question = EmbeddingNode(
                    name="embedding_question",
                    resource_key="bge-m3",
                    inputs={"texts": {INPUT: "question"}}
                )

                milvus_search_issue = MilvusNode(
                    name="milvus_search_issue",
                    resource_key="chatbot-libra",
                    operation="search",
                    inputs={
                        "query_vectors": embedding_question["embeddings"],
                        "output_fields": ['chunk_id', 'question'],
                        "partition_names": ["issues_log"],
                        "top_k": 1,
                        "threshold": 0,
                        "collection_name": f"{transform_bot_id(self.bot_id)}_ISSUES",
                        "expr": {code_create_query_topic_milvus: "query"}
                    }
                )

                code_collect_milvus_chunk_id = CodeNode(
                    name="code_collect_milvus_chunk_id",
                    code_fn=extract_single_chunk_id,
                    inputs={"milvus_chunks": milvus_search_issue["results"]},
                    return_keys=["chunk_id: List[str]", "question: str"]
                )

                llm_check_relevant_question = BasicChainNode(
                    name="llm_check_relevant_question",
                    resource_key="gpt-5.1-chat",
                    llm_configs= {"reasoning_effort": "none"},
                    user_prompt= PROMPTS["BEE247:CHECK_RELEVANT_QUESTION"],
                    inputs={
                        "main_question": {code_collect_milvus_chunk_id: "question"},
                        "new_question": {INPUT: "question"},
                    },
                )

                branch_logger_issues= BranchNode(
                    name="branch_logger_issues",
                    cases={
                        "'yes' in content": "graph_update_log_issues",
                    },
                    default= "graph_insert_new_question",
                    inputs= {
                        "content": llm_check_relevant_question,
                    }
                )

                # region ============== insert new issue ===============
                with GraphNode(
                    name="graph_insert_new_question",
                    description="insert new question to mongo and milvus",
                    inputs={
                        "question": INPUT,
                        "topic": llm_classify_issue,
                        "issue": llm_classify_issue,
                        "output_response": INPUT,
                        "embeddings": embedding_question,
                    }
                ) as graph_insert_new_question:       

                    # 1. Prepare insert data
                    code_preprocess_data_milvus = CodeNode(
                        name="code_preprocess_data_milvus",
                        code_fn=prepare_insert_milvus,
                        inputs={
                            "embeddings": INPUT,
                            "topic": INPUT,
                            "issue": INPUT,
                            "question": INPUT,
                        },
                        return_keys=["data_milvus: Any", "chunk_id: Any"]
                    )
                    
                    # 2. Insert to Milvus
                    milvus_insert_issues_log = MilvusNode(
                        name="milvus_insert_issues_log",
                        resource_key="chatbot-libra",
                        operation="insert",
                        inputs={
                            "data": {code_preprocess_data_milvus: "data_milvus"},
                            "collection_name": f"{transform_bot_id(self.bot_id)}_ISSUES",
                            "partition_name": "issues_log",
                        }
                    )
                    

                    # insert to postgreSQL
                    code_prepare_insert_postgre = CodeNode(
                        name="code_prepare_insert_postgre",
                        code_fn= prepare_insert_postgre,
                        inputs={
                            "issue": INPUT,
                            "question": INPUT,
                            "output_response": INPUT,
                            "topic": INPUT,
                            "chunk_id": {code_preprocess_data_milvus: "chunk_id"}
                        },
                        return_keys=["query: str", "params: Any"]
                    )

                    sql_insert_issues_postgre = SQLNode(
                        name="sql_insert_issues_postgre",
                        resource_key="anapp",               
                        operation=SQLOperation.EXECUTE,
                        inputs={
                            "query": code_prepare_insert_postgre,
                            "params": code_prepare_insert_postgre,           
                        },
                        outputs=OUTPUT
                    )


                    START >>  code_preprocess_data_milvus >> [  milvus_insert_issues_log,
                                                                code_prepare_insert_postgre] >> END
                    
                    milvus_insert_issues_log >> END
                    code_prepare_insert_postgre >> sql_insert_issues_postgre >> END
                
                # endregion ============== insert new issue ===============
                
                # region ============== update issue ===============
                with GraphNode(
                    name="graph_update_log_issues",
                    description="insert old question to mongo",
                    inputs={
                        "chunk_id": code_collect_milvus_chunk_id,
                    }
                ) as graph_update_log_issues:
                    
                    code_prepare_query_postgre = CodeNode(
                        name="code_prepare_query_postgre",
                        code_fn= prepare_query_postgre,
                        inputs={
                            "chunk_id": INPUT,
                        },
                        return_keys=["query: str", "params: tuple"]
                    )
                    
                    sql_query_issues_postgre = SQLNode(
                        name="sql_query_issues_postgre",
                        resource_key="anapp",               
                        operation=SQLOperation.QUERY,
                        inputs={
                            "query": code_prepare_query_postgre,
                            "params": code_prepare_query_postgre,           
                        },
                    )
                    
                    code_prepare_update_question = CodeNode(
                        name= "code_prepare_update_question",
                        code_fn= prepare_update_or_insert_relevant,
                        inputs= {
                            "data": sql_query_issues_postgre,
                        },
                        return_keys=["query: str", "params: tuple"]
                    )

                    sql_excuse_issues_postgre = SQLNode(
                        name="sql_excuse_issues_postgre",
                        resource_key="anapp",               
                        operation=SQLOperation.EXECUTE,
                        inputs={
                            "query": code_prepare_update_question,
                            "params": code_prepare_update_question,           
                        },
                    )

                    START >> code_prepare_query_postgre >> sql_query_issues_postgre >> code_prepare_update_question >> sql_excuse_issues_postgre >> END
                # endregion ============== update issue ===============

                
                START >> code_create_get_qa_mongo_query >> mongo_get_qa >> code_create_get_document_mongo_query >> mongo_get_topic_id >> code_create_get_topic_mongo_query >> mongo_get_topic_name 

                mongo_get_topic_name >> code_postprocess_topic >> select_prompt_topic >> llm_classify_issue >> code_create_query_topic_milvus >> embedding_question
                embedding_question >> milvus_search_issue >> code_collect_milvus_chunk_id >> llm_check_relevant_question >> branch_logger_issues >> [  graph_update_log_issues,
                                                                                                                                                    graph_insert_new_question] >> END               
            # endregion ================ issues report ========================


            START >> rewrite_query >> [qa_cached, topic_classifier, llm_check_intent_khcn_khdn] >> routing_qa_flow >> [stream_cached_qa_answer, routing_ask_back]
            
            stream_cached_qa_answer >> post_process_stream_cached_qa_answer_fn  >> graph_issues_log_cached >> cached_qa_add_session_memory >> END 
            
            routing_ask_back >> [llm_ask_back_khcn_khdn, search_session_memory]
            llm_ask_back_khcn_khdn >> END

            search_session_memory >> postprocess_mem0_results_fn >> routing_main_flow >> [standard_response, card_response, location_response]
            
            standard_response >> post_process_standard_response_fn >> standard_add_session_memory >> END
            
            card_response >> post_process_card_response_fn >> card_add_session_memory >> END
            
            location_response >> post_process_location_response_fn >> location_add_session_memory >> END

            [post_process_standard_response_fn,
             post_process_card_response_fn,
            post_process_location_response_fn] >> code_merge_node_response >> select_prompt_topic_standard >> llm_classify_issue_standard >> code_process_classifications >> forloop_logging_issues >> END

                                                                        

        bee247.compile()
        self.workflow = bee247

    async def run(
        self,
        messages: List[Dict],
        session_id: str,
        client_message_id: str,
        role_ids: List,
        username: str,
        **kwargs
    ):
        """Main pipeline with updated logic flow."""
        try:
            asyncio.create_task(self.workflow.run(
                request_id=client_message_id,
                inputs={
                    "messages": messages,
                    "session_id": session_id,
                    "role_ids": role_ids
                },
                user_id=username
            ))
            async for channel_name in STREAM_SERVICE.get_channels(client_message_id):
                async for chunk in STREAM_SERVICE.get(client_message_id, channel_name, json_mode=False):
                    yield chunk
        except Exception as e:
            import traceback
            LOGGER.error(traceback.format_exc(e))
            default_answers = 'Xin lỗi, đã xảy ra lỗi khi xử lý yêu cầu của bạn. Vui lòng thử lại sau.'
            yield fake_chunk_from(
                content=default_answers,
                model="error"
            )                  

async def main():
    bot = Bee247Bot(bot_id="cbc75713-2646-4331-84ad-645664ab86ef")

    dialogue_id = "70415394-bd0b-41c6-ba06-7719a356bf0f"
    username = "dev-bee247"
    
    import uuid
    client_message_id = str(uuid.uuid4())
    
    async for chunk in bot.run(
        messages=[
            {"role": "user", "content": "Khách hàng Cá nhân (KHCN) có được phép nộp thêm tiền vào sổ Tiết kiệm số tích lũy không, các loại tiền gửi áp dụng cho Tiết kiệm số tích lũy là gì, và quy định về mức nộp thêm tối thiểu, tối đa cho Tiết kiệm số tích lũy?"}],
        session_id = dialogue_id,
        client_message_id=client_message_id,
        role_ids=["QM"],
        username=username
    ):
        print(f"{chunk.choices[0].delta.content or ''}", end= "")

    await asyncio.sleep(4)


if __name__ == "__main__":
    asyncio.run(main())
