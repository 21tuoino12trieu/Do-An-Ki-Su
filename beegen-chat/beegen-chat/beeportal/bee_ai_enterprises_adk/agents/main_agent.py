# -*- coding: utf-8 -*-
"""Build MainAgent (LlmAgent) cho Bee AI Enterprises ADK."""
from __future__ import annotations

from google.adk.agents import LlmAgent

from ..utils.llm_utils import build_litellm_model
from ..prompts.react_agent import build_react_agent_prompt
from ..tools import (
    search_forms_tool, 
    search_documents_tool, 
    search_qna_tool,
    initialize_retrieval_nodes_sync,
)

_MAIN_AGENT_NAME = "ENTERPRISES_MAIN_AGENT"

def build_main_agent(definition: str = "") -> LlmAgent:
    """Tạo MainAgent với 3 GCP retrieval tools."""
    initialize_retrieval_nodes_sync()
    
    return LlmAgent(
        name=_MAIN_AGENT_NAME,
        model=build_litellm_model(),
        instruction=build_react_agent_prompt(definition=definition),
        tools=[
            search_forms_tool,
            search_documents_tool,
            search_qna_tool,
        ],
    )
