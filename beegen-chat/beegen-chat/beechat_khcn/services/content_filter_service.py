import re
import json
import time
from typing import Dict, List, Optional, AsyncGenerator, Any

from beechat.services.llm_service import LLMService
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from beechat_khcn.prompts import CONTENT_FILTER_PROMPT, REFUSAL_MESSAGES
from beegenerate.loggings import LOGGER
from beegenerate.loggings.loggers import lf


class ContentFilterService:
    """
    Service phân tích và lọc nội dung không phù hợp từ tin nhắn người dùng.
    Đảm bảo hệ thống phản hồi tin nhắn phù hợp với chính sách của MB Bank.
    """

    def __init__(self, llm_service: LLMService):
        """
        Khởi tạo service với LLM service cần thiết.

        Args:
            llm_service: LLM service để thực hiện phân tích nội dung
        """
        self.llm_service = llm_service

    async def check_content(self, query: str, user_info: Optional[Dict] = None, is_clarification: bool = False) -> Dict:
        """
        Kiểm tra nội dung của tin nhắn người dùng có phù hợp không, sử dụng LLM.

        Args:
            query: Nội dung tin nhắn cần kiểm tra
            user_info: Thông tin người dùng (nếu có) để phân tích ngữ cảnh
            is_clarification: True nếu đây là tin nhắn làm rõ yêu cầu trước đó

        Returns:
            Dict chứa kết quả kiểm tra với các trường:
            - filter_needed: "yes" hoặc "no"
            - filter_type: Loại lọc (1, 2, 3, 4, 5 hoặc "none")
        """
        try:
            # Gọi LLM với prompt để phân tích
            response = await self.llm_service.llm_task(
                inputs={"query": query},
                prompt_template=lf.get_prompt("BEECHAT_KHCN_CONTENT_FILTER_PROMPT"),
                use_primary=False,
                stream=False
            )

            # Parse response đơn giản
            filter_type = self._parse_filter_response(response)

            # Tạo kết quả
            if filter_type in ['1', '2', '3', '4', '5', '6', '7']:
                result = {
                    "filter_needed": "yes",
                    "filter_type": filter_type
                }
            else:
                result = {
                    "filter_needed": "no",
                    "filter_type": "none"
                }

            # Xử lý đặc biệt cho câu hỏi về khả năng bot
            if self._is_bot_capability_query(query) and result["filter_type"] == "1":
                result["filter_needed"] = "no"
                result["filter_type"] = "none"
                LOGGER.info(f"Bot capability query detected, allowing: {query[:50]}...")

            LOGGER.debug(f"Content filter result: {result} for query: {query[:50]}...")
            return result

        except Exception as e:
            LOGGER.error(f"Error in content filtering: {str(e)}")
            # Mặc định cho phép nếu có lỗi
            return {
                "filter_needed": "no",
                "filter_type": "none"
            }

    def _parse_filter_response(self, response: str) -> str:
        """Parse response từ LLM với support cho 7 filter types"""
        cleaned = response.strip().lower()

        # Direct match cho 7 loại
        if cleaned in ['none', '1', '2', '3', '4', '5', '6', '7']:
            return cleaned

        # Fallback: tìm số trong response (1-7)
        numbers = re.findall(r'[1-7]', cleaned)
        if numbers:
            return numbers[0]

        # Tìm 'none' trong response
        if 'none' in cleaned:
            return 'none'

        # Default: none (cho phép)
        LOGGER.warning(f"Could not parse filter response: {response[:100]}..., defaulting to 'none'")
        return 'none'

    def _is_bot_capability_query(self, query: str) -> bool:
        """
        Kiểm tra câu hỏi về khả năng bot.

        Args:
            query: Câu hỏi người dùng

        Returns:
            True nếu là câu hỏi về khả năng bot
        """
        bot_capability_terms = ["khả năng", "chức năng", "làm được gì", "giúp được gì", "hỗ trợ gì"]
        query_lower = query.lower()
        return any(term in query_lower for term in bot_capability_terms)

    def get_refusal_message(self, filter_type: str) -> str:
        """
        Lấy thông báo từ chối phù hợp với loại nội dung đã lọc.

        Args:
            filter_type: Loại lọc (1, 2, 3, 4, 5 hoặc "none")

        Returns:
            Thông báo từ chối phù hợp
        """
        return REFUSAL_MESSAGES.get(
            filter_type,
            "Xin lỗi, Mister Bụt chưa nắm được mong muốn của bạn. Bạn vui lòng mô tả cụ thể hơn được không, Mister Bụt rất sẵn lòng "
            "hỗ trợ! "
        )

    async def create_refusal_response(self, filter_type: str) -> AsyncGenerator[ChatCompletionChunk, None]:
        """
        Tạo phản hồi từ chối với status code 400 như complaint handler.

        Args:
            filter_type: Loại filter (1, 2, 3, 4, 5)

        Yields:
            ChatCompletionChunk với status_code 400
        """
        # Lấy thông báo từ chối
        message = self.get_refusal_message(filter_type)

        # Tạo prompt cho refusal response
        refusal_prompt = f"""
        Vai trò: Bee - trợ lý ảo ngân hàng MB

        Nhiệm vụ: Thông báo từ chối trả lời câu hỏi không phù hợp

        Thông báo cần truyền tải: "{message}"

        Hướng dẫn:
        - Trả lời CHÍNH XÁC nội dung thông báo
        - Giữ nguyên ý nghĩa và giọng điệu thân thiện
        - KHÔNG thêm thắt hoặc giải thích thêm
        - KHÔNG đề cập đến lý do lọc nội dung
        """

        # Stream response và gắn status code 400 vào mỗi chunk
        async for chunk in self.llm_service.llm_stream(
                prompt_template=refusal_prompt,
                sleep=0.01
        ):
            # Gắn status code 400 vào mỗi chunk như complaint handler
            chunk_dict = chunk.model_dump()
            chunk_dict["status_code"] = 200
            chunk_dict["status_message"] = "Success!"
            modified_chunk = ChatCompletionChunk(**chunk_dict)

            yield modified_chunk
