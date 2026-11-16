# -*- coding: utf-8 -*-
"""Shared runtime execution core for Bee AI Enterprises ADK (Workflow refactored)."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Literal, AsyncGenerator

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine

from google.adk.runners import Runner, RunConfig
from google.adk.sessions import DatabaseSessionService
from google.adk.events import Event
from google.adk.flows.llm_flows.base_llm_flow import StreamingMode
from google.adk.apps.app import App, EventsCompactionConfig
from google.adk.apps.llm_event_summarizer import LlmEventSummarizer
from google.adk.plugins.global_instruction_plugin import GlobalInstructionPlugin
from google.adk.agents.context_cache_config import ContextCacheConfig
from google.genai import types

from .orchestrator import build_root_workflow
from ..tools import initialize_retrieval_nodes_sync
from ..utils.llm_utils import build_small_model
from ..utils.langfuse_tracing import setup_langfuse_tracing
from ..utils.langfuse_client import get_langfuse_client
from ..utils.memory_manager import current_bot_id_var
logger = logging.getLogger(__name__)

AGENT_REQUESTS_SCHEMA = "agent_ai"
NAMESPACE_VERSION = "v7"

# ---------------------------------------------------------------------------
# Data Contracts
# ---------------------------------------------------------------------------

class EnterpriseRequest(BaseModel):
    user_id: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    user_query: str = Field(min_length=1)
    model: str | None = None

    @field_validator("user_id", "conversation_id", "request_id", "user_query", mode="before")
    @classmethod
    def strip_strings(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class EnterpriseResult(BaseModel):
    status: Literal[
        "completed",
        "ask_back",
        "invalid_request",
        "context_limit",
        "conflict",
        "retryable_error",
        "terminal_error",
        "review_exhausted",
    ]
    answer: str
    request_id: str
    docs: list | None = None
    trace_id: str | None = None


_FALLBACK_MESSAGES: dict[str, str] = {
    "invalid_request":  "Vui lòng nhập câu hỏi.",
    "context_limit":    "Cuộc hội thoại đã quá dài, vui lòng tạo phiên chat mới để tiếp tục.",
    "conflict":         "Hệ thống đang xử lý yêu cầu này, vui lòng chờ...",
    "retryable_error":  "Hệ thống gặp sự cố mất kết nối mạng cục bộ. Vui lòng thử lại.",
    "terminal_error":   "Xin lỗi, đã xảy ra lỗi khi xử lý yêu cầu của bạn. Vui lòng thử lại sau.",
}


def result_to_user_message(result: EnterpriseResult) -> str:
    if result.answer:
        return result.answer
    return _FALLBACK_MESSAGES.get(result.status, "Xin lỗi, đã xảy ra lỗi không xác định.")

# ---------------------------------------------------------------------------
# Core Runtime
# ---------------------------------------------------------------------------

class EnterpriseAgentRuntime:
    def __init__(self, bot_id: str) -> None:
        self.bot_id = bot_id

        self._initialized = False
        self._startup_lock = asyncio.Lock()

        self._lifecycle_lock = asyncio.Lock()
        self._closed = False
        self._closing = False
        self._active_executions = 0
        self._drained_event = asyncio.Event()
        self._drained_event.set()

        self._runner = None
        self._db_engine: AsyncEngine | None = None
        self._app_name = f"bee_ai_enterprises_adk_v2_{self.bot_id}"

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return

        async with self._startup_lock:
            if self._initialized:
                return

            # Langfuse OTel tracing — phải gọi TRƯỚC khi Runner chạy
            setup_langfuse_tracing()

            initialize_retrieval_nodes_sync()
            root_workflow = build_root_workflow()

            # Load banking ontology from Langfuse (fallback to constants)
            try:
                lf = get_langfuse_client()
                banking_ontology = lf.get_prompt("BEE_AI_ENTERPRISES_ADK_V2:BANKING_ONTOLOGY").compile()
            except Exception:
                logger.warning("[Runtime] Failed to load BANKING_ONTOLOGY from Langfuse — using fallback from constants")
                from ..constants import BANKING_CUSTOMER_ONTOLOGY
                banking_ontology = BANKING_CUSTOMER_ONTOLOGY

            pg_url = os.getenv("POSTGRES_URL")
            if not pg_url:
                raise ValueError("Bắt buộc phải có biến môi trường POSTGRES_URL")

            db_url_obj = make_url(pg_url)
            if "postgresql" not in db_url_obj.drivername:
                raise ValueError("POSTGRES_URL phải sử dụng PostgreSQL")
            db_url_obj = db_url_obj.set(drivername="postgresql+asyncpg")
            db_url = db_url_obj.render_as_string(hide_password=False)

            self._db_engine = create_async_engine(
                db_url,
                pool_pre_ping=True,
                pool_recycle=300
            )
            
            # Ensure docs column exists
            try:
                async with self._db_engine.begin() as conn:
                    await conn.execute(text("ALTER TABLE agent_ai.agent_requests ADD COLUMN IF NOT EXISTS docs JSONB"))
            except Exception as e:
                logger.warning(f"Could not add docs column to agent_requests table: {e}")

            session_service = DatabaseSessionService(db_url=db_url, pool_recycle=300)
            
            summarizer_model = build_small_model()
            lf = get_langfuse_client()
            compaction_instruction = lf.get_prompt("BEE_AI_ENTERPRISES_ADK_V2:COMPACTION_AGENT_PROMPT").compile()
            summarizer = LlmEventSummarizer(
                llm=summarizer_model,
                prompt_template=compaction_instruction
            )
            
            adk_app = App(
                name=self._app_name,
                root_agent=root_workflow,
                plugins=[
                    GlobalInstructionPlugin(global_instruction=banking_ontology),
                ],
                context_cache_config=ContextCacheConfig(
                    min_tokens=2048,
                    ttl_seconds=600,
                    cache_intervals=5,
                ),
                events_compaction_config=EventsCompactionConfig(
                    compaction_interval=15,
                    overlap_size=5,
                    summarizer=summarizer,
                )
            )
            
            self._runner = Runner(
                app=adk_app,
                session_service=session_service,
                auto_create_session=True,
            )
            self._initialized = True

    async def _fetch_request_state(self, request: EnterpriseRequest) -> dict | None:
        if not self._db_engine:
            return None
        query = text(
            "SELECT status, response, reviewer_verdict, reviewer_feedback, error, docs "
            "FROM agent_ai.agent_requests "
            "WHERE bot_id = :bot_id AND namespace_version = :namespace_version "
            "AND user_id = :user_id AND conversation_id = :conversation_id "
            "AND request_id = :request_id"
        )
        async with self._db_engine.connect() as conn:
            res = await conn.execute(query, {
                "bot_id": self.bot_id,
                "namespace_version": NAMESPACE_VERSION,
                "user_id": request.user_id,
                "conversation_id": request.conversation_id,
                "request_id": request.request_id,
            })
            row = res.fetchone()
            if not row:
                return None
            return {
                "status": row[0],
                "response": row[1],
                "reviewer_verdict": row[2],
                "reviewer_feedback": row[3],
                "error": row[4],
                "docs": row[5] if row[5] else []
            }

    async def _insert_request_state(self, request: EnterpriseRequest, request_hash: str) -> None:
        if not self._db_engine:
            return
        now = datetime.now(timezone.utc)
        lease_expires_at = now
        query = text(
            "INSERT INTO agent_ai.agent_requests ("
            "bot_id, namespace_version, user_id, conversation_id, request_id, request_hash, "
            "status, phase, iteration, attempt, lease_expires_at, created_at, updated_at"
            ") VALUES ("
            ":bot_id, :namespace_version, :user_id, :conversation_id, :request_id, :request_hash, "
            ":status, :phase, :iteration, :attempt, :lease_expires_at, :created_at, :updated_at"
            ")"
        )
        async with self._db_engine.begin() as conn:
            await conn.execute(query, {
                "bot_id": self.bot_id,
                "namespace_version": NAMESPACE_VERSION,
                "user_id": request.user_id,
                "conversation_id": request.conversation_id,
                "request_id": request.request_id,
                "request_hash": request_hash,
                "status": "processing",
                "phase": "starting",
                "iteration": 0,
                "attempt": 1,
                "lease_expires_at": lease_expires_at,
                "created_at": now,
                "updated_at": now,
            })

    async def _update_request_state(
        self,
        request: EnterpriseRequest,
        status: str,
        phase: str,
        response: str | None,
        reviewer_verdict: str | None,
        reviewer_feedback: str | None,
        error: str | None = None,
        iteration: int = 0,
        docs: list | None = None
    ) -> None:
        if not self._db_engine:
            return
        now = datetime.now(timezone.utc)
        
        query = text(
            "UPDATE agent_ai.agent_requests SET "
            "status = :status, phase = :phase, response = :response, "
            "reviewer_verdict = :reviewer_verdict, reviewer_feedback = :reviewer_feedback, "
            "iteration = :iteration, docs = :docs, "
            "error = :error, updated_at = :updated_at "
            "WHERE bot_id = :bot_id AND namespace_version = :namespace_version "
            "AND user_id = :user_id AND conversation_id = :conversation_id "
            "AND request_id = :request_id"
        )
        async with self._db_engine.begin() as conn:
            await conn.execute(query, {
                "status": status,
                "phase": phase,
                "response": response,
                "reviewer_verdict": reviewer_verdict,
                "reviewer_feedback": reviewer_feedback,
                "iteration": iteration,
                "docs": json.dumps(docs) if docs is not None else None,
                "error": error,
                "updated_at": now,
                "bot_id": self.bot_id,
                "namespace_version": NAMESPACE_VERSION,
                "user_id": request.user_id,
                "conversation_id": request.conversation_id,
                "request_id": request.request_id,
            })

    async def execute_stream(self, request: EnterpriseRequest, author: str) -> AsyncGenerator[Event, None]:
        async with self._lifecycle_lock:
            if self._closing or self._closed:
                return
            if self._active_executions == 0:
                self._drained_event.clear()
            self._active_executions += 1

        try:
            current_bot_id_var.set(self.bot_id)
            await self._ensure_initialized()

            existing = await self._fetch_request_state(request)
            if existing:
                if existing["status"] in {"completed", "ask_back", "review_exhausted", "terminal_error"} and existing.get("response"):
                    yield Event(
                        author=author,
                        content=types.Content(
                            role="model",
                            parts=[types.Part.from_text(text=existing["response"])],
                        ),
                        custom_metadata={"visibility": "final", "docs": existing.get("docs", [])}
                    )
                    return
                if existing["status"] in {"processing"}:
                    yield Event(
                        author=author,
                        content=types.Content(
                            role="model",
                            parts=[types.Part.from_text(text="Hệ thống đang xử lý yêu cầu này, vui lòng chờ...")],
                        ),
                        custom_metadata={"visibility": "final"}
                    )
                    return

            request_hash = str(abs(hash(request.user_query)))
            await self._insert_request_state(request, request_hash)

            final_answer = None
            final_status = "processing"
            final_phase = "processing"
            reviewer_verdict = None
            reviewer_feedback = None
            iteration = 0
            yielded_final = False
            final_docs = []
            trace_id_captured = None

            try:
                # Langfuse: propagate user/session context vào tất cả spans
                try:
                    from langfuse import propagate_attributes
                    _lf_ctx = propagate_attributes(
                        user_id=request.user_id,
                        session_id=request.conversation_id,
                        tags=["adk-v2", "bee-ai-enterprises"],
                        metadata={"bot_id": self.bot_id, "request_id": request.request_id},
                    )
                    _lf_ctx.__enter__()
                except Exception:
                    _lf_ctx = None

                async for event in self._runner.run_async(
                    user_id=request.user_id,
                    session_id=request.conversation_id,
                    new_message=types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=request.user_query)],
                    ),
                    invocation_id=request.request_id,
                    run_config=RunConfig(streaming_mode=StreamingMode.SSE),
                ):
                    # Capture OTel trace ID
                    if not trace_id_captured:
                        try:
                            from opentelemetry import trace
                            span = trace.get_current_span()
                            span_ctx = span.get_span_context() if span else None
                            if span_ctx and span_ctx.trace_id != 0:
                                trace_id_captured = f"{span_ctx.trace_id:032x}"
                        except Exception:
                            pass
                    state_delta = getattr(event.actions, "state_delta", {}) if hasattr(event, "actions") else getattr(event, "state", {})
                    if state_delta:
                        phase = state_delta.get("phase")
                        if phase:
                            iteration = state_delta.get("iteration", iteration)
                            final_phase = phase
                            
                            if phase in {"completed", "ask_back", "review_exhausted", "invalid_request"}:
                                final_status = phase if phase != "invalid_request" else "invalid_request"

                            if "reviewer_verdict" in state_delta:
                                reviewer_verdict = state_delta["reviewer_verdict"]
                            if "reviewer_feedback" in state_delta:
                                reviewer_feedback = state_delta["reviewer_feedback"]

                            await self._update_request_state(
                                request,
                                status=final_status if final_phase in {"completed", "review_exhausted", "ask_back", "invalid_request"} else "processing",
                                phase=final_phase,
                                response=None, # Only write response at the end
                                reviewer_verdict=reviewer_verdict,
                                reviewer_feedback=reviewer_feedback,
                                iteration=iteration
                            )

                    metadata = event.custom_metadata or {}
                    visibility = metadata.get("visibility")

                    # ── PARTIAL STREAMING ─────────────────────────────
                    # Forward partial (token-by-token) events to caller
                    # so UI can render text as it arrives from the LLM.
                    if getattr(event, "partial", False):
                        event.author = author
                        yield event
                        continue

                    if visibility == "final":
                        if yielded_final:
                            continue
                            
                        # Đã là final thì capture lại final text và yield ra ngoài
                        if event.content and event.content.parts:
                            final_answer = "".join(p.text for p in event.content.parts if p.text)
                        elif getattr(event, "output", None):
                            final_answer = str(event.output)
                            
                        if "docs" in metadata:
                            final_docs = metadata["docs"]
                            
                        if trace_id_captured:
                            metadata["trace_id"] = trace_id_captured
                        event.custom_metadata = metadata

                        # Gán lại author cho chuẩn UI stream
                        event.author = author
                        yield event
                        yielded_final = True

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.exception("[Runtime] Unexpected error inside runner.run_async()")
                final_status = "terminal_error"
                final_phase = "failed"
                final_answer = "Xin lỗi, đã xảy ra lỗi trong quá trình tra cứu."
                yield Event(
                    author=author,
                    content=types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=final_answer)],
                    ),
                    custom_metadata={"visibility": "final"}
                )
            finally:
                # Cleanup Langfuse propagate_attributes context
                if _lf_ctx is not None:
                    try:
                        _lf_ctx.__exit__(None, None, None)
                    except Exception:
                        pass

            # Đảm bảo record cuối cùng được ghi nhận
            # Chuyển đổi completed sang ask_back tuỳ verdict (như logic cũ)
            if final_status == "completed" and reviewer_verdict == "ASK_BACK":
                final_status = "ask_back"
                
            await self._update_request_state(
                request,
                status=final_status if final_status != "processing" else "completed",
                phase=final_phase,
                response=final_answer,
                reviewer_verdict=reviewer_verdict,
                reviewer_feedback=reviewer_feedback,
                iteration=iteration,
                docs=final_docs
            )

            # Long-term memory ingestion is now handled directly by ActorCriticOrchestrator._run_impl


        except Exception:
            logger.exception("[Runtime] Unexpected error in execute_stream()")
            await self._update_request_state(request, status="terminal_error", phase="failed", response=None, reviewer_verdict=None, reviewer_feedback=None)
            yield Event(
                author=author,
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_text(text="Xin lỗi, đã xảy ra lỗi hệ thống.")],
                ),
                custom_metadata={"visibility": "final"}
            )
        finally:
            async with self._lifecycle_lock:
                self._active_executions -= 1
                if self._active_executions == 0:
                    self._drained_event.set()

    async def execute(self, request: EnterpriseRequest) -> EnterpriseResult:
        """Sử dụng chung luồng với execute_stream để tránh lặp logic DB."""
        final_answer = ""
        final_status = "terminal_error"
        final_docs = []
        trace_id = None
        
        try:
            async for event in self.execute_stream(request, author="system"):
                metadata = getattr(event, "custom_metadata", {}) or {}
                if "trace_id" in metadata:
                    trace_id = metadata["trace_id"]
                visibility = metadata.get("visibility")
                if visibility == "final":
                    if getattr(event, "output", None):
                        final_answer = str(event.output)
                    elif event.content and event.content.parts:
                        final_answer = "".join(p.text for p in event.content.parts if p.text)
                    if "docs" in metadata:
                        final_docs = metadata["docs"]
            
            # Fetch the final status from DB to return accurate result
            if self._db_engine:
                existing = await self._fetch_request_state(request)
                if existing:
                    final_status = existing["status"]
                    if existing["response"]:
                        final_answer = existing["response"]
                    if existing.get("docs"):
                        final_docs = existing["docs"]
            
            if final_status not in {"completed", "ask_back", "review_exhausted", "invalid_request", "conflict", "retryable_error"}:
                final_status = "terminal_error"
                
            return EnterpriseResult(status=final_status, answer=final_answer, request_id=request.request_id, docs=final_docs, trace_id=trace_id)
            
        except Exception:
            logger.exception("[Runtime] Error wrapping execute_stream in execute()")
            return EnterpriseResult(status="terminal_error", answer="", request_id=request.request_id)

    async def aclose(self) -> None:
        if self._closed:
            return
        async with self._lifecycle_lock:
            if self._closed:
                return
            self._closing = True
            if self._active_executions > 0:
                logger.warning(
                    "[Runtime] aclose() called with %d active execution(s). Waiting for drain.",
                    self._active_executions,
                )
        if self._active_executions > 0:
            await self._drained_event.wait()
        async with self._lifecycle_lock:
            await self._close_resources()
            self._closed = True

    async def aclose_best_effort(self, timeout: float = 5.0) -> None:
        if self._closed:
            return
        async with self._lifecycle_lock:
            if self._closed:
                return
            self._closing = True
        try:
            if self._active_executions > 0:
                await asyncio.wait_for(self._drained_event.wait(), timeout=timeout)
            async with self._lifecycle_lock:
                await self._close_resources()
                self._closed = True
        except asyncio.TimeoutError:
            logger.warning(
                "[Runtime] aclose_best_effort() timed out after %s. %d executions still active. ",
                timeout, self._active_executions,
            )

    async def _close_resources(self) -> None:
        if self._db_engine is not None:
            await self._db_engine.dispose()
            self._db_engine = None
        self._initialized = False
