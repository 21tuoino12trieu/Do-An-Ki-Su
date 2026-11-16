# At the top of your main file
import asyncio
from typing import Dict, List

# --- Core Beeflow Imports ---
from beegen.utils.common import fake_chunk_from
from beegen.registry.resource_hub import RESOURCE_HUB
from beegen.prompts.prompt_manager import PromptManager
from beegen.loggings.loggers import LOGGER
from beeflow.workflow import WorkflowEngine
from beeflow.nodes.templates.basic_chain_node import BasicChainNode
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beeflow.nodes.graph.graph_node import GraphNode
from beeflow.nodes.flow.branch_node import BranchNode
from beeflow.nodes.base_node import END, START, OUTPUT, INPUT
from beeflow.nodes.primitives.memory.mem0_node import Mem0Node, Mem0Operation
from beeflow.nodes.templates.react_agent_node import ReactAgentNode
from beeflow.utils.streaming import STREAM_SERVICE

# --- Utils Imports ---
from examples.utils.nlp import annotate_query, init_query, extract_latest_bot_response, prepare_mem0_data

# --- Tool Imports (Giả định bạn đã có tool này) ---
# Bạn cần đảm bảo đã define calc_math_expression ở file tools tương ứng
from examples.agent.tools.math_tools import calc_math_expression 

PROMPTS = PromptManager("text2sql")

