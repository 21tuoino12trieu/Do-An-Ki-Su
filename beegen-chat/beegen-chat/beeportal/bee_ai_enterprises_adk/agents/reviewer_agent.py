# -*- coding: utf-8 -*-
"""Build ReviewerAgent (internal, stateless) cho Bee AI Enterprises ADK.

Refactored: Reviewer LlmAgent được build per-call với compiled instruction
(align theo Langfuse prompt design — 5 template variables nhúng vào instruction).
"""
from __future__ import annotations

import json
import logging
import re
import typing
import html
from typing import Literal

from langfuse.decorators import observe
from pydantic import BaseModel, Field

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from google.adk.models.llm_request import LlmRequest
from google.adk.agents.callback_context import CallbackContext

from ..utils.llm_utils import build_litellm_model
from ..prompts.reviewer_agent import get_reviewer_prompt_template
from ..constants import MAX_REVIEW_ITERATIONS

logger = logging.getLogger(__name__)

_REVIEWER_AGENT_NAME = "ENTERPRISES_REVIEWER_AGENT"

# ---------------------------------------------------------------------------
# Pydantic schema cho output của ReviewerAgent
# ---------------------------------------------------------------------------

class ReviewerResponse(BaseModel):
    status: Literal["PASS", "REVISE", "ASK_BACK"]
    supported_claims: str = Field(default="")
    unsupported_claims: str = Field(default="")
    issues: str = Field(default="")
    recommendations: str = Field(default="")
    ask_back_question: str | None = Field(default=None)


def _reviewer_before_model_callback(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> None:
    user_query = callback_context.state.get("original_user_query", "")
    agent_answer = callback_context.state.get("draft_answer", "")

    evidence_list = callback_context.state.get("retrieval_evidence", [])
    if isinstance(evidence_list, str):
        reasoning_draft = evidence_list
    else:
        evidence_parts = []
        for ev in evidence_list:
            part = f"Tool: {ev.get('tool_name')}\nQuery: {ev.get('query')}\nSuccess: {ev.get('success')}\nContent: {ev.get('content')}"
            evidence_parts.append(part)
        reasoning_draft = "\n---\n".join(evidence_parts) if evidence_parts else "No evidence provided."

    iteration = callback_context.state.get("review_iteration", 0)

    payload = f"""<review_input>
  <user_query>{html.escape(user_query)}</user_query>
  <draft>{html.escape(agent_answer)}</draft>
  <evidence>{html.escape(reasoning_draft)}</evidence>
  <iteration>{iteration}/{MAX_REVIEW_ITERATIONS}</iteration>
</review_input>"""

    # Append as user message
    llm_request.contents.append(types.Content(role="user", parts=[types.Part.from_text(text=payload)]))

def _create_reviewer_agent(instruction: str) -> LlmAgent:
    """Tạo ReviewerAgent dùng chung cấu hình."""
    return LlmAgent(
        name=_REVIEWER_AGENT_NAME,
        model=build_litellm_model(),
        instruction=instruction,
        output_schema=ReviewerResponse,
        include_contents="none",
        tools=[],
        before_model_callback=_reviewer_before_model_callback
    )

from google.adk.sessions import InMemorySessionService, BaseSessionService

@observe(name="run_reviewer", capture_output=False)
async def run_reviewer(
    user_query: str,
    agent_answer: str,
    reasoning_draft: str,
    iteration: int,
    max_iteration: int,
    session_service: BaseSessionService | None = None,
) -> ReviewerResponse:
    reviewer_agent = _create_reviewer_agent(instruction=get_reviewer_prompt_template())

    if session_service is None:
        session_service = InMemorySessionService()
        
    runner = Runner(
        agent=reviewer_agent,
        app_name="bee_ai_enterprises_reviewer",
        session_service=session_service,
        auto_create_session=True,
    )

    session_id = f"review_session_{id(runner)}"
    await session_service.create_session(
        app_name="bee_ai_enterprises_reviewer",
        user_id="reviewer_internal",
        session_id=session_id,
        state={
            "original_user_query": user_query,
            "draft_answer": agent_answer,
            "retrieval_evidence": reasoning_draft,
            "review_iteration": iteration,
        }
    )

    final_text = ""
    try:
        async for event in runner.run_async(
            user_id="reviewer_internal",
            session_id=session_id,
            new_message=types.Content(
                role="user",
                parts=[types.Part.from_text(text="Vui lòng thực hiện đánh giá.")],
            )
        ):
            if event.content and event.content.role == "model":
                for part in event.content.parts:
                    if part.text:
                        final_text += part.text

        logger.info("[Reviewer] output raw:\n%s", final_text)
        if not final_text.strip():
            logger.warning("[Reviewer] không trả về nội dung nào.")
            return ReviewerResponse(
                status="REVISE",
                recommendations="Reviewer không trả lời. Cần thử lại.",
                ask_back_question=None
            )

        return ReviewerResponse.model_validate_json(final_text)

    except Exception as e:
        logger.exception("[Reviewer] lỗi parse output")
        return ReviewerResponse(
            status="REVISE",
            recommendations=f"Lỗi Reviewer format (không phải JSON hợp lệ): {e}",
            ask_back_question=None
        )
