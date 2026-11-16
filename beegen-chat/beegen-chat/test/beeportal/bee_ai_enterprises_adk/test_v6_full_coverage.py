import pytest
import asyncio
import os
os.environ["ADK_WEB_ENABLE_PRODUCTION_RUNTIME"] = "true"
from unittest.mock import AsyncMock, MagicMock, patch

from beeportal.bee_ai_enterprises_adk.bot import BeeAiEnterprisesADK
from beeportal.bee_ai_enterprises_adk.utils.lock_manager import SessionLockManager, AgentRequestState, HeartbeatFailedError
from google.adk.events import Event
from google.genai import types

@pytest.fixture
def mock_bot():
    bot = BeeAiEnterprisesADK(bot_id="072fab09-7f7f-4682-9152-c142fa178444")
    runtime = bot._runtime
    runtime._ensure_initialized = AsyncMock()
    runtime._main_agent = MagicMock()
    runtime._main_agent.name = "ENTERPRISES_MAIN_AGENT"
    runtime._check_context_guard = AsyncMock(return_value=True)
    bot._runtime._app_name = "bee_ai_enterprises_adk:072fab09-7f7f-4682-9152-c142fa178444"
    bot._runtime._reviewer_agent = MagicMock()
    bot._runtime._lock_manager = MagicMock(spec=SessionLockManager)

    # Mock AgentRequestState
    req_state = MagicMock(spec=AgentRequestState)
    req_state.phase = "main_running"
    req_state.iteration = 0
    req_state.status = "processing"
    req_state.user_event_id = None
    req_state.draft_event_id = None
    req_state.reviewer_feedback = None
    req_state.reviewer_verdict = None
    req_state.response = None

    async def mock_update_state(**kwargs):
        for k, v in kwargs.items():
            if v is not None:
                setattr(req_state, k, v)
    req_state.update_state = AsyncMock(side_effect=mock_update_state)
    req_state.mark_completed = AsyncMock()
    req_state.mark_failed = AsyncMock()
    req_state.raise_if_heartbeat_failed = MagicMock()

    lock_ctx = MagicMock()
    lock_ctx.__aenter__ = AsyncMock(return_value=req_state)
    lock_ctx.__aexit__ = AsyncMock(return_value=None)
    bot._runtime._lock_manager.lock.return_value = lock_ctx

    mock_session = MagicMock()
    mock_session.events = []
    bot._runtime._canonical_session_service = __import__('unittest.mock').mock.MagicMock()
    bot._runtime._canonical_session_service.get_session = AsyncMock(return_value=mock_session)
    bot._runtime._canonical_session_service.create_session = AsyncMock(return_value=mock_session)
    bot._runtime._canonical_session_service.append_event = AsyncMock()

    bot._runtime._runner = MagicMock()
    async def dummy_run(*args, **kwargs):
        from google.adk.events import Event
        from google.genai import types
        yield Event(
            id="dummy_evt",
            author="ENTERPRISES_MAIN_AGENT",
            content=types.Content(role="model", parts=[types.Part.from_text(text="Dummy answer")]),
            partial=False
        )
    bot._runtime._runner.run_async = MagicMock(side_effect=dummy_run)
    patcher = patch("beeportal.bee_ai_enterprises_adk.core.state_machine.recover_stale_request", new_callable=AsyncMock)
    mock_recover = patcher.start()
    mock_recover.return_value = (True, "Draft", "Reasoning", "evt-draft", "evt-user")
    bot._runtime.mock_recover_stale_request = mock_recover

    bot._run_reviewer_agent = AsyncMock(return_value=("PASS", "Looks good", "Final response", "evt-rev"))

    return bot, req_state


@pytest.mark.asyncio
@patch("beeportal.bee_ai_enterprises_adk.core.state_machine.run_reviewer")
async def test_ask_back_creates_synthetic_event(mock_run_reviewer, mock_bot):
    bot, req_state = mock_bot

    # Mock Reviewer trả về ASK_BACK
    mock_verdict = MagicMock()
    mock_verdict.status = "ASK_BACK"
    mock_verdict.ask_back_question = "What exactly?"
    mock_run_reviewer.return_value = mock_verdict

    # Run the generator
    chunks = []
    async for chunk in bot.run(
        messages=[{"role": "user", "content": "hello"}],
        session_id="session1",
        client_message_id="msg1",
        username="test"
    ):
        chunks.append(chunk)

    # Đảm bảo append_event được gọi 2 lần (1 cho user, 1 cho synthetic final)
    assert bot._runtime._canonical_session_service.append_event.call_count == 2
    event_arg = bot._runtime._canonical_session_service.append_event.call_args_list[-1].args[1]
    assert event_arg.author == "ENTERPRISES_MAIN_AGENT"
    assert event_arg.content.role == "model"
    assert "What exactly?" in event_arg.content.parts[0].text
    assert event_arg.custom_metadata["is_ask_back"] is True

    # Đảm bảo final_evt_id trả về là ID của event
    req_state.mark_completed.assert_called_once()
    assert req_state.mark_completed.call_args.kwargs["final_event_id"] == event_arg.id


