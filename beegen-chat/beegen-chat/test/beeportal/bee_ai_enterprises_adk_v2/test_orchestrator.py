import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from google.adk import Context, Event
from google.genai import types

from ..core.schemas import ReviewVerdict
from ..core.orchestrator import (
    ActorCriticOrchestrator,
    InputGuardrailNode,
    _extract_query,
    _get_or_create_sync,
    _cleanup_sync,
    _SYNC_REGISTRY,
)


@pytest.fixture(autouse=True)
def _clean_sync_registry():
    """Ensure the global registry is clean before and after each test."""
    _SYNC_REGISTRY.clear()
    yield
    _SYNC_REGISTRY.clear()


@pytest.fixture
def mock_ctx():
    ctx = MagicMock(spec=Context)
    ctx.invocation_id = "test-invocation"
    ctx.session = MagicMock()
    ctx.session.events = []

    # Mock run_node
    async def mock_run_node(agent, input_data, run_id, use_as_output):
        if "reviewer" in agent.name.lower():
            # Mặc định trả về PASS
            return ReviewVerdict(status="PASS", recommendations="")
        return "Draft answer"

    ctx.run_node = AsyncMock(side_effect=mock_run_node)
    return ctx


def _pre_pass_guardrail(invocation_id: str) -> None:
    """Pre-signal guardrail as passed so ActorCritic doesn't wait forever."""
    sync = _get_or_create_sync(invocation_id)
    sync.guardrail_done.set()


def _pre_fail_guardrail(invocation_id: str, message: str = "Blocked.") -> None:
    """Pre-signal guardrail as failed."""
    sync = _get_or_create_sync(invocation_id)
    sync.refusal_message = message
    sync.guardrail_failed.set()
    sync.guardrail_done.set()


@pytest.fixture
def orchestrator():
    main_agent = MagicMock()
    main_agent.name = "mock_main_agent"
    reviewer_agent = MagicMock()
    reviewer_agent.name = "mock_reviewer_agent"

    # Use model_construct to bypass Pydantic validation for mock agents
    return ActorCriticOrchestrator.model_construct(
        name="test_orchestrator",
        main_agent=main_agent,
        reviewer_agent=reviewer_agent,
        max_revisions=2,
        max_reviewer_retries=2,
        max_evidence_size=200000,
        rerun_on_resume=True,
        definition="",
    )


# ---------------------------------------------------------------------------
# Existing tests (updated to pre-set guardrail signal)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_query():
    text_input = "Hello world"
    assert _extract_query(text_input) == "Hello world"

    content_input = types.Content(
        role="user", parts=[types.Part.from_text(text="Hello content")]
    )
    assert _extract_query(content_input) == "Hello content"


@pytest.mark.asyncio
async def test_orchestrator_pass(orchestrator, mock_ctx):
    _pre_pass_guardrail(mock_ctx.invocation_id)

    # Setup reviewer to return PASS
    async def mock_run_node(agent, input_data, run_id, use_as_output):
        if "reviewer" in agent.name.lower():
            return {"status": "PASS"}  # ADK 2.3.0 dict output
        return "Draft answer"

    mock_ctx.run_node.side_effect = mock_run_node

    events = []
    async for event in orchestrator._run_impl(ctx=mock_ctx, node_input="Test query"):
        events.append(event)

    # Lọc ra state_delta events
    states = [
        e.actions.state_delta.get("phase")
        for e in events
        if getattr(e, "actions", None) and e.actions.state_delta
    ]

    assert "main_running" in states
    assert "reviewing" in states
    assert "completed" in states

    # Final event
    final_event = events[-1]
    assert final_event.custom_metadata.get("visibility") == "final"

    # Registry must be cleaned up
    assert mock_ctx.invocation_id not in _SYNC_REGISTRY


