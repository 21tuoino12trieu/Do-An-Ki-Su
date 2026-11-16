# -*- coding: utf-8 -*-
"""Singleton Langfuse client with SSL verification disabled for internal environments."""

import logging
import os
import httpx
from langfuse import Langfuse

logger = logging.getLogger(__name__)

_langfuse_client = None

def get_langfuse_client() -> Langfuse:
    """Gets or initializes the singleton Langfuse client."""
    global _langfuse_client
    if _langfuse_client is None:
        verify_ssl = os.environ.get("HTTPX_VERIFY", "0") != "0"
        
        try:
            # Custom HTTPX Client to ignore self-signed certificates in dev/corp environments
            custom_httpx_client = httpx.Client(verify=verify_ssl)
            _langfuse_client = Langfuse(httpx_client=custom_httpx_client)
            logger.info("[Langfuse Prompts] Langfuse client initialized (verify_ssl=%s)", verify_ssl)
        except Exception as e:
            logger.error("[Langfuse Prompts] Failed to initialize Langfuse client: %s", e)
            # Fallback to default without custom httpx_client (might fail if verify=False is strictly needed)
            _langfuse_client = Langfuse()
            
    return _langfuse_client
