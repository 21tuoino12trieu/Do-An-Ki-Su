# At the top of your main file, before any other imports
import ast
import re
from beegen_v1.utils.common import fake_chunk_from
from pymongo import MongoClient
from datetime import datetime
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from typing import Any, Dict, List, Optional, AsyncGenerator
# from beeworkflow.workflow import WorkflowEngine
# from beeworkflow.configs.graph_config import GraphNodeConfig
from beegen_v1.utils.common import transform_bot_id
from beegen_v1.prompts.prompt_manager import PromptManager
from beegen_v1.registry.model_registry import ModelRegistry
from beeportal.utils import get_query, extract_all_questions, format_questions, get_matched_answer
from beeagent.beehai.manager import BeeHaiHR
from beeagent.beehai.beehai_intent_classify import UserIntent
from beeagent.crud.user import UserService
from beemcp.services.manager import MCPManagerService
from beegenerate.loggings import LOGGER


import threading
import sys
sys.stdout.reconfigure(encoding='utf-8')
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
prompt_storage = PromptManager("beegen")
QA_FILTER_PROMPT = prompt_storage.get(
    "BEEHAI:QA_FILTER_PROMPT")

NO_ANSWER_RESPONSE = "Kính gửi Anh/chị \nHiện tại yêu cầu tư vấn/hướng dẫn của anh/chị chưa được hỗ trợ. Anh/chị vui lòng truy cập https://dichvunoibo.mbbank.com.vn/ để gửi yêu cầu tới P.Chính sách chế độ TCKT xử lý \nTrân trọng"


class BeeHaiBot:
    def __init__(self, bot_id: str, user_service: UserService):
        self.bot_id = bot_id
        mongo_engine = ModelRegistry.self().sync_mongo("aicenter-chatbot")
        result = mongo_engine._find_one(
            collection_name="botinfo", query={"_id": self.bot_id})
        self.name = result.get('data', {'name': {}}).get('name', None)
        self.config = result.get('data', {'metadata': {}}).get('metadata', {})
        self._build_flow()
        self.beehai_hr_agent = BeeHaiHR(
            bot_id=bot_id, user_service=user_service)

    def _build_flow(self):
        # flow_config = (
        #     GraphNodeConfig.new()
        #     .name("bee-acc")
        #     .description("đây là luồng chạy của chatbot Beehai")
        #     .code(code_fn=get_query, inputs={"messages": "bee-acc"}, start=True)
        #     .edge("get_query", "qa_retriever", "route01")
        #     .retriever(
        #         name="qa_retriever",
        #         collection=transform_bot_id(self.bot_id),
        #         inputs={
        #             "query": "get_query",
        #             "role_names": "bee-acc",
        #             "bot_id": "bee-acc",
        #             "top_k": int(self.config["retrieval"]["retrieval_top_k"]),
        #             "threshold": float(self.config["retrieval"]["retrieval_threshold"]),
        #             "rerank_top_k": int(self.config["retrieval"]["rerank_top_k"]),
        #             "rerank_threshold": float(self.config["retrieval"]["rerank_threshold"]),
        #             "partition_names": ["QA"]
        #         }
        #     )
        #     .branch(
        #         name="route01",
        #         cases={"len(docs) > 0": "extract_all_questions"},
        #         default_target="no_document_answer",
        #         inputs={"docs": "qa_retriever"}
        #     )
        #     .llm(
        #         name="no_document_answer",
        #         model="no_cached",
        #         instant_response=True,
        #         inputs={"response": NO_ANSWER_RESPONSE},
        #         stream=True,
        #         end=True
        #     )
        #     .code(code_fn=extract_all_questions, inputs={"docs": "qa_retriever"})
        #     .edge("extract_all_questions", "route02")
        #     .branch(
        #         name="route02",
        #         cases={"len(docs) > 0": "format_questions"},
        #         default_target="no_document_answer_2",
        #         inputs={
        #             "docs": {"extract_all_questions": "qadocs"}}
        #     )
        #     .llm(
        #         name="no_document_answer_2",
        #         model="no_cached",
        #         instant_response=True,
        #         inputs={"response": NO_ANSWER_RESPONSE},
        #         stream=True,
        #         end=True
        #     )
        #     .code(code_fn=format_questions, inputs={"docs": {"extract_all_questions": "qadocs"}})
        #     .edge("format_questions", "qa_filter", "route03")
        #     .llm_chain(
        #         name="qa_filter",
        #         user_prompt=QA_FILTER_PROMPT,
        #         model="gpt-4.1",
        #         inputs={
        #             "question": {"get_query": "query"},
        #             "document": {"format_questions": "txt"}
        #         },
        #         output_schema=["result: int"]
        #     )
        #     .branch(
        #         name="route03",
        #         cases={
        #             "index >= 0": "get_matched_answer"},
        #         default_target="no_document_answer_3",
        #         inputs={
        #             "index": {"qa_filter": "result"}}
        #     )
        #     .llm(
        #         name="no_document_answer_3",
        #         model="no_cached",
        #         instant_response=True,
        #         inputs={
        #             "response": NO_ANSWER_RESPONSE},
        #         stream=True,
        #         end=True
        #     )
        #     .code(
        #         code_fn=get_matched_answer,
        #         inputs={
        #             "docs": {"extract_all_questions": "qadocs"},
        #             "index": {"qa_filter": "result"}
        #         }
        #     )
        #     .edge("get_matched_answer", "cached_answer")
        #     .llm(
        #         name="cached_answer",
        #         model="cached",
        #         instant_response=True,
        #         inputs={
        #             "response": "get_matched_answer",
        #             "docs": "get_matched_answer"
        #         },
        #         stream=True,
        #         end=True
        #     )

        #     .build()
        # )

        # self.workflow = WorkflowEngine(self.name, flow_config)

        pass

    async def run(
        self,
        messages: List[Dict],
        role_ids: List[str],
        topic: str,
        username: str,
        keycloak_token: str,
        token: dict,
        mcp_manager: MCPManagerService,
        **kwargs
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Main pipeline with updated logic flow."""
        try:
            user_intent = await self.beehai_hr_agent.beehai_intent_classifier(messages=messages)
            if user_intent.type_1_is_asking_human_resource_informaion:
                async for chunk in self.beehai_hr_agent.run(
                    messages=messages,
                    bot_id=self.bot_id,
                    role_ids=role_ids,
                    topic=topic,
                    username=username,
                    keycloak_token=keycloak_token,
                    token=token,
                    mcp_manager=mcp_manager
                ):
                    yield chunk
            # else:
            #     async for chunk in self.workflow.run(
            #         inputs={
            #             "messages": messages,
            #             "role_names": role_ids,
            #             "bot_id": self.bot_id
            #         }
            #     ):
            #         if isinstance(chunk, str):
            #             print(f"Final chunk: {chunk}")
            #             continue
            #         else:
            #             yield chunk
        except Exception as e:
            LOGGER.error(f"Got error: {e}")
            default_answers = 'Xin lỗi, đã xảy ra lỗi khi xử lý yêu cầu của bạn. Vui lòng thử lại sau.'
            yield fake_chunk_from(
                content=default_answers,
                model="error"
            )
            raise e


async def main():

    bot = BeeHaiBot(bot_id="b10f0d26-4d91-47f5-8cac-034b87e42c7f")

    async for chunk in bot.run(
        messages=[
            {"role": "user", "content": "làm thế nào để tính phép cộng?"}],
        role_ids=["L1"]
    ):
        print(chunk)

    await asyncio.sleep(4)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
