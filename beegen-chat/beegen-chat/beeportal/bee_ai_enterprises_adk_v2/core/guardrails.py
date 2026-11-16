import logging
import os
import json
from pydantic import BaseModel
from typing import Literal

from langfuse.decorators import observe

from google.genai import types
from google.adk.models.lite_llm import LiteLlm

from ..utils.llm_utils import build_small_model

logger = logging.getLogger(__name__)

class ContentFilterResult(BaseModel):
    category: Literal["none", "0", "1", "2", "3", "4", "5", "6", "7", "8"]


REFUSAL_REASON = {
    0: "Tấn công & Thao túng Hệ thống AI (Prompt Injection)",
    1: "Bạo lực / Tội phạm / Chất cấm",
    2: "Tự gây hại / Tự tử",
    3: "Nội dung tình dục / Khiêu dâm",
    4: "Chính trị / Nhạy cảm xã hội",
    5: "Ngôn ngữ xúc phạm / Thô tục",
    6: "Cờ bạc / Cá độ",
    7: "Mê tín / Bói toán / Trục lợi tâm linh",
    8: "Truy cập / Khai thác Dữ liệu Nội bộ Nhạy cảm hoặc Hạn chế (Data Leakage)"
}

REFUSAL_MESSAGES = {
    0: "Xin lỗi, tôi không thể thực hiện yêu cầu này. Tôi chỉ hỗ trợ tra cứu thông tin nghiệp vụ và sản phẩm nội bộ của MB Bank.",
    1: "Xin lỗi, tôi không thể hỗ trợ các nội dung vi phạm pháp luật hoặc bạo lực.",
    2: "Tôi nhận thấy nội dung câu hỏi có dấu hiệu gây hại. Xin hãy liên hệ với các đường dây hỗ trợ y tế hoặc người thân.",
    3: "Xin lỗi, tôi không thể hỗ trợ nội dung này.",
    4: "Xin lỗi, tôi không thảo luận về các chủ đề chính trị, tôn giáo hay các vấn đề nhạy cảm xã hội.",
    5: "Xin lỗi, hệ thống không thể xử lý các câu hỏi chứa ngôn từ không phù hợp.",
    6: "Xin lỗi, tôi không thể hỗ trợ các nội dung liên quan đến cờ bạc hoặc cá cược.",
    7: "Xin lỗi, tôi không thể hỗ trợ các nội dung liên quan đến mê tín dị đoan hoặc bói toán.",
    8: "Xin lỗi, tôi chỉ hỗ trợ tra cứu các tài liệu nghiệp vụ, quy trình và chính sách nội bộ được ban hành chính thức trong phạm vi hệ thống dữ liệu của MB. Tôi không được phép cung cấp hoặc tra cứu các thông tin mật, nhạy cảm hay các tài liệu chưa được công bố ra bên ngoài."
}

from ..utils.langfuse_client import get_langfuse_client

async def input_content_filter_guardrail(user_query: str, model_name: str, session_id: str = None, user_id: str = None, history: list = None) -> dict:
    """
    Quét nội dung người dùng để phát hiện vi phạm và prompt injection.
    Sử dụng ADK LiteLlm thay vì OpenAI client trực tiếp.
    """
    lf = get_langfuse_client()
    system_prompt = lf.get_prompt("BEE_AI_ENTERPRISES_ADK_V2:INPUT_GUARDRAILS_AGENT_PROMPT").compile()
    
    from google.adk.models.llm_request import LlmRequest
    try:
        model: LiteLlm = build_small_model()
        
        contents = [
            types.Content(role="system", parts=[types.Part.from_text(text=system_prompt)]),
        ]
        if history:
            for turn in history:
                if turn.role == "user" and turn.text:
                    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=turn.text)]))
                elif turn.role == "assistant" and turn.text:
                    contents.append(types.Content(role="model", parts=[types.Part.from_text(text=turn.text)]))
        
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=f'câu hỏi: "{user_query}"')]))

        
        req = LlmRequest(
            contents=contents,
            config=types.GenerateContentConfig(
                response_schema=ContentFilterResult,
                response_mime_type="application/json",
                temperature=0.0,
            )
        )
        
        response_text = ""
        async for chunk in model.generate_content_async(req):
            if chunk.content and chunk.content.parts:
                for part in chunk.content.parts:
                    if part.text:
                        response_text += part.text
        
        logger.info(f"[Guardrail] Response: {response_text}")
        
        # Parse JSON
        parsed_data = json.loads(response_text)
        category = str(parsed_data.get("category", "none"))
        
        if category != "none":
            cat_int = int(category) if category.isdigit() else 8
            result = {
                "guardrail_trigger_route": category,
                "reason": REFUSAL_REASON.get(cat_int, REFUSAL_REASON[8]),
                "message": REFUSAL_MESSAGES.get(cat_int, REFUSAL_MESSAGES[8]),
                "model_name": model_name,
                "prompt": system_prompt
            }
            logger.info("[Guardrail] Triggered category: %s", category)
        else:
            result = {
                "guardrail_trigger_route": "none",
                "reason": "none",
                "message": "Tin nhắn hợp lệ",
                "model_name": model_name,
                "prompt": system_prompt
            }
            
        return result
        
    except Exception as e:
        logger.error(f"[Guardrail] Error during evaluation: {e}")
        return {
            "guardrail_trigger_route": "8",
            "reason": REFUSAL_REASON[8],
            "message": REFUSAL_MESSAGES[8],
            "model_name": model_name,
            "prompt": system_prompt,
            "error": str(e)
        }