class FinanceCalculatorBot:
    def __init__(self, bot_id: str):
        self.bot_id = bot_id
        # mongo_engine = RESOURCE_HUB.sync_mongo("aicenter-chatbot")
        # result = mongo_engine._find_one(
        #     collection_name="botinfo", query={"_id": self.bot_id})
        # self.name = result.get('data', {'name': {}}).get('name', None)
        # self.config = result.get('data', {'metadata': {}}).get('metadata', {})
        # self.definition = self.config.get(
        #     'system_prompt', "Bạn là trợ lý tài chính đa năng.")
        self.definition = "Bạn là trợ lý tài chính đa năng."
        self._build_flow()

    def _build_flow(self):
        with WorkflowEngine(
            name="finance_calculator",
            description="Luồng tính toán tài chính đa domain",
            langfuse="text2sql"
        ) as wf:
            helper_math = CodeNode(name="calc_math_expression", code_fn=calc_math_expression, description="Máy tính toán học đa năng (Cộng, trừ, nhân, chia, biểu thức). Luôn dùng cái này cho tính toán trung gian.")
            loans_math = CodeNode(name="loans_calc_math_expression", code_fn=calc_math_expression, description="Máy tính toán học đa năng (Cộng, trừ, nhân, chia, biểu thức). Luôn dùng cái này cho tính toán trung gian.")
            savings_math = CodeNode(name="savings_calc_math_expression", code_fn=calc_math_expression, description="Máy tính toán học đa năng (Cộng, trừ, nhân, chia, biểu thức). Luôn dùng cái này cho tính toán trung gian.")
            salary_math = CodeNode(name="salary_calc_math_expression", code_fn=calc_math_expression, description="Máy tính toán học đa năng (Cộng, trừ, nhân, chia, biểu thức). Luôn dùng cái này cho tính toán trung gian.")
            corporate_math = CodeNode(name="corporate_calc_math_expression", code_fn=calc_math_expression, description="Máy tính toán học đa năng (Cộng, trừ, nhân, chia, biểu thức). Luôn dùng cái này cho tính toán trung gian.")

            # --- 1. Pre-processing Nodes ---
            _init_query = CodeNode(name="init_query", code_fn=init_query, inputs={"messages": INPUT})
            
            _annotate_query = CodeNode(name="annotate_query", code_fn=annotate_query, inputs={"origin_query": _init_query})
            
            _get_last_response = CodeNode(name="get_last_response", code_fn=extract_latest_bot_response, inputs={"messages": INPUT})

            # --- 2. Classifier Node (Phân loại Domain) ---
            # Prompt này cần được định nghĩa trong PromptManager để trả về field 'domain'
            # Các giá trị domain: 'loans', 'savings', 'corporate', 'salary', 'helper_math', 'chit_chat'
            llm_domain_classifier = BasicChainNode(
                name="llm_domain_classifier",
                resource_key="gpt-4.1", 
                parser="yaml",
                user_prompt=PROMPTS["FINANCE:CLASSIFY_DOMAIN_PROMPT"], 
                extract_schema=["rewrite: str", "domain: str"],
                inputs={"query": _annotate_query, "conversation": _init_query},
                stream=True
            )

            # --- 3. Memory Search ---
            mem0_search = Mem0Node(
                name="mem0_search",
                resource_key="mem0",
                operation=Mem0Operation.SEARCH,
                inputs={
                    "query": {llm_domain_classifier: "rewrite"},
                    "session_id": {INPUT: "session_id"},
                    "user_id": {INPUT: "user_id"},
                }
            )

            # --- 4. Router (Branching) ---
            domain_router = BranchNode(
                name="domain_router",
                cases={
                     "domain == 'chit_chat'": "llm_chit_chat_response",
                     "domain == 'loans'": "agent_loans",
                     "domain == 'savings'": "agent_savings",
                     "domain == 'corporate'": "agent_corporate",
                     "domain == 'salary'": "agent_salary",
                     "domain == 'helper_math'": "agent_helper_math",
                },
                inputs={
                    "domain": {llm_domain_classifier: "domain"}
                },
                default="agent_helper_math" # Fallback về toán cơ bản
            )

            # --- 5. Handlers & Agents ---

            # A. Chit Chat Handler
            llm_chit_chat_response = BasicChainNode(
                name="llm_chit_chat_response",
                resource_key="qwen-instruct-chat",
                user_prompt=PROMPTS["TEXT2QUERY:CHIT_CHAT_PROMPT"],
                inputs={"definition": self.definition},
                stream=True,
                outputs={"content": OUTPUT}
            )

            # B. Domain Agents (All have calc_math_expression)
            
            # Group 1: Loans & Credit
            agent_loans = ReactAgentNode(
                name="agent_loans",
                resource_key="gpt-4.1",
                tools=[loans_math], # Add thêm tool tính lãi vay nếu có
                max_iterations=5,
                context_prompt="""Bạn là chuyên gia về Tín dụng & Vay vốn. 
                Nhiệm vụ: Tính toán lịch trả nợ, lãi suất vay, hạn mức tín dụng.
                Luôn sử dụng tool calc_math_expression để tính toán chính xác.""",
                inputs={"query": {llm_domain_classifier: "rewrite"}},
                outputs={"Answer": {OUTPUT: "content"}}
            )

            # Group 2: Savings & Investment
            agent_savings = ReactAgentNode(
                name="agent_savings",
                resource_key="gpt-4.1",
                tools=[savings_math], # Add thêm tool dự phóng lãi tiết kiệm
                max_iterations=5,
                context_prompt="""Bạn là chuyên gia về Tiết kiệm & Đầu tư.
                Nhiệm vụ: Tính lãi suất tiết kiệm, lợi nhuận đầu tư, lãi kép.
                Luôn sử dụng tool calc_math_expression để tính toán chính xác.""",
                inputs={"query": {llm_domain_classifier: "rewrite"}},
                outputs={"Answer": OUTPUT}
            )

            # Group 3: Corporate Finance
            agent_corporate = ReactAgentNode(
                name="agent_corporate",
                resource_key="gpt-4.1",
                tools=[corporate_math],
                max_iterations=5,
                context_prompt="""Bạn là chuyên gia Tài chính Doanh nghiệp & Dự án.
                Nhiệm vụ: Tính toán các chỉ số NPV, IRR, ROI, báo cáo tài chính.
                Luôn sử dụng tool calc_math_expression để tính toán chính xác.""",
                inputs={"query": {llm_domain_classifier: "rewrite"}},
                outputs={"Answer": OUTPUT}
            )

            # Group 4: Salary & Tax (VN Specific)
            agent_salary = ReactAgentNode(
                name="agent_salary",
                resource_key="gpt-4.1",
                tools=[salary_math],
                max_iterations=5,
                context_prompt="""Bạn là chuyên gia Lương & Thuế tại Việt Nam.
                Nhiệm vụ: Tính lương Gross/Net, Thuế TNCN (PIT), Bảo hiểm xã hội theo luật pháp Việt Nam hiện hành.
                Lưu ý các mức giảm trừ gia cảnh và biểu thuế lũy tiến.
                Luôn sử dụng tool calc_math_expression để tính toán chính xác.""",
                inputs={"query": {llm_domain_classifier: "rewrite"}},
                outputs={"Answer": OUTPUT}
            )

            # Group 5: Helper Math
            agent_helper_math = ReactAgentNode(
                name="agent_helper_math",
                resource_key="gpt-4.1",
                tools=[helper_math],
                max_iterations=5,
                context_prompt="""Bạn là trợ lý toán học bổ trợ.
                Nhiệm vụ: Giải quyết các bài toán thông thường, thống kê cơ bản hoặc chuyển đổi đơn vị.
                Luôn sử dụng tool calc_math_expression để tính toán chính xác.""",
                inputs={"query": {llm_domain_classifier: "rewrite"}},
                outputs={"Answer": OUTPUT}
            )

            # --- 6. Post-processing (Memory Save) ---
            
            # Gom chung output từ các agent để xử lý lưu memory 1 lần (dùng CodeNode để merge logic nếu cần)
            # Ở đây ta giả lập việc chuẩn bị data cho memory sau khi có response từ bất kỳ nhánh nào
            
            _prepare_mem0_save = CodeNode(
                name="prepare_mem0_save",
                code_fn=prepare_mem0_data,
                inputs={
                    "rewrite": {llm_domain_classifier: "rewrite"},
                    "session_id": {INPUT: "session_id"},
                    # Lấy output từ bất kỳ nhánh nào đã chạy (Flow engine sẽ tự map giá trị của nhánh active)
                    # "response_content": {
                    #     llm_chit_chat_response: "content",
                    #     agent_loans: "content",
                    #     agent_savings: "content",
                    #     agent_corporate: "content",
                    #     agent_salary: "content",
                    #     agent_helper_math: "content"
                    # }
                },
                return_keys={"dialogue: list[dict]"}
            )

            mem0_add_data = Mem0Node(
                name="mem0_add_data",
                resource_key="mem0",
                operation=Mem0Operation.ADD,
                inputs={
                    "messages": {_prepare_mem0_save: "dialogue"},
                    "session_id": INPUT,
                    "custom_fact_extraction_prompt": PROMPTS["TEXT2QUERY:CUSTOM_FACT_EXTRACTION_PROMPT"],
                    "user_id": {INPUT: "user_id"},
                }
            )

            # --- 7. Linking Nodes ---
            START >> _init_query >> _annotate_query >> _get_last_response >> llm_domain_classifier >> mem0_search >> domain_router
            
            # Routing
            domain_router >> [llm_chit_chat_response, agent_loans, agent_savings, agent_corporate, agent_salary, agent_helper_math]

            # Converge to Memory Save
            [llm_chit_chat_response, agent_loans, agent_savings, agent_corporate, agent_salary, agent_helper_math] >> _prepare_mem0_save >> mem0_add_data >> END

        wf.compile()
        self.workflow = wf

    async def run(self, messages: List[Dict]):
        """Main pipeline execution."""
        try:
            import uuid
            request_id = str(uuid.uuid4())
            TEST_USER_ID = "finance_user"
            
            asyncio.create_task(self.workflow.run(
                request_id=request_id,
                inputs={
                    "messages": messages,
                    "user_id": TEST_USER_ID,
                    "session_id": "session_finance_01"
                }
            ))

            async for channel_name in STREAM_SERVICE.get_channels(request_id):
                async for chunk in STREAM_SERVICE.get(request_id, channel_name, json_mode=False):
                    try:
                        delta = getattr(chunk.choices[0].delta, "content", None)
                    except Exception:
                        delta = None
                    if delta:
                        yield delta                       
        except Exception as e:
            import traceback
            LOGGER.error(traceback.format_exc(e))
            yield fake_chunk_from(content="Xin lỗi, hệ thống tính toán đang gặp sự cố.", resource_key="error")

# --- Example Usage ---
async def main():
    bot = FinanceCalculatorBot(bot_id="fin-bot-01")
    
    # Test Case 1: Salary (VN Tax)
    print("--- Test Salary ---")
    async for chunk in bot.run(messages=[{"role": "user", "content": "Tính lương Net nếu lương Gross là 50 triệu, đóng bảo hiểm full, 2 người phụ thuộc"}]):
        print(chunk, end="", flush=True)
    print("\n")

    # Test Case 2: Loan
    print("--- Test Loan ---")
    async for chunk in bot.run(messages=[{"role": "user", "content": "Vay 1 tỷ lãi suất 10% trong 10 năm thì mỗi tháng trả bao nhiêu?"}]):
        print(chunk, end="", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
