# -*- coding: utf-8 -*-
"""Shared runtime execution core for Bee AI Enterprises ADK."""
from __future__ import annotations

import asyncio
import logging
import os
import hashlib
from pathlib import Path
from typing import Literal, AsyncGenerator

import yaml
from pydantic import BaseModel, Field, field_validator
from pymongo import MongoClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import make_url, text

from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.adk.events import Event

from ..agents.main_agent import build_main_agent
from ..tools import initialize_retrieval_nodes_sync
from ..utils.lock_manager import SessionLockManager, IdempotencyConflictError, HeartbeatFailedError
from .state_machine import run_state_machine
from .exceptions import MissingFinalDraftError

logger = logging.getLogger(__name__)

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



AGENT_REQUESTS_SCHEMA = "agent_ai"
AGENT_REQUESTS_REQUIRED_COLUMNS = {
    "bot_id", "namespace_version", "user_id", "request_hash", "conversation_id",
    "request_id", "status", "phase", "response", "final_event_id", "user_event_id",
    "error", "attempt", "draft_event_id", "reviewer_verdict", "reviewer_feedback",
    "iteration", "lease_expires_at", "created_at", "updated_at"
}
AGENT_REQUESTS_UNIQUE_COLUMNS = {
    "bot_id", "namespace_version", "user_id", "conversation_id", "request_id"
}

_FALLBACK_MESSAGES: dict[str, str] = {
    "invalid_request":  "Vui lòng nhập câu hỏi.",
    "context_limit":    "Cuộc hội thoại đã quá dài, vui lòng tạo phiên chat mới để tiếp tục.",
    "conflict":         "Hệ thống đang xử lý yêu cầu này, vui lòng chờ...",
    "retryable_error":  "Hệ thống gặp sự cố mất kết nối mạng cục bộ. Vui lòng thử lại.",
    "terminal_error":   "Xin lỗi, đã xảy ra lỗi khi xử lý yêu cầu của bạn. Vui lòng thử lại sau.",
}

def result_to_user_message(result: EnterpriseResult) -> str:
    """Map result to user message. Uses intentional answer if present."""
    if result.answer:
        return result.answer
    return _FALLBACK_MESSAGES.get(result.status, "Xin lỗi, đã xảy ra lỗi không xác định.")

# ---------------------------------------------------------------------------
# Core Runtime
# ---------------------------------------------------------------------------

