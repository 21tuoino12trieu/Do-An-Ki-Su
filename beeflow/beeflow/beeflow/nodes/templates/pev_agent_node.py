from typing import Dict, List, Any, Optional
import uuid

from beeflow.configs.node_config import NodeType
from beeflow.nodes import GraphNode, BaseNode

# Tích hợp các preambles từ PlanReActPlanner vào System Prompt chung
PEV_SYSTEM_PROMPT = """You are a Plan-Execute-Verify (PEV) Agent designed to handle complex tasks. 
    When answering the question, try to leverage the available tools to gather the information instead of your memorized knowledge.

    ## Available Tools
    You have access to the following tools:
    {tool_desc}

    ## Context
    {context_prompt}

    ## The Plan-Execute-Verify Process
    You MUST strictly follow these formatted tags in your responses:

    1. /*PLANNING*/
    First, come up with a plan in natural language text format. The plan must be a numbered list of steps covering all aspects of the user query. Only use available tools.

    2. /*REASONING*/
    Between tool actions, you must summarize the current trajectory based on the query and previous tool outputs. Verify if the last step succeeded, and outline instructions for the next steps.

    3. /*ACTION*/
    Then use a tool to execute the next step in the plan. You MUST output exactly ONE action per step using the following JSON format:
    ```json
    {{
        "tool_name": "[EXACTLY ONE tool name from: {tool_names}]",
        "tool_params": {{"parameter": "value"}}
    }}
    4. /REPLANNING/ (If necessary)
    If the initial plan cannot be successfully executed, learn from previous execution results, explain the failure, and write a revised plan under this tag.

    5. /FINAL_ANSWER/
    Once you have enough information verified by your reasoning, provide the precise and final answer. If the query is unanswerable with the available tools, inform the user why.

    Important Rules
    You MUST wait for "Observation:" after each /ACTION/ before proceeding.
    DO NOT use multiple tools in one step.
    Answer the user in Vietnamese.
    Current Conversation
"""

TOOL_FORMAT_PROMPT = """
    Tool name: {tool_name}
    Tool Description: {tool_description}
    Tool Args: {tool_argument}
"""

def format_pev_messages(query: str, system_prompt: str) -> Dict[str, Any]:
    """Khởi tạo context ban đầu cho PEV Agent."""
    formatted_messages = [{"role": "user", "content": query}]
    formatted_messages.insert(0, {"role": "system", "content": system_prompt})

    return {
        "messages": formatted_messages
    }

import re
import json
from typing import Dict, Any


def parse_pev_response(text: str) -> Dict[str, Any]:
    """
    Hàm CodeNode để bóc tách các tag từ Plan-Execute-Verify response.
    Ưu tiên tìm /*FINAL_ANSWER*/, nếu không có thì tìm /*ACTION*/ để parse JSON.
    """
    result = {
        "Action": None,
        "Params": {},
        "Final_Answer": None
    }

    if not text:
        return result

    # =====================================================
    # 1. Ưu tiên tìm FINAL_ANSWER
    # =====================================================
    final_match = re.search(
        r"/\*FINAL_ANSWER\*/(.*?)(?=/\*|$)",
        text,
        re.DOTALL
    )

    if final_match:
        result["Final_Answer"] = final_match.group(1).strip()
        return result

    # =====================================================
    # 2. Tìm ACTION block
    # =====================================================
    action_match = re.search(
        r"/\*ACTION\*/(.*?)(?=/\*|$)",
        text,
        re.DOTALL
    )

    if not action_match:
        return result

    action_block = action_match.group(1).strip()

    # =====================================================
    # 3. Extract JSON trong ACTION
    # =====================================================
    json_match = re.search(
        r"```json\s*(\{.*?\})\s*```",
        action_block,
        re.DOTALL
    )

    if json_match:
        json_str = json_match.group(1)
    else:
        json_str = action_block

    try:
        # Lấy JSON block đầu tiên hợp lệ
        start = json_str.find("{")
        end = json_str.rfind("}") + 1

        if start == -1 or end == 0:
            return result

        json_str = json_str[start:end]

        action_data = json.loads(json_str)

        result["Action"] = action_data.get("tool_name")
        result["Params"] = action_data.get("tool_params", {})

    except Exception as e:
        print(f"Parse error: {e}")

    return result

