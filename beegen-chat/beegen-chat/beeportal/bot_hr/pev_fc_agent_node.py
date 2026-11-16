from typing import Dict, List, Any
import json

from beeflow.configs.node_config import NodeType
from beeflow.nodes import GraphNode, BaseNode
from beegen.tools.schema.param import ParamSet
from beegen.utils.common import transform_bot_id
from beeflow.nodes.templates.retriever_node_v2 import RetrieverNode


# =========================================================
# PROMPTS
# =========================================================

PEV_NATIVE_SYSTEM_PROMPT = """
You are a Plan-Execute-Verify Agent.

Always answer in Vietnamese.

CONTEXT:
{context}

WORKFLOW:
1. Think and decide the next best action
2. Use EXACTLY ONE tool call at each step
3. Continue until enough information is collected
4. When enough information is available, respond with the final answer only

TOOL RULES:
- Only use provided tools
- Never use multi_tool_use.parallel
- Chỉ gọi từng tool một
- Không gọi thêm tool nếu đã đủ thông tin để trả lời

CONFIRMATION AND FOLLOW-UP RULES:
Khi cần xác nhận thông tin hoặc muốn hỏi thêm người dùng trước khi thực hiện thao tác (đặc biệt là các thao tác post/gửi thông tin), hãy đưa ra câu hỏi ở cuối câu trả lời và kèm theo nút bấm bằng thẻ HTML:

<button: Nội dung nút>

Cách dùng:
- Dùng <button: Text> để tạo nút follow-up cho người dùng bấm vào
- Có thể đưa ra nhiều nút cho nhiều lựa chọn khác nhau
- Khi người dùng bấm nút, nội dung nút sẽ được gửi lại như tin nhắn của người dùng

Ví dụ câu hỏi xác nhận:
Vui lòng xác nhận thông tin trước khi gửi:
<button: Xác nhận gửi thông tin>
<button: Hủy bỏ>

Ví dụ câu hỏi follow-up:
Bạn muốn tra cứu thêm thông tin gì khác?

<button: Xem thêm lịch sử giao dịch>
<button: Xem thông tin lãi suất>
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
def init_messages(messages: List[Dict], system_prompt: str):
    """Initialize messages with system prompt prepended.

    If the messages already contain a system prompt, the default system_prompt
    is not added to avoid duplication.

    Args:
        messages (List[Dict]): List of conversation messages.
        system_prompt (str): Default system prompt to prepend.

    Returns:
        Dict containing initialized_messages with system prompt added if needed.
    """
    has_system = any(m.get("role") == "system" for m in messages)
    if has_system:
        return {"initialized_messages": messages}
    return {
        "initialized_messages": [
            {"role": "system", "content": system_prompt},
            *messages
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
    assistant_msg = {
        "role": "assistant",
        "content": assistant_content or ""
        # "content": assistant_content
    }

    # Chỉ thêm tool_calls khi có tool_name hợp lệ
    if tool_name:
        assistant_msg["tool_calls"] = [
            {
                "id": tool_call_id,
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": json.dumps({k: v for k, v in tool_params.items() if k != "username"}, ensure_ascii=False)
                }
            }
        ]

    messages.append(assistant_msg)

    # Chỉ thêm tool observation khi có tool_calls hợp lệ
    if tool_name and tool_observation:
        messages.append(tool_observation)

    return {
        "out_messages": messages,
        "out_iteration_count": iteration_count + 1
    }


def extract_final_answer(content, out_messages):
    """Extract final answer from LLM content.

    Args:
        content: Can be a string (direct answer) or dict with 'answer' key (from final_answer tool)
        out_messages: Out messages
    """

    # Extract final answer text
    if isinstance(content, str):
        final_text = content
    elif isinstance(content, dict):
        final_text = content.get("answer", "")
    else:
        final_text = str(content) if content else ""

    # Add final answer as assistant message to messages
    out_messages = list(out_messages) if out_messages else []
    out_messages.append({
        "role": "assistant",
        "content": final_text
    })

    return {"final_answer": final_text, "final_state_messages": out_messages}


SYNTHESIZER_SYSTEM_PROMPT = """
Đã đạt giới hạn tìm kiếm. Không gọi tool nữa.
Nếu không có đủ thông tin, hãy thông báo cho người dùng biết những gì bạn đã tìm được và những gì chưa tìm được.

