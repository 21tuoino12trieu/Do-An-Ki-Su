from pydantic import BaseModel
import asyncio
import yaml, json
import re
import pandas as pd
import uuid
import psycopg2
from psycopg2.extras import RealDictCursor

from beegenerate.retrievers.vector_retriever import VectorRetriever
from beegenerate.vectordb import MilvusStorage
from beegenerate.reranks import RerankingFactory
from beegenerate.storage import (
    DocumentStore,
    BotStore
)
from beegenerate.storage.mongo.mongodb import MongoStorage
from beegenerate.configs.db.mongo_config import MongoConfig
from beegenerate.llms.llm_executor import LLMExecutor
from beegenerate.const import BEEGEN_ROOT
from beegenerate.configs.yaml_model import YamlModel

from openai import AsyncStream, AsyncOpenAI
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from agents import Agent, Runner, RunContextWrapper, function_tool, OpenAIChatCompletionsModel

from typing import (
    List,
    Dict,
    Tuple,
    Any,
    TypeVar,
    Type,
    Union,
    Optional,
    AsyncGenerator
)

from datetime import datetime
from beegenerate.utils.common import transform_bot_id
from beegenerate.llms.llm_response import fake_chunk_from

from beegenerate.loggings import LOGGER
from beegenerate.loggings.loggers import lf
from langfuse.decorators import langfuse_context, observe

from beeagent.beehcm.beehcm_intent_classify import create_beehcm_intent_classify_agent, UserIntent
from beeagent.beehcm.context import UserInfo
from beeagent.beehcm.beehcm_response import BeeHcmRes

from agents.extensions.models.litellm_model import LitellmModel

class UserStorage(MongoStorage):
    def __init__(
            self,
            config: Optional[MongoConfig] = None
    ) -> None:
        super().__init__(config)

    async def get_info_by_user_name(
            self,
            user_name: str,
            collection_name: str = "user",
    ):
        user_info=self.find(
            collection_name= collection_name,
            query={
                "username": user_name,
            }
        )
        return user_info

async def get_info_by_user_name_postgre(user_name: str) -> list[dict]:
    """
    Truy vấn PostgreSQL và trả về kết quả dạng list[dict].
    """
    try:
        yaml_loader=YamlModel()
        conn_info= yaml_loader.read_yaml(BEEGEN_ROOT / "config/postgre_hcm.yaml")
        conn_info=conn_info["db_info"]
        print("db_info: ",conn_info)
        query= f"""
            SELECT *
            FROM chatbot_beehi_hcm.beehi_base_emp_info
            WHERE username = '{user_name}';
            """
        print("query: ",query)
        with psycopg2.connect(**conn_info) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query)
                results = cur.fetchall()
        print(f"✅ Truy vấn thành công: {len(results)} bản ghi.")
        return [dict(row) for row in results]  # RealDictRow → dict
    except Exception as e:
        print(f"❌ Lỗi truy vấn thông tin user bằng username: {e}")
        return []

# test=UserStorage()
# print(test.get_info_by_user_name("ant4"))


# @function_tool
# async def query_postgres_as_dict(query: str) -> list[dict]:
#     """
#     Truy vấn PostgreSQL và trả về kết quả dạng list[dict].
#     """
#     try:
#         yaml_loader=YamlModel()
#         conn_info= yaml_loader.read_yaml(BEEGEN_ROOT / "config/postgre.yaml")
#         conn_info=conn_info["db_info"]
#         print(conn_info)
#         with psycopg2.connect(**conn_info) as conn:
#             with conn.cursor(cursor_factory=RealDictCursor) as cur:
#                 cur.execute(query)
#                 results = cur.fetchall()
#         print(f"✅ Truy vấn thành công: {len(results)} bản ghi.")
#         return [dict(row) for row in results]  # RealDictRow → dict
#     except Exception as e:
#         print(f"❌ Lỗi truy vấn: {e}")
#         return []

# sql = """
# SELECT e."employeeCode", e."fullName", d."school", e.username
# FROM beehi_base_emp_info e
# JOIN beehi_emp_degree_info d ON e."employeeId" = d."employeeId"
# LIMIT 5;
# """
# res=  asyncio.run(query_postgres_as_dict(sql))

from typing import Optional, Any

