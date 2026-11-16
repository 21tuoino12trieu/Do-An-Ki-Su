from typing import Dict, List, Any
import json

from beeflow.configs.node_config import NodeType
from beeflow.nodes import GraphNode, BaseNode


# =========================================================
# PROMPTS
# =========================================================
PEV_NATIVE_SYSTEM_PROMPT = """
You are a Plan-Execute-Verify Agent.

Always answer in Vietnamese.

You MUST follow this process:

1. Think and decide next action
2. Use EXACTLY ONE tool call each step
3. Continue until enough information
4. When done, MUST call tool `final_answer`

Important:
- Only use tools provided
- Only one tool call each step. Never use `multi_tool_use.parallel`
- Never write final_answer in text
- Final response MUST use tool `final_answer`
- Chỉ gọi từng tools. Không sử dụng multi_tool_use.parallel
"""

VERIFIER_PROMPT = """
You are a strict verifier.

Check:
1. Tool output valid?
2. Enough information?
3. Need next step?

Respond with ONLY:

CONFIDENT
or
CONTINUE
"""


# =========================================================
# HELPERS
# =========================================================
def final_answer(answer: str) -> dict:
    """Return final answer and finish workflow."""
    return {
        "final_answer": answer
    }

def convert_tools_to_openai_schema(tools):
    schemas = []

    for tool in tools:
        schemas.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.code_fn.__doc__ or "",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        })

    return schemas
def init_messages(query: str, system_prompt: str):
    return {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ]
    }


def build_observation(
    iteration_count: int,
    tool_result: Any,
    tool_error: str,
    tool_success: bool
):
    tool_call_id = f"call_{iteration_count}"

    return {
        "tool_observation": {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": json.dumps({
                "success": tool_success,
                "result": tool_result,
                "error": tool_error
            }, ensure_ascii=False)
        }
    }


def update_messages(
    messages: List[Dict],
    assistant_content: str,
    tool_name: str,
    tool_params: Dict,
    tool_observation: Dict,
    iteration_count: int
):
    tool_call_id = f"call_{iteration_count}"

    # assistant tool call message
    messages.append({
        "role": "assistant",
        "content": assistant_content,
        "tool_calls": [
            {
                "id": tool_call_id,
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": json.dumps(tool_params, ensure_ascii=False)
                }
            }
        ]
    })

    messages.append(tool_observation)

    return {
        "out_messages": messages,
        "out_iteration_count": iteration_count + 1
    }


def extract_final_answer(content: Dict):

    return {
        "final_answer": content["answer"]
    }

def extract_tool_call(tool_calls: Any):
    """
    Normalize tool call output from LLMNode.

    Supports:
    - OpenAI SDK tool call format
    - list / dict / object wrappers
    - JSON string arguments
    """
    if not tool_calls:
        return {
            "tool_name": None,
            "tool_params": {}
        }

    # unwrap
    first_call = tool_calls[0] if isinstance(tool_calls, list) else tool_calls

    function_obj = (
        first_call.get("function")
        if isinstance(first_call, dict)
        else getattr(first_call, "function", None)
    )

    tool_name = None
    raw_args = {}

    if function_obj:
        if isinstance(function_obj, dict):
            tool_name = function_obj.get("name")
            raw_args = function_obj.get("arguments", {})
        else:
            tool_name = getattr(function_obj, "name", None)
            raw_args = getattr(function_obj, "arguments", {})
    else:
        tool_name = (
            first_call.get("name")
            if isinstance(first_call, dict)
            else getattr(first_call, "name", None)
        )
        raw_args = (
            first_call.get("arguments", {})
            if isinstance(first_call, dict)
            else getattr(first_call, "arguments", {})
        )

    # parse params
    if isinstance(raw_args, str):
        try:
            tool_params = json.loads(raw_args.strip())
        except Exception as e:
            print(f"[extract_tool_call] JSON parse failed: {raw_args}, error={e}")
            tool_params = {}
    elif isinstance(raw_args, dict):
        tool_params = raw_args
    else:
        tool_params = {}

    return {
        "tool_name": tool_name,
        "tool_params": tool_params
    }
