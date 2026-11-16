# BeeAiEnterprisesADK Architecture V6.7

## Overview
`bee_ai_enterprises_adk` là package Google ADK cho chatbot Bee AI Enterprises. Package này có hai entry point rõ ràng:

- `agent.py`: entry point tĩnh cho ADK discovery (`adk web`, `adk run`). File này phải import nhanh, không đọc MongoDB/PostgreSQL và không tạo side effect hạ tầng.
- `bot.py`: wrapper runtime cho luồng API hiện tại trong `entrypoints/api/routes/chat.py` và `entrypoints/api/server.py`. File này build agent động theo `bot_id`, quản lý idempotency, reviewer loop, PostgreSQL session và stream response về API hiện tại.

## Package Layout

```text
bee_ai_enterprises_adk/
  __init__.py
  agent.py                  # ADK discovery root_agent
  bot.py                    # Runtime wrapper cho API hiện tại
  agents/
    main_agent.py           # Factory tạo LlmAgent chính
    reviewer_agent.py       # Reviewer isolated run
  core/
    session_utils.py        # Seed/recover/commit ADK session events
    state_machine.py        # Main/reviewer reflection state machine
  prompts/
    react_agent.py          # Local prompt cho main agent
    reviewer_agent.py       # Local prompt cho reviewer
  tools/
    __init__.py             # ADK tool functions wrapping retrievers
  utils/
    __init__.py
    langfuse_utils.py       # Langfuse helper, hiện không nằm trong prompt path ổn định
    llm_utils.py            # LiteLlm builder
    lock_manager.py         # PostgreSQL advisory lock + request state
```

## Data And State Machine
Mọi phiên chat và vòng đời agent được lưu tại PostgreSQL:

1. **ADK Session Service**: `DatabaseSessionService` quản lý lịch sử hội thoại canonical và working session.
2. **Idempotency State Machine**: bảng `agent_ai.agent_requests` quản lý tiến trình request. Các phase chính:
   - `main_running`: đang chạy main `LlmAgent`.
   - `draft_ready`: đã có draft và `draft_event_id`.
   - `reviewing`: đang chạy reviewer.
   - `reviewing_done`: reviewer đã trả verdict.
   - `accepted`: draft được chấp nhận hoặc cần ASK_BACK.
   - `completed`: đã commit canonical events và sẵn sàng stream cho client.

Schema fresh nằm tại `migrations/V6_7_full_agent_requests_fresh.sql`. Runtime validation trong `bot.py` kiểm tra bảng `agent_ai.agent_requests`, không dùng `public.agent_requests`.

## Session Model
Runtime dùng hai session id:

- `session_id`: canonical conversation id từ API hiện tại.
- `working_session_id`: id deterministic theo `app_name`, `bot_id`, `username`, `session_id`, `request_id` để chạy internal reflection/reviewer an toàn.

`core/session_utils.py` luôn tạo working session trước khi gọi `Runner.run_async`. Nếu canonical session có history, các event phù hợp được clone sang working session với deterministic clone id. Final output thông thường không được seed lại để tránh self-contamination; ASK_BACK có thể được giữ lại như context cần thiết.

## Advisory Lock
`utils/lock_manager.py` dùng `pg_try_advisory_lock` theo tổ hợp `app_name`, `bot_id`, `namespace_version`, `user_id`, `conversation_id`.

- Không cho hai request cùng conversation chạy song song trong cùng namespace.
- Có heartbeat bằng pool riêng để gia hạn `lease_expires_at`.
- Request stale có thể được re-claim sau khi lease timeout.
- Completed request được trả lại theo idempotency cache nếu `request_id` và `request_hash` khớp.

## Prompt Source
Trong giai đoạn ổn định rollout, prompt được đọc local từ `prompts/`, không phụ thuộc Langfuse prompt fetch. `utils/langfuse_utils.py` chỉ còn là helper dự phòng cho giai đoạn đẩy prompt lên Langfuse sau này.

## Tools
ADK tools nằm trong package `tools/`:

- `search_qna_tool`: tìm kho QnA source-of-truth.
- `search_documents_tool`: tìm tài liệu gốc.
- `search_forms_tool`: tìm biểu mẫu.

Các tool khởi tạo retriever lazy để tránh side effect khi ADK discovery import `agent.py`.

## Streaming
API wrapper chỉ stream sau khi state machine hoàn tất và lock đã được giải phóng. Response stream luôn kết thúc bằng chunk `last=True`.

## ADK Discovery
ADK discovery yêu cầu package có:

- `__init__.py` import được `agent`.
- `agent.py` define `root_agent`.

Vì vậy `agent.py` tiếp tục nhẹ với class `ProductionWorkflowAgent` khởi tạo lazy (trì hoãn kết nối DB/env đến khi `_ensure_runtime()` được gọi). Runtime chính vẫn uỷ thác toàn bộ cho `EnterpriseAgentRuntime` để tái sử dụng logic API.