class BeeHCM:
    def __init__(
            self,
            bot_config: Dict,
            # user_store: UserStorage,
            bot_store: BotStore,
            # bot_id: str,
            vec_store: Optional[Any] = None,
            doc_store: Optional[Any] = None
    ):
        
        # self.bot_id = bot_id
        self.bot_config = bot_config
        self.bot_id = bot_config.get("id")

        self._llm = LLMExecutor(
            primary_config=self.bot_config['llm'],
            config_store=bot_store
        )

        self.litellm_model= LitellmModel(
            model="gpt-4.1",
            api_key= bot_config["llm"].api_key,
            base_url= bot_config["llm"].base_url
        )
                # self._user_store=user_store
        self._user_store = UserStorage(config=MongoConfig.default())
    
    async def _is_user_exist(
            self,
            user_name : str
    ) -> bool:
        user_info= self._user_store.find(user_name)
        if user_info:
            return True
        else:
            return False


    async def run(
        self,
        messages: List[Dict],
        role_ids: List[str],
        topic: str,
        username: str,
        **kwargs      
    )-> AsyncGenerator[ChatCompletionChunk, None]:
        user_query = messages[-1]["content"]
        user_info= await get_info_by_user_name_postgre(username)
        print("user name: ", username)
        print("user info: ",user_info)
        default_answer= "Hiện tại yêu cầu của anh/chị chưa thể thực hiện.\nTrân trọng."
        if not user_info:
            answer=""
            yield fake_chunk_from(
                content= default_answer,
                model= "cached",
                chat_id= f"chat-{uuid.uuid4()}",
                current_time= 0,
                last= False,
                **kwargs
            )
        else:
            print("tồn tại user info")
            user_info_context=UserInfo(
                user_name= user_info[0].get("username",""),
                employee_id= user_info[0].get("employeeid",""),
                employee_code= user_info[0].get("employeecode",""),
                full_name= user_info[0].get("fullname",""),
                date_of_birth= user_info[0].get("dateofbirth",""),
                current_time= str(datetime.now()),
                org_name_manage= user_info[0].get("org_name_manage", ""),
                job_name= user_info[0].get("job_name", ""),
                org_level= str(user_info[0].get("org_level", 0)),
                org_name_level1= user_info[0].get("org_name_level_1", ""),
                org_name_level2= user_info[0].get("org_name_level_2", ""),
                org_name_level3= user_info[0].get("org_name_level_3", ""),
                management_level= str(user_info[0].get("management_level", 0))
            )
            print("run beehcm_intent_classify_agent")
            beehcm_intent_classify_agent= create_beehcm_intent_classify_agent(model= self.litellm_model)
            user_intent= await Runner.run(
                starting_agent= beehcm_intent_classify_agent,
                input= user_query,
                context= user_info_context
            )
            assert isinstance(user_intent.final_output, UserIntent)
            if not user_intent.final_output.type_1_is_asking_personal_profile_information :
                print("No type 1: Không hỏi thông tin cá nhân")
                # yield fake_chunk_from(
                #     content= default_answer,
                #     model= "cached",
                #     chat_id= f"chat-{uuid.uuid4()}",
                #     current_time= 0,
                #     last= False,
                #     **kwargs
                # )
                beehcm_res= BeeHcmRes(
                    # bot_id=bot_id
                    bot_id = self.bot_config,
                    litellm_model= self.litellm_model,
                    user_info= user_info_context
                )
                async for chunk in beehcm_res.run(
                    messages= user_query,
                    litellm_model= self.litellm_model
                ):
                    yield chunk
            else:
                print("Type 1: Hỏi thông tin cá nhân")
                beehcm_res= BeeHcmRes(
                    # bot_id=bot_id
                    bot_id = self.bot_config,
                    litellm_model= self.litellm_model,
                    user_info= user_info_context
                )
                async for chunk in beehcm_res.run(
                    messages= user_query,
                    litellm_model= self.litellm_model
                ):
                    yield chunk

async def main():
    bot_id = "b6704dfb-0e0d-4552-a1ff-26bbbfeb09a0"
    bot_store = BotStore(config=MongoConfig.default())
    bot_config = bot_store.fetch_bot_details(
        bot_id=bot_id
    )
    user_store=UserStorage()

    bot = BeeHCM(
        bot_config=bot_config,
        # user_store=user_store,
        bot_store=bot_store,
        # bot_id= bot_id
    )

    async for chunk in bot.run(
        messages=[
            {"role": "user", "content": "Cho tôi biết tuổi hiện tại của Ánh, có mã nhân viên là MB44444?"}],
        role_ids=["L1"],
        topic="default",
        username="dannk.os"
    ):
        print(chunk)

    await asyncio.sleep(4)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())