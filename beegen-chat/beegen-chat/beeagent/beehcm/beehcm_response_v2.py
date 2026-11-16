from agents import Agent, Runner, gen_trace_id, trace, RunConfig, ModelSettings,function_tool, RunContextWrapper, OpenAIChatCompletionsModel
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk, Choice, ChoiceDelta
from openai.types.responses import ResponseTextDeltaEvent

from typing import AsyncGenerator
from beegenerate.loggings import LOGGER
from beegenerate.const import BEEGEN_ROOT
from beegenerate.configs.yaml_model import YamlModel

from beemcp.services.manager import MCPManagerService
from beegen_v1.configs.mcp.mcp_config import RootMCPConfig
from beegen_v1.utils.common import fake_chunk_from
from beetools.system_aware import current_datetime
import time
from datetime import datetime

from uuid import uuid4
import psycopg2
from psycopg2.extras import RealDictCursor

from .context import UserInfo
# from ..llms_extend.litellm import litellm_model
from pydantic.dataclasses import dataclass

from ..base_agent import BaseAgent
from .beehcm_text2sql import create_beehcm_text2sql_agent

import asyncio
from beegenerate.loggings.loggers import lf

@function_tool
async def recreate_sql_query(query: str, error_message: str):
    pass

@function_tool
async def check_valid_role(query):
    pass


instructions = """
    ### BỐI CẢNH ###
    Bạn là **MB HCM Assistant**, một trợ lý thông minh của hệ thống nhân sự MB.
    Nhiệm vụ của bạn là đọc câu hỏi của người dùng và **trả lời dựa trên dữ liệu đã được cung cấp trước** trong tham số `user_data`.

    Bạn **không được** sinh SQL, không được gọi công cụ, và không được suy đoán thông tin không có trong dữ liệu.
    Mọi phản hồi phải dựa **duy nhất** vào nội dung thực tế được truyền vào.

    ---

    ### DỮ LIỆU ĐƯỢC CUNG CẤP (user_data) ###
    `user_data` là cấu trúc chứa danh sách các bảng và dữ liệu tương ứng.
    Mỗi bảng có dạng list[dict], mỗi dict là một bản ghi.
    Dưới đây là dữ liệu của người dùng được trích xuất:

    user_data:
    {user_data}

    ---

    Assistant phải:
    - Đọc đúng dữ liệu.
    - Trích xuất thông tin liên quan đến câu hỏi.
    - Trả lời dựa trên dữ liệu đã có.
    - Nếu không tìm thấy dữ liệu, phải trả lời: **"Không tìm thấy thông tin phù hợp."**

    Assistant tuyệt đối **không được tự bổ sung dữ liệu, tưởng tượng dữ liệu, hoặc dự đoán dữ liệu.**

    ---

    ### THÔNG TIN CÁ NHÂN NGƯỜI DÙNG ###
    Đây là thông tin xác thực từ hệ thống MB.  
    Assistant chỉ được dùng để **so khớp danh tính**, không được thay đổi hoặc giả định mới.

    {{
        "user_name": "{user_name}",
        "employee_id": "{employee_id}",
        "employee_code": "{employee_code}",
        "full_name": "{full_name}",
        "date_of_birth": "{date_of_birth}"
    }}

    ---

    ### NHIỆM VỤ ###
    1. Hiểu câu hỏi của người dùng.
    2. Kiểm tra dữ liệu trong `user_data`.
    3. Lọc đúng bảng và đúng bản ghi liên quan.
    4. Trả lời bằng **tiếng Việt trang trọng**, tự nhiên, mạch lạc.
    5. Tuyệt đối không hiển thị dữ liệu thô hoặc cấu trúc bảng trong phản hồi.

    ---

    ### QUY TẮC PHẢN HỒI ###
    - Nếu trong dữ liệu có thông tin phù hợp → trả lời rõ ràng, chính xác.
    - Nếu dữ liệu mâu thuẫn hoặc thiếu → trả lời: **"Không tìm thấy thông tin phù hợp."**
    - Không được giả định thông tin không có.
    - Không được trả lời ngoài phạm vi dữ liệu đã cấp.
    - Phản hồi **dạng chuỗi duy nhất** (str).

    ---

    ### THỜI GIAN HIỆN TẠI ###
    Dưới đây là thông tin thời gian hiện tại có thể dùng trong các nhiệm vụ cần thiết:
    {current_time}

    ---
    """

