# -*- coding: utf-8 -*-
"""Build ReviewerAgent cho Bee AI Enterprises ADK."""
from __future__ import annotations

from google.adk.agents import LlmAgent

from ..utils.llm_utils import build_medium_model
from ..utils.langfuse_client import get_langfuse_client
from ..core.schemas import ReviewVerdict

_REVIEWER_AGENT_NAME = "ENTERPRISES_REVIEWER_AGENT"


def build_reviewer_agent() -> LlmAgent:
    """Tạo ReviewerAgent nội bộ (stateless)."""
    lf = get_langfuse_client()
    instruction = lf.get_prompt("BEE_AI_ENTERPRISES_ADK_V2:REVIEWER_AGENT_PROMPT").compile()
    
    return LlmAgent(
        name=_REVIEWER_AGENT_NAME,
        model=build_medium_model(),
        instruction=instruction,
        tools=[],
        output_schema=ReviewVerdict,
    )
