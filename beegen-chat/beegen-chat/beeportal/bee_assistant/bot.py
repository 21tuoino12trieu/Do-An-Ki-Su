import asyncio
from typing import List, Dict, Any

from beeflow.nodes import BasicChainNode
from beeflow.nodes.base_node import INPUT, START, END, OUTPUT
from beeflow.utils.streaming import STREAM_SERVICE
from beeflow.workflow import WorkflowEngine
from beegen.registry.resource_hub import ResourceHub

from beeflow.nodes.primitives.transform.code_node import CodeNode
from beeportal.bee_aio.function import *

from beeportal.bee_aio.chat_state.load_state import LoadStateNode
from beeportal.bee_aio.chat_state.save_state import SaveStateNode
from beeflow.nodes.flow.branch_node import BranchNode


from beegen.utils.common import fake_chunk_from

def merge_response(
      gpt_response: Optional[Any] = None,
      gemini_flash_response: Optional[Any] = None,
      gemini_pro_response: Optional[Any] = None,
  ) -> Dict[str, Any]:
      """
      Merge response từ các LLM nodes.
      Lấy kết quả đầu tiên khác None.
      """
      for resp in [gpt_response, gemini_flash_response, gemini_pro_response]:
          if resp is not None:
              return {"result": resp}
      return {"result": None}

