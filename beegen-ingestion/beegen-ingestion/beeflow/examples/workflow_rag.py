# At the top of your main file, before any other imports
import threading
 
from beeflow.utils.streaming import STREAM_SERVICE
_scipy_lock = threading.Lock()
 
def fix_scipy_imports():
    with _scipy_lock:
        try:
            import scipy
            import scipy.sparse
            import scipy.sparse._lil
            scipy.sparse.lil_matrix((1, 1))  # Force initialization
            print("✅ Scipy pre-imported")
        except:
            pass
 
# Call immediately
fix_scipy_imports()
 
from typing import Dict, List
from examples.utils.nlp import annotate_query, format_filter_documents, get_intent_retriever, init_query
from beeflow.nodes.base_node import END, INPUT, OUTPUT, START
from beeflow.nodes.flow.branch_node import BranchNode
from beeflow.nodes.graph.graph_node import GraphNode
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beeflow.nodes.templates.basic_chain_node import BasicChainNode
from beeflow.nodes.templates.retriever_node_v2 import RetrieverNode
from beeflow.workflow import WorkflowEngine
from beegen.loggings.loggers import LOGGER
from beegen.prompts.prompt_manager import PromptManager
from beegen.registry.resource_hub import ResourceHub
from beegen.utils.common import fake_chunk_from, transform_bot_id
 
 
PROMPTS = PromptManager("beegen")
 
 
class BeeRAG:
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
            name="bee",
            description="Đây là luồng chat standard của tất cả bot"
        ) as bee_workflow:
            n_init_query = CodeNode(name="n_init_query", code_fn=init_query, inputs={"messages": INPUT})
            n_annotate_query = CodeNode(name="n_annotate_query", code_fn=annotate_query, inputs={"origin_query": n_init_query})
             
            intent_query = BasicChainNode(
                name="intent_query",
                resource_key="qwen-instruct-chat",
                parser="yaml",
                user_prompt=PROMPTS["BEE:REWRITE_AND_CLASSIFY_PROMPT"],
                extract_schema=["rewrite: str", "intent: str"],
                inputs={"query": n_annotate_query, "conversation": n_init_query, "status_code": 400, "custom_data": INPUT}
            )
             
            standard_retriever = RetrieverNode(
                name = "standard_retriever",
                inputs={
                    "collection": transform_bot_id(self.bot_id),
                    "query": {intent_query: "rewrite"},
                    "bot_id": self.bot_id,
                    'allowed_roles': ["L1"],
                    "top_k": 20,
                    "rerank_top_k": 10,
                    # "partition_names": ["document"],
                    'output_fields': ['chunk_id'],
                }
            )
             
            n_format_filter_documents = CodeNode(
                name="n_format_filter_documents",
                code_fn=format_filter_documents,
                inputs={"docs": {standard_retriever: "docs"}}
            )
             
            intent_retriever = CodeNode(name="intent_retriever",code_fn=get_intent_retriever, inputs={"docs": {standard_retriever: "docs"}})           
             
            routing_case = BranchNode(
                name="routing_case",
                cases={
                     "query == 'chit_chat' and intent == 'chit_chat'": "chit_chat_response",
                },
                inputs={
                    "query": {n_init_query: "rewrite"},
                    "intent": {intent_retriever: "intent"}
                },
                default="non_chit_chat_response"
            )
             
            chit_chat_response = BasicChainNode(
                name="chit_chat_response",
                resource_key="qwen-instruct-chat",
                user_prompt=PROMPTS["BEE:CHIT_CHAT_PROMPT"],
                inputs={"definition": self.definition, "custom_data": INPUT},
            )
             
            with GraphNode(
                name="non_chit_chat_response",
                description="đây là luồng non chit chat",
                inputs={
                    "query": {intent_query: "rewrite"},
                    "documents": {n_format_filter_documents: "documents_list"},
                    "definition": self.definition,
                    "custom_data": INPUT
                }
            ) as non_chit_chat_response:       
                verify_document = BasicChainNode(
                    name="verify_document",
                    resource_key="qwen-instruct-chat",
                    parser="yaml",
                    user_prompt=PROMPTS["BEE:VERIFY_DOCUMENT_PROMPT"],
                    extract_schema=["output: str"],
                    inputs={
                        "query": INPUT,
                        "documents": INPUT,
                        "custom_data": INPUT
                    }
                )
                 
                matching_case = BranchNode(
                    name="matching_case",
                    cases={
                        "verify == 'matched'": "non_chit_chat_flow",
                        "verify == 'unmatched'": "non_chit_chat_refuse_flow"
                    },
                    inputs={"verify": {verify_document: "output"}}
                )
                 
                non_chit_chat_flow = BasicChainNode(
                    name="non_chit_chat_flow",
                    resource_key="qwen-instruct-chat",
                    system_prompt=PROMPTS["BEE:NON_CHIT_CHAT_PROMPT"],
                    user_prompt="{query}",
                    inputs={
                        "definition": INPUT,
                        "query": INPUT,
                        "documents": INPUT,
                        "custom_data": INPUT
                    },
                    outputs={"content": OUTPUT},
                    stream=True
                )
                 
                non_chit_chat_refuse_flow = BasicChainNode(
                    name="non_chit_chat_refuse_flow",
                    resource_key="qwen-instruct-chat",
                    system_prompt=PROMPTS["BEE:NON_CHIT_CHAT_REFUSE_PROMPT"],
                    user_prompt="{query}",
                    inputs={
                        "query": INPUT,
                        "definition": INPUT,
                        "custom_data": INPUT
                    },
                    outputs={"content": OUTPUT}
                )
                 
                START >> verify_document >> matching_case >> [non_chit_chat_flow,
                                                              non_chit_chat_refuse_flow] >> END
             
            START >> n_init_query >> n_annotate_query >> intent_query >> standard_retriever
             
            standard_retriever >> [n_format_filter_documents, intent_retriever]
             
            [intent_query, intent_retriever] >> routing_case
             
            routing_case >> [chit_chat_response, non_chit_chat_response] >> END
             
        bee_workflow.compile()
                 
        self.workflow = bee_workflow
 
         
    async def run(
        self,
        messages: List[Dict],
        role: str = "L1",
        topic: str = "default"
    ):
        """Main pipeline with updated logic flow."""
        try:
            import uuid
            request_id = str(uuid.uuid4())
            asyncio.create_task(self.workflow.run(
                request_id=request_id,
                inputs={
                    "messages": messages,
                    "custom_data": {"env": "dev"}
                }
            ))
            async for channel_name in STREAM_SERVICE.get_channels(request_id):
                async for chunk in STREAM_SERVICE.get(request_id, channel_name, json_mode=False):
                    try:
                        delta = getattr(chunk.choices[0].delta, "content", None)
                    except Exception:
                        delta = None

                    if delta:
                        print(delta, end="", flush=True) 
                        yield delta 
        except Exception as e:
            import traceback
            LOGGER.error(traceback.format_exc(e))
            default_answers = 'Xin lỗi, đã xảy ra lỗi khi xử lý yêu cầu của bạn. Vui lòng thử lại sau.'
            yield fake_chunk_from(
                content=default_answers,
                model="error"
            )
             
async def main():
     
    bot = BeeRAG(bot_id="71eff3f6-1fc4-48c4-8ca8-df836d26d4c5")
     
    async for chunk in bot.run(
        messages = [{"role": "user", "content": "Quy định về hoàn thuế giá trị gia tăng đối với dự án đầu tư của cơ sở kinh doanh ngành, nghề đầu tư kinh doanh có điều kiện"}]
    ):
        print(chunk)
         
    await asyncio.sleep(4)
 
 
if __name__ == "__main__":
    import asyncio
    asyncio.run(main())