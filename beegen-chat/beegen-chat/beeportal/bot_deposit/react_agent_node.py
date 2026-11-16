import json
import re
import logging
from typing import Dict, List, Any, Optional
from beeflow.configs.node_config import NodeType
from beeflow.nodes import GraphNode, BaseNode
from beeflow.states.workflow_state import WorkflowState
from beegen.tools.schema.param import ParamSet

LOGGER = logging.getLogger("beegen")

LLAMAINDEX_REACT_PROMPT = """Bạn là một Agent ReAct (Reasoning and Acting) - suy nghĩ và hành động từng bước một.

## Công cụ có sẵn
{tool_desc}

## Ngữ cảnh
{context_prompt}

## Quy tắc quan trọng - BẮT BUỘC PHẢI TUÂN THỦ
1. Chỉ thực HIỆN MỘT công cụ mỗi bước - KHÔNG BAO GIỜ dùng song song
2. Luôn bắt đầu với "=== Thought ===" để lập luận
3. Dùng chính xác MỘT công cụ với "=== Action ===" và "=== Params ==="
4. Đợi "Observation:" trước khi tiếp bước tiếp theo
5. Tiếp tục cho đến khi có câu trả lời mà không cần thêm công cụ
6. Trả lời bằng Tiếng Việt

## Định dạng BẮT BUỘC
Bạn PHẢI theo định dạng chính xác này (dùng === làm dấu phân cách):

=== Thought ===
[Lập luận của bạn - cụ thể]
=== Action ===
[tên CHÍNH XÁC một công cụ từ: {tool_names}]
=== Params ===
{{"parameter": "value"}}

Sau mỗi action, bạn sẽ nhận được:
```
Observation: [kết quả từ công cụ]
```

Khi đã đủ thông tin, kết thúc với:
=== Thought ===
[Giải thích tại sao bạn có thể trả lời]
=== Answer ===
[Câu trả lời cuối cùng bằng Tiếng Việt]

Nếu không thể hoàn thành:
=== Thought ===
[Giải thích tại sao không thể tiếp tục]
=== Answer ===
[Giải thích bằng Tiếng Việt về hạn chế]

## Ví dụ minh họa
Human: Tính (8 + 1) x (12 + 10)?

=== Thought ===
Tôi cần tính biểu thức này từng bước. Đầu tiên, tôi sẽ tính 8 + 1.
=== Action ===
add
=== Params ===
{{"a": 8, "b": 1}}

Observation: 9

=== Thought ===
Bây giờ tôi cần tính 12 + 10.
=== Action ===
add
=== Params ===
{{"a": 12, "b": 10}}

Observation: 22

=== Thought ===
Cuối cùng, tôi cần nhân 9 x 22.
=== Action ===
mul
=== Params ===
{{"a": 9, "b": 22}}

Observation: 198

=== Thought ===
Tôi đã có đủ thông tin để trả lời câu hỏi.
=== Answer ===
Kết quả của (8 + 1) x (12 + 10) là 198.

## Lưu ý quan trọng
- KHÔNG dùng định dạng "Thought:" thông thường - phải dùng "=== Thought ==="
- KHÔNG dùng multi_tool_use.parallel hay bất kỳ thực thi song song nào
- KHÔNG cố dùng nhiều công cụ trong một bước
- KHÔNG bỏ qua bước Thought
- KHÔNG bao quanh toàn bộ phản hồi bằng markdown code blocks
- LUÔN đợi Observation trước khi tiếp theo Action tiếp theo
- Kiên nhẫn và có phương pháp - đây là sức mạnh của ReAct
- LUÔN sử dụng ÍT NHẤT 1 CÔNG CỤ và đợi phản hồi

## Cuộc trò chuyện hiện tại
Dưới đây là cuộc trò chuyện hiện tại:"""

TOOL_FORMAT_PROMPT = """
> Tool name: {tool_name}
Tool Description: {tool_description}
Tool Args: {tool_argument}
"""


