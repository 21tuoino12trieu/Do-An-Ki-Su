import asyncio
from typing import List, Dict, Any

from beeflow.nodes import BasicChainNode, BranchNode
from beeflow.nodes.base_node import INPUT, START, END, OUTPUT
from beeflow.utils.streaming import STREAM_SERVICE
from beeflow.workflow import WorkflowEngine
from beegen.registry.resource_hub import ResourceHub

from beegenerate.llms.llm_response import fake_chunk_from
from beeflow.nodes.templates.agent_executor_node import AgentExecutorNode
from beeflow.nodes.primitives.ai.llm_node import LLMNode
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beeportal.bee_aio.function import *
from beeportal.bee_aio.agent_retrieval_node import AgentRetrievalNode

from beeportal.bee_aio.chat_state.load_state import LoadStateNode
from beeportal.bee_aio.chat_state.save_state import SaveStateNode
from beeportal.bee_aio.beegen_load.beegen_executor import BeegenExecutorNode, get_bot_manager
from beeportal.utils import PROMPTS

# ---------------------------------------------------------------------------
# Main BeeAIO class
# ---------------------------------------------------------------------------

class BeeAIO:
    def __init__(self, bot_id: str):
        self.bot_id = bot_id

        # Truy xuất thông tin bot từ Mongo khi khởi tạo
        mongo_engine = ResourceHub.self().sync_mongo("aicenter-chatbot")
        bot_info = mongo_engine._find_one(
            collection_name="botinfo", query={"_id": self.bot_id}
        )
        self.name       = bot_info.get("data", {}).get("name", None)
        raw_bots = get_bot_manager()

        self.available_workflows = {}
        for bid, entry in raw_bots.items():
            bot = entry.get('bot', entry) if isinstance(entry, dict) else entry
            if hasattr(bot, 'workflow'):
                self.available_workflows[bid] = bot

        self.available_bots = raw_bots

        self._build_flow()

    def _build_flow(self):
        with WorkflowEngine(
            name="beeAIO",
            description="Chatbot điều phối tất cả trong 1 – luồng mới"
        ) as beeAIO:

            # ------------------------------------------------------------------
            # BƯỚC 1: Load State – lấy lịch sử chat từ Redis/Mongo
            # ------------------------------------------------------------------
            load_state = LoadStateNode(
                name="load_state",
                inputs={
                    "session_id": INPUT,
                    "messages": INPUT,
                },
            )

            # ------------------------------------------------------------------
            # BƯỚC 2: Agent Router – tìm top-k candidates phù hợp
            # ------------------------------------------------------------------
            agent_retrieval = AgentRetrievalNode(
                name="agent_retrieval",
                inputs={
                    "query": {load_state: "origin_query"},
                    "metadata":   INPUT,
                },
            )

            # ------------------------------------------------------------------
            # BƯỚC 3: Content filtering
            # ------------------------------------------------------------------
            llm_guardrails = BasicChainNode(
                name="llm_guardrails",
                resource_key="gpt-4.1",
                llm_configs={"reasoning_effort": "none"},
                system_prompt= PROMPTS["BEEAIO:GUARDRAILS"],
                user_prompt="""
                    <conversation_history> 
                    {conversation}
                    </conversation_history>

                    <user_message>
                    {query}
                    </user_message>
                """,
                inputs={
                    "query":         {load_state: "origin_query"},
                    "conversation":  {load_state: "conversation"},   # ← last 3 turns từ LoadStateNode
                },
                parser="json",
                extract_schema=[
                    "category: str",
                ]
            )

            # ------------------------------------------------------------------
            # BƯỚC 3: Orchestration – LLM chọn agent phù hợp
            # ------------------------------------------------------------------
            orchestration_agent = BasicChainNode(
                name="orchestration_agent",
                resource_key="gpt-4.1",
                llm_configs={"reasoning_effort": "none"},
                system_prompt="""
                    You are a supervisor agent responsible for routing user messages to the correct agent.
                    You must choose the most appropriate agent from the provided agent list.

                    Rules:
                    1. Only choose agents from the provided list below.
                    2. If multiple agents match, choose the most specific one.
                    3. If no agent is suitable, return "missing_info_prompt".
                    4. If intent is ambiguous between agents, ask for clarification.

                    ## Available Agents
                    {agent_context}

                    You must return JSON only.

                    Output format:
                    If found:
                    {{ "selected_agent": "<bot_id>" }}
                    If missing:
                    {{ "missing_info_prompt": "<apology + scope>" }}
                    If ambiguous:
                    {{ "clarify_prompt": "<clarification question>" }}

                    ## Examples

                    Example 1:
                    Available Agents:
                    - bot_id: "ahjsah12345haskdf14"| description: "Agent hỗ trợ thông tin về vay tín dụng, lãi suất, điều kiện vay"
                    - bot_id: "154078912980512908"| description: "Agent hỗ trợ thông tin sản phẩm tiền gửi, lãi suất tiết kiệm"
                    - bot_id: "asfar321532jkhn25"| description: "Agent chào hỏi, giới thiệu chung về ngân hàng"
                    Query: "Tôi muốn vay mua nhà 2 tỷ thì cần những gì?"
                    Output: {{ "selected_agent": "ahjsah12345haskdf14" }}

                    Example 2:
                    Available Agents:
                    - bot_id: "ahjsah12345haskdf14"| description: "Agent hỗ trợ thông tin về vay tín dụng, lãi suất, điều kiện vay"
                    - bot_id: "154078912980512908"| description: "Agent hỗ trợ thông tin sản phẩm tiền gửi, lãi suất tiết kiệm"
                    - bot_id: "asfar321532jkhn25"| description: "Agent chào hỏi, giới thiệu chung về ngân hàng"
                    User Query: "Gửi tiết kiệm 100 triệu lãi suất bao nhiêu?"
                    Output: {{ "selected_agent": "deposit_v1" }}

                    Example 3 (missing — general chat, no matching agent):
                    Available Agents:
                    - bot_id: "ahjsah12345haskdf14"| description: "Agent hỗ trợ thông tin về vay tín dụng, lãi suất, điều kiện vay"
                    - bot_id: "hlfasfh214dahjuiort"| description: "Agent hỗ trợ tra cứu chính sách MB, pháp luật"
                    User Query: "soạn giúp tôi tin nhắn chúc mừng sinh nhật khách hàng dư nợ đang quản lý"
                    Output: {{ "missing_info_prompt": "Xin lỗi, tôi chỉ hỗ trợ các câu hỏi về vay tín dụng và chính sách MB. Yêu cầu soạn tin nhắn chúc mừng sinh nhật không thuộc phạm vi hỗ trợ." }}

                    Example 4 (missing — greeting unrelated to any agent):
                    Available Agents:
                    - bot_id: "ahjsah12345haskdf14"| description: "Agent hỗ trợ thông tin về vay tín dụng, lãi suất, điều kiện vay"
                    - bot_id: "hlfasfh214dahjuiort"| description: "Agent hỗ trợ tra cứu chính sách MB, pháp luật"
                    User Query: "chào bạn, hôm nay thế nào?"
                    Output: {{ "missing_info_prompt": "Xin chào! Tôi là trợ lý ảo hỗ trợ các câu hỏi về vay tín dụng và chính sách MB. Bạn cần tôi giúp gì về các lĩnh vực này?" }}

                    Example 5 (ambiguous):
                    Available Agents:
                    - bot_id: "ahjsah12345haskdf14"| description: "Agent hỗ trợ thông tin về vay tín dụng, lãi suất, điều kiện vay"
                    - bot_id: "jjvjurndjkk3215325nn"| description: "Agent hỗ trợ chính sách cho vay, quy định nội bộ"
                    User Query: "cho tôi hỏi về chính sách cho vay"
                    Output: {{ "clarify_prompt": "Bạn muốn hỏi về điều kiện vay cụ thể (lãi suất, hạn mức) hay chính sách/quy định nội bộ về cho vay?" }}

                    Example 6 (must not classify unmatched intent into a vaguely related agent):
                    Available Agents:
                    - bot_id: "ahjsah12345haskdf14"| description: "Agent hỗ trợ thông tin về vay tín dụng, lãi suất, điều kiện vay"
                    - bot_id: "154078912980512908"| description: "Agent hỗ trợ thông tin sản phẩm tiền gửi, lãi suất tiết kiệm"
                    User Query: "soạn giúp tôi email cảm ơn khách hàng thân thiết"
                    Output: {{ "missing_info_prompt": "Xin lỗi, tôi chỉ hỗ trợ các câu hỏi về vay tín dụng và sản phẩm tiền gửi. Yêu cầu soạn email cảm ơn không thuộc phạm vi hỗ trợ của tôi." }}
                """,
                user_prompt="""
                    Conversation history (last 3 turns):
                    {conversation}

                    Latest query: {query}
                """,
                inputs={
                    "query":         {load_state: "origin_query"},
                    "conversation":  {load_state: "conversation"},   # ← last 3 turns từ LoadStateNode
                    "agent_context": {agent_retrieval: "agent_context"},
                },
                parser="json",
                extract_schema=[
                    "selected_agent: str",
                    "missing_info_prompt: str",
                    "clarify_prompt: str",
                ]
            )
            # ------------------------------------------------------------------
            # BƯỚC 4: Branch kết quả routing
            # ------------------------------------------------------------------

            code_map_guardrail_response = CodeNode(
                name="code_map_guardrail_response",
                code_fn=map_guardrail_category_response,
                inputs={
                    "category": {llm_guardrails: "category"},
                },
                return_keys=["response: str"],
            )

            branch_content_filtering = BranchNode(
                name="branch_content_filtering",
                inputs={
                    "category": {llm_guardrails: "category"},
                },
                cases={
                    "category is not null": "code_map_guardrail_response",
                },
                default="branch_routing"
            )

            llm_guardrail_response = LLMNode(
                name="llm_guardrail_response",
                resource_key="fake",
                instant_response=True,
                inputs={"response": {code_map_guardrail_response: "response"},
                        "custom_data": prepare_bot_id(self.bot_id)
                        },
                stream=True
            )

            branch_routing = BranchNode(
                name="branch_routing",
                inputs={
                    "selected_agent":      orchestration_agent,
                    "missing_info_prompt": orchestration_agent,
                    "clarify_prompt":      orchestration_agent,
                },
                cases={
                    "selected_agent is not null": "code_postprocess_routing",
                    "clarify_prompt is not null": "llm_clarify_prompt",
                },
                default="llm_missing_info_prompt"
            )

            # Trả về câu hỏi làm rõ (intent mơ hồ giữa 2 agent)
            llm_clarify_prompt = LLMNode(
                name="llm_clarify_prompt",
                resource_key="fake",
                instant_response=True,
                inputs={"response": {orchestration_agent: "clarify_prompt"},
                        "custom_data": prepare_bot_id(self.bot_id)
                        },
                stream=True
            )

            # Trả về thông báo ngoài phạm vi
            llm_missing_info_prompt = LLMNode(
                name="llm_missing_info_prompt",
                resource_key="fake",
                instant_response=True,
                inputs={"response": {orchestration_agent: "missing_info_prompt"},
                        "custom_data": prepare_bot_id(self.bot_id)
                        },
                stream=True
            )

            # ------------------------------------------------------------------
            # BƯỚC 5: Postprocess routing – xác định agent_type + workflow_name
            # ------------------------------------------------------------------

            code_postprocess_routing = CodeNode(
                name="code_postprocess_routing",
                code_fn=get_agent_by_bot_id,
                inputs={
                    "agents": {orchestration_agent: "selected_agent"},
                    "metadata":   INPUT,
                },
                return_keys=["extract_bot_id: Dict[str, str]", "executor_type: str"],
            )

            llm_status_message = LLMNode(
                name="llm_status_message",
                resource_key="fake",
                instant_response=True,
                inputs={"response": " ",
                        "custom_data": {code_postprocess_routing: "extract_bot_id"}
                        },
                stream=True
            )

            # Chuẩn bị input cho beeflow workflow
            code_get_input_workflow = CodeNode(
                name="code_get_input_workflow",
                code_fn=get_input_workflow,
                inputs={
                    "messages":       {load_state: "merged_messages"},
                    "session_id":     INPUT["session_id"],
                    "role_ids":       ["L1", "QM", "CHUYÊN VIÊN"],
                },
                return_keys=["workflow_inputs: Dict[str, str]"]
            )

            # Convert workflow_inputs sang format cho beegen_executor
            code_convert_to_beegen = CodeNode(
                name="code_convert_to_beegen",
                code_fn=convert_to_beegen_input,
                inputs={
                    "workflow_inputs": code_get_input_workflow,
                    "role": INPUT["role"],
                    "bot_id": {orchestration_agent: "selected_agent"}
                },
                return_keys=["bot_inputs: Dict[str, Any]"]
            )

            # Thực thi beeflow agent
            agent_executor = AgentExecutorNode(
                name="agent_executor",
                available_workflows=self.available_workflows,
                inputs={
                    "workflow_name":   {orchestration_agent: "selected_agent"},
                    "workflow_inputs": code_get_input_workflow,
                },
                outputs = {"content": OUTPUT}
            )

            # Thực thi beegen bot (Bot-based executor)
            beegen_executor = BeegenExecutorNode(
                name="beegen_executor",
                inputs={
                    "bot_id":      {orchestration_agent: "selected_agent"},
                    "bot_inputs":  code_convert_to_beegen,
                }
            )

            # Branch phân loại executor theo executor_type
            branch_executor = BranchNode(
                name="branch_executor",
                inputs={
                    "executor_type": code_postprocess_routing,
                },
                cases={
                    "executor_type == 'beeflow'": "agent_executor",
                    "executor_type == 'beegen'": "code_convert_to_beegen",
                },
                default="beegen_executor"
            )

            # Merge response từ 2 executor
            code_merge_executor_response = CodeNode(
                name="code_merge_executor_response",
                code_fn=merge_executor_response,
                inputs={
                    "agent_result":  agent_executor["content"],
                    "beegen_result": beegen_executor["result"],
                },
                return_keys=["result: Any"]
            )

            code_collect_response = CodeNode(
                name="code_collect_response",
                code_fn=collect_response,
                inputs={
                    "result": code_merge_executor_response,
                    "session_id": INPUT
                },
                return_keys=["bot_response: str", "redis_key: str"]
            )

            # Save State sau khi execute
            save_state = SaveStateNode(
                name="save_state",
                ttl_seconds=300,
                inputs={
                    "merged_messages": {load_state: "merged_messages"},
                    "bot_response": {code_collect_response: "bot_response"},
                    "session_id": INPUT["session_id"],
                    "redis_key": code_collect_response,
                }
            )

            # ------------------------------------------------------------------
            # Workflow
            # ------------------------------------------------------------------
            # Load state đầu tiên
            load_state >> agent_retrieval >> [orchestration_agent,
                                              llm_guardrails]
            llm_guardrails >> branch_content_filtering

            branch_content_filtering >> [branch_routing,
                                         code_map_guardrail_response]
            code_map_guardrail_response >> llm_guardrail_response >> END

            branch_routing >> [llm_clarify_prompt,
                               code_postprocess_routing,
                               llm_missing_info_prompt]

            llm_clarify_prompt      >> END
            llm_missing_info_prompt >> END

            # Branch phân loại executor, sau đó tới collect response
            code_postprocess_routing >> [code_get_input_workflow,
                                         llm_status_message] >> branch_executor >> [agent_executor, 
                                                                                    code_convert_to_beegen]
                                          
            code_convert_to_beegen >> beegen_executor
            [agent_executor,
             beegen_executor] >> code_merge_executor_response >> code_collect_response >> save_state >> END

        beeAIO.compile()
        self.workflow = beeAIO

    async def run(
        self,
        messages: List[Dict],
        client_message_id: str,
        session_id: str,
        username: str,
        metadata: Dict = {},
        **kwargs,
    ):
        """Main pipeline theo luồng mới."""
        try:
            # Chạy workflow với inputs (load/save state đã implement trong workflow)
            asyncio.create_task(
                self.workflow.run(
                    request_id=client_message_id,
                    inputs={
                        "messages":     messages,
                        "session_id":   session_id,
                        "metadata":     metadata,
                        # "bot_id":         kwargs.get("bot_id", []),
                        "role":         kwargs.get("role", []),
                    },
                    session_id=session_id,
                    user_id = username
                )
            )

            # Yield chunks từ STREAM_SERVICE
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
    bot = BeeAIO("85e36d75-1c66-4409-aef1-ebecac1d674a")
    import uuid

    dialogue_id       = "test"
    client_message_id = str(uuid.uuid4())

    async for chunk in bot.run(
        messages=[
                {
                "role": "user",
                # "content": "Khách hàng vay mua nhà đất tài sản hình thành từ vốn vay có nguồn thu từ lương hồ sơ cần cung cấp cho ngân hàng bao gồm gì",
                "content": "Cho tôi danh sách sản phẩm deposit mà bạn có?"
                # "content": "hello, hôm nay là thứ mấy"
            }
        ],
        
        session_id=dialogue_id,
        client_message_id=client_message_id,
        role= ["QM", "MY VIP", "SPK", "CRU", "APP", "Team 2", "Team 3", "L1", "L2", "L3"],
        metadata={
            "agents": [
                {
                    "bot_id":      "347f7a6e-83d2-4cfa-9e85-6bc080c234c4",
                    # "name":        "deposit",
                    "description": "Bot deposit chuyên cung cấp thông tin chính xác và chi tiết về các sản phẩm gửi tiền (deposit), bao gồm lãi suất, điều kiện gửi tiền và các chính sách liên quan đến huy động vốn cho cán bộ nhân viên.",
                    # "keyword":    ["vay", "thẻ", "tiết kiệm", "app MB", "KHCN"],
                    # "role":        ["QM", "MY VIP", "SPK", "CRU", "APP"],
                },
                {
                    "bot_id":      "dfb5a874-b980-4275-bd34-0ddbd1acefdf",
                    # "name":        "AI_Enterprise_KHCN",
                    "description": "Agent chuyên trả lời câu hỏi liên quan đến policy sản phẩm vay, tín dụng",
                    "keyword":    ["policy", "tín dụng", "điều kiện vay", "quy định"],
                    # "role":        ["L1", "Team 2", "Team 3"],
                },
                {
                    "bot_id":      "269c75a7-b3dc-4a34-ae6f-a337ad7e8d34",
                    # "name":        "BeeRM",
                    "description": "Agent hỗ trợ tra cứu chính sách của MB, pháp luật",
                    "keyword":    ["chính sách", "pháp luật"],
                    # "role":        ["L1"],
                },
                {
                    "bot_id":      "a1b2c3d4-0005-0005-0005-000000000005",
                    # "name":        "CHATBOT_RM/UB",
                    "description": "Agent hỗ trợ doanh nghiệp về thanh toán quốc tế, L/C, chuyển tiền ngoại tệ",
                    "keyword":    ["doanh nghiệp", "thanh toán quốc tế", "chuyển tiền ngoại tệ", "L/C"],
                    # "role":        ["L1", "L2", "L3"],
                },
            ]
        },
    ):
        print(f"{chunk.choices[0].delta.content or ''}", end="")

    await asyncio.sleep(4)


if __name__ == "__main__":
    asyncio.run(main())
