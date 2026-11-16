import asyncio
from typing import Dict, List

from beeportal.utils import PROMPTS, annotate_query, format_retrieved_documents, get_intent_retriever, init_query, post_process_mem0_search_results, post_process_response
from beeflow.nodes.base_node import END, INPUT, START, OUTPUT
from beeflow.nodes.flow.branch_node import BranchNode
from beeflow.nodes.graph.graph_node import GraphNode
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


class BeeBot:
    def __init__(self, bot_id: str):
        self.bot_id = bot_id
        mongo_engine = ResourceHub.self().sync_mongo("aicenter-chatbot")
        result = mongo_engine._find_one(collection_name="botinfo", query={"_id": self.bot_id})
        self.name = result.get('data', {'name': {}}).get('name', None)
        self.config = result.get('data', {'metadata': {}}).get('metadata', {})
        
        self.definition = self.config.get('system_prompt', "không có mô tả nào được cung cấp")
        
        self._build_flow()
    
    def _build_flow(self):
        with WorkflowEngine(
            name="wf_chatbot_bee",
            description="Đây là luồng chat standard của tất cả bot"
        ) as wf_chatbot_bee:
            
            # region ===== rewrite query =====
            with GraphNode(
                name="graph_rewrite_query",
                description="luồng rewrite query",
                inputs={"messages": INPUT},
            ) as graph_rewrite_query:
                code_init_query = CodeNode(
                    name="code_init_query",
                    code_fn=init_query,
                    inputs={"messages": INPUT},
                    return_keys=["origin_query: str", "conversation: List[str]"],
                    outputs={"conversation": OUTPUT}
                )
                
                code_annotate_query = CodeNode(
                    name="code_annotate_query",
                    code_fn=annotate_query,
                    inputs={"origin_query": {code_init_query: "origin_query"}},
                    return_keys=["query: str"]
                )
                
                llm_classify_intent = BasicChainNode(
                    name="llm_classify_intent",
                    resource_key="gpt-4o",
                    parser="yaml",
                    user_prompt=PROMPTS["BEE:REWRITE_AND_CLASSIFY_PROMPT"],
                    extract_schema=["rewrite: str", "intent: str"],
                    inputs={
                        "query": {code_annotate_query: "query"}, 
                        "conversation": {code_init_query: "conversation"}
                    },
                    outputs={
                        "rewrite": {OUTPUT: "enhanced_query"},
                        "intent": {OUTPUT: "query_intent"}
                    }
                ) 

                START >> code_init_query >> code_annotate_query >> llm_classify_intent >> END
            # endregion ===== rewrite query =====
            
            # region ===== retrieve documents and qa =====
            with GraphNode(
                name="graph_retrive_doc_qa",
                description="retrieve documents and qa",
                inputs={
                    "query": {graph_rewrite_query: "enhanced_query"}, "role_ids": INPUT
                }
            ) as graph_retrive_doc_qa:
                retrieve_documents = RetrieverNode(
                    name = "retrieve_documents",
                    inputs={
                        "query": INPUT,
                        "collection": transform_bot_id(self.bot_id),
                        "partition_names": ["document"],
                        "top_k": 20,
                        "rerank_top_k": 10,
                        "output_fields": ["chunk_id"],
                        "allowed_roles": {INPUT: "role_ids"},
                        "bot_id": self.bot_id,
                    },
                    outputs={"docs": {OUTPUT: "retrieved_docs"}}
                )
                
                retrieve_qa = RetrieverNode(
                    name="retrieve_qa",
                    inputs={
                        "query": INPUT,
                        "collection": transform_bot_id(self.bot_id),
                        "partition_names": ["QA"],
                        "top_k": 5, "rerank_top_k": 1,
                        "output_fields": ["chunk_id"],
                        "allowed_roles": {INPUT: "role_ids"},
                        "bot_id": self.bot_id,
                    },
                    outputs={"docs": {OUTPUT: "retrieved_qas"}}
                )
                
                code_format_retrieved_documents = CodeNode(
                    name="code_format_retrieved_documents",
                    code_fn=format_retrieved_documents,
                    inputs={
                        "docs": {retrieve_documents: "docs"}, 
                        "qas": {retrieve_qa: "docs"}},
                    return_keys=[
                        "cache_qa: Optional[str]", 
                        "doc: Optional[str]", 
                        "ids: Optional[List[Dict[str, Any]]]",
                        "qa_ids: Optional[List[Dict[str, Any]]]",
                        "doc_ids: Optional[List[Dict[str, Any]]]",
                    ],
                    outputs=OUTPUT
                )
            
                START >> [retrieve_documents, retrieve_qa] >> code_format_retrieved_documents >> END
            # endregion ===== retrieve documents and qa =====
            
            code_get_intent_from_retrieved_docs = CodeNode(
                name="code_get_intent_from_retrieved_docs",
                code_fn=get_intent_retriever,
                inputs={
                    "docs": {graph_retrive_doc_qa: "retrieved_docs"},
                    "qas": {graph_retrive_doc_qa: "retrieved_qas"},
                },
                return_keys=["intent: str"]
            )
            
            # region ===== chitchat response =====
            with GraphNode(
                name="graph_chitchat_response",
                description="flow chitchat",
                inputs={
                    "query": {graph_rewrite_query: "enhanced_query"},
                    "session_id": INPUT
                }
            ) as graph_chitchat_response:
                llm_answer_chitchat = BasicChainNode(
                    name="llm_answer_chitchat",
                    resource_key="gpt-4.1",
                    system_prompt=PROMPTS["BEE:CHIT_CHAT_PROMPT"],
                    user_prompt="{query}",
                    inputs={"definition": self.definition, "query": INPUT},
                    stream=True
                )
                
                code_post_process_chitchat = CodeNode(
                    name="code_post_process_chitchat",
                    code_fn=post_process_response,
                    inputs={
                        "query": INPUT,
                        "content": llm_answer_chitchat,
                    },
                    return_keys=["dialogue: Dict[str, List[Dict[str, str]]]"]
                )
                
                mem_chitchat_add_session = Mem0Node(
                    name="mem_chitchat_add_session",
                    resource_key="mem0",
                    operation=Mem0Operation.ADD,
                    inputs={
                        "messages": {code_post_process_chitchat: "dialogue"},
                        "session_id": INPUT,
                        "custom_fact_extraction_prompt": PROMPTS["BEE:CUSTOM_FACT_EXTRACTION_PROMPT"],
                    }
                )
                
                START >> llm_answer_chitchat >> code_post_process_chitchat >> mem_chitchat_add_session >> END
            # endregion ===== chitchat response =====
            
            # region ===== non chitchat =====
            with GraphNode(
                name="graph_non_chitchat_response",
                description="đây là luồng non chit chat",
                inputs={
                    "query": {graph_rewrite_query: "enhanced_query"},
                    "conversation": graph_rewrite_query,
                    "documents": {graph_retrive_doc_qa: "doc"},
                    "qnas": {graph_retrive_doc_qa: "cache_qa"},
                    "qa_ids": {graph_retrive_doc_qa: "qa_ids"},
                    "doc_ids": {graph_retrive_doc_qa: "doc_ids"},
                    "definition": self.definition,
                    "session_id": INPUT
                }
            ) as graph_non_chitchat_response:
                
                # region ===== check cached qa =====
                with GraphNode(
                    name="graph_find_matched_qa",
                    description="find matched qa",
                    inputs={
                        "query": INPUT,
                        "qnas": INPUT
                    }
                ) as graph_find_matched_qa:   
                    qa_filter = BasicChainNode(
                        name="qa_filter",
                        resource_key="gpt-4.1",
                        parser="yaml",
                        user_prompt=PROMPTS["BEE:QA_FILTER_PROMPT"],
                        inputs={
                            "question": {INPUT: "query"},
                            "document": {INPUT: "qnas"}
                        },
                        extract_schema=["result: str"],
                        outputs={"result": OUTPUT}
                    )

                    START >> qa_filter >> END
                # endregion ===== check cached qa =====

                llm_stream_cached_qa_answer = BasicChainNode(
                    name="llm_stream_cached_qa_answer",
                    resource_key="gpt-4o",
                    user_prompt=PROMPTS["BEE:NORMAL_RAG_ANSWER_PROMPT"],
                    inputs={
                        "question": {INPUT: "query"},
                        "final_documents": {graph_find_matched_qa: "qnas"},
                        "docs": {INPUT: "qa_ids"}
                    },
                    stream=True
                )
                
                code_post_process_stream_cached_qa_answer = CodeNode(
                    name="code_post_process_stream_cached_qa_answer",
                    code_fn=post_process_response,
                    inputs={
                        "query": INPUT,
                        "content": llm_stream_cached_qa_answer,
                    },
                    return_keys=["dialogue: Dict[str, List[Dict[str, str]]]"]
                )
                
                mem_cached_qa_add_session = Mem0Node(
                    name="mem_cached_qa_add_session",
                    resource_key="mem0",
                    operation=Mem0Operation.ADD,
                    inputs={
                        "messages": {code_post_process_stream_cached_qa_answer: "dialogue"},
                        "session_id": INPUT,
                        "custom_fact_extraction_prompt": PROMPTS["BEE:CUSTOM_FACT_EXTRACTION_PROMPT"],
                    }
                )
                
                mem_search_session = Mem0Node(
                    name="mem_search_session",
                    resource_key="mem0",
                    operation=Mem0Operation.SEARCH,
                    inputs={
                        "query": INPUT,
                        "session_id": INPUT,
                    }
                )
                
                code_post_process_mem_results= CodeNode(
                    name="code_post_process_mem_results",
                    code_fn=post_process_mem0_search_results,
                    inputs={
                        "mem0_response": {mem_search_session: "results"}
                    },
                    return_keys=["memory_context: str"]
                )
                
                branch_routing_qa_flow = BranchNode(
                    name="branch_routing_qa_flow",
                    cases={
                        "'có' in result.lower()": llm_stream_cached_qa_answer, 
                    },
                    default=mem_search_session,
                    inputs={
                        "result": graph_find_matched_qa
                    }
                )
                
                llm_verify_document_relevance = BasicChainNode(
                    name="llm_verify_document_relevance",
                    resource_key="gpt-4.1",
                    parser="yaml",
                    user_prompt=PROMPTS["BEE:VERIFY_DOCUMENT_PROMPT"],
                    extract_schema=["output: str"],
                    inputs={
                        "query": INPUT,
                        "documents": INPUT
                    }
                )
                
                branch_is_document_matched = BranchNode(
                    name="branch_is_document_matched",
                    cases={
                        "verify == 'matched'": "llm_answer_with_context",
                        "verify == 'unmatched'": "llm_refuse_to_answer"
                    },
                    inputs={"verify": {llm_verify_document_relevance: "output"}}
                )
                
                llm_answer_with_context = BasicChainNode(
                    name="llm_answer_with_context",
                    resource_key="gpt-4o",
                    user_prompt=PROMPTS["BEE:NON_CHIT_CHAT_PROMPT"],
                    inputs={
                        "definition": graph_non_chitchat_response,
                        "query": graph_non_chitchat_response,
                        "documents": graph_non_chitchat_response,
                        "conversation": INPUT,
                        "memory_context": code_post_process_mem_results,
                        "docs": {INPUT: "doc_ids"}
                    },
                    stream=True
                )
                
                code_post_process_answer_with_context = CodeNode(
                    name="code_post_process_answer_with_context",
                    code_fn=post_process_response,
                    inputs={
                        "query": INPUT,
                        "content": llm_answer_with_context,
                    },
                    return_keys=["dialogue: Dict[str, List[Dict[str, str]]]"]
                )
                
                mem_answer_with_context_add_session = Mem0Node(
                    name="mem_answer_with_context_add_session",
                    resource_key="mem0",
                    operation=Mem0Operation.ADD,
                    inputs={
                        "messages": {code_post_process_answer_with_context: "dialogue"},
                        "session_id": INPUT,
                        "custom_fact_extraction_prompt": PROMPTS["BEE:CUSTOM_FACT_EXTRACTION_PROMPT"],
                    }
                )
                
                llm_refuse_to_answer = BasicChainNode(
                    name="llm_refuse_to_answer",
                    resource_key="gpt-4o",
                    system_prompt=PROMPTS["BEE:NON_CHIT_CHAT_REFUSE_PROMPT"],
                    user_prompt="{query}",
                    inputs={
                        "query": graph_non_chitchat_response,
                        "definition": graph_non_chitchat_response
                    },
                    stream=True
                )
                
                START >> graph_find_matched_qa >> branch_routing_qa_flow >> [llm_stream_cached_qa_answer, mem_search_session]
                
                llm_stream_cached_qa_answer >> code_post_process_stream_cached_qa_answer >> mem_cached_qa_add_session >> END
                
                mem_search_session >> [code_post_process_mem_results, llm_verify_document_relevance]
                
                llm_verify_document_relevance >> branch_is_document_matched >> [llm_answer_with_context, llm_refuse_to_answer]
                
                llm_answer_with_context >> code_post_process_answer_with_context >> mem_answer_with_context_add_session >> END
                
                llm_refuse_to_answer >> END
            # endregion ===== non chitchat =====
            
            branch_is_chitchat = BranchNode(
                name="branch_is_chitchat",
                cases={
                     "query_intent == 'chit_chat' and docs_intent == 'chitchat'": graph_chitchat_response,
                },
                inputs={
                    "query_intent": graph_rewrite_query,
                    "docs_intent": {code_get_intent_from_retrieved_docs: "intent"}
                },
                default=graph_non_chitchat_response
            )
            
            START >> graph_rewrite_query >> graph_retrive_doc_qa >> code_get_intent_from_retrieved_docs >> branch_is_chitchat >> [graph_chitchat_response, graph_non_chitchat_response]
            
            graph_chitchat_response >> END
            graph_non_chitchat_response >> END
            
        wf_chatbot_bee.compile()
                
        self.workflow = wf_chatbot_bee

        
    async def run(
        self,
        messages: List[Dict],
        session_id: str,
        client_message_id: str,
        role_ids: List,
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
                }
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
    import uuid
    bot = BeeBot(bot_id="dfb5a874-b980-4275-bd34-0ddbd1acefdf")

    dialogue_id = str(uuid.uuid4())
    
    import uuid
    client_message_id = str(uuid.uuid4())
    
    async for chunk in bot.run(
        messages=[
            {"role": "user", "content": "Khách hàng 30 tuổi có nhu cầu vay MB 600 triệu đồng cho mục đích vay tiêu dùng thế chấp tài sản là ô tô giá trị 5 tỷ đồng thì vay được tối đa bao nhiêu tiền"}],
        session_id = dialogue_id,
        client_message_id=client_message_id,
        role_ids=["L1"]
    ):
        print(f"{chunk.choices[0].delta.content or ''}", end= "")

    await asyncio.sleep(4)


if __name__ == "__main__":
    asyncio.run(main())