# =========================================================
# MAIN NODE
# =========================================================
class PlanExecuteVerifyAgentNode(GraphNode):

    type: NodeType = "pev-agent-v3-native"

    def __init__(
        self,
        resource_key: str,
        tools: List[BaseNode],
        max_iterations: int = 5,
        context_prompt: str = "",
        **kwargs
    ):
        super().__init__(**kwargs)

        self.resource_key = resource_key
        self.tool_schemas  = [t.get_openai_tool_schema() for t in tools]
        self.tools = tools
        self.max_iterations = max_iterations
        self.context_prompt = context_prompt

        self._build_graph()

    def _build_graph(self):
        from beeflow.nodes import (
            CodeNode,
            LLMNode,
            BranchNode,
            ToolExecutorNode,
            WhileLoopNode,
            START,
            END,
            INPUT,
            OUTPUT,
            CONTINUE
        )

        with self:

            init_prompt = CodeNode(
                name="init_prompt",
                code_fn=init_messages,
                inputs={
                    "query": INPUT,
                    "system_prompt": PEV_NATIVE_SYSTEM_PROMPT
                },
                return_keys=["messages"]
            )

            with WhileLoopNode(
                name="pev_loop",
                inputs={
                    "messages": init_prompt,
                    "iteration_count": 0
                },
                outputs={"final_answer": OUTPUT}
            ) as loop:

                # =====================================================
                # Native tool calling LLM
                # =====================================================
                planner = LLMNode(
                    name="planner_native",
                    resource_key=self.resource_key,
                    inputs={"messages": INPUT, "tools": self.tool_schemas, "tool_choice": "auto"},
                    stream=True
                )

                extract_call = CodeNode(
                    name="extract_tool_call",
                    code_fn=extract_tool_call,
                    inputs={
                        "tool_calls": planner["tool_calls"]
                    },
                    return_keys=[
                        "tool_name",
                        "tool_params"
                    ]
                )

                # =====================================================
                # Extract native tool call
                # =====================================================
                tool_executor = ToolExecutorNode(
                    name="tool_executor",
                    tools=self.tools,
                    inputs={
                        "tool_name": extract_call["tool_name"],
                        "tool_params": extract_call["tool_params"]
                    }
                )

                final_output = CodeNode(
                    name="final_output",
                    code_fn=lambda result: {
                        "final_answer": result.get("final_answer")
                    },
                    inputs={
                        "result": tool_executor["result"]
                    },
                    return_keys=["final_answer"],
                    outputs={"final_answer": OUTPUT}
                )

                # =====================================================
                # Build structured observation
                # =====================================================
                observation_builder = CodeNode(
                    name="observation_builder",
                    code_fn=build_observation,
                    inputs={
                        "iteration_count": INPUT["iteration_count"],
                        "tool_result": tool_executor["result"],
                        "tool_error": tool_executor["error"],
                        "tool_success": tool_executor["success"]
                    },
                    return_keys=["tool_observation"]
                )

                # =====================================================
                # Update context
                # =====================================================
                update_loop = CodeNode(
                    name="update_loop",
                    code_fn=update_messages,
                    inputs={
                        "messages": INPUT["messages"],
                        "assistant_content": planner["content"],
                        "tool_name": extract_call["tool_name"],
                        "tool_params": extract_call["tool_params"],
                        "tool_observation": observation_builder,
                        "iteration_count": INPUT["iteration_count"]
                    },
                    return_keys=[
                        "out_messages",
                        "out_iteration_count"
                    ],
                    outputs={
                        "out_messages": INPUT["messages"],
                        "out_iteration_count": INPUT["iteration_count"]
                    }
                )

                # =====================================================
                # Final answer detector
                # =====================================================
                final_output = CodeNode(
                    name="final_output",
                    code_fn=extract_final_answer,
                    inputs={"content": extract_call["tool_params"]},
                    return_keys=["final_answer"],
                    outputs={"final_answer": OUTPUT}
                )

                branch = BranchNode(
                    name="branch",
                    cases={
                        "tool_name == 'final_answer'": "final_output",
                        "iteration_count < max_iterations": "tool_executor"
                    },
                    default=END,
                    inputs={
                        "tool_name": extract_call["tool_name"],
                        "iteration_count": INPUT["iteration_count"],
                        "max_iterations": self.max_iterations
                    }
                )

                START >> planner >> extract_call  >> branch >> [tool_executor, final_output, END]
                tool_executor >> observation_builder >> update_loop >> CONTINUE
                final_output >> END

            START >> init_prompt >> loop >> END

        self.build()

# =========================================================
# KHỐI TEST CHẠY THỬ
# =========================================================
async def main():
    import asyncio
    import uuid

    from beeflow.nodes import (
        CodeNode,
        START,
        END,
        INPUT,
        OUTPUT
    )
    from beeflow.workflow import WorkflowEngine
    from beeflow.utils.streaming import STREAM_SERVICE

    # =====================================================
    # MOCK TOOLS
    # =====================================================
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
        """Generate recommendation based on weather."""
        return {
            "recommend": "Nên mang ô và mặc đồ thoáng mát",
            "city": city
        }

    # =====================================================
    # BUILD WORKFLOW
    # =====================================================
    with WorkflowEngine(
        name="workflow_pev_v3",
        description="Workflow test PEV Agent V3 Native Tool Calling"
    ) as workflow:

        # Tools
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

        n_final_answer = CodeNode(
            name="final_answer",
            code_fn=final_answer
        )

        # Agent
        agent = PlanExecuteVerifyAgentNode(
            name="pev_agent_v3",
            resource_key="gemini-2.5-flash-chat",
            tools=[
                n_weather,
                n_population,
                n_recommend,
                n_final_answer
            ],
            max_iterations=5,
            context_prompt="You are a helpful assistant.",
            inputs=INPUT,
            outputs={"final_answer": OUTPUT}
        )

        START >> agent >> END

    workflow.compile()

    # =====================================================
    # TEST INPUT
    # =====================================================
    inputs = {
        "query": (
            "Hà Nội hiện tại thời tiết thế nào, "
            "dân số là bao nhiêu và tôi nên làm gì?"
        )
    }

    request_id = str(uuid.uuid4())

    # =====================================================
    # RUN WORKFLOW
    # =====================================================
    await workflow.run(
        inputs=inputs,
        request_id=request_id
    )

    # =====================================================
    # STREAM OUTPUT
    # =====================================================
    async for channel_name in STREAM_SERVICE.get_channels(request_id):
        print(f"\n=== Channel: {channel_name} ===")

        async for chunk in STREAM_SERVICE.get(
            request_id,
            channel_name
        ):
            try:
                delta = chunk.choices[0].delta

                # normal text streaming
                if hasattr(delta, "content") and delta.content:
                    print(delta.content, end="", flush=True)

                # native tool call debug
                elif hasattr(delta, "tool_calls") and delta.tool_calls:
                    print("\n[TOOL CALL]", delta.tool_calls)

                else:
                    print(chunk)

            except Exception as e:
                print(f"\n[STREAM ERROR] {e}")
                print(chunk)

        print()

    print("\n" + "=" * 50)
    print("DONE")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())