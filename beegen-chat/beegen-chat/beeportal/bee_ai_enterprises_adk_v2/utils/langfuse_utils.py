# -*- coding: utf-8 -*-
"""Langfuse utilities cho bee_ai_enterprises_adk.

Cung cấp:
  - Singleton Langfuse client (đọc config từ os.getenv)
  - Prompt fetching với in-memory TTL cache
  - Fallback helpers (raw + compiled)

Pattern tương tự beegen-agent/app/utils/langfuse_utils.py nhưng không phụ thuộc
vào app/config.py — đọc trực tiếp từ biến môi trường.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory prompt cache
# ---------------------------------------------------------------------------

_langfuse_cache: Dict[str, tuple[str, float]] = {}
DEFAULT_CACHE_TTL = 3600

# ---------------------------------------------------------------------------
# Singleton client
# ---------------------------------------------------------------------------

_langfuse_client = None


def get_langfuse_client():
    """Khởi tạo (hoặc trả về) singleton Langfuse client.

    Đọc 3 biến môi trường:
      - LANGFUSE_PUBLIC_KEY
      - LANGFUSE_SECRET_KEY
      - LANGFUSE_HOST
    """
    global _langfuse_client

    if _langfuse_client is not None:
        return _langfuse_client

    try:
        from langfuse import Langfuse
        
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

        public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
        secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")
        host = os.getenv("LANGFUSE_HOST", "")

        if not public_key or not secret_key or not host:
            logger.warning(
                "[Langfuse] Thiếu biến môi trường LANGFUSE_PUBLIC_KEY / "
                "LANGFUSE_SECRET_KEY / LANGFUSE_HOST — client không khởi tạo."
            )
            return None

        _langfuse_client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
        )

        try:
            from langfuse.decorators import langfuse_context
            langfuse_context.configure(
                public_key=public_key,
                secret_key=secret_key,
                host=host,
            )
        except Exception as e:
            logger.warning("[Langfuse] Failed to configure decorator context: %s", e)

        logger.info("[Langfuse] Client initialized: %s", host)
        return _langfuse_client

    except Exception as e:
        logger.error("[Langfuse] Failed to initialize client: %s", e)
        _langfuse_client = None
        return None


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _get_cached_prompt(prompt_name: str, cache_ttl: int = DEFAULT_CACHE_TTL) -> Optional[str]:
    if prompt_name in _langfuse_cache:
        content, timestamp = _langfuse_cache[prompt_name]
        cache_age = time.time() - timestamp
        if cache_age < cache_ttl:
            logger.debug(
                "[CACHE HIT] prompt: %s (age: %.1fs, TTL: %ds)",
                prompt_name, cache_age, cache_ttl,
            )
            return content
        else:
            del _langfuse_cache[prompt_name]
            logger.debug("[CACHE EXPIRED] prompt: %s (age: %.1fs)", prompt_name, cache_age)

    return None


def _cache_prompt(prompt_name: str, content: str) -> None:
    _langfuse_cache[prompt_name] = (content, time.time())


def clear_cache(prompt_name: Optional[str] = None) -> None:
    """Xoá cache prompt (tất cả hoặc theo tên)."""
    if prompt_name:
        _langfuse_cache.pop(prompt_name, None)
        logger.info("[Langfuse] Cleared cache for prompt: %s", prompt_name)
    else:
        _langfuse_cache.clear()
        logger.info("[Langfuse] Cleared all prompt cache")


# ---------------------------------------------------------------------------
# Fetch raw prompt (chưa compile)
# ---------------------------------------------------------------------------

def get_prompt_from_langfuse(
    prompt_name: str,
    cache_ttl: int = DEFAULT_CACHE_TTL,
    version: Optional[int] = None,
) -> Optional[str]:
    """Fetch raw prompt string từ Langfuse (có cache TTL).

    Returns:
        Prompt string nếu thành công, None nếu thất bại.
    """
    cached = _get_cached_prompt(prompt_name, cache_ttl)
    if cached is not None:
        return cached

    try:
        langfuse = get_langfuse_client()
        if not langfuse:
            logger.warning("[FETCH] Langfuse client not available for: %s", prompt_name)
            return None

        logger.info("[FETCH] Calling langfuse.get_prompt(): %s", prompt_name)
        online_prompt = langfuse.get_prompt(
            prompt_name,
            cache_ttl_seconds=0,
            version=version,
        )

        if not online_prompt:
            logger.warning("[FETCH] Prompt not found in Langfuse: %s", prompt_name)
            return None

        prompt_content = online_prompt.prompt
        _cache_prompt(prompt_name, prompt_content)

        logger.info(
            "[FETCH SUCCESS] Retrieved prompt from Langfuse: %s "
            "(version: %s, length: %d)",
            prompt_name, online_prompt.version, len(prompt_content),
        )

        return prompt_content

    except Exception as e:
        logger.error("[FETCH ERROR] Failed to get prompt '%s' from Langfuse: %s", prompt_name, e)
        return None


def get_prompt_with_fallback(
    prompt_name: str,
    fallback_value: Optional[str] = None,
    cache_ttl: int = DEFAULT_CACHE_TTL,
    version: Optional[int] = None,
) -> Optional[str]:
    """Fetch prompt từ Langfuse, fallback về giá trị local nếu thất bại."""
    langfuse_prompt = get_prompt_from_langfuse(prompt_name, cache_ttl, version)

    if langfuse_prompt is not None:
        logger.info("[FALLBACK] Using Langfuse prompt (no fallback needed): %s", prompt_name)
        return langfuse_prompt

    if fallback_value is None:
        logger.warning("[FALLBACK ERROR] Prompt '%s' not found and no fallback provided", prompt_name)
        return None

    logger.info(
        "[FALLBACK] Using local fallback for prompt: %s (length: %d)",
        prompt_name, len(fallback_value),
    )
    return fallback_value


# ---------------------------------------------------------------------------
# Fetch + compile prompt (có template variables)
# ---------------------------------------------------------------------------

def get_compiled_prompt_from_langfuse(
    prompt_name: str,
    variables: Optional[Dict[str, Any]] = None,
    cache_ttl: int = DEFAULT_CACHE_TTL,
    version: Optional[int] = None,
) -> Optional[str]:
    """Fetch prompt từ Langfuse và compile template variables.

    Langfuse sử dụng cú pháp ``{{variable}}`` cho template variables.
    Hàm ``online_prompt.compile(**variables)`` sẽ thay thế các biến đó.

    Returns:
        Compiled prompt string nếu thành công, None nếu thất bại.
    """
    try:
        langfuse = get_langfuse_client()
        if not langfuse:
            return None

        online_prompt = langfuse.get_prompt(
            prompt_name,
            cache_ttl_seconds=0,
            version=version,
        )

        if not online_prompt:
            return None

        if variables:
            compiled = online_prompt.compile(**variables)
        else:
            compiled = online_prompt.prompt

        # Cache raw template (không cache compiled result vì variables thay đổi)
        _cache_prompt(prompt_name, online_prompt.prompt)

        logger.info("[COMPILE SUCCESS] Compiled prompt from Langfuse: %s", prompt_name)
        return compiled

    except Exception as e:
        logger.error("[COMPILE ERROR] Failed to compile prompt '%s' from Langfuse: %s", prompt_name, e)
        return None


def get_compiled_prompt_with_fallback(
    prompt_name: str,
    variables: Optional[Dict[str, Any]] = None,
    fallback_value: Optional[str] = None,
    cache_ttl: int = DEFAULT_CACHE_TTL,
    version: Optional[int] = None,
) -> Optional[str]:
    """Fetch + compile prompt từ Langfuse, fallback về giá trị local nếu thất bại."""
    compiled = get_compiled_prompt_from_langfuse(
        prompt_name, variables, cache_ttl, version,
    )

    if compiled is not None:
        return compiled

    if fallback_value is None:
        logger.warning("[FALLBACK ERROR] Prompt '%s' not found and no fallback provided", prompt_name)
        return None

    logger.info("[FALLBACK] Using local fallback for compiled prompt: %s", prompt_name)
    return fallback_value
