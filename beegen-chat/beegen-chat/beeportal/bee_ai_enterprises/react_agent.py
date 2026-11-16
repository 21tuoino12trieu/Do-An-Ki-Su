from typing import Dict, List, Any
import json

from beeflow.configs.node_config import NodeType
from beeflow.nodes import GraphNode, BaseNode
from beegen.tools.schema.param import ParamSet
from beegen.utils.common import transform_bot_id
from beeflow.nodes.templates.retriever_node_v2 import RetrieverNode
from beeflow.nodes.templates.basic_chain_node import BasicChainNode


# =========================================================
# PROMPTS
# =========================================================
# PEV_NATIVE_SYSTEM_PROMPT = """
# You are a Plan-Execute-Verify Agent.

# Always answer in Vietnamese.

# You MUST follow this process:

# 1. Think and decide next action
# 2. Use EXACTLY ONE tool call each step
# 3. Continue until enough information
# 4. When done, just respond with your final answer in the response content

# Important:
# - Only use tools provided
# - Only one tool call each step. Never use `multi_tool_use.parallel`
# - Chỉ gọi từng tools. Không sử dụng multi_tool_use.parallel
# - Khi đã có đủ thông tin, chỉ cần trả lời trực tiếp trong nội dung response, không cần gọi thêm tool nào
# REFERENCE RULES:
# Nếu câu trả lời sử dụng thông tin từ tài liệu, BẮT BUỘC trích nguồn bằng format HTML:

# <a href="#" type="document-reference" data-chunk-id="chunk_id">Text</a>
# Requirements:
# - chunkID là ID của chunk tài liệu
# - Không dùng markdown link
# - Có thể dùng nhiều references trong cùng câu trả lời

# Ví dụ:
# Theo quy định hiện hành
# <a href="#" type="document-reference" data-chunk-id="2674511e-3fea-438f-b271-2721ab3321d6">[1]</a>
# khách hàng cần đáp ứng điều kiện về lịch sử tín dụng.

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
    """
    Always replace the first system prompt if it exists.
    Otherwise prepend a new system prompt.
    """

    # Latest user message
    raw_last_message = next(
        (
            m.get("content", "")
            for m in reversed(messages)
            if m.get("role") == "user"
        ),
        "",
    )

    if isinstance(raw_last_message, list):
        # Extract text components from standard multimodal content list
        last_user_message = "\n".join([
            item.get("text", "") 
            for item in raw_last_message 
            if isinstance(item, dict) and item.get("type") == "text"
        ]).strip()
    else:
        last_user_message = raw_last_message

    final_system_prompt = f"""
{system_prompt}

# Câu hỏi hiện tại của người dùng:
{last_user_message}
""".strip()

    new_system = {
        "role": "system",
        "content": final_system_prompt,
    }

    if messages and messages[0].get("role") == "system":
        # Replace the first system prompt
        initialized_messages = [new_system, *messages[1:]]
    else:
        # Insert a new system prompt
        initialized_messages = [new_system, *messages]

    return {
        "initialized_messages": initialized_messages,
        "user_query": last_user_message,
    }

def tool_prompt_builder(
    iteration_count: int,
    tool_result: Any,
    tool_error: str,
    tool_success: bool
):
    tool_call_id = f"tool_call_{iteration_count}"

    return {
        "tool_prompt": {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": json.dumps({
                "success": tool_success,
                "result": tool_result,
                "error": tool_error
            }, ensure_ascii=False)
        }
    }
def revision_prompt_builder(   
    supported_claims: str,
    unsupported_claims: str,
    issues: str,
    recommendations: str
):
    # Định dạng lại nội dung dưới dạng một lời nhắc (prompt) rõ ràng để Agent đọc hiểu
    prompt_content = f"""[SYSTEM FEEDBACK - REVISION REQUIRED]
Lần thực thi/nháp câu trả lời vừa rồi của bạn chưa đạt yêu cầu. Dưới đây là đánh giá từ Reviewer:

1. Trích dẫn các luận điểm trong draft đã được chứng minh là ĐÚNG dựa trên Context (supported_claims): {supported_claims}
2. Trích dẫn các luận điểm trong draft bị SAI, SUY DIỄN, hoặc KHÔNG CÓ trong Context (unsupported_claims): {unsupported_claims}
3. Liệt kê các vấn đề về logic, sự thiếu sót trong cách trả lời, hoặc việc không tuân thủ yêu cầu của người dùng (issues): {issues}
4. Hướng dẫn sửa đổi (recommendations): {recommendations}

YÊU CẦU:
Dựa vào các hướng dẫn trên, hãy tổng hợp lại thông tin và trả lời trực tiếp cho người dùng. Không gọi thêm công cụ nếu thông tin đã đủ.
"""

    return {
        "revision_prompt": {
            "role": "user",
            "content": prompt_content
        }
    }