Bạn chỉ được sử dụng những thông tin tìm kiếm được để phản hồi cho người dùng, không nên đưa ra các kết luận. Phân tích dựa trên các tài liệu hiện có 

Đưa ra các follow-up cho người dùng hoặc dự đoán ý người dùng bằng thẻ HTML:

<button: Nội dung nút>

Cách dùng:

Dùng <button: Text> để tạo nút follow-up cho người dùng bấm vào
Có thể đưa ra nhiều nút cho nhiều lựa chọn khác nhau
Khi người dùng bấm nút, nội dung nút sẽ được gửi lại như tin nhắn của người dùng
Ví dụ câu hỏi xác nhận:
Vui lòng xác nhận thông tin trước khi gửi:
<button: Xác nhận gửi thông tin>
<button: Hủy bỏ>

Ví dụ câu hỏi follow-up:
Bạn muốn tra cứu thêm thông tin gì khác?

<button: Xem thêm lịch sử giao dịch>
<button: Xem thông tin lãi suất> 
"""


def prepare_synthesizer_input(messages: List[Dict]) -> Dict[str, Any]:
    """Prepares input messages for the final summarizer LLM by prepending synthesizer system prompt.

    Args:
        messages: Full conversation messages including tool results.

    Returns:
        Dict with 'messages' containing system prompt + conversation history.
    """
    return {
        "synthesizer_messages": [
            *messages[1:],
            {"role": "user", "content": SYNTHESIZER_SYSTEM_PROMPT}
        ]
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


def get_references_ids(messages: List[Dict]) -> Dict[str, Any]:
    """Extract all document reference IDs from tool results in messages.

    Parses tool content from messages and extracts document IDs from various
    possible structures (result.data[*]._id, result.docs[*].id, etc.)

    Args:
        messages (List[Dict]): List of conversation messages containing tool results.

    Returns:
        Dict with 'docs' containing list of unique document reference IDs.
    """
    seen_ids = set()
    docs = []

    for msg in reversed(messages):
        # Only process tool messages
        if msg.get("role") != "tool":
            continue

        content = msg.get("content", "")
        if not content:
            continue

        # Parse JSON content
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            continue

        # Extract from various possible structures
        _extract_ids_to_docs(data, seen_ids, docs)

    # Đảo ngược để ID mới nhất lên đầu, lấy tối đa 20 docs
    # docs.reverse()

    return {"docs": docs[:20]}

# Về sau có thể chuyển thành hàm inject thêm các hidden 
def inject_sensitive_keys_to_params(toolparams: Dict, sensitive_keys: str = None) -> Dict[str, Any]:
    """Thêm username vào tool_params để truyền vào các HCM tools.

    Args:
        tool_params (Dict): Tool parameters từ LLM call
        sensitive_keys (str): Username lấy từ workflow INPUT

    Returns:
        Dict với username được thêm vào tool_params
    """
    if sensitive_keys:
        return {"tool_params": {**toolparams, "sensitive_keys": sensitive_keys}}
    return {"tool_params": toolparams}


def _extract_ids_to_docs(data: Any, seen_ids: set, docs: list) -> None:
    """Recursively extract document IDs from nested data structures.

    Handles multiple ID field names:
    - _id (MongoDB style)
    - id (standard)
    - doc_id (alternative)

    Args:
        data: Any data structure to search
        seen_ids: Set to track already-seen IDs (for deduplication)
        docs: List to accumulate found documents as {"id": ...}
    """
    if isinstance(data, dict):
        # Check for common ID field names
        for id_field in ["_id", "id", "doc_id"]:
            if id_field in data and data[id_field]:
                id_val = data[id_field]
                if id_val not in seen_ids:
                    seen_ids.add(id_val)
                    docs.append({"id": id_val, "score": f"{data.get("document_matching_score") * 100:.1f}%" if data.get("document_matching_score") is not None else None})

        # Recurse into nested structures
        for value in data.values():
            _extract_ids_to_docs(value, seen_ids, docs)

    elif isinstance(data, list):
        for item in data:
            _extract_ids_to_docs(item, seen_ids, docs)


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
                    "messages": INPUT,
                    "system_prompt": PEV_NATIVE_SYSTEM_PROMPT.format(context=self.context_prompt)
                },
                return_keys=["initialized_messages"]
            )

            with WhileLoopNode(
                name="pev_loop",
                inputs={
                    "messages": init_prompt["initialized_messages"],
                    "iteration_count": 0,
                    "sensitive_keys": INPUT
                },
                outputs={"final_answer": OUTPUT, "final_state_messages": OUTPUT}
            ) as loop:

                # =====================================================
                # Native tool calling LLM
                # =====================================================

                get_references_ids_fn = CodeNode(
                    name="get_references_ids",
                    code_fn=get_references_ids,
                    inputs={"messages": INPUT},
                    return_keys=["docs"]
                )

                planner = LLMNode(
                    name="planner_native",
                    resource_key=self.resource_key,
                    inputs={"messages": INPUT, "tools": self.tool_schemas, "tool_choice": "auto", "docs": get_references_ids_fn, "temperature": 1.0, "top_p": 0.95, "top_k": 64},
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
                inject_sensitive_keys = CodeNode(
                    name="inject_sensitive_keys",
                    code_fn=inject_sensitive_keys_to_params,
                    inputs={
                        "toolparams": extract_call["tool_params"],
                        "sensitive_keys": INPUT["sensitive_keys"]
                    },
                    return_keys=["tool_params"]
                )

                tool_executor = ToolExecutorNode(
                    name="tool_executor",
                    tools=self.tools,
                    inputs={
                        "tool_name": extract_call["tool_name"],
                        "tool_params": inject_sensitive_keys["tool_params"]
                    }
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
                prepare_synthesizer_input_fn = CodeNode(
                    name="prepare_synthesizer_input",
                    code_fn=prepare_synthesizer_input,
                    inputs={
                        "messages": update_loop["out_messages"]
                    },
                    return_keys=["synthesizer_messages"]
                )

                synthesizer_llm = LLMNode(
                    name="synthesizer_llm",
                    resource_key=self.resource_key,
                    inputs={
                        "messages": prepare_synthesizer_input_fn["synthesizer_messages"],
                        "tools": self.tool_schemas, 
                        "tool_choice": "auto",
                        "docs": get_references_ids_fn
                    },
                    stream=True
                )

                final_output = CodeNode(
                    name="final_output",
                    code_fn=extract_final_answer,
                    inputs={"content": planner["content"], "out_messages": update_loop},
                    return_keys=["final_answer", "final_state_messages"],
                    outputs={"final_answer": OUTPUT, "final_state_messages": OUTPUT}
                )

                final_output_with_synthesizer = CodeNode(
                    name="final_output_with_synthesizer",
                    code_fn=extract_final_answer,
                    inputs={"content": synthesizer_llm["content"], "out_messages": update_loop},
                    return_keys=["final_answer", "final_state_messages"],
                    outputs={"final_answer": OUTPUT, "final_state_messages": OUTPUT}
                )

                branch = BranchNode(
                    name="branch",
                    cases={
                        "not tool_calls": "final_output",  # LLM tự dừng → trả lời ngay
                        "iteration_count >= max_iterations": "prepare_synthesizer_input",  # Hết vòng lặp → ép LLM tổng hợp
                        "iteration_count < max_iterations": "tool_executor",   # Còn iteration và có tool → executefinal answer 
                    },
                    default=END,
                    inputs={
                        "tool_calls": planner["tool_calls"],
                        "tool_name": extract_call["tool_name"],
                        "iteration_count": INPUT["iteration_count"],
                        "max_iterations": self.max_iterations
                    }
                )

                START >> get_references_ids_fn >> planner >> extract_call >> inject_sensitive_keys >> branch >> [tool_executor, final_output, prepare_synthesizer_input_fn, END]
                
                tool_executor >> observation_builder >> update_loop >> CONTINUE
                
                prepare_synthesizer_input_fn >> synthesizer_llm >> final_output_with_synthesizer >> END
                
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
        "messages": [
            {"role": "user", "content": "Hà Nội hiện tại thời tiết thế nào, dân số là bao nhiêu và tôi nên làm gì?"}
        ]
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