@pytest.mark.asyncio
async def test_heartbeat_failure_calls_mark_failed(mock_bot):
    bot, req_state = mock_bot

    req_state.raise_if_heartbeat_failed.side_effect = HeartbeatFailedError("Heartbeat died")

    chunks = []
    async for chunk in bot.run(
        messages=[{"role": "user", "content": "hello"}],
        session_id="session1",
        client_message_id="msg1",
        username="test"
    ):
        chunks.append(chunk)

    req_state.mark_failed.assert_called_once_with("Heartbeat died", status="retryable_failed")
    full_text = "".join(getattr(chunk.choices[0].delta, "content", "") for chunk in chunks if chunk.choices and chunk.choices[0].delta)
    assert "mất kết nối mạng cục bộ" in full_text


@pytest.mark.asyncio
async def test_idempotent_cached_response(mock_bot):
    bot, req_state = mock_bot
    req_state.status = "completed"
    req_state.response = "Cached answer"

    chunks = []
    async for chunk in bot.run(
        messages=[{"role": "user", "content": "hello"}],
        session_id="session1",
        client_message_id="msg1",
        username="test"
    ):
        chunks.append(chunk)

    full_text = "".join(getattr(chunk.choices[0].delta, "content", "") for chunk in chunks if chunk.choices and getattr(chunk.choices[0], "delta", None))
    assert "Cached answer" in full_text

    bot._runtime._runner.run_async.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("POSTGRES_URL"), reason="Requires POSTGRES_URL")
async def test_integration_advisory_lock():
    """Test kết nối PostgreSQL thực: hai tiến trình cố khoá cùng một session."""
    pg_url = os.getenv("POSTGRES_URL")
    lm = await SessionLockManager.create(pg_url)

    async def try_lock(req_id):
        try:
            async with lm.lock("test_app", "test_bot", "v1", "user1", "session123", req_id, "hash", timeout=1.0, lease_duration=5) as state:
                await asyncio.sleep(2.0)
                return "locked"
        except Exception as e:
            print(f"Lock exception: {e}")
            return "timeout"

    # Chạy song song 2 coroutine
    results = await asyncio.gather(try_lock("req1"), try_lock("req2"))

    # Cần 1 cái lấy được lock, 1 cái bị timeout (vì wait 1.0s nhưng sleep 2.0s)
    assert "locked" in results
    assert "timeout" in results

    await lm.close()


@pytest.mark.asyncio
@patch("beeportal.bee_ai_enterprises_adk.core.state_machine.run_reviewer")
async def test_crash_recovery_user_event_id(mock_run_reviewer, mock_bot):
    """Kiểm tra khôi phục user_event_id khi pod chết sau khi persist sự kiện user nhưng chưa checkpoint."""
    bot, req_state = mock_bot

    mock_verdict = MagicMock()
    mock_verdict.status = "PASS"
    mock_run_reviewer.return_value = mock_verdict

    # Mô phỏng session có user event (đã persist) với invocation_id đúng dạng iter 0
    mock_session = bot._runtime._canonical_session_service.get_session.return_value

    user_event = Event(
        id="user_evt_1",
        author="user",
        invocation_id="req123:main:0",
        content=types.Content(role="user", parts=[types.Part.from_text(text="hello")])
    )

    draft_event = Event(
        id="draft_evt_1",
        author="ENTERPRISES_MAIN_AGENT",
        invocation_id="req123:main:0",
        content=types.Content(role="model", parts=[types.Part.from_text(text="Here is draft")])
    )

    mock_session.events = [user_event, draft_event]

    req_state.phase = "main_running"
    req_state.iteration = 0
    req_state.user_event_id = None
    bot._runtime.mock_recover_stale_request.return_value = (True, "Here is draft", None, "draft_evt_1", "user_evt_1")
    req_state.user_event_id = None

    # No longer needed to unmock since it's a separate module function

    chunks = []
    with patch.object(Event, "is_final_response", return_value=True):
        async for chunk in bot.run(
            messages=[{"role": "user", "content": "hello"}],
            session_id="session1",
            client_message_id="req123",
            username="test"
        ):
            chunks.append(chunk)

    # Đảm bảo req_state.update_state đã được gọi kèm user_event_id="user_evt_1"
    bot._runtime._canonical_session_service.get_session.assert_called()
    assert req_state.user_event_id == "user_evt_1"

    # Assert recovered answer is exactly "Here is draft" (no user message prepended)
    final_chunk_texts = [getattr(c.choices[0].delta, "content", "") for c in chunks if getattr(c.choices[0].delta, "content", "")]
    recovered_answer = "".join(final_chunk_texts)
    assert recovered_answer == "Here is draft"


