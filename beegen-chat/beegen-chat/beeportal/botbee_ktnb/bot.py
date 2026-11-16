import os
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime
from dotenv import load_dotenv

from beeportal.utils import PROMPTS, annotate_query, format_retrieved_documents, get_intent_retriever, init_query, post_process_mem0_search_results, post_process_response
from beeflow.nodes import END, INPUT, START, OUTPUT, LLMNode, ForLoopNode
from beeflow.nodes.flow.branch_node import BranchNode
from beeflow.nodes.graph.graph_node import GraphNode
from beeflow.nodes.primitives.ai.rerank_node import RerankNode
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beeflow.nodes.templates.basic_chain_node import BasicChainNode
from beeflow.nodes.templates.retriever_node_v2 import RetrieverNode
from beeflow.nodes.primitives.memory.mem0_node import Mem0Node
from beeflow.workflow import WorkflowEngine
from beeflow.utils.streaming import STREAM_SERVICE
from beegen.loggings.loggers import LOGGER
from beegen.registry.resource_hub import ResourceHub
from beegen.configs.memory.mem0_config import Mem0Operation
from beegen.utils.common import fake_chunk_from, transform_bot_id

from beeportal.botbee_ktnb.beektnb.summary_processor import prepare_paths_batch_data

from beeportal.botbee_ktnb.beektnb.ultis import (
    get_history_chat,
    get_special_task_data,
    format_summary_data,
    prepare_system_prompt,
    format_final_documents
)
from beeportal.botbee_ktnb.beektnb.constant import list_category


load_dotenv()


