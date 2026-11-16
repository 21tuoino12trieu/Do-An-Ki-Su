import os
os.environ["ADK_WEB_ENABLE_PRODUCTION_RUNTIME"] = "true"
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from beeportal.bee_ai_enterprises_adk.agent import BeeAiEnterprisesADK
from beeportal.bee_ai_enterprises_adk.core.runtime import EnterpriseResult

@pytest.fixture
def mock_bot():
    bot = BeeAiEnterprisesADK(bot_id="bot1")
    bot._runtime = MagicMock()
    bot._runtime.execute = AsyncMock()
    bot._runtime.aclose = AsyncMock()
    bot._runtime.aclose_best_effort = AsyncMock()
    return bot

@pytest.mark.asyncio
async def test_api_adapter_completed(mock_bot):
    mock_bot._runtime.execute.return_value = EnterpriseResult(
        status="completed",
        answer="Hello API",
        request_id="req1"
    )
    
    chunks = []
    async for chunk in mock_bot.run(
        messages=[{"role": "user", "content": "hi"}],
        session_id="sess1",
        client_message_id="msg1",
        username="user1"
    ):
        chunks.append(chunk)
        
    assert len(chunks) == 2 # 1 text chunk + 1 end chunk
    assert chunks[0].choices[0].delta.content == "Hello API"
    assert chunks[1].choices[0].delta.content == ""
    assert chunks[1].choices[0].finish_reason == "stop"

@pytest.mark.asyncio
async def test_api_adapter_review_exhausted(mock_bot):
    mock_bot._runtime.execute.return_value = EnterpriseResult(
        status="review_exhausted",
        answer="Exhausted answer",
        request_id="req1"
    )
    
    chunks = []
    async for chunk in mock_bot.run(
        messages=[{"role": "user", "content": "hi"}],
        session_id="sess1",
        client_message_id="msg1",
        username="user1"
    ):
        chunks.append(chunk)
        
    text = "".join(chunk.choices[0].delta.content for chunk in chunks if chunk.choices[0].delta.content)
    assert text == "Exhausted answer"

@pytest.mark.asyncio
async def test_api_adapter_terminal_error_no_answer(mock_bot):
    mock_bot._runtime.execute.return_value = EnterpriseResult(
        status="terminal_error",
        answer="",
        request_id="req1"
    )
    
    chunks = []
    async for chunk in mock_bot.run(
        messages=[{"role": "user", "content": "hi"}],
        session_id="sess1",
        client_message_id="msg1",
        username="user1"
    ):
        chunks.append(chunk)
        
    assert "lỗi" in chunks[0].choices[0].delta.content.lower()

@pytest.mark.asyncio
async def test_api_adapter_empty_query(mock_bot):
    chunks = []
    async for chunk in mock_bot.run(
        messages=[{"role": "user", "content": "   "}],
        session_id="sess1",
        client_message_id="msg1",
        username="user1"
    ):
        chunks.append(chunk)
        
    assert mock_bot._runtime.execute.call_count == 0
    assert chunks[0].choices[0].delta.content == "Vui lòng nhập câu hỏi."

@pytest.mark.asyncio
async def test_api_adapter_invalid_identity(mock_bot):
    chunks = []
    async for chunk in mock_bot.run(
        messages=[{"role": "user", "content": "hi"}],
        session_id="  ",  # invalid session
        client_message_id="msg1",
        username="user1"
    ):
        chunks.append(chunk)
        
    assert mock_bot._runtime.execute.call_count == 0
    assert "không hợp lệ" in chunks[0].choices[0].delta.content.lower()

@pytest.mark.asyncio
async def test_api_adapter_delegates_close(mock_bot):
    await mock_bot.aclose()
    mock_bot._runtime.aclose.assert_called_once()
    
    await mock_bot.aclose_best_effort(timeout=3.0)
    mock_bot._runtime.aclose_best_effort.assert_called_once_with(timeout=3.0)
