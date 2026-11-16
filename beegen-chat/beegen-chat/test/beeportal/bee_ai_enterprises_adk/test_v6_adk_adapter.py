import pytest
import os
os.environ["ADK_WEB_ENABLE_PRODUCTION_RUNTIME"] = "true"
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from beeportal.bee_ai_enterprises_adk.agent import ProductionWorkflowAgent
from beeportal.bee_ai_enterprises_adk.core.runtime import EnterpriseResult

from google.adk.agents import InvocationContext
from google.adk.sessions import Session, InMemorySessionService
from google.genai import types

@pytest.fixture
def base_ctx():
    session = Session(id="sess1", user_id="user1", app_name="test")
    return InvocationContext(
        session_service=InMemorySessionService(),
        session=session,
        invocation_id="invoc1",
        user_content=types.Content(
            role="user",
            parts=[types.Part.from_text(text="hello ADK")]
        )
    )

@pytest.fixture
def mock_agent():
    agent = ProductionWorkflowAgent(name="BEE_AI_ENTERPRISES_PRODUCTION", bot_id="bot1")
    agent._runtime = MagicMock()
    agent._runtime.execute = AsyncMock()
    agent._runtime.aclose_best_effort = AsyncMock()
    return agent

@pytest.mark.asyncio
async def test_adk_adapter_identity_mapping(mock_agent, base_ctx):
    mock_agent._runtime.execute.return_value = EnterpriseResult(
        status="completed",
        answer="Hello ADK",
        request_id="invoc1"
    )
    
    events = []
    async for event in mock_agent._run_async_impl(base_ctx):
        events.append(event)
        
    assert len(events) == 1
    assert events[0].content.parts[0].text == "Hello ADK"
    
    req = mock_agent._runtime.execute.call_args[0][0]
    assert req.user_id == "user1"
    assert req.conversation_id == "sess1"
    assert req.request_id == "invoc1"
    assert req.user_query == "hello ADK"

@pytest.mark.asyncio
async def test_adk_adapter_multipart_content(mock_agent, base_ctx):
    base_ctx.user_content.parts = [
        types.Part.from_text(text="part 1 "),
        types.Part.from_text(text=" part 2")
    ]
    mock_agent._runtime.execute.return_value = EnterpriseResult(
        status="completed", answer="ok", request_id="invoc1"
    )
    
    async for _ in mock_agent._run_async_impl(base_ctx):
        pass
        
    req = mock_agent._runtime.execute.call_args[0][0]
    assert req.user_query == "part 1  part 2"

@pytest.mark.asyncio
async def test_adk_adapter_empty_query(mock_agent, base_ctx):
    base_ctx.user_content.parts = [types.Part.from_text(text="   ")]
    
    events = []
    async for event in mock_agent._run_async_impl(base_ctx):
        events.append(event)
        
    assert mock_agent._runtime.execute.call_count == 0
    assert "Vui lòng nhập câu hỏi." in events[0].content.parts[0].text

@pytest.mark.asyncio
async def test_adk_adapter_missing_web_env(base_ctx):
    # No bot_id and no env var
    agent = ProductionWorkflowAgent(name="TEST")
    
    with patch.dict(os.environ, clear=True):
        events = []
        async for event in agent._run_async_impl(base_ctx):
            events.append(event)
            
        assert "lỗi cấu hình" in events[0].content.parts[0].text.lower()

@pytest.mark.asyncio
async def test_adk_adapter_missing_enable_flag(base_ctx):
    agent = ProductionWorkflowAgent(name="TEST", bot_id="bot1")
    
    with patch.dict(os.environ, {"ADK_WEB_ENABLE_PRODUCTION_RUNTIME": "false"}):
        events = []
        async for event in agent._run_async_impl(base_ctx):
            events.append(event)
            
        assert "lỗi cấu hình" in events[0].content.parts[0].text.lower()

@pytest.mark.asyncio
async def test_adk_adapter_review_exhausted(mock_agent, base_ctx):
    mock_agent._runtime.execute.return_value = EnterpriseResult(
        status="review_exhausted", answer="Exhausted adk", request_id="invoc1"
    )
    
    events = []
    async for event in mock_agent._run_async_impl(base_ctx):
        events.append(event)
        
    assert events[0].content.parts[0].text == "Exhausted adk"

@pytest.mark.asyncio
async def test_adk_adapter_concurrent_ensure_runtime():
    agent = ProductionWorkflowAgent(name="TEST", bot_id="bot1")
    
    with patch.dict(os.environ, {"ADK_WEB_ENABLE_PRODUCTION_RUNTIME": "true"}):
        with patch("beeportal.bee_ai_enterprises_adk.agent.EnterpriseAgentRuntime") as mock_runtime_cls:
            mock_runtime_cls.return_value = MagicMock()
            
            # Call _ensure_runtime concurrently
            results = await asyncio.gather(
                agent._ensure_runtime(),
                agent._ensure_runtime(),
                agent._ensure_runtime()
            )
            
            # Should only instantiate once
            mock_runtime_cls.assert_called_once_with(bot_id="bot1")
            assert results[0] is results[1] is results[2]

@pytest.mark.asyncio
async def test_adk_adapter_aclose(mock_agent):
    await mock_agent.aclose()
    mock_agent._runtime.aclose_best_effort.assert_called_once_with(timeout=5.0)
