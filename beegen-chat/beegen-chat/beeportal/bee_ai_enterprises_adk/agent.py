# -*- coding: utf-8 -*-
"""Composition root and adapters for Bee AI Enterprises ADK."""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import AsyncGenerator

from pydantic import PrivateAttr, ValidationError

from google.adk.agents import BaseAgent, InvocationContext
from google.genai import types
from google.adk.events import Event

from .core.runtime import EnterpriseAgentRuntime, EnterpriseRequest, result_to_user_message
from .tools import initialize_retrieval_nodes_sync
from beegenerate.llms.llm_response import fake_chunk_from

initialize_retrieval_nodes_sync()

logger = logging.getLogger(__name__)


class BeeAiEnterprisesADK:
    """OpenAI API streaming adapter."""

    def __init__(self, bot_id: str) -> None:
        self.bot_id = bot_id
        self._runtime = EnterpriseAgentRuntime(bot_id=bot_id)

    async def run(
        self,
        messages: list[dict],
        session_id: str,
        client_message_id: str,
        username: str,
        **kwargs
    ) -> AsyncGenerator:
        user_query = (messages[-1].get("content", "") if messages else "").strip()
        model_name = kwargs.get("model", "gemini-2.5-flash")
        req_id = client_message_id or uuid.uuid4().hex

        if not user_query:
            answer = "Vui lòng nhập câu hỏi."
            yield fake_chunk_from(content=answer, last=False, chat_id=req_id, model=model_name)
            yield fake_chunk_from(content="", last=True, chat_id=req_id, model=model_name)
            return

        try:
            request = EnterpriseRequest(
                user_id=username,
                conversation_id=session_id,
                request_id=req_id,
                user_query=user_query,
                model=kwargs.get("model"),
            )
        except ValidationError:
            logger.warning("[BeeAiEnterprisesADK] Invalid request identity: user=%s session=%s", username, session_id)
            answer = "Xin lỗi, yêu cầu không hợp lệ. Vui lòng thử lại."
            yield fake_chunk_from(content=answer, last=False, chat_id=req_id, model=model_name)
            yield fake_chunk_from(content="", last=True, chat_id=req_id, model=model_name)
            return

        result = await self._runtime.execute(request)
        answer = result_to_user_message(result)

        chunk_size = 15
        for i in range(0, len(answer), chunk_size):
            yield fake_chunk_from(
                content=answer[i:i+chunk_size],
                last=False,
                chat_id=req_id,
                model=model_name
            )
            await asyncio.sleep(0.01)

        yield fake_chunk_from(
            content="",
            last=True,
            chat_id=req_id,
            model=model_name
        )

    async def aclose(self) -> None:
        """Wait for execution drain and close resources."""
        await self._runtime.aclose()

    async def aclose_best_effort(self, timeout: float = 5.0) -> None:
        """Bounded alternative for process shutdown."""
        await self._runtime.aclose_best_effort(timeout=timeout)


class ProductionWorkflowAgent(BaseAgent):
    """ADK Web BaseAgent adapter."""

    bot_id: str = ""

    _runtime: EnterpriseAgentRuntime | None = PrivateAttr(default=None)
    _runtime_lock: asyncio.Lock = PrivateAttr(default_factory=asyncio.Lock)

    async def _ensure_runtime(self) -> EnterpriseAgentRuntime:
        if self._runtime is not None:
            return self._runtime

        async with self._runtime_lock:
            if self._runtime is not None:
                return self._runtime

            bot_id = self.bot_id or os.environ.get("BEE_AI_ENTERPRISES_ADK_WEB_BOT_ID", "072fab09-7f7f-4682-9152-c142fa178444").strip()
            if not bot_id:
                raise RuntimeError("BEE_AI_ENTERPRISES_ADK_WEB_BOT_ID must be set.")

            enable_flag = os.environ.get("ADK_WEB_ENABLE_PRODUCTION_RUNTIME", "true").strip().lower()
            if enable_flag != "true":
                raise RuntimeError(
                    "ADK_WEB_ENABLE_PRODUCTION_RUNTIME=true is required. "
                    "ADK Web will write to the production PostgreSQL database."
                )

            self._runtime = EnterpriseAgentRuntime(bot_id=bot_id)
        return self._runtime

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        user_query = "".join(
            p.text or "" for p in (ctx.user_content.parts or []) if p.text
        ).strip() if ctx.user_content else ""

        if not user_query:
            yield Event(author=self.name, content=types.Content(
                role="model", parts=[types.Part.from_text(text="Vui lòng nhập câu hỏi.")]
            ))
            return

        try:
            request = EnterpriseRequest(
                user_id=ctx.user_id,
                conversation_id=ctx.session.id,
                request_id=ctx.invocation_id,
                user_query=user_query,
            )
        except ValidationError:
            logger.warning(
                "[ProductionWorkflowAgent] Invalid identity: user=%s session=%s invocation=%s",
                ctx.user_id, getattr(ctx.session, 'id', None), ctx.invocation_id
            )
            yield Event(author=self.name, content=types.Content(
                role="model",
                parts=[types.Part.from_text(text="Xin lỗi, yêu cầu không hợp lệ.")]
            ))
            return

        try:
            initialize_retrieval_nodes_sync()
            runtime = await self._ensure_runtime()
        except RuntimeError as e:
            logger.error("[ProductionWorkflowAgent] Runtime init failed: %s", e)
            yield Event(author=self.name, content=types.Content(
                role="model",
                parts=[types.Part.from_text(text="Xin lỗi, hệ thống gặp lỗi cấu hình. Vui lòng liên hệ quản trị viên.")]
            ))
            return

        async for item in runtime.execute_stream(request):
            if isinstance(item, Event):
                item.invocation_id = ctx.invocation_id
                if ctx.node_path:
                    inner_path = item.node_info.path or item.author
                    if inner_path:
                        item.node_info.path = f"{ctx.node_path}/{inner_path}"
                    else:
                        item.node_info.path = ctx.node_path
                yield item
            elif hasattr(item, "status") and hasattr(item, "answer"):
                yield Event(
                    author=self.name,
                    node_info={"path": ctx.node_path} if ctx.node_path else {},
                    content=types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=result_to_user_message(item))],
                    ),
                )

    async def aclose(self) -> None:
        if self._runtime is not None:
            await self._runtime.aclose_best_effort(timeout=5.0)


# root_agent is instantiated at import time; no env is read here.
root_agent = ProductionWorkflowAgent(name="BEE_AI_ENTERPRISES_PRODUCTION")