def update_messages(
    messages: List[Dict],
    assistant_content: str,
    tool_name: str,
    tool_params: Dict,
    tool_prompt: Dict,
    revision_prompt: Dict,
    iteration_count: int
):
    tool_call_id = f"tool_call_{iteration_count}"

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
                    "arguments": json.dumps(tool_params, ensure_ascii=False)
                }
            }
        ]

    messages.append(assistant_msg)

    # Chỉ thêm tool observation khi có tool_calls hợp lệ
    if tool_name and tool_prompt:
        messages.append(tool_prompt)
    if revision_prompt:
        messages.append(revision_prompt)
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

    Docs from the most recent tool call are placed first, older docs follow.
    Deduplication logic is updated to use: unique_id = id + '_' + doc

    Args:
        messages (List[Dict]): List of conversation messages containing tool results.

    Returns:
        Dict with 'docs' containing list of unique document reference IDs.
    """
    tool_messages = [
        msg for msg in messages
        if msg.get("role") == "tool" and msg.get("content")
    ]

    if not tool_messages:
        return {"docs": []}

    seen_ids = set()
    latest_docs = []
    older_docs = []

    def extract_docs(data_payload, target_list):
        """Internal function to extract documents and filter duplicates."""
        docs_list = []
        if isinstance(data_payload, dict):
            # Extract docs list from {"result": {"docs": [...]}} or {"docs": [...]} structure
            if "result" in data_payload and isinstance(data_payload["result"], dict):
                docs_list = data_payload["result"].get("docs", [])
            else:
                docs_list = data_payload.get("docs", [])
                
        for doc in docs_list:
            if not isinstance(doc, dict):
                continue
            
            # CREATE NEW UNIQUE ID: id + '_' + doc
            c_id = str(doc.get("id", ""))
            doc_id = str(doc.get("doc", ""))
            unique_id = f"{c_id}_{doc_id}"
            
            if c_id.lower().startswith("qna"):
                continue

            if unique_id not in seen_ids:
                seen_ids.add(unique_id)
                
                # Format the output document as requested
                doc_content = doc.get("content")
                if unique_id.lower().startswith("bm"):
                    doc_content = ""
                target_list.append({
                    "id": unique_id,
                    "score": doc.get("score"),
                    "type": doc.get("type"),
                    "content": doc_content,
                    "title": doc.get("title"),
                    "link": doc.get("link")
                })

    # Extract docs from the most recent tool message first
    latest_msg = tool_messages[-1]
    try:
        content = latest_msg["content"]
        # Parse JSON if content is a string, keep as is if already a dict
        data = json.loads(content) if isinstance(content, str) else content
        extract_docs(data, latest_docs)
    except (json.JSONDecodeError, TypeError, Exception):
        pass

    # Extract remaining docs from older tool messages (reverse order, skip last)
    for msg in reversed(tool_messages[:-1]):
        try:
            content = msg["content"]
            data = json.loads(content) if isinstance(content, str) else content
            extract_docs(data, older_docs)
        except (json.JSONDecodeError, TypeError, Exception):
            continue

    return {"docs": latest_docs + older_docs}


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
                    docs.append({"id": id_val, "score": f"{data.get("document_matching_score") * 100:.1f}%" if data.get("document_matching_score") is not None else None, "type": data.get("type"), "content": data.get("content"), "title": data.get("title")})

        # Recurse into nested structures
        for value in data.values():
            _extract_ids_to_docs(value, seen_ids, docs)

    elif isinstance(data, list):
        for item in data:
            _extract_ids_to_docs(item, seen_ids, docs)

def extract_reviewer_inputs(messages: List[Dict]) -> Dict[str, Any]:
    """Extract reasoning_draft as both clean text (without base64) and original messages list for multimodal LLM."""
    raw_draft = messages[1:] if len(messages) > 1 else []
    
    # 1. Format clean text (without base64) for system prompt template placeholder
    lines = []
    for msg in raw_draft:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role", "").upper()
        if role == "SYSTEM":
            continue
        content = msg.get("content")
        text_content = ""
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        parts.append(part.get("text", ""))
                    elif part.get("type") == "image_url":
                        parts.append("[Hình ảnh]")
                else:
                    parts.append(str(part))
            text_content = " ".join(parts).strip()
        else:
            text_content = str(content)
        lines.append(f"{role}: {text_content}")
    reasoning_draft_text = "\n".join(lines)
    
    return {
        "reasoning_draft_text": reasoning_draft_text,
        "reasoning_draft_messages": raw_draft
    }

def prepare_reviewer_messages(
    user_query: str,
    agent_answer: str,
    reasoning_draft_text: str,
    reasoning_draft_messages: List[Dict],
    iteration: int,
    max_iteration: int,
    system_prompt_template: str
) -> Dict[str, Any]:
    """Build messages list for reviewer LLM, passing multimodal images properly."""
    try:
        system_prompt_formatted = system_prompt_template.format(
            user_query=user_query,
            agent_answer=agent_answer,
            reasoning_draft=reasoning_draft_text,
            iteration=iteration,
            max_iteration=max_iteration
        )
    except Exception:
        system_prompt_formatted = system_prompt_template
        for k, v in [
            ("user_query", user_query),
            ("agent_answer", agent_answer),
            ("reasoning_draft", reasoning_draft_text),
            ("iteration", str(iteration)),
            ("max_iteration", str(max_iteration))
        ]:
            system_prompt_formatted = system_prompt_formatted.replace(f"{{{k}}}", str(v))

    messages = []
    
    # Add system prompt
    messages.append({
        "role": "system",
        "content": system_prompt_formatted
    })
    
    # Add the conversation history (including multimodal user images)
    for msg in reasoning_draft_messages:
        if isinstance(msg, dict):
            messages.append(msg)
            
    # Add the agent's drafted answer as assistant message
    messages.append({
        "role": "assistant",
        "content": agent_answer
    })
    
    # Add a final instruction for JSON evaluation output
    messages.append({
        "role": "user",
        "content": (
            "Vui lòng kiểm duyệt câu trả lời (assistant) ở trên dựa theo tài liệu và hướng dẫn trong system prompt. "
            "Hãy trả về kết quả dưới định dạng JSON theo đúng schema yêu cầu (gồm các trường: status, supported_claims, "
            "unsupported_claims, issues, recommendations, ask_back_question)."
        )
    })
    
    return {
        "messages": messages
    }

# =========================================================
# MAIN NODE
# =========================================================
class ReActAgentNode(GraphNode):

    type: NodeType = "react-agent"

    def __init__(
        self,
        resource_key: str,
        tools: List[BaseNode],
        max_iterations: int = 5,
        context_prompt: str = "",
        reviewer_prompt: str = "",
        **kwargs
    ):
        super().__init__(**kwargs)

        self.resource_key = resource_key
        self.tool_schemas  = [t.get_openai_tool_schema() for t in tools]
        self.tools = tools
        self.max_iterations = max_iterations
        self.context_prompt = context_prompt
        self.reviewer_prompt = reviewer_prompt

        self._build_graph()

    def _build_graph(self):
        from beeflow.nodes import (
            CodeNode,
            LLMNode,
            BranchNode,
            ToolExecutorNode,
            WhileLoopNode,
            ParserNode,
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
                return_keys=["initialized_messages", "user_query"]
            )

            with WhileLoopNode(
                name="pev_loop",
                inputs={
                    "messages": init_prompt["initialized_messages"],
                    "iteration_count": 0,
                    "user_query": init_prompt
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

                code_extract_reviewer_inputs = CodeNode(
                    name="extract_reviewer_data",
                    code_fn=extract_reviewer_inputs,
                    inputs={
                        "messages": INPUT
                    },
                    return_keys=["reasoning_draft_text", "reasoning_draft_messages"]
                )

                planner_executor_agent = LLMNode(
                    name="planner_executor_agent",
                    resource_key=self.resource_key,
                    inputs={"messages": INPUT, "tools": self.tool_schemas, "tool_choice": "auto", "docs": get_references_ids_fn, "reasoning_effort": "none", "max_tokens": 4096},
                    outputs={"content": OUTPUT},
                    stream=False
                )

                extract_call = CodeNode(
                    name="extract_tool_call",
                    code_fn=extract_tool_call,
                    inputs={
                        "tool_calls": planner_executor_agent["tool_calls"]
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

                # =====================================================
                # Build structured observation
                # =====================================================
                code_tool_prompt_builder = CodeNode(
                    name="code_tool_prompt_builder",
                    code_fn=tool_prompt_builder,
                    inputs={
                        "iteration_count": INPUT["iteration_count"],
                        "tool_result": tool_executor["result"],
                        "tool_error": tool_executor["error"],
                        "tool_success": tool_executor["success"]
                    },
                    return_keys=["tool_prompt"]
                )

                # =====================================================
                # Revision answer detector
                # =====================================================
                branch_check_answer = BranchNode(
                    name="branch_check_answer",
                    cases={
                        "not tool_calls": "prepare_reviewer_messages_fn",  # Không có tool_calls → trả lời ngay
                        "iteration_count < max_iterations": "tool_executor",
                        "iteration_count > max_iterations": "final_output"   # Còn iteration → execute tool
                    },
                    default=END,
                    inputs={
                        "tool_calls": planner_executor_agent["tool_calls"],
                        "tool_name": extract_call["tool_name"],
                        "iteration_count": INPUT["iteration_count"],
                        "max_iterations": self.max_iterations
                    }
                )

                prepare_reviewer_messages_fn = CodeNode(
                    name="prepare_reviewer_messages_fn",
                    code_fn=prepare_reviewer_messages,
                    inputs={
                        "user_query": INPUT["user_query"],
                        "agent_answer": planner_executor_agent["content"],
                        "reasoning_draft_text": code_extract_reviewer_inputs["reasoning_draft_text"],
                        "reasoning_draft_messages": code_extract_reviewer_inputs["reasoning_draft_messages"],
                        "iteration": INPUT["iteration_count"],
                        "max_iteration": self.max_iterations,
                        "system_prompt_template": self.reviewer_prompt
                    },
                    return_keys=["messages"]
                )

                reviewer_llm = LLMNode(
                    name="reviewer_llm",
                    resource_key=self.resource_key,
                    inputs={
                        "messages": prepare_reviewer_messages_fn["messages"],
                        "reasoning_effort": "none",
                        "max_tokens": 4096
                    },
                    stream=False
                )

                reviewer_parser = ParserNode(
                    name="reviewer_parser",
                    format="json",
                    extract_schema=["status: str", "supported_claims: str", "unsupported_claims: str", "issues: str", "recommendations: str", "ask_back_question: str"],
                    inputs={
                        "text": reviewer_llm["content"]
                    },
                    outputs=OUTPUT
                )

                code_revision_prompt_builder = CodeNode(
                    name="code_revision_prompt_builder",
                    code_fn=revision_prompt_builder,
                    inputs={
                        "supported_claims": reviewer_parser,
                        "unsupported_claims": reviewer_parser,
                        "issues": reviewer_parser,
                        "recommendations": reviewer_parser
                    },
                    return_keys=["revision_prompt"]
                )

                branch_check_reviewer = BranchNode(
                    name="branch_check_reviewer",
                    cases={
                        "status == 'PASS'": "llm_stream_answer",  # PASS → trả lời ngay
                        "status == 'REVISE'": "code_revision_prompt_builder",
                        "status == 'ASK_BACK'": "llm_stream_ask_back"   # ASK_BACK → hỏi lại người dùng
                    },
                    default=END,
                    inputs={
                        "status": reviewer_parser,
                    }
                )

                llm_stream_answer = LLMNode(
                    name="llm_stream_answer",
                    instant_response=True,
                    resource_key="fake",
                    inputs={"response": planner_executor_agent["content"], "docs": get_references_ids_fn},
                    outputs=OUTPUT,
                    stream=True
                )

                llm_stream_ask_back = LLMNode(
                    name="llm_stream_ask_back",
                    instant_response=True,
                    resource_key="fake",
                    inputs={"response": reviewer_parser["ask_back_question"], "docs": get_references_ids_fn},
                    outputs=OUTPUT,
                    stream=True
                )

                # =====================================================
                # Update context
                # =====================================================
                update_loop = CodeNode(
                    name="update_loop",
                    code_fn=update_messages,
                    inputs={
                        "messages": INPUT["messages"],
                        "assistant_content": planner_executor_agent["content"],
                        "tool_name": extract_call["tool_name"],
                        "tool_params": extract_call["tool_params"],
                        "tool_prompt": code_tool_prompt_builder,
                        "revision_prompt": code_revision_prompt_builder,
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
                # Final output
                # =====================================================
                final_output = CodeNode(
                    name="final_output",
                    code_fn=extract_final_answer,
                    inputs={"content": planner_executor_agent["content"], "out_messages": update_loop},
                    return_keys=["final_answer", "final_state_messages"],
                    outputs={"final_answer": OUTPUT, "final_state_messages": OUTPUT}
                )

                START >> [get_references_ids_fn, code_extract_reviewer_inputs] >> planner_executor_agent >> extract_call  >> branch_check_answer >> [prepare_reviewer_messages_fn, tool_executor, final_output, END]
                prepare_reviewer_messages_fn >> reviewer_llm >> reviewer_parser >> branch_check_reviewer >> [llm_stream_answer, code_revision_prompt_builder, llm_stream_ask_back]
                code_revision_prompt_builder >> update_loop >> CONTINUE
                tool_executor >> code_tool_prompt_builder >> update_loop >> CONTINUE
                llm_stream_answer >> final_output >> END 
                llm_stream_ask_back >> final_output >> END             

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
        agent = ReActAgentNode(
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