@pytest.mark.asyncio
async def test_orchestrator_revise_then_pass(orchestrator, mock_ctx):
    _pre_pass_guardrail(mock_ctx.invocation_id)

    iteration_call = 0

    async def mock_run_node(agent, input_data, run_id, use_as_output):
        nonlocal iteration_call
        if "reviewer" in agent.name.lower():
            if iteration_call == 0:
                iteration_call += 1
                return {"status": "REVISE", "recommendations": "Fix this"}
            return {"status": "PASS"}
        return f"Draft answer {iteration_call}"

    mock_ctx.run_node.side_effect = mock_run_node

    events = []
    async for event in orchestrator._run_impl(ctx=mock_ctx, node_input="Test query"):
        events.append(event)

    states = [
        e.actions.state_delta.get("phase")
        for e in events
        if getattr(e, "actions", None) and e.actions.state_delta
    ]
    assert states.count("main_running") == 2
    assert states.count("reviewing") == 2
    assert states[-1] == "completed"


@pytest.mark.asyncio
async def test_orchestrator_review_exhausted(orchestrator, mock_ctx):
    _pre_pass_guardrail(mock_ctx.invocation_id)

    async def mock_run_node(agent, input_data, run_id, use_as_output):
        if "reviewer" in agent.name.lower():
            return {"status": "REVISE", "recommendations": "Still wrong"}
        return "Draft answer"

    mock_ctx.run_node.side_effect = mock_run_node

    events = []
    async for event in orchestrator._run_impl(ctx=mock_ctx, node_input="Test query"):
        events.append(event)

    states = [
        e.actions.state_delta.get("phase")
        for e in events
        if getattr(e, "actions", None) and e.actions.state_delta
    ]
    assert states.count("main_running") == 3  # iteration 0, 1, 2
    assert states[-1] == "review_exhausted"


# ---------------------------------------------------------------------------
# NEW: Concurrent guardrail tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_guardrail_blocked_returns_refusal(orchestrator, mock_ctx):
    """When guardrail signals FAIL before checkpoint, ActorCritic yields refusal."""
    _pre_fail_guardrail(mock_ctx.invocation_id, message="Nội dung vi phạm.")

    async def mock_run_node(agent, input_data, run_id, use_as_output):
        return "Draft that should be discarded"

    mock_ctx.run_node.side_effect = mock_run_node

    events = []
    async for event in orchestrator._run_impl(ctx=mock_ctx, node_input="Bad query"):
        events.append(event)

    # Should have final refusal event
    final_events = [
        e
        for e in events
        if getattr(e, "custom_metadata", None)
        and e.custom_metadata.get("visibility") == "final"
    ]
    assert len(final_events) == 1

    refusal_event = final_events[0]
    assert refusal_event.content.parts[0].text == "Nội dung vi phạm."
    assert refusal_event.actions.state_delta.get("guardrail_blocked") is True

    # Registry cleaned up
    assert mock_ctx.invocation_id not in _SYNC_REGISTRY


@pytest.mark.asyncio
async def test_guardrail_delayed_pass(orchestrator, mock_ctx):
    """Main agent finishes first, waits for guardrail, guardrail passes."""

    async def mock_run_node(agent, input_data, run_id, use_as_output):
        if "reviewer" in agent.name.lower():
            return {"status": "PASS"}
        return "Draft answer"

    mock_ctx.run_node.side_effect = mock_run_node

    # Simulate delayed guardrail pass - set it after a short delay
    async def delayed_guardrail_pass():
        await asyncio.sleep(0.05)
        sync = _get_or_create_sync(mock_ctx.invocation_id)
        sync.guardrail_done.set()

    task = asyncio.create_task(delayed_guardrail_pass())

    events = []
    async for event in orchestrator._run_impl(ctx=mock_ctx, node_input="Test query"):
        events.append(event)

    await task  # Ensure the background task finishes

    states = [
        e.actions.state_delta.get("phase")
        for e in events
        if getattr(e, "actions", None) and e.actions.state_delta
    ]
    assert "completed" in states


@pytest.mark.asyncio
async def test_guardrail_delayed_fail(orchestrator, mock_ctx):
    """Main agent finishes first, waits for guardrail, guardrail FAILS."""

    async def mock_run_node(agent, input_data, run_id, use_as_output):
        return "Draft that should be discarded"

    mock_ctx.run_node.side_effect = mock_run_node

    # Simulate delayed guardrail fail
    async def delayed_guardrail_fail():
        await asyncio.sleep(0.05)
        sync = _get_or_create_sync(mock_ctx.invocation_id)
        sync.refusal_message = "Delayed block."
        sync.guardrail_failed.set()
        sync.guardrail_done.set()

    task = asyncio.create_task(delayed_guardrail_fail())

    events = []
    async for event in orchestrator._run_impl(ctx=mock_ctx, node_input="Test query"):
        events.append(event)

    await task

    final_events = [
        e
        for e in events
        if getattr(e, "custom_metadata", None)
        and e.custom_metadata.get("visibility") == "final"
    ]
    assert len(final_events) == 1
    assert final_events[0].content.parts[0].text == "Delayed block."
    assert final_events[0].actions.state_delta.get("guardrail_blocked") is True