class EnterpriseAgentRuntime:
    """Unified runtime state machine executor for API and ADK Web."""
    
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
        
        self._main_agent = None
        self._canonical_session_service = None
        self._runner = None
        self._lock_manager = None
        self._enable_reviewer = True
        self._app_name = f"bee_ai_enterprises_adk:{self.bot_id}"

    async def _ensure_initialized(self) -> None:
        """Concurrency-safe lazy initialization of bot configurations and resources."""
        if self._initialized:
            return
            
        async with self._startup_lock:
            if self._initialized:
                return

            mongo_path_str = os.getenv("MONGO_CONFIG_PATH", "config/mongo.yaml")
            mongo_path = Path(mongo_path_str)
            if not mongo_path.exists():
                raise ValueError(f"Thiếu file cấu hình MongoDB: {mongo_path}")

            try:
                with open(mongo_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
                mongo_uri = cfg.get("uri")
                mongo_authen = cfg.get("authen_source")
                if not mongo_uri:
                    raise ValueError(f"Thiếu 'uri' trong cấu hình {mongo_path}")
                if not mongo_authen:
                    raise ValueError(f"Thiếu 'authen_source' trong cấu hình {mongo_path}")
            except Exception as e:
                logger.error("[Runtime] Lỗi đọc %s: %s", mongo_path, e)
                raise ValueError(f"Lỗi đọc cấu hình MongoDB {mongo_path}: {e}") from e

            definition = ""
            client = MongoClient(mongo_uri)
            try:
                with client:
                    db = client[mongo_authen]
                    bots_collection = db["botinfo"]
                    doc = bots_collection.find_one({"_id": self.bot_id})
                    if not doc:
                        raise LookupError(f"Không tìm thấy bot_id {self.bot_id} trong cấu hình.")

                    bot_data = doc.get("data") or {}
                    metadata = bot_data.get("metadata") or {}
                    definition = metadata.get("system_prompt", "")
            except LookupError:
                raise
            except Exception as e:
                logger.error("[Runtime] Lỗi kết nối MongoDB: %s", e)
                raise RuntimeError(f"Lỗi kết nối hoặc đọc từ MongoDB: {e}") from e

            initialize_retrieval_nodes_sync()
            self._main_agent = build_main_agent(definition=definition)

            pg_url = os.getenv("POSTGRES_URL")
            if not pg_url:
                raise ValueError("Bắt buộc phải có biến môi trường POSTGRES_URL")

            # Validate and format lock DSN (native driver)
            lock_dsn_obj = make_url(pg_url)
            if "postgresql" not in lock_dsn_obj.drivername:
                raise ValueError("POSTGRES_URL phải sử dụng PostgreSQL")
            lock_dsn_obj = lock_dsn_obj.set(drivername="postgresql")
            lock_dsn = lock_dsn_obj.render_as_string(hide_password=False)

            try:
                self._lock_manager = await SessionLockManager.create(lock_dsn)
            except Exception as e:
                logger.error("[Runtime] Không thể khởi tạo SessionLockManager: %s", e)
                raise

            # Validate and format ADK DB DSN (asyncpg driver)
            adk_db_url_obj = lock_dsn_obj.set(drivername="postgresql+asyncpg")
            adk_db_url = adk_db_url_obj.render_as_string(hide_password=False)

            engine = None
            try:
                # 1. Validation phase with temporary engine
                engine = create_async_engine(adk_db_url)
                async with engine.connect() as conn:
                    # Check schema
                    res = await conn.execute(text("SELECT schema_name FROM information_schema.schemata WHERE schema_name = :schema"), {"schema": AGENT_REQUESTS_SCHEMA})
                    if not res.fetchone():
                        raise ValueError(f"Schema {AGENT_REQUESTS_SCHEMA} không tồn tại.")
                    
                    # Check columns
                    res = await conn.execute(text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = :schema AND table_name = 'agent_requests'"
                    ), {"schema": AGENT_REQUESTS_SCHEMA})
                    cols = {row[0] for row in res.fetchall()}
                    if not cols:
                        raise ValueError(f"Table {AGENT_REQUESTS_SCHEMA}.agent_requests không tồn tại.")
                    
                    missing_cols = AGENT_REQUESTS_REQUIRED_COLUMNS - cols
                    if missing_cols:
                        raise ValueError(f"Table agent_requests thiếu các cột bắt buộc: {missing_cols}")

                    # Check unique constraints with strict grouping and invalid/partial filtering
                    res = await conn.execute(text(
                        "SELECT c.conname, a.attname "
                        "FROM pg_constraint c "
                        "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey) "
                        "JOIN pg_class cls ON cls.oid = c.conrelid "
                        "JOIN pg_namespace n ON n.oid = cls.relnamespace "
                        "LEFT JOIN pg_index i ON i.indexrelid = c.conindid "
                        "WHERE n.nspname = :schema AND cls.relname = 'agent_requests' "
                        "AND c.contype = 'u' "
                        "AND (i.indexrelid IS NULL OR (i.indisvalid = true AND i.indpred IS NULL))"
                    ), {"schema": AGENT_REQUESTS_SCHEMA})
                    
                    rows = res.fetchall()
                    indexes = {}
                    for row in rows:
                        indexes.setdefault(row[0], set()).add(row[1])
                    
                    has_valid_unique = any(cols == AGENT_REQUESTS_UNIQUE_COLUMNS for cols in indexes.values())
                    if not has_valid_unique:
                        raise ValueError(f"Table agent_requests thiếu ít nhất một valid, non-partial unique constraint với chính xác các cột: {AGENT_REQUESTS_UNIQUE_COLUMNS}")

                # Temporary engine is disposed in finally block

                # 2. Initialization of long-lived services
                self._canonical_session_service = DatabaseSessionService(db_url=adk_db_url)
                self._runner = Runner(
                    agent=self._main_agent,
                    session_service=self._canonical_session_service,
                    app_name=self._app_name
                )
                self._initialized = True
                
            except Exception as e:
                safe_url = adk_db_url_obj.render_as_string(hide_password=True)
                logger.error("[Runtime] Khởi tạo runtime thất bại với URL: %s", safe_url)
                if self._lock_manager:
                    await self._lock_manager.close()
                    self._lock_manager = None
                raise RuntimeError(f"DatabaseSessionService init error for {safe_url}: {e}") from e
            finally:
                if engine is not None:
                    await engine.dispose()

    async def _check_context_guard(self, session_id: str, user_id: str, app_name: str) -> bool:
        session = await self._canonical_session_service.get_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id
        )
        if session and session.events:
            total_len = 0
            for event in session.events:
                if event.content and getattr(event.content, "parts", None):
                    for part in event.content.parts:
                        if hasattr(part, "text") and part.text:
                            total_len += len(part.text)
                            if total_len > 3_000_000:
                                logger.warning(
                                    "[Runtime] Session %s vượt quá 3M context length.",
                                    session_id
                                )
                                return False
        return True

    async def execute(self, request: EnterpriseRequest, event_queue: asyncio.Queue | None = None) -> EnterpriseResult:
        """Non-streaming async execution of the state machine."""
        async with self._lifecycle_lock:
            if self._closing or self._closed:
                return EnterpriseResult(status="retryable_error", answer="", request_id=request.request_id)
            if self._active_executions == 0:
                self._drained_event.clear()
            self._active_executions += 1
            
        try:
            await self._ensure_initialized()
            app_name = self._app_name

            is_safe = await self._check_context_guard(
                session_id=request.conversation_id,
                user_id=request.user_id,
                app_name=app_name
            )
            if not is_safe:
                return EnterpriseResult(status="context_limit", answer="", request_id=request.request_id)

            req_hash = hashlib.sha256(request.user_query.encode("utf-8")).hexdigest()
            try:
                async with self._lock_manager.lock(
                    app_name=app_name,
                    bot_id=self.bot_id,
                    namespace_version="v7",
                    user_id=request.user_id,
                    conversation_id=request.conversation_id,
                    request_id=request.request_id,
                    request_hash=req_hash,
                    timeout=15.0
                ) as req_state:
                    
                    # Check for cached complete/failed state
                    if req_state.status == "completed":
                        if req_state.reviewer_verdict == "ASK_BACK" and req_state.reviewer_feedback:
                            return EnterpriseResult(status="ask_back", answer=req_state.reviewer_feedback, request_id=request.request_id)
                        elif req_state.response:
                            return EnterpriseResult(status="completed", answer=req_state.response, request_id=request.request_id)

                    if req_state.status == "terminal_failed":
                        if req_state.error and "max_iterations" in str(req_state.error):
                            return EnterpriseResult(status="review_exhausted", answer=req_state.response or "", request_id=request.request_id)
                        return EnterpriseResult(status="terminal_error", answer=req_state.response or "", request_id=request.request_id)
                        

                    # Run state machine
                    try:
                        final_answer, is_ask_back = await run_state_machine(
                            runner=self._runner,
                            app_name=app_name,
                            req_state=req_state,
                            session_service=self._canonical_session_service,
                            request=request,
                            enable_reviewer=self._enable_reviewer,
                            main_agent_name=self._main_agent.name,
                            bot_id=self.bot_id,
                            event_queue=event_queue
                        )
                    except HeartbeatFailedError as e:
                        await req_state.mark_failed(str(e), status="retryable_failed")
                        return EnterpriseResult(status="retryable_error", answer="", request_id=request.request_id)
                    except MissingFinalDraftError as e:
                        return EnterpriseResult(status="retryable_error", answer="", request_id=request.request_id)

                    if req_state.status == "terminal_failed":
                        if req_state.error and "max_iterations" in str(req_state.error):
                            return EnterpriseResult(status="review_exhausted", answer=final_answer or "", request_id=request.request_id)
                        return EnterpriseResult(status="terminal_error", answer=final_answer or "", request_id=request.request_id)

                    if is_ask_back:
                        return EnterpriseResult(status="ask_back", answer=final_answer, request_id=request.request_id)
                        
                    return EnterpriseResult(status="completed", answer=final_answer, request_id=request.request_id)
            except TimeoutError:
                return EnterpriseResult(
                    status="conflict",
                    answer="Hệ thống đang xử lý yêu cầu này, vui lòng chờ...",
                    request_id=request.request_id
                )
        except asyncio.CancelledError:
            raise
        except IdempotencyConflictError:
            return EnterpriseResult(status="conflict", answer="", request_id=request.request_id)
        except HeartbeatFailedError:
            return EnterpriseResult(status="retryable_error", answer="", request_id=request.request_id)
        except MissingFinalDraftError:
            return EnterpriseResult(status="retryable_error", answer="", request_id=request.request_id)
        except Exception:
            logger.exception("[Runtime] Unexpected error in execute()")
            return EnterpriseResult(status="terminal_error", answer="", request_id=request.request_id)
        finally:
            async with self._lifecycle_lock:
                self._active_executions -= 1
                if self._active_executions == 0:
                    self._drained_event.set()

    async def execute_stream(self, request: EnterpriseRequest) -> AsyncGenerator[Event | EnterpriseResult, None]:
        """Stream async execution of the state machine."""
        event_queue = asyncio.Queue()

        async def run_task():
            try:
                res = await self.execute(request, event_queue=event_queue)
                await event_queue.put(res)
            except Exception as e:
                await event_queue.put(e)

        task = asyncio.create_task(run_task())

        while True:
            item = await event_queue.get()
            if isinstance(item, EnterpriseResult):
                yield item
                break
            elif isinstance(item, Exception):
                raise item
            else:
                yield item

    async def aclose(self) -> None:
        """Wait for drain with asyncio.Event; never close pool under active executions."""
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
        """Bounded alternative for process shutdown. Avoids force close if executions are active."""
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
                "[Runtime] aclose_best_effort() timed out after %s. %d executions still active. "
                "Resources will be leaked or forcefully closed by OS.",
                timeout, self._active_executions
            )

    async def _close_resources(self) -> None:
        if self._lock_manager:
            await self._lock_manager.close()
            self._lock_manager = None
        if self._canonical_session_service and hasattr(self._canonical_session_service, "close"):
            await self._canonical_session_service.close()
            self._canonical_session_service = None
        self._initialized = False