class BeeAssistant:
    def __init__(self, bot_id: str):
        self.bot_id = bot_id
        self._workflow_cache: Dict[str, Any] = {}       # cache theo resource_key

        mongo_engine = ResourceHub.self().sync_mongo("aicenter-chatbot")
        bot_info = mongo_engine._find_one(
            collection_name="botinfo", query={"_id": self.bot_id}
        )
        self.name = bot_info.get("data", {}).get("name", None)
        self._build_flow()

    def _build_flow(self):
        with WorkflowEngine(
            name="beeAssistant",       
            description="Chatbot trợ lí hỗ trợ công việc"
        ) as beeAssistant:

            load_state = LoadStateNode(
                name="load_state",
                inputs={
                    "session_id":         INPUT,
                    "messages":           INPUT,
                    "number_of_messages": 20
                },
            )

            branch_model = BranchNode(
                name= "select_model",
                inputs= {
                    "resource_key": INPUT,
                },
                cases= {
                    "resource_key == 'gemini-3.5-flash'": "llm_gemini_flash",
                    "resource_key == 'gemini-3.1-pro'": "llm_gemini_pro",
                },
                default="llm_gpt_response",
            )

            llm_gpt_response = BasicChainNode(
                name="llm_gpt_response",
                resource_key="gpt-5.2-chat",
                llm_configs={"reasoning_effort": "none"},
                system_prompt="""
                    Bạn là trợ lý AI thông minh, thân thiện và hữu ích.
                    Nhiệm vụ của bạn là trả lời câu hỏi của người dùng một cách chính xác, ngắn gọn và dễ hiểu.

                    Nguyên tắc:
                    - Luôn trả lời bằng ngôn ngữ mà người dùng đang sử dụng (tiếng Việt).
                    - Nếu không biết câu trả lời, hãy thành thật nói không biết thay vì bịa đặt.
                    - Giữ giọng điệu lịch sự, chuyên nghiệp nhưng gần gũi.
                    - Dựa vào lịch sử hội thoại để trả lời có ngữ cảnh, tránh lặp lại thông tin đã nói.
                """,
                user_prompt="""
                    Lịch sử hội thoại:
                    {conversation}

                    Câu hỏi mới nhất của người dùng: {query}
                """,
                inputs={
                    "query":        {load_state: "origin_query"},
                    "conversation": {load_state: "conversation"},
                },
                stream=True
            )

            llm_gemini_flash = BasicChainNode(
                name="llm_gemini_flash",
                resource_key="gemini-3.5-flash-chat",
                llm_configs={"reasoning_effort": "none"},
                system_prompt="""
                    Bạn là trợ lý AI thông minh, thân thiện và hữu ích.
                    Nhiệm vụ của bạn là trả lời câu hỏi của người dùng một cách chính xác, ngắn gọn và dễ hiểu.

                    Nguyên tắc:
                    - Luôn trả lời bằng ngôn ngữ mà người dùng đang sử dụng (tiếng Việt).
                    - Nếu không biết câu trả lời, hãy thành thật nói không biết thay vì bịa đặt.
                    - Giữ giọng điệu lịch sự, chuyên nghiệp nhưng gần gũi.
                    - Dựa vào lịch sử hội thoại để trả lời có ngữ cảnh, tránh lặp lại thông tin đã nói.
                """,
                user_prompt="""
                    Lịch sử hội thoại:
                    {conversation}

                    Câu hỏi mới nhất của người dùng: {query}
                """,
                inputs={
                    "query":        {load_state: "origin_query"},
                    "conversation": {load_state: "conversation"},
                },
                stream=True
            )

            llm_gemini_pro = BasicChainNode(
                name="llm_gemini_pro",
                resource_key="gemini-3.1-pro-chat",
                llm_configs={"reasoning_effort": "none"},
                system_prompt="""
                    Bạn là trợ lý AI thông minh, thân thiện và hữu ích.
                    Nhiệm vụ của bạn là trả lời câu hỏi của người dùng một cách chính xác, ngắn gọn và dễ hiểu.

                    Nguyên tắc:
                    - Luôn trả lời bằng ngôn ngữ mà người dùng đang sử dụng (tiếng Việt).
                    - Nếu không biết câu trả lời, hãy thành thật nói không biết thay vì bịa đặt.
                    - Giữ giọng điệu lịch sự, chuyên nghiệp nhưng gần gũi.
                    - Dựa vào lịch sử hội thoại để trả lời có ngữ cảnh, tránh lặp lại thông tin đã nói.
                """,
                user_prompt="""
                    Lịch sử hội thoại:
                    {conversation}

                    Câu hỏi mới nhất của người dùng: {query}
                """,
                inputs={
                    "query":        {load_state: "origin_query"},
                    "conversation": {load_state: "conversation"},
                },
                stream=True
            )

            code_merge_response = CodeNode(
                name="code_merge_response",
                code_fn=merge_response,
                inputs={
                    "gpt_response":  llm_gpt_response["content"],
                    "gemini_flash_response": llm_gemini_flash["content"],
                    "gemini_pro_response": llm_gemini_pro["content"]
                },
                return_keys=["result: Any"]
            )

            code_collect_response = CodeNode(
                name="code_collect_response",
                code_fn=collect_response,
                inputs={
                    "result":     code_merge_response,
                    "session_id": INPUT
                },
                return_keys=["bot_response: str", "redis_key: str"]
            )

            save_state = SaveStateNode(
                name="save_state",
                ttl_seconds=300,
                inputs={
                    "merged_messages": {load_state: "merged_messages"},
                    "bot_response":    {code_collect_response: "bot_response"},
                    "session_id":      INPUT["session_id"],
                    "redis_key":       code_collect_response,
                }
            )

            load_state >> branch_model >> [
                llm_gemini_flash,
                llm_gemini_pro,
                llm_gpt_response
            ]  >> code_merge_response >> code_collect_response >> save_state >> END

        beeAssistant.compile()
        self.workflow = beeAssistant

    async def run(
        self,
        messages: List[Dict],
        client_message_id: str,
        session_id: str,
        metadata: Dict = {},
        **kwargs,
    ):
        model_key    = metadata.get("model", "gemini-3.5-flash")

        try:
            asyncio.create_task(
                self.workflow.run(
                    request_id=client_message_id,
                    inputs={
                        "messages":   messages,
                        "session_id": session_id,
                        "resource_key": model_key
                    },
                    session_id=session_id,
                )
            )

            async for channel_name in STREAM_SERVICE.get_channels(client_message_id):
                async for chunk in STREAM_SERVICE.get(
                    client_message_id, channel_name, json_mode=False
                ):
                    yield chunk

        except Exception as e:
            import traceback
            traceback.print_exc()
            yield fake_chunk_from(
                content="Xin lỗi, đã xảy ra lỗi khi xử lý yêu cầu của bạn. Vui lòng thử lại sau.",
                model="error",
            )
# ---------------------------------------------------------------------------
# Local test (fake data)
# ---------------------------------------------------------------------------

async def main():
    bot = BeeAssistant("cea24abe-c015-48e4-8ddc-84389efc7e50")
    import uuid

    dialogue_id       = "test"
    client_message_id = str(uuid.uuid4())

    async for chunk in bot.run(
        messages=[
                {
                "role": "user",
                # "content": "Khách hàng vay mua nhà đất tài sản hình thành từ vốn vay có nguồn thu từ lương hồ sơ cần cung cấp cho ngân hàng bao gồm gì",
                "content": "hello, hôm nay là thứ mấy"
            }
        ],
        
        session_id=dialogue_id,
        client_message_id=client_message_id,
        role= ["QM", "MY VIP", "SPK", "CRU", "APP", "Team 2", "Team 3", "L1", "L2", "L3"],
        metadata={ 
            "model": "gpt-5.2"
                },
        ):
        # print(f"{chunk.choices[0].delta.content or ''}", end="")
        pass

    await asyncio.sleep(4)


if __name__ == "__main__":
    asyncio.run(main())