def parse_react_output(text: str) -> Dict[str, Any]:
    """Parse ReAct output bằng regex thay vì YAML/JSON.

    Extracts Thought, Action, Params, và Answer từ output của LLM.
    Xử lý được format === Thought === ... === Action === ...
    """
    result = {
        "Thought": None,
        "Action": None,
        "Params": None,
        "Answer": None
    }

    # Pattern cho Answer với quotes: === Thought === "..." === Answer === "..."
    answer_match = re.search(
        r'=== Thought ===\s*"([^"]+)"\s*=== Answer ===\s*"([^"]+)"',
        text, re.DOTALL
    )
    if answer_match:
        result["Thought"] = answer_match.group(1).strip()
        result["Answer"] = answer_match.group(2).strip()
        return result

    # Pattern cho Answer KHÔNG có quotes: === Answer === text...
    # Tìm từ === Answer === đến hết text hoặc đến dòng mới
    answer_no_quote = re.search(
        r'=== Answer ===\s*(.+?)(?=\n===|\n*$|<\|)',
        text, re.DOTALL
    )
    if answer_no_quote:
        result["Answer"] = answer_no_quote.group(1).strip()
        # Tìm Thought trước Answer
        thought_for_answer = re.search(
            r'=== Thought ===\s*"([^"]+)"\s*(?:=== Answer ===)',
            text, re.DOTALL
        )
        if thought_for_answer:
            result["Thought"] = thought_for_answer.group(1).strip()
        return result

    # Pattern cho Action (Thought + Action + Params)
    thought_match = re.search(r'=== Thought ===\s*"([^"]+)"', text)
    if thought_match:
        result["Thought"] = thought_match.group(1).strip()

    action_match = re.search(r'=== Action ===\s*(\w+)', text)
    if action_match:
        result["Action"] = action_match.group(1).strip()

    # Extract Params
    params_match = re.search(r'=== Params ===\s*(\{[^}]+\})', text, re.DOTALL)
    if params_match:
        params_str = params_match.group(1).strip()
        try:
            result["Params"] = json.loads(params_str)
        except json.JSONDecodeError:
            result["Params"] = params_str

    return result


