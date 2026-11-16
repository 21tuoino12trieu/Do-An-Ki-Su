import pytest
import os
os.environ["ADK_WEB_ENABLE_PRODUCTION_RUNTIME"] = "true"
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from beeportal.bee_ai_enterprises_adk.agent import BeeAiEnterprisesADK, ProductionWorkflowAgent
from beeportal.bee_ai_enterprises_adk.core.runtime import EnterpriseResult, EnterpriseRequest

from google.adk.agents import InvocationContext
from google.adk.sessions import Session, InMemorySessionService
from google.genai import types

@pytest.fixture
def api_bot():
    bot = BeeAiEnterprisesADK(bot_id="bot1")
    bot._runtime = MagicMock()
    bot._runtime.execute = AsyncMock()
    bot._runtime.aclose_best_effort = AsyncMock()
    return bot

@pytest.fixture
def adk_bot():
    agent = ProductionWorkflowAgent(name="BEE_AI_ENTERPRISES_PRODUCTION", bot_id="bot1")
    agent._runtime = MagicMock()
    agent._runtime.execute = AsyncMock()
    agent._runtime.aclose_best_effort = AsyncMock()
    return agent

@pytest.mark.asyncio
async def test_parity_request_mapping(api_bot, adk_bot):
    # Setup expected result
    result = EnterpriseResult(status="completed", answer="Test parity", request_id="req1")
    api_bot._runtime.execute.return_value = result
    adk_bot._runtime.execute.return_value = result
    
    # 1. API Call
    api_events = []
    async for chunk in api_bot.run(
        messages=[{"role": "user", "content": "same query"}],
        session_id="session_id",
        client_message_id="req1",
        username="user1"
    ):
        api_events.append(chunk)
    
    # 2. ADK Call
    session = Session(id="session_id", user_id="user1", app_name="test")
    ctx = InvocationContext(
        session_service=InMemorySessionService(),
        session=session,
        invocation_id="req1",
        user_content=types.Content(
            role="user",
            parts=[types.Part.from_text(text="same query")]
        )
    )
    
    adk_events = []
    async for event in adk_bot._run_async_impl(ctx):
        adk_events.append(event)
        
    # Verify both adapters sent exactly the same request to Runtime
    api_req = api_bot._runtime.execute.call_args[0][0]
    adk_req = adk_bot._runtime.execute.call_args[0][0]
    
    assert isinstance(api_req, EnterpriseRequest)
    assert isinstance(adk_req, EnterpriseRequest)
    
    assert api_req.user_id == adk_req.user_id == "user1"
    assert api_req.conversation_id == adk_req.conversation_id == "session_id"
    assert api_req.request_id == adk_req.request_id == "req1"
    assert api_req.user_query == adk_req.user_query == "same query"
    
    # Verify that the output strings are semantically identical
    api_text = "".join(chunk.choices[0].delta.content for chunk in api_events if chunk.choices[0].delta.content)
    adk_text = "".join(part.text for part in adk_events[0].content.parts if part.text)
    
    assert api_text == adk_text == "Test parity"

@pytest.mark.asyncio
async def test_parity_fallback_messages(api_bot, adk_bot):
    result = EnterpriseResult(status="context_limit", answer="", request_id="req1")
    api_bot._runtime.execute.return_value = result
    adk_bot._runtime.execute.return_value = result
    
    # API Call
    api_events = []
    async for chunk in api_bot.run(
        messages=[{"role": "user", "content": "same query"}],
        session_id="session_id",
        client_message_id="req1",
        username="user1"
    ):
        api_events.append(chunk)
        
    # ADK Call
    session = Session(id="session_id", user_id="user1", app_name="test")
    ctx = InvocationContext(
        session_service=InMemorySessionService(),
        session=session,
        invocation_id="req1",
        user_content=types.Content(
            role="user",
            parts=[types.Part.from_text(text="same query")]
        )
    )
    
    adk_events = []
    async for event in adk_bot._run_async_impl(ctx):
        adk_events.append(event)
        
    api_text = "".join(chunk.choices[0].delta.content for chunk in api_events if chunk.choices[0].delta.content)
    adk_text = "".join(part.text for part in adk_events[0].content.parts if part.text)
    
    assert api_text == adk_text
    assert "quá dài" in api_text.lower()