@pytest.mark.asyncio
@patch("beeportal.bee_ai_enterprises_adk.core.state_machine.run_reviewer")
async def test_ask_back_dedup(mock_run_reviewer, mock_bot):
    """Kiểm tra nếu ASK_BACK event đã tồn tại trong session thì không append thêm."""
    bot, req_state = mock_bot

    mock_verdict = MagicMock()
    mock_verdict.status = "ASK_BACK"
    mock_verdict.ask_back_question = "What exactly?"
    mock_run_reviewer.return_value = mock_verdict

    # Mô phỏng trong DB đã có event ASK_BACK
    mock_session = bot._runtime._canonical_session_service.get_session.return_value

    existing_ask_event = MagicMock()
    existing_ask_event.invocation_id = "req_dedup:ask_back"
    existing_ask_event.author = "ENTERPRISES_MAIN_AGENT"

    def mock_get(key, default=None):
        if key == "request_id": return "req_dedup"
        if key == "is_ask_back": return True
        return default

    existing_ask_event.custom_metadata.get.side_effect = mock_get
    existing_ask_event.content.role = "model"
    part = MagicMock()
    part.text = "What exactly?"
    existing_ask_event.content.parts = [part]
    import uuid
    EVENT_NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")
    identity_final = f"bee_ai_enterprises_adk:072fab09-7f7f-4682-9152-c142fa178444|072fab09-7f7f-4682-9152-c142fa178444|test|session1|req_dedup|final"
    final_event_id = uuid.uuid5(EVENT_NAMESPACE, identity_final).hex
    existing_ask_event.id = final_event_id
    existing_ask_event.partial = False

    identity_user = f"bee_ai_enterprises_adk:072fab09-7f7f-4682-9152-c142fa178444|072fab09-7f7f-4682-9152-c142fa178444|test|session1|req_dedup|user"
    user_event_id = uuid.uuid5(EVENT_NAMESPACE, identity_user).hex
    existing_user_event = MagicMock()
    existing_user_event.id = user_event_id
    existing_user_event.partial = False

    mock_session.events = [existing_user_event, existing_ask_event]

    # Separate working session to avoid mutating canonical session
    mock_working_session = MagicMock()
    mock_working_session.events = []

    chunks = []
    async for chunk in bot.run(
        messages=[{"role": "user", "content": "hello"}],
        session_id="session1",
        client_message_id="req_dedup",
        username="test"
    ):
        chunks.append(chunk)

    # Đảm bảo KHÔNG append_event thêm ASK_BACK trùng vào canonical session
    for call in bot._runtime._canonical_session_service.append_event.call_args_list:
        kwargs = call.kwargs
        if kwargs.get("session_id") == "session1":
            evt = kwargs.get("event")
            if evt:
                assert evt.id != final_event_id, "Duplicate ASK_BACK appended to canonical session"

    # Nhưng final_event_id phải lấy từ event cũ
    req_state.mark_completed.assert_called_once()
    assert req_state.mark_completed.call_args.kwargs["final_event_id"] == final_event_id


@pytest.mark.asyncio
async def test_unlock_before_stream(mock_bot):
    """Đảm bảo pg_advisory_unlock xảy ra TRƯỚC KHI yield chunk đầu tiên."""
    bot, req_state = mock_bot
    req_state.status = "completed"
    req_state.response = "Hello stream"

    lock_ctx = bot._runtime._lock_manager.lock.return_value
    unlocked_flag = {"unlocked": False}

    # Theo dõi __aexit__
    async def mock_aexit(*args):
        unlocked_flag["unlocked"] = True
    lock_ctx.__aexit__.side_effect = mock_aexit

    streamed_after_unlock = []
    async for chunk in bot.run(
        messages=[{"role": "user", "content": "hello"}],
        session_id="session1",
        client_message_id="msg1",
        username="test"
    ):
        if getattr(chunk.choices[0].delta, "content", ""):
            streamed_after_unlock.append(unlocked_flag["unlocked"])

    assert all(streamed_after_unlock)