def update_pev(
    messages: List[Dict],
    llm_reasoning: str,
    tool_result: Any,
    tool_error: str,
    tool_success: bool,
    iteration_count: int 
) -> Dict[str, Any]:
    """Cập nhật hội thoại, buộc LLM phải verify kết quả của công cụ"""
    messages.append({
        "role": "assistant", 
        "content": llm_reasoning
    })
    
    if tool_success:
        observation = f"Observation: {tool_result}\n\nPlease analyze this under /*REASONING*/ to VERIFY if the step succeeded, and take the next /*ACTION*/ or output /*FINAL_ANSWER*/."
    else:
        observation = f"Observation: Error - {tool_error}\n\nPlease analyze this error under /*REASONING*/, provide a new plan under /*REPLANNING*/ if needed, and try a new /*ACTION*/."
    
    messages.append({
        "role": "user",
        "content": observation
    })
    
    return {
        "out_messages": messages,
        "out_iteration_count": iteration_count + 1
    }


class PlanExecuteVerifyAgentNode(GraphNode):
    """
    Plan-Execute-Verify Agent
    
    Áp dụng workflow PlanReAct:
    1. Plan - Lên kế hoạch chi tiết (/*PLANNING*/)
    2. Execute - Chọn tool để chạy (/*ACTION*/)
    3. Verify/Reason - Phân tích observation, kiểm tra tính đúng đắn, replan nếu cần (/*REASONING*/)
    4. Lặp lại cho đến khi tự tin chốt đáp án (/*FINAL_ANSWER*/)
    """
    
    type: NodeType = "pev-agent"
    
    def __init__(
        self,
        resource_key: str,
        tools: List[BaseNode],
        max_iterations: int = 3,
        context_prompt: str = "",
        **kwargs
    ) -> None:
        super().__init__(**kwargs)
        
        self.resource_key = resource_key
        self.tools = tools
        self.max_iterations = max_iterations
        self.context_prompt = context_prompt
        self._build_graph()
        
    def _create_pev_prompt(self) -> str:
        def desc(tool: BaseNode) -> str:
            return TOOL_FORMAT_PROMPT.format(
                tool_name=tool.name,
                tool_description=tool.description,
                tool_argument=tool.get_openai_function_schema()["parameters"]
            )
        
        tools_desc = [desc(tool) for tool in self.tools]
        tool_names = [tool.name for tool in self.tools]
        
        return PEV_SYSTEM_PROMPT.format(
            tool_desc='\n'.join(tools_desc),
            tool_names=', '.join(tool_names),
            context_prompt=self.context_prompt
        )
        
    def _build_graph(self):
        from beeflow.nodes import (
            CodeNode, START, END, INPUT, OUTPUT, CONTINUE, 
            LLMNode, BranchNode, ToolExecutorNode, WhileLoopNode
        )
        
        with self:
            init_prompt = CodeNode(
                name="init_prompt",
                code_fn=format_pev_messages,
                inputs={
                    "query": INPUT, 
                    "system_prompt": self._create_pev_prompt()
                },
                return_keys=["messages"]
            )
            
            with WhileLoopNode(
                name="pev_loop",
                description="Vòng lặp Lên kế hoạch - Thực thi - Xác thực",
                inputs={"messages": init_prompt, "iteration_count": 0},
                outputs={"Final_Answer": OUTPUT}
            ) as while_node:
                
                # LLM suy luận với các thẻ Tags (PLANNING, REASONING, ACTION...)
                reason = LLMNode(
                    name="reason",
                    resource_key=self.resource_key,
                    inputs={"messages": INPUT},
                    stream=True
                )
                
                # Bóc tách Action / Final Answer bằng custom python logic
                parser = CodeNode(
                    name="tag_parser",
                    code_fn=parse_pev_response,
                    inputs={"text": reason["content"]},
                    return_keys=["Final_Answer", "Action", "Params"],
                    outputs={
                        "Final_Answer": OUTPUT,
                        "Action": OUTPUT,
                        "Params": OUTPUT
                    }
                )
                
                # Nếu LLM ra Final Answer thì END, nếu không thì sang Tool Manager
                verify_branch = BranchNode(
                    name="verify_branch",
                    cases={
                        "Final_Answer is None and iteration_count < max_iterations": "tool_manager",
                    },
                    default=END,
                    inputs={
                        "iteration_count": INPUT,
                        "max_iterations": self.max_iterations,
                        "Final_Answer": parser["Final_Answer"]
                    }
                )
                
                # Thực thi Tool (Execute)
                tool_manager = ToolExecutorNode(
                    name="tool_manager",
                    tools=self.tools,
                    inputs={
                        "tool_name": parser["Action"],
                        "tool_params": parser["Params"]
                    }
                )
                
                # Xác thực & Cập nhật Context (Verify)
                update_loop = CodeNode(
                    name="update_loop",
                    code_fn=update_pev,
                    inputs={
                        "messages": INPUT["messages"],
                        "iteration_count": INPUT["iteration_count"],
                        "llm_reasoning": reason["content"],
                        "tool_result": tool_manager["result"],
                        "tool_error": tool_manager["error"],
                        "tool_success": tool_manager["success"]
                    },
                    return_keys=["out_messages", "out_iteration_count"],
                    outputs={
                        "out_messages": INPUT["messages"],
                        "out_iteration_count": INPUT["iteration_count"]
                    }
                )
                
                START >> reason >> parser >> verify_branch >> [tool_manager, END] 
                tool_manager >> update_loop >> CONTINUE
            
            START >> init_prompt >> while_node >> END
        
        self.build()
        