class KTNBBot:
    def __init__(self, bot_id: str):
        self.bot_id = bot_id
        mongo_engine = ResourceHub.self().sync_mongo("aicenter-chatbot")
        result = mongo_engine._find_one(collection_name="botinfo", query={"_id": self.bot_id})
        self.name = result.get('data', {'name': {}}).get('name', None)
        self.config = result.get('data', {'metadata': {}}).get('metadata', {})
        self.definition = self.config.get('system_prompt', "không có mô tả nào được cung cấp")
        self.flag_advise_detect = False
        self.character_ask_human = "[?]"
        
        self._build_flow()

    def _build_flow(self):
        # region === workflow engine ===
        with WorkflowEngine(
            name="wf_ktnb_chatbot_bee",
            description="Chatbot KTNB main workflow",
        ) as wf_ktnb_chatbot_bee:
            
            # region ===== summarize context =====

            with GraphNode(
                name="graph_summarize_context",
                description="context summarization flow",
                inputs={
                    "query": INPUT,
                    "paths": INPUT,
                    "keycloak_token": INPUT
                }
            ) as graph_summarize_context:
                with GraphNode(
                    name="graph_summarize_path",
                    description="Summarize path flow",
                    inputs={
                        "paths": INPUT,
                        "keycloak_token": INPUT
                    }
                ) as graph_summarize_path:
                    llm_notify_message_for_summarize_path = LLMNode(
                        name="llm_notify_message_for_summarize_path",
                        resource_key="fake",
                        instant_response=True,
                        inputs={"response": "BotKTNB đang chuẩn bị bản tóm tắt, bạn vui lòng đợi trong giây lát.\n"},
                        outputs={"content": OUTPUT},
                        stream=True
                    )

                    with GraphNode(
                        name="graph_process_documents",
                        description="Batch process document",
                        inputs={
                            "paths": INPUT,
                            "keycloak_token": INPUT
                        }
                    ) as graph_process_documents:
                            
                        code_prepare_document = CodeNode(
                            name="code_prepare_document",
                            code_fn=prepare_paths_batch_data,
                            inputs={
                                "paths": INPUT,
                                "capacity_tokens": 8000,
                                "keycloak_token": INPUT
                            },
                            return_keys=["batch_data: dict"]
                        )

                        with ForLoopNode(
                            name="for_each_summary",
                            inputs={"batch_data": code_prepare_document},  # Takes list of items
                        ) as for_each_summary:
                            
                            llm_summarize_paths_document = BasicChainNode(
                                name="llm_summarize_paths_document",
                                resource_key="gpt-4o",
                                user_prompt=PROMPTS["BEEKTNB:SUMMARY_DOCUMENT_PROMPT_FLOW"],
                                inputs=INPUT,
                                outputs={"content": OUTPUT},
                            )

                            START >> llm_summarize_paths_document >> END

                        for_each_summary.build()

                        code_format_summary_data = CodeNode(
                            name="code_format_summary_data",
                            code_fn=format_summary_data,
                            inputs={
                                "batch_summarized_data": for_each_summary
                            },
                            return_keys=["format_doc: str"]
                        )

                        START >> code_prepare_document >> for_each_summary >> code_format_summary_data >> END

                    with ForLoopNode(
                        name="for_each_generator",
                        inputs={"chunks": {graph_process_documents: "batch_path_result"}},  # Takes list of items
                    ) as for_each_generator:
                        
                        llm_generator_chunk = LLMNode(
                            name="llm_generator_chunk",
                            resource_key="fake",
                            instant_response=True,
                            inputs=INPUT,
                            stream=True
                        )

                        START >> llm_generator_chunk >> END

                    for_each_generator.build()

                    START >> llm_notify_message_for_summarize_path >> graph_process_documents >> for_each_generator >> END

                with GraphNode(
                    name="graph_summarize_query",
                    description="Summarize query",
                    inputs={
                        "query": INPUT
                    }
                ) as graph_summarize_query:
                    llm_notify_message_for_origin_query = LLMNode(
                        name="llm_notify_message_for_origin_query",
                        resource_key="fake",
                        instant_response=True,
                        inputs={"response": "BotKTNB đang chuẩn bị bản tóm tắt, bạn vui lòng đợi trong giây lát.\n"},
                        outputs={"content": OUTPUT},
                        stream=True
                    )

                    llm_summarize_paths_document = BasicChainNode(
                        name="llm_summarize_paths_document",
                        resource_key="gpt-4o",
                        user_prompt=PROMPTS["BEEKTNB:SUMMARY_DOCUMENT_PROMPT_FLOW"],
                        inputs={
                            "document": {INPUT: "query"},
                        },
                        outputs={"content": OUTPUT},
                    )

                    llm_generator_chunk_origin_query = LLMNode(
                        name="llm_generator_chunk_origin_query",
                        resource_key="fake",
                        instant_response=True,
                        inputs=llm_summarize_paths_document,
                        outputs={"content": OUTPUT},
                        stream=True
                    )

                    START >> llm_notify_message_for_origin_query >> llm_summarize_paths_document >> llm_generator_chunk_origin_query >> END

                branch_check_path_exists = BranchNode(
                    name="branch_check_path_exists",
                    cases={
                        "paths and len(paths) > 0" : graph_summarize_path
                    },
                    default=graph_summarize_query,
                    inputs={"paths": INPUT}
                )

                START >> branch_check_path_exists >> [graph_summarize_query, graph_summarize_path] 
                graph_summarize_query >> END
                graph_summarize_path >> END

            # end region === summarize context ===


            # region === main chat ===
        
            with GraphNode(
                name="graph_main_default_chat",
                description="Main chat flow",
                inputs={
                    "query": INPUT,
                    "messages": INPUT,
                    "role_ids": INPUT
                }
            ) as graph_main_default_chat:
                    
                with GraphNode(
                    name="graph_preprocessing_main_chat",
                    description="Preprocessing query",
                    inputs={
                        "query": INPUT,
                        "messages": INPUT,
                    }
                ) as graph_preprocessing_main_chat:
                
                    llm_classify_intent = BasicChainNode(
                        name="llm_classify_intent",
                        resource_key="gpt-4o",
                        user_prompt=PROMPTS["BEEKTNB:CLASSIFY_INTENT"],
                        extract_schema=["task1: str", "task2: str", "task3: str"],
                        inputs={"query": INPUT},
                        outputs=OUTPUT,
                        parser="xml",
                    )

                    with GraphNode(
                        name="graph_rewrite_follow_up_query_new_chat",
                        description="Rewrite query with history context in new chat",
                        inputs={
                            "messages": INPUT,
                        },
                         outputs={  # 👈 ADD THIS LINE
                            "follow_up_rewrite_query": OUTPUT
                        }
                    ) as graph_rewrite_follow_up_query_new_chat:
                        
                        code_history_messages = CodeNode(
                            name="code_history_messages",
                            code_fn=get_history_chat,
                            inputs={
                                "hist_messages": {INPUT: "messages"}
                            },
                            return_keys=["query: str", "history_messages: List"],
                        )

                        llm_rewrite_follow_up_query = BasicChainNode(
                            name="llm_rewrite_follow_up_query",
                            resource_key="gpt-4o",
                            user_prompt=PROMPTS["BEEKTNB:REWRITE_FOLLOW_UP_QUERY"],
                            extract_schema=["is_follow_up: bool", "rewrite: str"],
                            inputs={
                                "query": {code_history_messages: "query"},
                                "conversation": {code_history_messages: "history_messages"}
                            },
                            outputs={
                                "is_follow_up": OUTPUT,
                                "rewrite": {OUTPUT: "follow_up_rewrite_query"}
                            },
                            parser="xml",
                        )

                        START >> code_history_messages >> llm_rewrite_follow_up_query >> END

                    START >> [llm_classify_intent, graph_rewrite_follow_up_query_new_chat] >> END

                llm_chit_chat_new_chat = BasicChainNode(
                    name="llm_chit_chat_new_chat",
                    resource_key="gpt-4o",
                    user_prompt=PROMPTS["BEEKTNB:CHIT_CHAT_PROMPT"],
                    inputs={
                        "definition": self.definition,
                    },
                    stream=True
                )

                with GraphNode(
                    name="graph_special_chat_new_chat",
                    description="Special case chat",
                    inputs={
                        "query_task": {graph_preprocessing_main_chat: "task2"}
                    }
                ) as graph_special_chat_new_chat:
                    code_get_special_task = CodeNode(
                        name="code_get_special_task",
                        code_fn=get_special_task_data,
                        inputs={"query_task": INPUT},
                        return_keys={"task: str"}
                    )

                    llm_special_chat = BasicChainNode(
                        name="llm_special_chat",
                        resource_key="gpt-4o",
                        user_prompt=PROMPTS["BEEKTNB:NON_CHIT_CHAT_ILLEGAL"],
                        inputs={
                            "definition": self.definition,
                            "task": code_get_special_task
                        },
                        stream=True
                    )

                    START >> code_get_special_task >> llm_special_chat >> END

                with GraphNode(
                    name="graph_rag_pipeline",
                    description="RAG pipeline",
                    inputs={
                        "role_ids": INPUT,
                        "query": {graph_preprocessing_main_chat: "follow_up_rewrite_query"},
                    }
                ) as graph_rag_pipeline:
                    

                    with GraphNode(
                        name="document_retrieval_pipeline",
                        description="Document retrieval pipeline",
                        inputs={
                            "role_ids": INPUT,
                            "query": INPUT,
                        }
                    ) as document_retrieval_pipeline:

                        retrieve_documents = RetrieverNode(
                            name = "retrieve_documents",
                            use_rerank = False,
                            inputs={
                                "query": INPUT,
                                "collection": transform_bot_id(self.bot_id),
                                "partition_names": ["document"],
                                "threshold": 0.55,
                                "top_k": 30,
                                "output_fields": ["chunk_id"],
                                "allowed_roles": {INPUT: "role_ids"},
                                "bot_id": self.bot_id,
                            },
                        )

                        rerank_documents = RerankNode(
                            name="rerank_documents",
                            resource_key="bge-m3",
                            inputs={
                                "query": INPUT,
                                "documents": retrieve_documents["docs"],
                                "top_k": -1,
                                "threshold": 0.15  # Only docs with score > 0.15
                            }
                        )

                        code_final_format_documents = CodeNode(
                            name="code_final_format_documents",
                            code_fn=format_final_documents,
                            inputs={
                                "retrieval_documents": {retrieve_documents: "docs"},
                                "rerank_documents": {rerank_documents: "reranks"},
                                "final_top_k": 30
                            },
                            return_keys=["final_documents: list"],
                            outputs=OUTPUT
                        )

                        START >> retrieve_documents >> rerank_documents >> code_final_format_documents >> END

                    
                    retrieve_qa = RetrieverNode(
                        name="retrieve_qa",
                        inputs={
                            "query": INPUT,
                            "collection": transform_bot_id(self.bot_id),
                            "partition_names": ["QA"],
                            "threshold": 0.9,
                            "top_k": 3,
                            "use_rerank": True,
                            "rerank_top_k": 1,
                            "output_fields": ["chunk_id"],
                            "allowed_roles": {INPUT: "role_ids"},
                            "bot_id": self.bot_id,
                        }
                    )
 
                    code_format_retrieval_documents = CodeNode(
                        name="code_format_retrieval_documents",
                        code_fn=format_retrieved_documents,
                        inputs={
                            "docs": {document_retrieval_pipeline: "final_documents"}, 
                            "qas": {retrieve_qa: "docs"}
                        },
                        return_keys=[
                            "cache_qa: Optional[str]", 
                            "doc: Optional[str]", 
                            "ids: Optional[List[Dict[str, Any]]]",
                            "qa_ids: Optional[List[Dict[str, Any]]]",
                            "doc_ids: Optional[List[Dict[str, Any]]]",
                        ]
                    )

                    code_prepare_system_prompt = CodeNode(
                        name="code_prepare_system_prompt",
                        code_fn=prepare_system_prompt,
                        inputs={
                            "query": {INPUT: "follow_up_rewrite_query"},
                            "datetime": datetime.now().strftime('%Y-%m-%d'),
                            "definition": self.definition,
                            "documents":  {code_format_retrieval_documents: "doc"},
                        },
                        return_keys=[
                            "prompt: str"
                        ]
                    )

                    llm_rag_chat = BasicChainNode(
                        name="llm_rag_chat",
                        resource_key="gpt-4.1",
                        user_prompt="{query}",
                        inputs={
                            "query": {code_prepare_system_prompt: "prompt"}
                        },
                        stream=True
                    )
                
                    START >> [document_retrieval_pipeline, retrieve_qa] >> code_format_retrieval_documents >> code_prepare_system_prompt >> llm_rag_chat >> END

                branch_check_chat_intent_new_chat = BranchNode(
                    name="branch_check_chat_intent_new_chat",
                    cases={
                        "task1 == 'chit_chat'": llm_chit_chat_new_chat,
                        "task2 is not None": graph_special_chat_new_chat,
                    },
                    default=graph_rag_pipeline,
                    inputs = {
                        "task1": {graph_preprocessing_main_chat: "task1"},
                        "task2": {graph_preprocessing_main_chat: "task2"}
                    },
                )
                        

                START >> graph_preprocessing_main_chat >> branch_check_chat_intent_new_chat
                branch_check_chat_intent_new_chat >> [llm_chit_chat_new_chat, graph_special_chat_new_chat, graph_rag_pipeline] 
                
                llm_chit_chat_new_chat >> END
                graph_special_chat_new_chat >> END
                graph_rag_pipeline >> END
            # end region ============ main chat =============
            
            # branch_type_chat_processor = BranchNode(
            #     name="type_chat_processor",
            #     cases={
            #         "type_chat == 'SUMMARY'": graph_summarize_context,
            #     },
            #     default=graph_main_default_chat,
            #     inputs={
            #         "type_chat": INPUT
            #     }
            # )

            # START >> branch_type_chat_processor >> [graph_summarize_context, graph_main_default_chat] 
            
            # graph_summarize_context >> END
            # graph_main_default_chat >> END

            START >> graph_main_default_chat >> END

        wf_ktnb_chatbot_bee.compile()
        self.workflow = wf_ktnb_chatbot_bee


        # end region ========== workflow engine ===========

    async def run(
        self,
        messages: List[Dict],
        session_id: str,
        request_id: str,
        user_id: str,
        role_ids: list = [],
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """Main pipeline with updated logic flow."""
        try:
            # keycloak_token = ""
            # if "keycloak_token" in kwargs and kwargs["keycloak_token"]:
            #     keycloak_token = kwargs["keycloak_token"]
            # else:
            #     raise ValueError("Keycloak token is not provide")

            if metadata is not None:
                paths = metadata.get("paths", [])
                type_chat = metadata.get("type", "DEFAULT")
            else:
                paths = []
                type_chat = "DEFAULT"

            asyncio.create_task(self.workflow.run(
                request_id=request_id,
                session_id=session_id,
                user_id=user_id,
                inputs={
                    "query": messages[-1]["content"],
                    "messages": messages,
                    "role_ids": role_ids,
                    # "keycloak_token": keycloak_token,
                    # "paths": paths,
                    # "type_chat": type_chat,
                },
            ))
            async for channel_name in STREAM_SERVICE.get_channels(request_id):
                async for chunk in STREAM_SERVICE.get(request_id, channel_name, json_mode=False):
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
    import uuid

    bot_id = "f359b089-6b2d-4c0a-8dfe-e85eca992a61"
    bot = KTNBBot(bot_id=bot_id)
    session_id = "be9678da-32fd-456e-a24f-bed6f0d56bc2"
    request_id = str(uuid.uuid4())
    user_id = "quanpvdjka"


    async for chunk in bot.run(
        messages=[
            {
                "content": "Bạn thống kê giúp tôi các phát hiện, tư vấn về cấp tín dụng cho người có liên quan theo luật các tổ chức tín dụng tại các chương kiểm toán báo cáo tài chính hoặc chương trình thẩm tra báo cáo tài chính",
                "role": "user"
            }
        ],
        metadata={},
        session_id=session_id,
        request_id=request_id,
        user_id=user_id,
        role_ids=["L1"]
    ):
        print(f"chunk: {chunk}")

    await asyncio.sleep(4)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())