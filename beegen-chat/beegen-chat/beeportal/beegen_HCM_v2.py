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

from beeagent.beehcm.beehcm_intent_classify_v2 import create_beehcm_intent_classify_agent, UserIntent
from beeagent.beehcm.context import UserInfo
from beeagent.beehcm.beehcm_response_v2 import BeeHcmRes
from beeagent.beehcm.beehcm_extract_tables import create_table_extractor_agent
from beeagent.beehcm.beehcm_fetch_data import fetch_user_all_data, filter_user_data
from beeagent.beehcm.table_schema import table_schemas

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
        print(bot_config)
        self.bot_id = bot_config.get("id")

        self._llm = LLMExecutor(
            primary_config=self.bot_config['llm'],
            config_store=bot_store
        )

        self.litellm_model= LitellmModel(
            model= "litellm_proxy/"+bot_config["llm"].model,
            api_key= bot_config["llm"].api_key,
            base_url= bot_config["llm"].base_url
        )
                # self._user_store=user_store
        self._user_store = UserStorage(config=MongoConfig.default())

    async def run(
        self,
        messages: List[Dict],
        role_ids: List[str],
        topic: str,
        username: str,
        **kwargs      
    )-> AsyncGenerator[ChatCompletionChunk, None]:
        print("\n" + "="*80)
        print("=== Starting BeeHCM_v2.run() ===")
        print(f"Input parameters:")
        print(f"  - messages count: {len(messages) if messages else 0}")
        print(f"  - role_ids: {role_ids}")
        print(f"  - topic: {topic}")
        print(f"  - username: {username}")
        print(f"  - kwargs keys: {list(kwargs.keys()) if kwargs else 'None'}")

        try:
            # Extract user query
            user_query = messages[-1]["content"] if messages and len(messages) > 0 else ""
            print(f"\nStep 1: Extracted user query: '{user_query[:100]}{'...' if len(user_query) > 100 else ''}'")
            print(f"Query length: {len(user_query)}")

            print(f"\nStep 2: Fetching user info from PostgreSQL...")
            start_time = datetime.now()
            user_info= await get_info_by_user_name_postgre(username)
            fetch_time = (datetime.now() - start_time).total_seconds()
            print(f"User info fetched in {fetch_time:.2f} seconds")
            print(f"User info type: {type(user_info)}, length: {len(user_info) if user_info else 0}")

            # Check user info structure
            if user_info:
                print(f"First user info keys: {list(user_info[0].keys()) if user_info[0] else 'Empty dict'}")

            print("user name: ", username)
            print("user info: ", user_info)

            default_answer= "Hiện tại yêu cầu của anh/chị chưa thể thực hiện.\nTrân trọng."

            if not user_info:
                print(f"\n⚠️ No user info found for username: {username}")
                print("Step 3: Returning default answer")
                answer=""
                chat_id = f"chat-{uuid.uuid4()}"
                print(f"Generated chat_id: {chat_id}")

                yield fake_chunk_from(
                    content= default_answer,
                    model= "cached",
                    chat_id= chat_id,
                    current_time= 0,
                    last= False,
                    **kwargs
                )
                print("✅ Default answer yielded successfully")
            else:
                print(f"\n✅ Found user info for: {username}")
                print("Step 3: Creating UserInfo context object")

                try:
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
                    print("UserInfo context created successfully")
                    print(f"UserInfo context keys: {user_info_context.__dict__.keys() if hasattr(user_info_context, '__dict__') else 'N/A'}")
                except Exception as e:
                    print(f"❌ ERROR creating UserInfo context: {e}")
                    raise

                print("\nType 1: Hỏi thông tin cá nhân")
                print("Step 4: Fetching all user data from database...")

                try:
                    # Get all data của user trên db
                    yaml_loader=YamlModel()
                    config_path = BEEGEN_ROOT / "config/postgre_hcm.yaml"
                    print(f"Config file path: {config_path}")

                    conn_info= yaml_loader.read_yaml(config_path)
                    conn_info=conn_info["db_info"]
                    user_all_data= fetch_user_all_data(
                        username= username,
                        conn_info=conn_info,
                        table_schemas= table_schemas
                    )
                    print(f"User all data type: {type(user_all_data)}")
                    print(f"User all data length: {len(user_all_data) if isinstance(user_all_data, (list, dict)) else 'N/A'}")
                    print(user_all_data)
                except Exception as e:
                    print(f"❌ ERROR in fetch_user_all_data: {e}")
                    print(f"Error type: {type(e).__name__}")
                    import traceback
                    print(f"Traceback:\n{traceback.format_exc()}")
                    raise

                print("\nStep 5: Creating table extractor agent...")
                try:
                    # Khởi tạo agent trích xuất bảng
                    table_extractor_agent=create_table_extractor_agent(
                        model= self.litellm_model
                    )
                    print(f"Table extractor agent created: {type(table_extractor_agent)}")
                    print(f"Model type: {type(self.litellm_model)}")
                except Exception as e:
                    print(f"❌ ERROR creating table_extractor_agent: {e}")
                    raise

                print("\nStep 6: Running table extraction...")
                try:
                    start_time = datetime.now()
                    list_tables= await Runner.run(
                        starting_agent= table_extractor_agent,
                        input= user_query
                    )
                    run_time = (datetime.now() - start_time).total_seconds()
                    print(f"Table extraction completed in {run_time:.2f} seconds")
                    print("list_tables: ", list_tables)

                    if hasattr(list_tables, 'final_output') and hasattr(list_tables.final_output, 'tables'):
                        print(f"Extracted tables: {list_tables.final_output.tables}")
                    else:
                        print("⚠️ No tables extracted or missing final_output.tables")
                except Exception as e:
                    print(f"❌ ERROR in table extraction: {e}")
                    print(f"Error type: {type(e).__name__}")
                    import traceback
                    print(f"Traceback:\n{traceback.format_exc()}")
                    raise

                print("\nStep 7: Filtering user data...")
                try:
                    tables_to_include = list_tables.final_output.tables if hasattr(list_tables, 'final_output') and hasattr(list_tables.final_output, 'tables') else []
                    user_data= filter_user_data(
                        all_user_data= user_all_data,
                        tables_to_include= tables_to_include
                    )
                    print(f"Filtered user data type: {type(user_data)}")
                    print(f"Filtered user data: {user_data}")
                except Exception as e:
                    print(f"❌ ERROR in filter_user_data: {e}")
                    raise

                print("\nStep 8: Creating BeeHcmRes object...")
                try:
                    beehcm_res= BeeHcmRes(
                        bot_id = self.bot_config,
                        litellm_model= self.litellm_model,
                        user_info= user_info_context,
                        user_data= user_data
                    )
                    print(f"BeeHcmRes created successfully: {type(beehcm_res)}")
                except Exception as e:
                    print(f"❌ ERROR creating BeeHcmRes: {e}")
                    raise

                print("\nStep 9: Running BeeHcmRes response generation...")
                try:
                    chunk_count = 0
                    async for chunk in beehcm_res.run(
                        messages= user_query,
                        litellm_model= self.litellm_model
                    ):
                        chunk_count += 1
                        if chunk_count == 1:
                            print(f"✅ First chunk received: {type(chunk)}")
                        yield chunk
                    print(f"✅ Total chunks yielded: {chunk_count}")
                except Exception as e:
                    print(f"❌ ERROR in beehcm_res.run: {e}")
                    print(f"Error type: {type(e).__name__}")
                    import traceback
                    print(f"Traceback:\n{traceback.format_exc()}")
                    raise

        except Exception as e:
            print(f"\n❌ CRITICAL ERROR in run() method: {e}")
            print(f"Error type: {type(e).__name__}")
            import traceback
            print(f"Full traceback:\n{traceback.format_exc()}")

            # Try to yield error message if possible
            try:
                error_response = f"Xin lỗi, đã xảy ra lỗi: {str(e)}"
                yield fake_chunk_from(
                    content= error_response,
                    model= "error",
                    chat_id= f"chat-{uuid.uuid4()}",
                    current_time= 0,
                    last= True,
                    **kwargs
                )
            except Exception as yield_error:
                print(f"❌ Failed to yield error response: {yield_error}")
            raise

        print("\n" + "="*80)
        print("=== BeeHCM_v2.run() completed ===")
        print("="*80 + "\n")

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
            {"role": "user", "content": "Chức danh của tôi tại VNG Corporation là gì?"}],
        role_ids=["L1"],
        topic="default",
        username="beehi_hcm_06"
    ):
        # print(chunk)
        tmp=chunk

    await asyncio.sleep(4)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
