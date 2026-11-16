from typing import AsyncGenerator

from openai.types.chat import ChatCompletionChunk


async def stream_error_message(llm_service, message: str) -> AsyncGenerator[ChatCompletionChunk, None]:
    """Stream error message using LLM service."""
    error_prompt = f"""
    Vai trò: Bạn là Bee - trợ lý ảo của MB Bank

    Nhiệm vụ: Thông báo lỗi cho người dùng

    Thông báo cần truyền tải: "{message}"

    Hãy đưa ra thông báo một cách ngắn gọn, thân thiện và lịch sự. Không thêm giải thích nào khác.
    """

    async for chunk in llm_service.llm_stream(
            prompt_template=error_prompt,
            sleep=0.01
    ):
        yield chunk