# -*- coding: utf-8 -*-
"""Build MainAgent (LlmAgent) cho Bee AI Enterprises ADK."""
from __future__ import annotations

import logging
import threading
from google.adk.agents import LlmAgent
from typing import Any, Optional
from google.adk.tools.tool_context import ToolContext

from ..utils.llm_utils import build_medium_model
from ..utils.langfuse_client import get_langfuse_client
from ..tools import (
    search_forms_tool, 
    search_documents_tool, 
    search_qna_tool,
    search_documents_by_name_tool,
    initialize_retrieval_nodes_sync,
)
from ..utils.const import MINIMAL_BUILTIN_THINKING
from ..core.schemas import MainVerdict
import re
import unicodedata
from ..utils.intent_detector import get_intent_future
from ..tools.retrieval_tools import _format_docs

logger = logging.getLogger(__name__)

_MAIN_AGENT_NAME = "ENTERPRISES_MAIN_AGENT"

# ---------------------------------------------------------------------------
# Module-level tool call counter (thread-safe)
# Orchestrator sẽ gọi reset_tool_counter() trước mỗi iteration.
# ---------------------------------------------------------------------------
_MAX_TOOL_CALLS = 6

def limit_tool_loop_callback(
    tool: Any,
    args: dict[str, Any],
    tool_context: ToolContext,
    tool_response: dict,
) -> Optional[dict]:
    # Use session.state to avoid concurrency issues with global variables
    current = tool_context.session.state.get("tool_call_count", 0) + 1
    tool_context.session.state["tool_call_count"] = current

    logger.debug("[ToolCounter] Tool '%s' called, count=%d/%d",
                 getattr(tool, "name", "?"), current, _MAX_TOOL_CALLS)

    if current > _MAX_TOOL_CALLS:
        return {
            "SYSTEM_ALERT": (
                f"BẠN ĐÃ ĐẠT GIỚI HẠN GỌI TOOL (TỐI ĐA {_MAX_TOOL_CALLS} LẦN). "
                "DỮ LIỆU ĐÃ CẠN KIỆT. BẠN PHẢI DỪNG LẠI NGAY LẬP TỨC "
                "VÀ TRẢ LỜI NGƯỜI DÙNG VỚI THÔNG TIN ĐÃ CÓ. "
                "TUYỆT ĐỐI KHÔNG GỌI THÊM TOOL NÀO NỮA."
            )
        }
    return None


def _remove_vn_accents(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'[đĐ]', 'd', text)
    return ''.join(c for c in unicodedata.normalize('NFD', text)
                   if unicodedata.category(c) != 'Mn')

_KHCN_KEYWORDS = [
    r"khcn",
    r"khach hang ca nhan"
]
_KHDN_KEYWORDS = [
    r"khdn",
    r"sme",
    r"khach hang doanh nghiep"
]

_KHCN_DOC_MARKER = re.compile(r'|'.join(_KHCN_KEYWORDS), re.IGNORECASE)
_KHDN_DOC_MARKER = re.compile(r'|'.join(_KHDN_KEYWORDS), re.IGNORECASE)

async def segment_filter_callback(
    tool: Any,
    args: dict[str, Any],
    tool_context: ToolContext,
    tool_response: dict,
) -> Optional[dict]:
    # Lấy intent future từ registry (được ghi bởi IntentDetectionNode)
    future = get_intent_future(tool_context.invocation_id)

    # Await kết quả nhận diện
    intent = await future
    if not intent:
        return None

    docs = tool_response.get("docs", [])
    if not docs:
        return None
        
    logger.info("[SegmentFilter] Bắt được Intent: %s. Đang quét %d tài liệu trả về từ %s", intent, len(docs), tool.name if hasattr(tool, "name") else "tool")

    filtered_docs = []
    for doc in docs:
        title = doc.get("title", "")
        normalized_title = _remove_vn_accents(title)

        is_khcn_doc = bool(_KHCN_DOC_MARKER.search(normalized_title))
        is_khdn_doc = bool(_KHDN_DOC_MARKER.search(normalized_title))

        if intent == "KHDN" and is_khcn_doc and not is_khdn_doc:
            continue
        elif intent == "KHCN" and is_khdn_doc and not is_khcn_doc:
            continue
        filtered_docs.append(doc)

    if len(filtered_docs) < len(docs):
        removed = len(docs) - len(filtered_docs)
        logger.info("[SegmentFilter] Xóa %d tài liệu sai phân khúc (Intent: %s)", removed, intent)
        tool_response["docs"] = filtered_docs
        
        # Cập nhật lại chuỗi văn bản cho LLM đọc
        source_type = tool_response.get("source_type", "raw")
        tool_response["evidence_text"] = _format_docs(filtered_docs, source_type)
        return tool_response

    return None


def build_main_agent(*, has_review: bool = False) -> LlmAgent:
    """Tạo MainAgent với 3 GCP retrieval tools.

    Args:
        has_review: Khi True, MainAgent trả về structured ``MainVerdict``
            (có ``needs_review`` flag) để Reviewer duyệt, dùng prompt có
            output format JSON.
            Khi False (default), bỏ output_schema → trả plain text, dùng
            prompt không có structured output.
    """
    initialize_retrieval_nodes_sync()
    
    lf = get_langfuse_client()
    prompt_name = (
        "BEE_AI_ENTERPRISES_ADK_V2:REACT_AGENT_PROMPT"
        if has_review
        else "BEE_AI_ENTERPRISES_ADK_V2:REACT_AGENT_PROMPT_NO_REVIEW"
    )
    prompt_obj = lf.get_prompt(prompt_name)
    instruction = prompt_obj.compile()
    
    return LlmAgent(
        name=_MAIN_AGENT_NAME,
        model=build_medium_model(enable_minimal_thinking=True),
        instruction=instruction,
        planner=MINIMAL_BUILTIN_THINKING,
        tools=[
            search_forms_tool,
            search_documents_tool,
            search_documents_by_name_tool,
            search_qna_tool,
        ],
        output_schema=MainVerdict if has_review else None,
        after_tool_callback=[limit_tool_loop_callback, segment_filter_callback],
    )

