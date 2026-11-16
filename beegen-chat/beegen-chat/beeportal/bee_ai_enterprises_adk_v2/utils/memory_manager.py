# -*- coding: utf-8 -*-
"""Long-term memory manager backed by mem0 + Milvus + LiteLLM Proxy.

Responsibilities
----------------
- Singleton lifecycle: one ``mem0.Memory`` instance per process.
- ``add_memory``: ingest a (user_query, answer) turn into mem0 keyed by
  ``user_id`` and ``run_id`` (session_id). Runs in a thread-pool so it
  never blocks the asyncio event-loop.
- ``search_memory``: semantic search for memories relevant to the current
  query, returning a ready-to-inject context string.

Scope convention
----------------
mem0 supports ``user_id``, ``agent_id``, and ``run_id`` filters.
We use only ``user_id`` (cross-session profile) and ``run_id`` (session_id,
intra-session context). ``agent_id`` is intentionally omitted.
"""
from __future__ import annotations

import asyncio
import contextvars
import logging
import os
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy singleton / factory
# ---------------------------------------------------------------------------

# ContextVar to propagate bot_id through asyncio tasks without polluting ADK signatures
current_bot_id_var = contextvars.ContextVar("current_bot_id", default="")

_instances: dict[str, "_Mem0Manager"] = {}
_init_failed_at: float = 0.0  # timestamp of last failure (0 = never failed)
_RETRY_AFTER_SECS: float = 60.0  # retry after 60 seconds
_lock = threading.Lock()


def get_memory_manager(bot_id: str = "") -> "_Mem0Manager":
    """Return the MemoryManager for a specific bot_id.

    If initialisation fails (e.g. Milvus unreachable), a *disabled* stub
    is returned that silently no-ops on add/search so the rest of the
    application keeps working. Retries after ``_RETRY_AFTER_SECS`` seconds.
    """
    global _init_failed_at
    bot_id = bot_id or current_bot_id_var.get()
    
    if bot_id:
        safe_bot_id = bot_id.replace("-", "_").strip()
        collection_name = f"mem_{safe_bot_id}"
    else:
        collection_name = os.environ.get("MEM0_MILVUS_COLLECTION", "bee_ai_user_memory")

    cache_key = collection_name

    if cache_key in _instances:
        return _instances[cache_key]
    if _init_failed_at and (time.monotonic() - _init_failed_at) < _RETRY_AFTER_SECS:
        return _DISABLED_STUB

    with _lock:
        if cache_key in _instances:
            return _instances[cache_key]
        if _init_failed_at and (time.monotonic() - _init_failed_at) < _RETRY_AFTER_SECS:
            return _DISABLED_STUB
        try:
            mgr = _Mem0Manager(collection_name=collection_name)
            _instances[cache_key] = mgr
            _init_failed_at = 0.0  # reset on success
            return mgr
        except Exception:
            _init_failed_at = time.monotonic()
            logger.exception(
                "[MemoryManager] Initialization FAILED (Milvus/LLM/Embedder unreachable?) "
                "— long-term memory DISABLED, will retry after %.0fs",
                _RETRY_AFTER_SECS,
            )
            return _DISABLED_STUB


class _DisabledMem0Manager:
    """No-op stub for when MemoryManager initialization fails."""
    async def add_memory(self, *args, **kwargs) -> None:
        pass
    
    async def search_memory(self, *args, **kwargs) -> str:
        return ""

_DISABLED_STUB = _DisabledMem0Manager()

# ---------------------------------------------------------------------------
# Manager class
# ---------------------------------------------------------------------------

