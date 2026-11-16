import asyncio
from datetime import datetime
from typing import List, Dict

from beeflow.nodes import BasicChainNode, BranchNode
from beeflow.nodes.base_node import INPUT, OUTPUT, START, END
from beeflow.nodes.graph.graph_node import GraphNode
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beeflow.nodes.templates.retriever_node_v2 import RetrieverNode
from beeflow.utils.streaming import STREAM_SERVICE
from beeflow.workflow import WorkflowEngine
from beegen.registry.resource_hub import ResourceHub
from beegen.utils.common import transform_bot_id

from beegenerate.llms.llm_response import fake_chunk_from
from beeportal.bot_enterprise_KHCN.enterprise_KHCN.functions import format_retrieved_docs
from beeportal.utils import PROMPTS, init_query


class BeeEnterpriseKHCN:
    def __init__(self, bot_id: str):
        self.bot_id = bot_id
        mongo_engine = ResourceHub.self().sync_mongo("aicenter-chatbot")
        bot_info = mongo_engine._find_one(
            collection_name="botinfo", query={"_id": self.bot_id})
        self.name = bot_info.get('data', {'name': {}}).get('name', None)
        self.config = bot_info.get(
            'data', {'metadata': {}}).get('metadata', {})
        self.definition = self.config.get('system_prompt', "không có mô tả nào được cung cấp")

        self._build_flow()

    def _build_flow(self):
        with WorkflowEngine(
            name="beeEnterpriseKHCN",
            description="Chat bot Enterprise KHCN"
        ) as beeEnterpriseKHCN:

            with GraphNode(
                name="generate_intent",
                description="luồng generate intent",
                inputs={"messages": INPUT}
            ) as generate_intent:
                init_query_fn = CodeNode(
                    name="init_quiery_fn",
                    code_fn=init_query,
                    inputs={"messages": INPUT},
                    return_keys=["origin_query: str", "conversation: List[str]"]
                )

                rewrite = BasicChainNode(
                    name="rewrite",
                    resource_key="gpt-4.1",
                    parser="yaml",
                    user_prompt=PROMPTS['BEE_ENTERPRISE_KHCN:REWRITE_AND_CLASSIFY_PROMPT'],
                    inputs={
                        "question": {init_query_fn: "origin_query"},
                        "conversation": init_query_fn
                    },
                    extract_schema=["intent: str", "query: str"],
                    outputs={"intent": OUTPUT, "query": OUTPUT}

                )


                START >> init_query_fn >> rewrite >> END

            # retriver_and_rerank
            with GraphNode(
                name="retriver_and_rerank",
                description="luồng retriver and rerank",
                inputs={"intent": generate_intent, "query": generate_intent}
            ) as standard_retriever:

                retriever = RetrieverNode(
                    name="standard_retriever",
                    description="luồng standard retriever",
                    inputs={
                        "query": {INPUT: "query"},
                        "collection": transform_bot_id(self.bot_id),
                        "top_k": self.config['retrieval'].get('retrieval_top_k', 16),
                        "rerank_top_k": self.config['reranking'].get('rerank_top_k', 8),
                        "allowed_roles": ['L1'],
                        "bot_id": self.bot_id,
                        "partition_names": ['document'],
                        "output_fields": ["chunk_id"],
                        "rerank_threshold": self.config['reranking'].get('rerank_threshold', 0.0),
                        "threshold": self.config['retrieval'].get('retrieval_threshold', 0.0)
                    },
                    outputs={
                        "docs": OUTPUT
                    }
                )

                format_retrieved_docs_fn = CodeNode(
                    name='format_retrieved_docs_fn',
                    code_fn=format_retrieved_docs,
                    inputs={
                        'docs': {retriever: "docs"}
                    },
                    return_keys=["doc_contents: List[str]", "documents_text: str","doc_ids: List[str]", "ids: List[Dict[str, Any]]", "lengths: int"],
                    outputs={
                        "doc_contents": OUTPUT,
                        "documents_text": OUTPUT,
                        "doc_ids": OUTPUT,
                        "ids": OUTPUT,
                        "lengths": OUTPUT
                    }
                )


                START >> retriever >> format_retrieved_docs_fn >> END


            # verify the relevant of documents
            verify_document = BasicChainNode(
                name='verify_document',
                resource_key="gpt-4.1",
                user_prompt=PROMPTS['BEE_ENTERPRISE_KHCN:VERIFY_DOCUMENT_PROMPT'] + '/no_think',
                inputs={
                    "query": {generate_intent: "query"},
                    "documents": {standard_retriever: "docs"}
                },
                parser="yaml",
                extract_schema=["output:str"],
                # outputs={"output_verify_document": {OUTPUT: "output"}}
            )

            # verify document logic of documents
            verify_document_logic = BasicChainNode(
                name='verify_document_logic',
                resource_key="gpt-4.1",
                user_prompt=PROMPTS['BEE_ENTERPRISE_KHCN:RM_VERIFY_DOCUMENT_PROMPT'] + 'no_think',
                inputs={
                    "query": {generate_intent: "query"},
                    "documents": {standard_retriever: "docs"}
                },
                parser="yaml",
                extract_schema=["output:str"],
                # outputs={"output_verify_document_logic": {OUTPUT: "output"}}
            )


            branch_answer = BranchNode(
                name="branch_answer",
                inputs={
                    "intent": {generate_intent: "intent"},
                    "length_docs": {standard_retriever: "length"},
                    "output_verify_document": {verify_document: "output"},
                    "output_verify_document_logic": {verify_document_logic: "output"}

                },
                cases={
                    "intent == 'chit_chat' or length_docs == 0": "chit_chat_answer",
                    "intent == 'non_chit_chat' and (output_verify_document=='matched' or output_verify_document_logic=='matched')": "non_chit_chat_answer",
                },
                default="non_chit_chat_refuse_answer"
            )


            # response chit chat
            chit_chat_answer = BasicChainNode(
                name='chit_chat_answer',
                resource_key='gpt-4.1',
                system_prompt=PROMPTS['BEE_ENTERPRISE_KHCN:CHIT_CHAT_PROMPT'],
                user_prompt='{query} + /no_think',
                inputs={
                    "definition": self.definition,
                    "query": {generate_intent: "query"},
                    "docs": {standard_retriever: "ids"}
                },
                outputs={"content": OUTPUT},
                stream=True
            )

            # response non chit chat

            non_chit_chat_refuse_answer = BasicChainNode(
                name="non_chit_chat_refuse_answer",
                resource_key="gpt-4.1",
                system_prompt=PROMPTS['BEE_ENTERPRISE_KHCN:REFUSE_PROMPT'],
                inputs={
                    "definition": self.definition
                },
                outputs={"content": OUTPUT},
                stream=True
            )

            non_chit_chat_answer = BasicChainNode(
                name="non_chit_chat_answer",
                resource_key="gpt-4.1",
                system_prompt=PROMPTS['BEE_ENTERPRISE_KHCN:NON_CHIT_CHAT_PROMPT'],
                user_prompt='{query} + /no_think',
                inputs={
                    "definition": self.definition,
                    "query": {generate_intent: "query"},
                    "date": datetime.now().strftime('%Y-%m-%d'),
                    "documents": {standard_retriever: "documents_text"}
                },
                # stream=True
            )

            direct_answer = BasicChainNode(
                name="direct_answer",
                resource_key="gpt-4.1",
                system_prompt=PROMPTS['BEE_ENTERPRISE_KHCN:DIRECT_ANSWER_FIRST_PROMPT'],
                inputs={
                    "answer": {non_chit_chat_answer: "content"},
                    "query": {generate_intent: "query"},
                    "docs": {standard_retriever: "ids"}
                },
                stream=True
            )

            START >> generate_intent >> standard_retriever >> [verify_document, verify_document_logic] >> branch_answer >> [chit_chat_answer, non_chit_chat_refuse_answer, non_chit_chat_answer]

            chit_chat_answer >> END
            non_chit_chat_refuse_answer >> END
            non_chit_chat_answer >> direct_answer >> END

        beeEnterpriseKHCN.compile()
        self.workflow = beeEnterpriseKHCN

    async def run(self,
                  messages: List[Dict],
                  client_message_id: str,
                  role_ids: List[str] = [],
                  **kwargs
                  ):
        "Main pipline with update logic flow"
        try:
            asyncio.create_task(self.workflow.run(
                request_id=client_message_id,
                inputs={
                    "messages": messages
                }
            ))

            async for channel_name in STREAM_SERVICE.get_channels(client_message_id):
                async for chunk in STREAM_SERVICE.get(client_message_id, channel_name, json_mode=False):
                    yield chunk

        except Exception as e:
            import traceback
            default_answers = 'Xin lỗi, đã xảy ra lỗi khi xử lý yêu cầu của bạn. Vui lòng thử lại sau.'
            yield fake_chunk_from(
                content=default_answers,
                model="error"
            )

async def main():
    bot_id = "dfb5a874-b980-4275-bd34-0ddbd1acefdf"
    bot = BeeEnterpriseKHCN(bot_id)
    import uuid
    client_message_id = str(uuid.uuid4())

    async for chunk in bot.run(
            messages=[
                {"role": "user",
                 "content": "Khách hàng mua ô tô huyndai của hàn quốc 45 tuổi vay được bao lâu và giá trị vay bao nhiêu"},
            ],
            client_message_id=client_message_id,
            role_ids=["L1"],
            topic="default"
    ):
        print(f"{chunk.choices[0].delta.content or ''}", end="")

    await asyncio.sleep(4)

if __name__ == '__main__':
    asyncio.run(main())
