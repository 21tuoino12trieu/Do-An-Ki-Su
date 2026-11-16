# -*- coding: utf-8 -*-
"""LiteLLM model builder for Bee AI Enterprises ADK."""
from __future__ import annotations

import logging
import os

from google.adk.models.lite_llm import LiteLlm

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LiteLLM Proxy – Priority request headers
# Route qua priority queue để tốc độ nhanh và ổn định hơn.
# ---------------------------------------------------------------------------
_LITELLM_PRIORITY_HEADERS = {
    "X-Vertex-AI-LLM-Request-Type": "shared",
    "X-Vertex-AI-LLM-Shared-Request-Type": "priority",
}


def _set_litellm_proxy_api_key(api_key: str | None) -> None:
    """Mirror API key to LiteLLM proxy env expected by litellm."""
    if api_key and not os.getenv("LITELLM_PROXY_API_KEY"):
        os.environ["LITELLM_PROXY_API_KEY"] = api_key


def build_medium_model(*, enable_minimal_thinking: bool = False) -> LiteLlm:
    """Build a medium-sized LiteLlm model from AIE_LLM_MEDIUM_MODEL (default: gemini-3.5-flash)."""
    api_type = os.getenv("AIE_LLM_API_TYPE", "litellm_proxy")
    api_key = os.getenv("AIE_LLM_API_KEY")
    base_url = os.getenv("AIE_LLM_BASE_URL")
    model = os.getenv("AIE_LLM_MEDIUM_MODEL", "gemini-3.5-flash")

    if api_type != "litellm_proxy":
        raise ValueError("AIE_LLM_API_TYPE must be 'litellm_proxy'.")

    missing = [
        name
        for name, value in {
            "AIE_LLM_API_KEY": api_key,
            "AIE_LLM_BASE_URL": base_url,
            "AIE_LLM_MEDIUM_MODEL": model,
        }.items()
        if not value
    ]
    if missing:
        raise ValueError(f"Missing required environment variables: {missing}")

    _set_litellm_proxy_api_key(api_key)
    
    kwargs = {"reasoning_effort": "none"}
    if enable_minimal_thinking:
        if "gemini" in model.lower():
            kwargs["thinking_config"] = {"thinking_level": "minimal"}

    return LiteLlm(
        model=f"litellm_proxy/{model}",
        api_base=base_url,
        api_key=api_key,
        temperature=1.0,
        extra_headers=_LITELLM_PRIORITY_HEADERS,
        metadata={"headers": _LITELLM_PRIORITY_HEADERS},
        **kwargs
    )


def build_small_model() -> LiteLlm:
    """Build a small-sized LiteLlm model from AIE_LLM_SMALL_MODEL (default: gemini-3.1-flash-lite)."""
    api_type = os.getenv("AIE_LLM_API_TYPE", "litellm_proxy")
    api_key = os.getenv("AIE_LLM_API_KEY")
    base_url = os.getenv("AIE_LLM_BASE_URL")
    model = os.getenv("AIE_LLM_SMALL_MODEL", "gemini-3.1-flash-lite")

    if api_type != "litellm_proxy":
        raise ValueError("AIE_LLM_API_TYPE must be 'litellm_proxy'.")

    missing = [
        name
        for name, value in {
            "AIE_LLM_API_KEY": api_key,
            "AIE_LLM_BASE_URL": base_url,
            "AIE_LLM_MODEL_SUMMARIZER (or default fallback)": model,
        }.items()
        if not value
    ]
    if missing:
        raise ValueError(f"Missing required environment variables for summarizer: {missing}")

    _set_litellm_proxy_api_key(api_key)
    
    return LiteLlm(
        model=f"litellm_proxy/{model}",
        api_base=base_url,
        api_key=api_key,
        temperature=1.0,
        stream=False,
        reasoning_effort="none",
        extra_headers=_LITELLM_PRIORITY_HEADERS,
        metadata={"headers": _LITELLM_PRIORITY_HEADERS},
    )


def build_local_model() -> LiteLlm:
    """Build a local-sized LiteLlm model from AIE_LLM_LOCAL_MODEL (default: qwen-instruct)."""
    api_type = os.getenv("AIE_LLM_API_TYPE", "litellm_proxy")
    api_key = os.getenv("AIE_LLM_API_KEY")
    base_url = os.getenv("AIE_LLM_BASE_URL")
    model = os.getenv("AIE_LLM_LOCAL_MODEL", "qwen-instruct")

    if api_type != "litellm_proxy":
        raise ValueError("AIE_LLM_API_TYPE must be 'litellm_proxy'.")

    missing = [
        name
        for name, value in {
            "AIE_LLM_API_KEY": api_key,
            "AIE_LLM_BASE_URL": base_url,
            "AIE_LLM_LOCAL_MODEL": model,
        }.items()
        if not value
    ]
    if missing:
        raise ValueError(f"Missing required environment variables for local model: {missing}")

    _set_litellm_proxy_api_key(api_key)
    
    return LiteLlm(
        model=f"litellm_proxy/{model}",
        api_base=base_url,
        api_key=api_key,
        temperature=1.0,
        reasoning_effort="none",
        extra_headers=_LITELLM_PRIORITY_HEADERS,
        metadata={"headers": _LITELLM_PRIORITY_HEADERS},
    )


