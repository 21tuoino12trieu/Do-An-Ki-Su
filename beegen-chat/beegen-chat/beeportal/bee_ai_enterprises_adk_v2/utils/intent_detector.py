# -*- coding: utf-8 -*-
import asyncio
import logging
import json
from typing import Literal
from pydantic import BaseModel
from google.genai import types
from google.adk.models.llm_request import LlmRequest

from .llm_utils import build_local_model
from .langfuse_client import get_langfuse_client
from langfuse.decorators import observe

logger = logging.getLogger(__name__)

# --- Registry quản lý Async Task/Future ---
_INTENT_FUTURES: dict[str, asyncio.Future] = {}

def get_intent_future(invocation_id: str) -> asyncio.Future:
    if invocation_id not in _INTENT_FUTURES:
        loop = asyncio.get_running_loop()
        _INTENT_FUTURES[invocation_id] = loop.create_future()
    return _INTENT_FUTURES[invocation_id]

def cleanup_intent_future(invocation_id: str) -> None:
    _INTENT_FUTURES.pop(invocation_id, None)

# --- LLM Classification ---
class IntentResult(BaseModel):
    segment: Literal["KHDN", "KHCN", "UNKNOWN"]

DEFAULT_INTENT_PROMPT = """Phân tích câu hỏi người dùng và xác định phân khúc khách hàng mục tiêu.
- KHDN: Liên quan đến khách hàng doanh nghiệp, công ty, SME, FDI, KHDNL.
- KHCN: Liên quan đến khách hàng cá nhân, retail.
- UNKNOWN: Không rõ ràng hoặc câu hỏi chung chung (áp dụng cho cả hai).
Chỉ trả về định dạng JSON."""

@observe(as_type="generation", name="IntentDetector")
async def detect_segment_llm(query: str) -> str | None:
    """Gọi Local LLM để nhận diện phân khúc KH từ câu hỏi."""
    try:
        model = build_local_model()
        
        # Load prompt từ Langfuse, fallback về default
        try:
            lf = get_langfuse_client()
            prompt = lf.get_prompt("BEE_AI_ENTERPRISES_ADK_V2:INTENT_DETECTOR_PROMPT").compile()
        except Exception:
            logger.warning("[IntentDetector] Failed to load prompt from Langfuse, using default.")
            prompt = DEFAULT_INTENT_PROMPT

        req = LlmRequest(
            contents=[
                types.Content(role="system", parts=[types.Part.from_text(text=prompt)]),
                types.Content(role="user", parts=[types.Part.from_text(text=query)])
            ],
            config=types.GenerateContentConfig(
                response_schema=IntentResult,
                response_mime_type="application/json",
                temperature=0.0
            )
        )
        
        response_text = ""
        async for chunk in model.generate_content_async(req):
            if chunk.content and chunk.content.parts:
                for part in chunk.content.parts:
                    if part.text:
                        response_text += part.text
                        
        data = json.loads(response_text)
        segment = data.get("segment", "UNKNOWN")
        return segment if segment != "UNKNOWN" else None
    except Exception as e:
        logger.error(f"[IntentDetector] Error classifying intent: {e}")
        return None
