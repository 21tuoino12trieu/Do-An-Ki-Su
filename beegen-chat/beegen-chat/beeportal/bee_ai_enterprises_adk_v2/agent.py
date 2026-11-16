# -*- coding: utf-8 -*-
"""Composition root and adapters for Bee AI Enterprises ADK."""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import AsyncGenerator

from pydantic import ValidationError

from .core.runtime import EnterpriseAgentRuntime, EnterpriseRequest
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
        model_name = kwargs.get("model") or os.getenv("AIE_LLM_MEDIUM_MODEL", "unknown")
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

        # ── REAL STREAMING ────────────────────────────────────────
        # Stream partial (token-by-token) events from the LLM as they
        # arrive, then send a final chunk with docs metadata.
        docs: list = []
        trace_id: str | None = None
        has_streamed_content = False

        async for event in self._runtime.execute_stream(request, author="system"):
            ev_metadata = event.custom_metadata or {}

            # Capture trace_id from runtime
            if "trace_id" in ev_metadata:
                trace_id = ev_metadata["trace_id"]

            # ── Partial streaming tokens ──────────────────────────
            if getattr(event, "partial", False):
                if event.content and event.content.parts:
                    text = "".join(
                        p.text for p in event.content.parts if getattr(p, "text", None)
                    )
                    if text:
                        chunk_kwargs = {
                            "content": text,
                            "last": False,
                            "chat_id": req_id,
                            "model": model_name,
                        }
                        # Đính kèm docs vào chunk đầu tiên (nếu đã có)
                        if not has_streamed_content and docs:
                            chunk_kwargs["docs"] = docs
                        yield fake_chunk_from(**chunk_kwargs)
                        has_streamed_content = True
                continue

            # ── Final event (visibility=final) ────────────────────
            visibility = ev_metadata.get("visibility")
            if visibility == "final":
                # Thu thập docs từ metadata
                if "docs" in ev_metadata:
                    docs = ev_metadata["docs"]

                # Nếu chưa stream gì (ví dụ: guardrail block, cached result,
                # hoặc luồng has_review=True chưa bật real-stream), thì
                # yield toàn bộ text từ final event.
                if not has_streamed_content:
                    final_text = ""
                    if event.content and event.content.parts:
                        final_text = "".join(
                            p.text for p in event.content.parts if getattr(p, "text", None)
                        )
                    elif getattr(event, "output", None):
                        final_text = str(event.output)

                    if final_text:
                        chunk_kwargs = {
                            "content": final_text,
                            "last": False,
                            "chat_id": req_id,
                            "model": model_name,
                        }
                        if docs:
                            chunk_kwargs["docs"] = docs
                        yield fake_chunk_from(**chunk_kwargs)
                        has_streamed_content = True

        # ── Closing chunk ─────────────────────────────────────────
        final_kwargs = {
            "content": "",
            "last": True,
            "chat_id": req_id,
            "model": model_name,
        }
        # Nếu docs chưa được đính kèm ở chunk nào trước đó, gắn vào chunk cuối
        if docs:
            final_kwargs["docs"] = docs
        yield fake_chunk_from(**final_kwargs)

        # ── Trace ID update ───────────────────────────────────────
        if client_message_id:
            if not trace_id:
                try:
                    from opentelemetry import trace
                    span = trace.get_current_span()
                    span_ctx = span.get_span_context() if span else None
                    if span_ctx and span_ctx.trace_id != 0:
                        trace_id = f"{span_ctx.trace_id:032x}"
                except Exception:
                    pass
            if not trace_id:
                try:
                    from langfuse.decorators import langfuse_context
                    trace_id = langfuse_context.get_current_trace_id()
                except Exception:
                    pass
            if not trace_id:
                trace_id = client_message_id

            from beeportal.utils import update_turn_chat_trace_id
            asyncio.create_task(update_turn_chat_trace_id(
                session_id=session_id,
                client_message_id=client_message_id,
                trace_id=trace_id,
            ))

    async def aclose(self) -> None:
        """Wait for execution drain and close resources."""
        await self._runtime.aclose()

    async def aclose_best_effort(self, timeout: float = 5.0) -> None:
        """Bounded alternative for process shutdown."""
        await self._runtime.aclose_best_effort(timeout=timeout)


from .core.orchestrator import build_root_workflow
from .utils.langfuse_tracing import setup_langfuse_tracing
from google.adk.apps.app import App
from google.adk.plugins.global_instruction_plugin import GlobalInstructionPlugin
from .utils.langfuse_client import get_langfuse_client

# ADK Web UI integration
# load_dotenv đảm bảo env vars được nạp khi adk web CLI khởi chạy module
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass

# Langfuse OTel tracing — PHẢI gọi TRƯỚC khi root_agent được tạo
# để GoogleADKInstrumentor patch các ADK classes kịp thời
setup_langfuse_tracing()

# Load banking ontology from Langfuse (fallback to constants)
try:
    _lf = get_langfuse_client()
    _banking_ontology = _lf.get_prompt("BEE_AI_ENTERPRISES_ADK_V2:BANKING_ONTOLOGY").compile()
except Exception:
    from .constants import BANKING_CUSTOMER_ONTOLOGY
    _banking_ontology = BANKING_CUSTOMER_ONTOLOGY

initialize_retrieval_nodes_sync()
_workflow = build_root_workflow()
app = App(
    name="bee_ai_enterprises_adk_v2",
    root_agent=_workflow,
    plugins=[
        GlobalInstructionPlugin(global_instruction=_banking_ontology),
    ],
)