@dataclass
class Result:
    res:str

class BeeHcmRes(BaseAgent):
    """
    Agents that help generate the final response to the user
    """
    def __init__(self, bot_id: str, litellm_model: OpenAIChatCompletionsModel, user_info: UserInfo, user_data: dict):
        self.bot_id=bot_id
        self._user_info= user_info
        self._user_data= user_data
        self._beehcm_text2sql_agent= create_beehcm_text2sql_agent(
            model= litellm_model,
            user_info= self._user_info
            )
        self.tools=[]
        
    async def run(self, messages, litellm_model, **kwargs) -> AsyncGenerator[ChatCompletionChunk, None]:
        """
        Main entry point for handling BeeHCM chat session.
        Args:
            messages: List of chat messages or str message.
            litellm_model: litellm model is used to call the llm model
        Yields:
            ChatCompletionChunk: Streaming chat response chunks."""
        
        print("Đã vào hàm run")
        current_timestamp = int(time.time())
        result_id = str(uuid4().hex)

        result = await self._agent_executor(
            message=messages,
            agent_context=self._user_info,
            litellm_model=litellm_model
        )
        print("Đã gọi agent excutor")
        final_data=""
        try:
            async for event in result.stream_events():
                if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
                    final_data += event.data.delta
                    yield fake_chunk_from(
                        content=str(event.data.delta),
                        model=str('gpt-4.1'),
                        chat_id=result_id,
                        current_time=current_timestamp,
                        **kwargs
                    )
                # -----------------------
                # When the agent updates, print that
                elif event.type == "agent_updated_stream_event":
                    LOGGER.info(
                        f"Agent updated: {event.new_agent.name}")
                    continue
                # When items are generated, print them
                elif event.type == "run_item_stream_event":
                    if event.item.type == "tool_call_item":
                        LOGGER.info("-- Tool was called")
                    elif event.item.type == "tool_call_output_item":
                        LOGGER.info(
                            f"-- Tool output: {event.item.output}")
        except Exception as e:
            LOGGER.error(f"ERROR agent run: {e}", exc_info=True, stack_info=True)
        finally:
            print("final_data: ",final_data)
            LOGGER.info(f"-- Final output (str): {final_data}")      
    async def _agent_executor(self, message, agent_context: UserInfo, litellm_model):
        """
        Arg:
            messages: List of chat messages or str message.
            agent_context: Context for user information used by the agent
            litellm_model: litellm model is used to call the llm model
        """
        print("\n" + "="*60)
        print("=== Starting _agent_executor ===")
        print(f"Input message: '{message[:100]}{'...' if len(message) > 100 else ''}'")
        print(f"Agent context type: {type(agent_context)}")
        print(f"LiteLLM model type: {type(litellm_model)}")

        # Log agent context details
        if hasattr(agent_context, '__dict__'):
            print(f"Agent context attributes: {list(agent_context.__dict__.keys())}")
        else:
            print("Agent context has no __dict__ attribute")

        print("\n--- Step 1: Loading prompt template ---")
        try:
            BEEHI_HCM_RES = lf.get_prompt(name="BEEHI_HCM_RES")
            print("✅ Successfully fetched BEEHI_HCM_RES from langfuse")
            print("BEEHI_HCM_RES: ", BEEHI_HCM_RES)
            print(f"Prompt type: {type(BEEHI_HCM_RES)}")
            if hasattr(BEEHI_HCM_RES, 'template'):
                print(f"Template length: {len(str(BEEHI_HCM_RES.template)) if BEEHI_HCM_RES.template else 0}")
        except Exception as e:
            print(f"❌ Failed to fetch langfuse prompt: {e}")
            print("Using default instructions")
            BEEHI_HCM_RES = instructions
            print(f"Using default instructions, length: {len(BEEHI_HCM_RES)}")

        print("\n--- Step 2: Compiling instructions with context ---")
        try:
            # Validate context before compilation
            context_data = {
                'user_data': self._user_data,
                'user_name': agent_context.user_name,
                'employee_id': agent_context.employee_id,
                'employee_code': agent_context.employee_code,
                'full_name': agent_context.full_name,
                'date_of_birth': agent_context.date_of_birth,
                'current_time': agent_context.current_time
            }
            print(f"Context data keys: {list(context_data.keys())}")
            print(f"User data type: {type(self._user_data)}")
            print(f"User data length: {len(str(self._user_data)) if self._user_data else 0}")

            compiled_instructions = BEEHI_HCM_RES.compile(**context_data)
            print(f"✅ Instructions compiled successfully")
            print(f"Compiled instructions length: {len(compiled_instructions)}")
        except Exception as e:
            print(f"❌ ERROR compiling instructions: {e}")
            print(f"Error type: {type(e).__name__}")
            import traceback
            print(f"Traceback:\n{traceback.format_exc()}")
            raise

        print("\n--- Step 3: Creating response agent ---")
        try:
            res_agents = Agent(
                name="Response for agent",
                model=litellm_model,
                instructions=compiled_instructions
            )
            print(f"✅ Agent created: {type(res_agents)}")
            print(f"Agent name: {res_agents.name}")
        except Exception as e:
            print(f"❌ ERROR creating agent: {e}")
            print(f"Error type: {type(e).__name__}")
            import traceback
            print(f"Traceback:\n{traceback.format_exc()}")
            raise

        print("\n--- Step 4: Assigning tools to agent ---")
        try:
            res_agents.tools = self.tools
            print(f"✅ Tools assigned to agent")
            print(f"Number of tools: {len(self.tools) if self.tools else 0}")
            if self.tools:
                print(f"Tool names: {[tool.name if hasattr(tool, 'name') else str(tool) for tool in self.tools]}")
        except Exception as e:
            print(f"❌ ERROR assigning tools: {e}")
            raise

        print("\n--- Step 5: Running agent with streamed output ---")
        try:
            start_time = datetime.now()
            print(f"Starting agent with input: '{message[:50]}{'...' if len(message) > 50 else ''}'")

            result = Runner.run_streamed(
                starting_agent=res_agents,
                input=message
            )
            print(f"✅ Streamed runner started in {(datetime.now() - start_time).total_seconds():.2f} seconds")
            print(f"Result type: {type(result)}")

            print("\n=== _agent_executor completed successfully ===")
            print("="*60 + "\n")
            return result
        except Exception as e:
            print(f"❌ ERROR in Runner.run_streamed: {e}")
            print(f"Error type: {type(e).__name__}")
            import traceback
            print(f"Traceback:\n{traceback.format_exc()}")
            raise


async def main():
    bee_test=BeeHcmRes(
        bot_id="xxxxxx"
    )
    user_info_context=UserInfo(
        user_name="dannk.os",
        employee_code="MB1112233",
        email="dannk.os@mbbank.com",
        full_name="Nguyễn Kim Dân",
        job_title="dev",
        current_time="22/10/2025"
    )
    print("Đã setup xong")
    async for chunk in bee_test.run(
        messages="cho tôi biết chức danh của tôi hiện tại",
        userinfo_context=user_info_context
    ):
        print("Chunk nhận được:", chunk)
    print("Đã run")
if __name__ == "__main__":
    asyncio.run(main())

        