# =========================================================
# KHỐI TEST CHẠY THỬ
# =========================================================
async def main():
    import asyncio
    from beeflow.nodes import (
        CodeNode,
        START,
        END,
        INPUT,
        OUTPUT
    )
    from beeflow.workflow import WorkflowEngine
    from beeflow.utils.streaming import STREAM_SERVICE
    import uuid

    def fetch_weather(city: str) -> dict:
        """Fetch the current weather for a specific city."""
        return {
            "weather": "30 degrees, sunny",
            "city": city
        }

    def fetch_population(city: str) -> dict:
        """Fetch the current population for a specific city."""
        return {
            "population": "8.5 million",
            "city": city
        }
    def recommend(city: str, weather: str) -> dict:
        """Generate recommendations based on the city's current weather conditions."""
        if weather == "30 degrees, sunny":
            return {
                "recommend": "Nên mang ô và mặc đồ thoáng mát",
                "city": city
            }

    # =====================================================
    # Build workflow theo style mới
    # =====================================================
    with WorkflowEngine(
        name="workflow_pev",
        description="Workflow test PEV Agent"
    ) as workflow:

        # Init tools
        n_weather = CodeNode(
            name="fetch_weather",
            code_fn=fetch_weather
        )

        n_population = CodeNode(
            name="fetch_population",
            code_fn=fetch_population
        )

        n_recommend = CodeNode(
            name="recommend",
            code_fn=recommend
        )

        # Init PEV Agent
        agent = PlanExecuteVerifyAgentNode(
            name="pev_agent",
            resource_key="gemini-2.5-flash-chat",
            tools=[n_weather, n_population, n_recommend],
            max_iterations=5,
            context_prompt="You are a helpful assistant.",
            inputs=INPUT,
            outputs={"Final_Answer": OUTPUT}
        )

        START >> agent >> END

    workflow.compile()

    # =====================================================
    # Input test
    # =====================================================
    inputs = {
        "query": "Hà Nội hiện tại thời tiết thế nào và dân số là bao nhiêu? Tôi nên làm gì với thời tiết này"
    }

    request_id = str(uuid.uuid4())

    # chạy async background
    asyncio.create_task(
        workflow.run(
            inputs=inputs,
            request_id=request_id
        )
    )

    # =====================================================
    # Stream output
    # =====================================================
    async for channel_name in STREAM_SERVICE.get_channels(request_id):
        print(f"\nChannel: {channel_name}")

        async for chunk in STREAM_SERVICE.get(request_id, channel_name):
            try:
                print(
                    chunk.choices[0].delta.content,
                    end="",
                    flush=True
                )
            except Exception:
                print(chunk)

        print()

    print("\n" + "=" * 50)
    print("DONE")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())