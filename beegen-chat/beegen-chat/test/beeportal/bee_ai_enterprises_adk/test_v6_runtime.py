import os
os.environ["ADK_WEB_ENABLE_PRODUCTION_RUNTIME"] = "true"
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from beeportal.bee_ai_enterprises_adk.core.runtime import (
    EnterpriseAgentRuntime,
    EnterpriseRequest,
    EnterpriseResult,
    IdempotencyConflictError,
    HeartbeatFailedError
)

@pytest.fixture
def base_request():
    return EnterpriseRequest(
        user_id="user1",
        conversation_id="conv1",
        request_id="req1",
        user_query="hello"
    )

@pytest.mark.asyncio
async def test_runtime_context_limit(base_request):
    runtime = EnterpriseAgentRuntime(bot_id="bot1")
    runtime._ensure_initialized = AsyncMock(); runtime._main_agent = MagicMock(); runtime._main_agent.name = "ENTERPRISES_MAIN_AGENT"
    runtime._check_context_guard = AsyncMock(return_value=False)
    
    result = await runtime.execute(base_request)
    assert result.status == "context_limit"
    assert result.request_id == "req1"

@pytest.mark.asyncio
async def test_runtime_idempotency_conflict(base_request):
    runtime = EnterpriseAgentRuntime(bot_id="bot1")
    runtime._ensure_initialized = AsyncMock(); runtime._main_agent = MagicMock(); runtime._main_agent.name = "ENTERPRISES_MAIN_AGENT"
    runtime._check_context_guard = AsyncMock(return_value=True)
    
    mock_lock_mgr = MagicMock()
    mock_lock_mgr.lock.side_effect = IdempotencyConflictError("conflict")
    runtime._lock_manager = mock_lock_mgr
    
    result = await runtime.execute(base_request)
    assert result.status == "conflict"
    assert result.request_id == "req1"

@pytest.mark.asyncio
async def test_runtime_heartbeat_failed(base_request):
    runtime = EnterpriseAgentRuntime(bot_id="bot1")
    runtime._ensure_initialized = AsyncMock(); runtime._main_agent = MagicMock(); runtime._main_agent.name = "ENTERPRISES_MAIN_AGENT"
    runtime._check_context_guard = AsyncMock(return_value=True)
    
    mock_lock_mgr = MagicMock()
    mock_lock_mgr.lock.side_effect = HeartbeatFailedError("heartbeat failed")
    runtime._lock_manager = mock_lock_mgr
    
    result = await runtime.execute(base_request)
    assert result.status == "retryable_error"
    assert result.request_id == "req1"

@pytest.mark.asyncio
async def test_runtime_cancelled_error(base_request):
    runtime = EnterpriseAgentRuntime(bot_id="bot1")
    runtime._ensure_initialized = AsyncMock(); runtime._main_agent = MagicMock(); runtime._main_agent.name = "ENTERPRISES_MAIN_AGENT"
    runtime._check_context_guard = AsyncMock(return_value=True)
    
    mock_lock_mgr = MagicMock()
    mock_lock_mgr.lock.side_effect = asyncio.CancelledError()
    runtime._lock_manager = mock_lock_mgr
    
    with pytest.raises(asyncio.CancelledError):
        await runtime.execute(base_request)

@pytest.mark.asyncio
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.run_state_machine")
async def test_runtime_success_pass(mock_run_state, base_request):
    runtime = EnterpriseAgentRuntime(bot_id="bot1")
    runtime._ensure_initialized = AsyncMock(); runtime._main_agent = MagicMock(); runtime._main_agent.name = "ENTERPRISES_MAIN_AGENT"
    runtime._check_context_guard = AsyncMock(return_value=True)
    
    mock_lock_mgr = MagicMock()
    lock_ctx = MagicMock()
    req_state = MagicMock(); req_state.response = "mock_resp"; req_state.error = "mock_err"; req_state.reviewer_feedback = "mock_fb"; req_state.reviewer_verdict = "mock_verdict"
    req_state.status = "processing"
    lock_ctx.__aenter__ = AsyncMock(return_value=req_state)
    lock_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_lock_mgr.lock.return_value = lock_ctx
    runtime._lock_manager = mock_lock_mgr
    
    mock_run_state.return_value = ("Success answer", False)
    
    result = await runtime.execute(base_request)
    assert result.status == "completed"
    assert result.answer == "Success answer"

