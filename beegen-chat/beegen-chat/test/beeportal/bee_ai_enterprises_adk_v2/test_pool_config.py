"""Tests for EnterpriseAgentRuntime pool configuration in bee_ai_enterprises_adk_v2."""

import os
os.environ["POSTGRES_URL"] = "postgresql://user:LOCAL_PASSWORD@localhost:5432/test_db"
os.environ.setdefault("BEE_AI_ENTERPRISES_SYSTEM_PROMPT", "test")

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Import the module early so it doesn't fail due to conftest mocking pydantic.root_model
from beeportal.bee_ai_enterprises_adk_v2.core.runtime import EnterpriseAgentRuntime

MODULE = "beeportal.bee_ai_enterprises_adk_v2.core.runtime"


def _make_engine_mock():
    mock_engine = MagicMock()
    mock_conn = AsyncMock()
    mock_engine.begin.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_engine


def _make_langfuse_mock():
    mock_lf_client = MagicMock()
    mock_prompt = MagicMock()
    mock_prompt.compile.return_value = "test prompt"
    mock_lf_client.get_prompt.return_value = mock_prompt
    return mock_lf_client


@pytest.mark.asyncio
@patch(f"{MODULE}.Runner")
@patch(f"{MODULE}.App")
@patch(f"{MODULE}.EventsCompactionConfig")
@patch(f"{MODULE}.ContextCacheConfig")
@patch(f"{MODULE}.LlmEventSummarizer")
@patch(f"{MODULE}.build_small_model")
@patch(f"{MODULE}.get_langfuse_client")
@patch(f"{MODULE}.DatabaseSessionService")
@patch(f"{MODULE}.create_async_engine")
@patch(f"{MODULE}.build_root_workflow")
@patch(f"{MODULE}.initialize_retrieval_nodes_sync")
@patch(f"{MODULE}.setup_langfuse_tracing")
async def test_pool_recycle_300_on_main_engine(
    mock_setup_lf, mock_init_retrieval, mock_build_root, mock_create_engine,
    mock_db_session_svc, mock_get_lf, mock_build_small, mock_summarizer,
    mock_ctx_cache, mock_compaction, mock_app, mock_runner
):
    """Verify create_async_engine is called with pool_recycle=300."""
    mock_create_engine.return_value = _make_engine_mock()
    mock_get_lf.return_value = _make_langfuse_mock()

    runtime = EnterpriseAgentRuntime(bot_id="test_bot")
    await runtime._ensure_initialized()

    mock_create_engine.assert_called_once()
    _, kwargs = mock_create_engine.call_args
    assert kwargs.get("pool_recycle") == 300, (
        f"Expected pool_recycle=300 on main engine, got {kwargs.get('pool_recycle')}"
    )
    assert kwargs.get("pool_pre_ping") is True, (
        f"Expected pool_pre_ping=True on main engine, got {kwargs.get('pool_pre_ping')}"
    )


@pytest.mark.asyncio
@patch(f"{MODULE}.Runner")
@patch(f"{MODULE}.App")
@patch(f"{MODULE}.EventsCompactionConfig")
@patch(f"{MODULE}.ContextCacheConfig")
@patch(f"{MODULE}.LlmEventSummarizer")
@patch(f"{MODULE}.build_small_model")
@patch(f"{MODULE}.get_langfuse_client")
@patch(f"{MODULE}.DatabaseSessionService")
@patch(f"{MODULE}.create_async_engine")
@patch(f"{MODULE}.build_root_workflow")
@patch(f"{MODULE}.initialize_retrieval_nodes_sync")
@patch(f"{MODULE}.setup_langfuse_tracing")
async def test_pool_recycle_300_on_session_service(
    mock_setup_lf, mock_init_retrieval, mock_build_root, mock_create_engine,
    mock_db_session_svc, mock_get_lf, mock_build_small, mock_summarizer,
    mock_ctx_cache, mock_compaction, mock_app, mock_runner
):
    """Verify DatabaseSessionService is called with pool_recycle=300."""
    mock_create_engine.return_value = _make_engine_mock()
    mock_get_lf.return_value = _make_langfuse_mock()

    runtime = EnterpriseAgentRuntime(bot_id="test_bot")
    await runtime._ensure_initialized()

    mock_db_session_svc.assert_called_once()
    _, kwargs = mock_db_session_svc.call_args
    assert kwargs.get("pool_recycle") == 300, (
        f"Expected pool_recycle=300 on DatabaseSessionService, got {kwargs.get('pool_recycle')}"
    )