class ReactAgentNode(GraphNode):
    """
    ReAct Agent với manual loop trong run() method.

    Luồng hoạt động:
    1. Thought - LLM suy nghĩ -> stream Thought cho user
    2. Action - LLM chọn tool -> stream Action + Params
    3. Execute tool -> stream Observation
    4. Cập nhật messages -> tiếp tục hoặc kết thúc với Answer
    """

    type: NodeType = "react-agent"

    input_schema: ParamSet = (
        ParamSet.new()
            .var("messages: List")
            .var("query: str")
            .build()
    )

    output_schema: ParamSet = (
        ParamSet.new()
            .var("Answer: str")
            .build()
    )

    def __init__(
        self,
        resource_key: str,
        tools: List[BaseNode],
        max_iterations: int = 5,
        context_prompt: str = "",
        **kwargs
    ) -> None:
        super().__init__(**kwargs)

        self.resource_key = resource_key
        self.tools = tools
        self.max_iterations = max_iterations
        self.context_prompt = context_prompt

    def build(self):
        """Override build vì ReactAgentNode dùng manual loop trong run(), không cần internal graph."""
        # Không làm gì - không cần build internal graph
        pass

    def _create_react_prompt(self) -> str:

        def desc(tool: BaseNode) -> str:
            tool_desc = TOOL_FORMAT_PROMPT.format(
                tool_name=tool.name,
                tool_description=tool.description,
                tool_argument=tool.get_openai_function_schema()["parameters"]
            )

            return tool_desc

        tools_desc = [desc(tool) for tool in self.tools]
        tool_names = [tool.name for tool in self.tools]

        return LLAMAINDEX_REACT_PROMPT.format(
            tool_desc='\n'.join(tools_desc),
            tool_names=', '.join(tool_names),
            context_prompt=self.context_prompt
        )

    async def run(self, state: WorkflowState, context_id: str = None) -> Dict[str, Any]:
        """Chạy ReAct agent với manual loop - streaming từng bước."""
        from beeflow.utils.streaming import STREAM_SERVICE
        from beegen.utils.common import fake_chunk_from
        from beegen.registry.resource_hub import ResourceHub
        import asyncio

        request_id = state.request_id

        # Lấy messages để log
        try:
            messages_for_log = state["beeDeposit", "messages", context_id]
        except:
            messages_for_log = None

        LOGGER.info(f"request[{request_id}]: None, running NODE: {self.name}: REACT_AGENT, messages = {messages_for_log}")

        # Lấy query từ inputs - có thể là messages hoặc query trực tiếp
        # Sử dụng cách truy cập đúng của WorkflowState
        messages_input = None

        # Thử lấy từ process_query (node trước đó)
        try:
            origin_query = state["process_query", "origin_query", context_id]
            query = origin_query
        except:
            query = None

        # Nếu không có origin_query, thử lấy từ messages
        if not query:
            try:
                messages_input = state["beeDeposit", "messages", context_id]
            except:
                pass

            # Trích xuất query từ messages (tin nhắn cuối cùng của user)
            if messages_input and isinstance(messages_input, list):
                for msg in reversed(messages_input):
                    if msg.get("role") == "user":
                        query = msg.get("content")
                        break

        # Fallback cuối cùng
        if not query:
            query = "Xin chào"

        # Tạo messages ban đầu
        system_prompt = self._create_react_prompt()
        messages = [{"role": "system", "content": system_prompt}]

        # Thêm lịch sử chat (ngoại trừ tin nhắn cuối cùng của user vì đó là query hiện tại)
        if messages_input and isinstance(messages_input, list) and len(messages_input) > 1:
            # Lấy tất cả tin nhắn trừ tin nhắn cuối cùng
            history = messages_input[:-1]
            for msg in history:
                role = msg.get("role")
                content = msg.get("content")
                if role in ["user", "assistant"] and content:
                    messages.append({"role": role, "content": content})

        # Thêm query hiện tại
        messages.append({"role": "user", "content": query})

        # LLM resource
        llm = ResourceHub.self().llm(self.resource_key)

        # Langfuse client cho logging - log riêng từng bước
        langfuse = ResourceHub.self().langfuse("beegen")
        request_trace = langfuse.trace(id=request_id, name=f"react_agent_{self.name}")

        iteration = 0
        final_answer = None
        retrieved_docs = None  # Store docs từ retrieval tool
        last_tool_result = None  # Store last tool result for fallback
        retrieval_forced = False  # Track nếu đã force gọi retrieval

        # Tìm retrieval_graph tool để force call nếu cần
        retrieval_tool = None
        for tool in self.tools:
            if "retrieval" in tool.name.lower():
                retrieval_tool = tool
                break

        while iteration < self.max_iterations:
            LOGGER.info(f"request[{request_id}]: None, running NODE: {self.name}: REACT_AGENT, iteration = {iteration + 1}/{self.max_iterations}")

            # Chỉ stream bắt đầu vòng mới nếu là vòng đầu
            if iteration == 0:
                await STREAM_SERVICE.push(
                    request_id=request_id,
                    channel_name=self.identity(context_id),
                    data=fake_chunk_from(
                        content="",
                        model=self.resource_key,
                        docs=retrieved_docs
                    )
                )

            # Gọi LLM để suy nghĩ - stream ngay khi thấy === Answer ===
            try:
                # Log lên langfuse - tạo generation cho mỗi vòng
                generation = request_trace.generation(
                    name=f"iter_{iteration + 1}_thought",
                    input=messages,
                    metadata={"iteration": iteration + 1, "step": "thought"}
                )

                response_text = ""
                answer_started = False
                answer_content = ""

                async for chunk in llm.stream(messages=messages):
                    if chunk.choices and chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        response_text += content

                        # Kiểm tra nếu chưa bắt đầu answer và trong content có === Answer ===
                        if not answer_started:
                            if "=== Answer ===" in response_text:
                                answer_started = True
                                # Lấy phần sau === Answer ===
                                answer_match = re.search(r'=== Answer ===\s*(.+?)$', response_text, re.DOTALL)
                                if answer_match:
                                    answer_content = answer_match.group(1).strip()
                                    # Stream phần Answer đã có
                                    await STREAM_SERVICE.push(
                                        request_id=request_id,
                                        channel_name=self.identity(context_id),
                                        data=fake_chunk_from(
                                            content=answer_content,
                                            model=self.resource_key,
                                            docs=retrieved_docs
                                        )
                                    )
                        else:
                            # Đã bắt đầu answer, tiếp tục stream phần còn lại
                            # Tìm phần mới thêm vào sau Answer
                            if "=== Answer ===" in content:
                                # Content bắt đầu bằng Answer, lấy phần sau
                                new_content = content.split("=== Answer ===", 1)[1] if "=== Answer ===" in content else content
                            else:
                                new_content = content

                            if new_content:
                                answer_content += new_content
                                await STREAM_SERVICE.push(
                                    request_id=request_id,
                                    channel_name=self.identity(context_id),
                                    data=fake_chunk_from(
                                        content=new_content,
                                        model=self.resource_key,
                                        docs=retrieved_docs
                                    )
                                )

                # End langfuse generation
                generation.end(
                    output=response_text,
                    model=self.resource_key
                )

                # Nếu đã stream answer trong quá trình streaming
                if answer_started and answer_content:
                    LOGGER.info(f"request[{request_id}]: None, NODE: {self.name}: REACT_ANSWER, answer = {answer_content[:200]}...")
                    final_answer = answer_content
                    break

                # Parse output (chỉ cần khi không stream trong khi nhận)
                parsed = parse_react_output(response_text)
                action = parsed.get("Action")
                params = parsed.get("Params")
                answer = parsed.get("Answer")

                LOGGER.info(f"request[{request_id}]: None, NODE: {self.name}: PARSED, action = {action}, params = {params}, answer = {answer}")
                print(f"[DEBUG] Parsed result - action: {action}, params: {params}, answer: {answer}")

                # Xử lý khi LLM trả lời trực tiếp (không theo format ReAct)
                # LLM có thể trả lời thẳng mà không cần gọi tool
                if not answer_started and not answer and not action and not params:
                    # === FORCE LLM TO CALL RETRIEVAL: Trước khi trả lời trực tiếp ===
                    # Nếu LLM định trả lời trực tiếp mà chưa có retrieval → nhắc LLM gọi retrieval
                    if iteration == 0 and not retrieval_forced and retrieval_tool:
                        LOGGER.info(f"request[{request_id}]: None, NODE: {self.name}: REMIND_TO_CALL_RETRIEVAL_BEFORE_ANSWER")
                        print(f"[DEBUG] Remind LLM to call retrieval before direct answer")

                        # Thêm message nhắc LLM gọi retrieval - LLM sẽ tự tạo query phù hợp
                        remind_message = (
                            f"Trước khi trả lời, bạn cần tìm kiếm thông tin trong tài liệu. "
                            f"Hãy sử dụng tool retrieval_graph để tìm kiếm thông tin liên quan đến câu hỏi."
                        )
                        messages.append({"role": "assistant", "content": response_text})
                        messages.append({"role": "user", "content": remind_message})

                        retrieval_forced = True
                        LOGGER.info(f"request[{request_id}]: None, NODE: {self.name}: REMIND_DONE")

                        # Tiếp tục loop để LLM quyết định gọi retrieval với query do LLM tạo
                        iteration += 1
                        continue

                    # LLM trả lời trực tiếp, lấy response_text làm answer
                    LOGGER.info(f"request[{request_id}]: None, NODE: {self.name}: DIRECT_ANSWER, answer = {response_text[:200]}...")
                    print(f"[DEBUG] LLM returned direct answer (no ReAct format), using response_text")
                    final_answer = response_text.strip()
                    if final_answer:
                        # Stream answer này về cho user
                        await STREAM_SERVICE.push(
                            request_id=request_id,
                            channel_name=self.identity(context_id),
                            data=fake_chunk_from(
                                content=final_answer,
                                model=self.resource_key,
                                docs=retrieved_docs
                            )
                        )
                        break

                # Nếu đã stream trong khi nhận thì không cần làm gì thêm
                # Chỉ xử lý khi chưa có answer (LLM gọi tool)
                if not answer_started and not answer and action and params:
                    # Chưa có Answer -> execute tool (không stream ra ngoài)
                    # Log action lên langfuse (không stream)
                    action_gen = request_trace.generation(
                        name=f"iter_{iteration + 1}_action",
                        input={"response_text": response_text, "action": action, "params": params},
                        metadata={"iteration": iteration + 1, "step": "action", "action": action, "params": params}
                    )

                    # Execute tool
                    tool_result = None
                    tool_error = None
                    tool_success = False
                    tool_matched = False

                    for tool in self.tools:
                        # Log để debug
                        print(f"[DEBUG] Looking for tool: {action}, available: {tool.name}")

                        if tool.name == action:
                            tool_matched = True
                            LOGGER.info(f"request[{request_id}]: None, NODE: {self.name}: EXEC_TOOL, tool = {action}, params = {params}")
                            try:
                                # Inject inputs cho tool với params từ LLM
                                tool_inputs = {}
                                if params:
                                    # Merge params vào tool inputs
                                    tool_inputs.update(params)

                                print(f"[DEBUG] Injecting inputs for tool {tool.name}: {tool_inputs}")

                                # Inject inputs vào state cho tool
                                if tool_inputs:
                                    state.inject_inputs(
                                        node=tool.full_name,
                                        inputs=tool_inputs,
                                        context_id=context_id
                                    )

                                # Chạy tool
                                tool_result = await tool.run(state, context_id)
                                # Giới hạn độ dài khi log
                                tool_result_str = str(tool_result)
                                if len(tool_result_str) > 100:
                                    tool_result_str = tool_result_str[:100] + "..."
                                print(f"[DEBUG] Tool result: {tool_result_str}")

                                # Extract docs từ tool_result nếu là retrieval tool
                                if isinstance(tool_result, dict) and "docs" in tool_result:
                                    docs = tool_result.get("docs", [])
                                    if docs:
                                        # Lấy danh sách doc IDs
                                        retrieved_docs = [{"id": doc.get("chunk_id") or doc.get("id")} for doc in docs if isinstance(doc, dict)]
                                        print(f"[DEBUG] Retrieved docs IDs: {retrieved_docs}")
                                        # Lưu lại docs gốc để dùng cho fallback
                                        last_tool_result = tool_result

                                if isinstance(tool_result, dict):
                                    tool_result = tool_result.get("result") or str(tool_result)

                                # Lưu tool_result để dùng khi fallback
                                if tool_success:
                                    last_tool_result = tool_result

                                tool_success = True
                            except Exception as e:
                                import traceback
                                tool_error = f"{str(e)}\n{traceback.format_exc()}"
                            break

                    if not tool_matched:
                        tool_error = f"Không tìm thấy tool: {action}. Các tool available: {[t.name for t in self.tools]}"

                    # End action generation
                    action_gen.end(
                        output={"tool_result": tool_result, "tool_error": tool_error},
                        model="tool_execution"
                    )

                    # Log observation lên langfuse (không stream)
                    obs_gen = request_trace.generation(
                        name=f"iter_{iteration + 1}_observation",
                        input={"tool_result": tool_result, "tool_error": tool_error},
                        metadata={"iteration": iteration + 1, "step": "observation"}
                    )

                    obs_content = f"Observation: {tool_result}" if tool_success else f"Observation: Error - {tool_error}"

                    # End observation generation
                    obs_gen.end(
                        output=obs_content,
                        model="observation"
                    )

                    # Cập nhật messages (không stream observation)
                    messages.append({
                        "role": "assistant",
                        "content": response_text
                    })
                    messages.append({
                        "role": "user",
                        "content": obs_content
                    })

                    # === FORCE LLM TO CALL RETRIEVAL: Sau khi execute tool của LLM ===
                    # Chỉ ở iteration đầu tiên, sau khi tool chạy xong, nếu chưa có retrieval thì yêu cầu LLM gọi
                    # Thay vì gọi trực tiếp, ta nhắc LLM để LLM tự tạo query phù hợp
                    if iteration == 0 and not retrieval_forced and retrieval_tool:
                        action_is_retrieval = action and "retrieval" in action.lower()

                        if not action_is_retrieval:
                            LOGGER.info(f"request[{request_id}]: None, NODE: {self.name}: REMIND_TO_CALL_RETRIEVAL, action = {action}")
                            print(f"[DEBUG] Remind LLM to call retrieval - action: {action}")

                            # Thêm message "nhắc" LLM gọi retrieval - không gọi trực tiếp
                            # LLM sẽ tự tạo query phù hợp hơn
                            remind_message = (
                                f"Trước khi trả lời, bạn cần tìm kiếm thông tin trong tài liệu. "
                                f"Hãy sử dụng tool retrieval_graph để tìm kiếm thông tin liên quan đến câu hỏi."
                            )
                            messages.append({"role": "user", "content": remind_message})

                            retrieval_forced = True  # Đánh dấu để không nhắc nữa
                            LOGGER.info(f"request[{request_id}]: None, NODE: {self.name}: REMIND_DONE")

                            # Tiếp tục loop để LLM quyết định gọi retrieval với query do LLM tạo
                            iteration += 1
                            continue
                        else:
                            # Tool vừa chạy là retrieval rồi
                            retrieval_forced = True

            except Exception as e:
                import traceback
                traceback.print_exc()
                break

            iteration += 1

        # Kết thúc
        await STREAM_SERVICE.end(request_id, self.identity(context_id))

        # Fallback: nếu không có answer nhưng có tool_result từ retrieval, gọi LLM để trả lời
        LOGGER.info(f"request[{request_id}]: None, NODE: {self.name}: CHECK_FALLBACK, final_answer = {final_answer is not None}, has_tool_result = {last_tool_result is not None}")
        # Giới hạn độ dài khi log
        final_answer_str = str(final_answer)[:100] + "..." if final_answer and len(str(final_answer)) > 100 else final_answer
        last_tool_result_str = str(last_tool_result)[:100] + "..." if last_tool_result and len(str(last_tool_result)) > 100 else last_tool_result
        print(f"[DEBUG FALLBACK] final_answer={final_answer_str}, last_tool_result={last_tool_result_str}")
        if not final_answer and last_tool_result:
            LOGGER.info(f"request[{request_id}]: None, NODE: {self.name}: FALLBACK_START")
            try:
                # Tạo prompt từ tool_result
                context_text = ""
                if isinstance(last_tool_result, dict) and "docs" in last_tool_result:
                    docs = last_tool_result.get("docs", [])
                    LOGGER.info(f"request[{request_id}]: None, NODE: {self.name}: FALLBACK_DOCS, count = {len(docs) if docs else 0}")
                    print(f"[DEBUG FALLBACK] docs count: {len(docs) if docs else 0}")
                    if docs:
                        # Lấy text content từ docs
                        for i, doc in enumerate(docs[:5]):  # Giới hạn 5 docs
                            if isinstance(doc, dict):
                                content = doc.get("content", "") or doc.get("text", "") or ""
                                print(f"[DEBUG FALLBACK] doc {i} content: {content[:100]}...")
                                if content:
                                    context_text += f"\n--- Tài liệu {i+1} ---\n{content}"

                if context_text:
                    # Tạo messages với lịch sử chat
                    system_prompt = self._create_react_prompt()
                    fallback_messages = [{"role": "system", "content": system_prompt}]

                    # Thêm lịch sử chat (ngoại trừ tin nhắn cuối cùng)
                    if messages_input and isinstance(messages_input, list) and len(messages_input) > 1:
                        history = messages_input[:-1]
                        for msg in history:
                            role = msg.get("role")
                            content = msg.get("content")
                            if role in ["user", "assistant"] and content:
                                fallback_messages.append({"role": role, "content": content})

                    # Thêm query hiện tại với context từ docs
                    fallback_messages.append({
                        "role": "user",
                        "content": f"Câu hỏi: {query}\n\nTài liệu tham khảo:{context_text}\n\nHãy trả lời câu hỏi dựa trên tài liệu trên:"
                    })

                    # Stream answer
                    async for chunk in llm.stream(messages=fallback_messages):
                        if chunk.choices and chunk.choices[0].delta.content:
                            content = chunk.choices[0].delta.content
                            final_answer = (final_answer or "") + content
                            await STREAM_SERVICE.push(
                                request_id=request_id,
                                channel_name=self.identity(context_id),
                                data=fake_chunk_from(
                                    content=content,
                                    model=self.resource_key,
                                    docs=retrieved_docs
                                )
                            )
            except Exception as e:
                import traceback
                traceback.print_exc()

        if not final_answer:
            final_answer = "Không thể hoàn thành yêu cầu trong giới hạn iterations."

        # Lưu kết quả vào state để node tiếp theo có thể đọc được
        state[self.full_name, "Answer", context_id] = final_answer

        LOGGER.info(f"request[{request_id}]: None, complete NODE: {self.name}: REACT_AGENT, answer = {final_answer[:200] if final_answer else 'None'}...")

        return self.get_result(state)
        