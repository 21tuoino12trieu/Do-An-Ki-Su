# -*- coding: utf-8 -*-
"""LiteLLM model builder for Bee AI Enterprises ADK."""
from __future__ import annotations

import logging
import os

from google.adk.models.lite_llm import LiteLlm

logger = logging.getLogger(__name__)


def _set_litellm_proxy_api_key(api_key: str | None) -> None:
    """Mirror API key to LiteLLM proxy env expected by litellm."""
    if api_key and not os.getenv("LITELLM_PROXY_API_KEY"):
        os.environ["LITELLM_PROXY_API_KEY"] = api_key


def build_litellm_model() -> LiteLlm:
    """Build a LiteLlm model from AIE_LLM_* environment variables."""
    api_type = os.getenv("AIE_LLM_API_TYPE", "litellm_proxy")
    api_key = os.getenv("AIE_LLM_API_KEY")
    base_url = os.getenv("AIE_LLM_BASE_URL")
    model = os.getenv("AIE_LLM_MODEL")

    if api_type != "litellm_proxy":
        raise ValueError("AIE_LLM_API_TYPE must be 'litellm_proxy'.")

    missing = [
        name
        for name, value in {
            "AIE_LLM_API_KEY": api_key,
            "AIE_LLM_BASE_URL": base_url,
            "AIE_LLM_MODEL": model,
        }.items()
        if not value
    ]
    if missing:
        raise ValueError(f"Missing required environment variables: {missing}")

    _set_litellm_proxy_api_key(api_key)
    
    return LiteLlm(
        model=f"litellm_proxy/{model}",
        api_base=base_url,
        api_key=api_key,
    )