@pytest.mark.asyncio
async def test_input_guardrail_node_pass():
    """InputGuardrailNode signals pass and yields no output."""
    ctx = MagicMock(spec=Context)
    ctx.invocation_id = "guardrail-pass-test"
    ctx.session = MagicMock()
    ctx.session.events = []

    node = InputGuardrailNode(name="test_guardrail")

    with patch(
        "beeportal.bee_ai_enterprises_adk_v2.core.orchestrator.input_content_filter_guardrail",
        new_callable=AsyncMock,
        return_value={"guardrail_trigger_route": "none", "message": "OK"},
    ):
        events = []
        async for event in node._run_impl(ctx=ctx, node_input="Safe question"):
            events.append(event)

    sync = _get_or_create_sync(ctx.invocation_id)
    assert sync.guardrail_done.is_set()
    assert not sync.guardrail_failed.is_set()
    # Should only yield Events without content/output
    assert all(
        isinstance(e, Event)
        and not getattr(e, "content", None)
        and not getattr(e, "output", None)
        for e in events
    )


@pytest.mark.asyncio
async def test_input_guardrail_node_block():
    """InputGuardrailNode signals block and yields no output."""
    ctx = MagicMock(spec=Context)
    ctx.invocation_id = "guardrail-block-test"
    ctx.session = MagicMock()
    ctx.session.events = []

    node = InputGuardrailNode(name="test_guardrail")

    with patch(
        "beeportal.bee_ai_enterprises_adk_v2.core.orchestrator.input_content_filter_guardrail",
        new_callable=AsyncMock,
        return_value={
            "guardrail_trigger_route": "1",
            "message": "Bạo lực bị cấm.",
        },
    ):
        events = []
        async for event in node._run_impl(ctx=ctx, node_input="Violent content"):
            events.append(event)

    sync = _get_or_create_sync(ctx.invocation_id)
    assert sync.guardrail_done.is_set()
    assert sync.guardrail_failed.is_set()
    assert sync.refusal_message == "Bạo lực bị cấm."
    # No output events - signal only
    assert all(
        isinstance(e, Event)
        and not getattr(e, "content", None)
        and not getattr(e, "output", None)
        for e in events
    )


@pytest.mark.asyncio
async def test_input_guardrail_node_error_failopen():
    """InputGuardrailNode fails open on exception - passes, no block."""
    ctx = MagicMock(spec=Context)
    ctx.invocation_id = "guardrail-error-test"
    ctx.session = MagicMock()
    ctx.session.events = []

    node = InputGuardrailNode(name="test_guardrail")

    with patch(
        "beeportal.bee_ai_enterprises_adk_v2.core.orchestrator.input_content_filter_guardrail",
        new_callable=AsyncMock,
        side_effect=RuntimeError("LLM timeout"),
    ):
        events = []
        async for event in node._run_impl(ctx=ctx, node_input="Some question"):
            events.append(event)

    sync = _get_or_create_sync(ctx.invocation_id)
    assert sync.guardrail_done.is_set()
    assert not sync.guardrail_failed.is_set()  # fail-open


@pytest.mark.asyncio
async def test_sync_registry_cleanup(orchestrator, mock_ctx):
    """_SYNC_REGISTRY entry is cleaned up even if _run_impl_inner raises."""
    _pre_pass_guardrail(mock_ctx.invocation_id)

    async def exploding_run_node(agent, input_data, run_id, use_as_output):
        raise RuntimeError("kaboom")

    mock_ctx.run_node.side_effect = exploding_run_node

    with pytest.raises(RuntimeError, match="kaboom"):
        async for _ in orchestrator._run_impl(
            ctx=mock_ctx, node_input="Test query"
        ):
            pass

    # Registry must still be cleaned
    assert mock_ctx.invocation_id not in _SYNC_REGISTRY