@pytest.mark.asyncio
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.run_state_machine")
async def test_runtime_ask_back(mock_run_state, base_request):
    runtime = EnterpriseAgentRuntime(bot_id="bot1")
    runtime._ensure_initialized = AsyncMock(); runtime._main_agent = MagicMock(); runtime._main_agent.name = "ENTERPRISES_MAIN_AGENT"
    runtime._check_context_guard = AsyncMock(return_value=True)
    
    mock_lock_mgr = MagicMock()
    lock_ctx = MagicMock()
    req_state = MagicMock(); req_state.response = "mock_resp"; req_state.error = "mock_err"; req_state.reviewer_feedback = "mock_fb"; req_state.reviewer_verdict = "mock_verdict"
    req_state.status = "processing"
    lock_ctx.__aenter__ = AsyncMock(return_value=req_state)
    lock_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_lock_mgr.lock.return_value = lock_ctx
    runtime._lock_manager = mock_lock_mgr
    
    mock_run_state.return_value = ("Clarifying question?", True)
    
    result = await runtime.execute(base_request)
    assert result.status == "ask_back"
    assert result.answer == "Clarifying question?"

@pytest.mark.asyncio
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.run_state_machine")
async def test_runtime_review_exhausted(mock_run_state, base_request):
    runtime = EnterpriseAgentRuntime(bot_id="bot1")
    runtime._ensure_initialized = AsyncMock(); runtime._main_agent = MagicMock(); runtime._main_agent.name = "ENTERPRISES_MAIN_AGENT"
    runtime._check_context_guard = AsyncMock(return_value=True)
    
    mock_lock_mgr = MagicMock()
    lock_ctx = MagicMock()
    req_state = MagicMock(); req_state.response = "mock_resp"; req_state.error = "mock_err"; req_state.reviewer_feedback = "mock_fb"; req_state.reviewer_verdict = "mock_verdict"
    req_state.status = "terminal_failed"
    req_state.error = "max_iterations reached"
    lock_ctx.__aenter__ = AsyncMock(return_value=req_state)
    lock_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_lock_mgr.lock.return_value = lock_ctx
    runtime._lock_manager = mock_lock_mgr
    
    mock_run_state.return_value = ("Exhausted fallback answer", False)
    
    result = await runtime.execute(base_request)
    assert result.status == "review_exhausted"
    assert result.answer == "mock_resp"

@pytest.mark.asyncio
async def test_runtime_unexpected_error(base_request):
    runtime = EnterpriseAgentRuntime(bot_id="bot1")
    runtime._ensure_initialized = AsyncMock(); runtime._main_agent = MagicMock(); runtime._main_agent.name = "ENTERPRISES_MAIN_AGENT"
    runtime._check_context_guard = AsyncMock(return_value=True)
    
    mock_lock_mgr = MagicMock()
    mock_lock_mgr.lock.side_effect = Exception("Unexpected")
    runtime._lock_manager = mock_lock_mgr
    
    result = await runtime.execute(base_request)
    assert result.status == "terminal_error"

@pytest.mark.asyncio
async def test_concurrent_aclose_idempotent():
    runtime = EnterpriseAgentRuntime(bot_id="bot1")
    runtime._close_resources = AsyncMock()
    
    await asyncio.gather(runtime.aclose(), runtime.aclose())
    runtime._close_resources.assert_called_once()
    assert runtime._closed is True

@pytest.mark.asyncio
async def test_aclose_waits_for_drain():
    runtime = EnterpriseAgentRuntime(bot_id="bot1")
    runtime._close_resources = AsyncMock()
    
    # Simulate active execution
    runtime._active_executions = 1
    runtime._drained_event.clear()
    
    # Run aclose in background
    close_task = asyncio.create_task(runtime.aclose())
    
    # Ensure it blocks
    await asyncio.sleep(0.1)
    assert not close_task.done()
    assert runtime._close_resources.call_count == 0
    
    # Drain
    runtime._active_executions = 0
    runtime._drained_event.set()
    
    await close_task
    runtime._close_resources.assert_called_once()

@pytest.mark.asyncio
async def test_execute_while_closing_returns_retryable(base_request):
    runtime = EnterpriseAgentRuntime(bot_id="bot1")
    runtime._closing = True
    
    result = await runtime.execute(base_request)
    assert result.status == "retryable_error"

@pytest.mark.asyncio
async def test_aclose_best_effort_timeout():
    runtime = EnterpriseAgentRuntime(bot_id="bot1")
    runtime._close_resources = AsyncMock()
    
    # Simulate active execution
    runtime._active_executions = 1
    runtime._drained_event.clear()
    
    await runtime.aclose_best_effort(timeout=0.01)
    # Should not have called _close_resources because execution was active
    assert runtime._close_resources.call_count == 0
    assert runtime._closed is False
    assert runtime._closing is True