class _Mem0Manager:
    """Thin async wrapper around ``mem0.Memory`` (synchronous)."""

    def __init__(self, collection_name: str) -> None:
        from mem0 import Memory

        # All config must come from env vars — no hardcoded defaults
        milvus_uri = os.environ.get("MEM0_MILVUS_URI", "")
        milvus_username = os.environ.get("MEM0_MILVUS_USERNAME", "")
        milvus_password = os.environ.get("MEM0_MILVUS_PASSWORD", "")
        milvus_db = os.environ.get("MEM0_MILVUS_DB", "")

        missing = [k for k, v in {
            "MEM0_MILVUS_URI": milvus_uri,
            "MEM0_MILVUS_DB": milvus_db,
        }.items() if not v]
        if missing:
            raise ValueError(f"Missing required mem0 environment variables: {missing}")

        # pymilvus MilvusClient accepts token as "username:password"
        milvus_token = (
            f"{milvus_username}:{milvus_password}"
            if milvus_username and milvus_password
            else os.environ.get("MEM0_MILVUS_TOKEN", "")
        )

        embed_base_url = os.environ.get("MEM0_EMBED_BASE_URL", "")
        embed_model = os.environ.get("MEM0_EMBED_MODEL", "")
        embed_dims = int(os.environ.get("MEM0_EMBED_DIMS", "1024"))

        if not embed_base_url or not embed_model:
            raise ValueError(
                "Missing required mem0 embedding env vars: MEM0_EMBED_BASE_URL, MEM0_EMBED_MODEL"
            )
        api_key = os.environ.get("AIE_LLM_API_KEY", "")

        llm_base_url = os.environ.get("AIE_LLM_BASE_URL", "")
        llm_model = os.environ.get("AIE_LLM_LOCAL_MODEL", "qwen-instruct")

        # Ensure litellm proxy env vars are set (same pattern as llm_utils.py)
        if api_key and not os.environ.get("LITELLM_PROXY_API_KEY"):
            os.environ["LITELLM_PROXY_API_KEY"] = api_key

        config = {
            "llm": {
                "provider": "litellm",
                "config": {
                    "model": f"litellm_proxy/{llm_model}",
                    "api_key": api_key,
                    "temperature": 0.0,
                    "max_tokens": 2000,
                },
            },
            "embedder": {
                # mem0 v2 has no 'litellm' embedder provider.
                # Use 'openai' provider with openai_base_url pointing to LiteLLM Proxy
                # (OpenAI-compatible /v1/embeddings endpoint).
                "provider": "openai",
                "config": {
                    "model": embed_model,
                    "openai_base_url": embed_base_url,
                    "api_key": api_key,
                },
            },
            "vector_store": {
                "provider": "milvus",
                "config": {
                    "url": milvus_uri,
                    "token": milvus_token,
                    "collection_name": collection_name,
                    "db_name": milvus_db,
                    "embedding_model_dims": embed_dims,
                    "metric_type": "COSINE",
                },
            },
            "version": "v1.1",
        }

        custom_instructions = os.environ.get("MEM0_CUSTOM_INSTRUCTIONS", "").strip()
        if custom_instructions:
            config["custom_instructions"] = custom_instructions

        # litellm needs LITELLM_PROXY_API_BASE to know where to route litellm_proxy/ calls
        if llm_base_url and not os.environ.get("LITELLM_PROXY_API_BASE"):
            os.environ["LITELLM_PROXY_API_BASE"] = llm_base_url

        self._mem = Memory.from_config(config_dict=config)
        logger.info(
            "[MemoryManager] mem0 initialized (Milvus: %s, collection: %s)",
            milvus_uri,
            collection_name,
        )

    # -----------------------------------------------------------------------
    # Public async API
    # -----------------------------------------------------------------------

    async def add_memory(
        self,
        user_query: str,
        answer: str,
        user_id: str,
        session_id: str,
    ) -> None:
        """Ingest a conversation turn into mem0 (fire-and-forget friendly).

        Runs ``mem0.Memory.add`` in a thread-pool to avoid blocking the
        event-loop. Exceptions are caught and logged — never re-raised so
        callers can use ``asyncio.create_task`` safely.
        """
        messages = [
            {"role": "user", "content": user_query},
            {"role": "assistant", "content": answer},
        ]
        try:
            await asyncio.to_thread(
                self._mem.add,
                messages,
                user_id=user_id,
                run_id=session_id,
                # agent_id intentionally omitted per project requirement
            )
            logger.info(
                "[MemoryManager] add_memory ok (user=%s session=%s)",
                user_id,
                session_id,
            )
        except Exception:
            logger.exception(
                "[MemoryManager] add_memory failed (user=%s session=%s) — skipping",
                user_id,
                session_id,
            )

    async def search_memory(
        self,
        query: str,
        user_id: str,
        session_id: str,
        limit: int = 5,
    ) -> str:
        """Return a formatted context string with memories relevant to *query*.

        Searches scoped to ``user_id`` + ``run_id`` (session_id).
        Returns an empty string when no memories are found or on error.
        """
        try:
            filters = {}
            if user_id:
                filters["user_id"] = user_id
            # Cố tình không filter theo session_id (run_id) 
            # để bot có thể nhớ được thông tin từ các session cũ của cùng user_id.

            results = await asyncio.to_thread(
                self._mem.search,
                query,
                filters=filters,
                limit=limit,
            )
            raw_list = (
                results.get("results") if isinstance(results, dict) else results
            ) or []

            memories: list[str] = []
            for r in raw_list:
                mem_text = r.get("memory") if isinstance(r, dict) else str(r)
                if mem_text:
                    memories.append(mem_text)

            if not memories:
                return ""

            lines = "\n".join(f"- {m}" for m in memories)
            return f"[Thông tin đã biết về người dùng]\n{lines}"

        except Exception:
            logger.exception(
                "[MemoryManager] search_memory failed (user=%s) — skipping",
                user_id,
            )
            return ""