@pytest.mark.asyncio
async def test_revise_recovery(mock_bot):
    """Kiểm tra REVISE recovery (iteration > 0, phase=main_running)."""
    bot, req_state = mock_bot
    req_state.iteration = 1
    req_state.phase = "main_running"
    req_state.reviewer_feedback = "Need more details"

    # Reset mock to simulate recovery failing for the old draft if needed,
    # but wait, the test actually needs recover_stale_request to return False the second time?
    # Actually the test relied on mock_recover side effect:
    # iteration=0 -> True, iteration=1 -> False
    # Let's just set the side_effect
    bot._runtime.mock_recover_stale_request.side_effect = [
        (True, "Old draft", "Reason", "evt-draft1", "evt-user"),
        (False, None, None, None, None)
    ]
    req_state.user_event_id = None

    chunks = []
    async for chunk in bot.run(
        messages=[{"role": "user", "content": "hello"}],
        session_id="session1",
        client_message_id="msg1",
        username="test"
    ):
        chunks.append(chunk)

    # runner.run_async should be called with iteration=1 and the internal revision instruction
    call_kwargs = bot._runtime._runner.run_async.call_args.kwargs
    assert "new_message" in call_kwargs
    assert call_kwargs["invocation_id"] == "msg1:main:1"
    
    msg_text = call_kwargs["new_message"].parts[0].text
    assert "[INTERNAL REVISION INSTRUCTION]" in msg_text
    assert "Old draft" in msg_text
    assert "Need more details" in msg_text


@pytest.mark.asyncio
@patch("beeportal.bee_ai_enterprises_adk.core.state_machine.run_reviewer")
async def test_ask_back_mismatch_invariant(mock_run_reviewer, mock_bot):
    """Kiểm tra ASK_BACK dedup raise exception nếu metadata không khớp."""
    bot, req_state = mock_bot
    mock_run_reviewer.return_value = MagicMock(status="ASK_BACK", ask_back_question="What exactly?")

    req_state.reviewer_verdict = "ASK_BACK"
    req_state.reviewer_feedback = "What exactly?"
    req_state.status = "processing"
    req_state.phase = "seed_working_session"

    mock_session = bot._runtime._canonical_session_service.get_session.return_value

    existing_ask_event = MagicMock()
    existing_ask_event.invocation_id = "req_mismatch:ask_back"
    existing_ask_event.author = "ENTERPRISES_MAIN_AGENT"
    existing_ask_event.custom_metadata.get.side_effect = lambda k: "req_mismatch" if k == "request_id" else True
    existing_ask_event.content.role = "model"
    # Content text is DIFFERENT
    existing_ask_event.content.parts = [MagicMock(text="Different question?")]
    import uuid
    EVENT_NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")
    identity_final = f"bee_ai_enterprises_adk:072fab09-7f7f-4682-9152-c142fa178444|072fab09-7f7f-4682-9152-c142fa178444|test|session1|req_mismatch|final"
    final_event_id = uuid.uuid5(EVENT_NAMESPACE, identity_final).hex

    existing_ask_event.id = "existing_evt_1"
    existing_ask_event.partial = False

    # Generate clone id to inject into working session
    identity_clone = f"bee_ai_enterprises_adk:072fab09-7f7f-4682-9152-c142fa178444|072fab09-7f7f-4682-9152-c142fa178444|test|session1|req_mismatch|clone|existing_evt_1"
    clone_id = uuid.uuid5(EVENT_NAMESPACE, identity_clone).hex

    clone_event = MagicMock()
    clone_event.id = clone_id
    clone_event.custom_metadata.get.side_effect = lambda k: "existing_evt_1" if k == "canonical_source_event_id" else None
    clone_event.author = "ENTERPRISES_MAIN_AGENT"
    clone_event.content.role = "model"
    clone_event.partial = False
    clone_event.content.parts = [MagicMock(text="Original question mismatch")]

    mock_session.events = [existing_ask_event]

    # Separate working session
    mock_working_session = MagicMock()
    mock_working_session.events = [clone_event]
    
    async def mock_get_session(app_name, user_id, session_id):
        if session_id == "session1":
            return mock_session
        return mock_working_session
        
    bot._runtime._canonical_session_service.get_session.side_effect = mock_get_session

    chunks = []
    async for chunk in bot.run(
        messages=[{"role": "user", "content": "hello"}],
        session_id="session1",
        client_message_id="req_mismatch",
        username="test"
    ):
        chunks.append(chunk)

    # Should raise Invariant violation, captured as error chunk
    full_response = "".join(
        c.choices[0].delta.content 
        for c in chunks 
        if getattr(c.choices[0].delta, "content", None)
    )
    assert "Xin l\u1ed7i, \u0111\xe3 x\u1ea3y ra l\u1ed7i" in full_response
