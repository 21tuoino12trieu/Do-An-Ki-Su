import asyncio
import json
import time
import uuid
from typing import Dict, List, AsyncGenerator, Any

from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from beegenerate.llms.llm_executor import LLMExecutor
from beegenerate.storage import BotStore
from beegenerate.configs import LLMConfig, MongoConfig
from beegenerate.const import BEEGEN_ROOT

from beegenerate.loggings import LOGGER


class LLMService:
    def __init__(self):
        """Initialize LLM service with primary and alternative LLM executors."""
        bot_store = BotStore(config=MongoConfig.default())

        self._llm_semaphore = asyncio.Semaphore(15)
        self._semaphore_timeout = 30
        primary_bot_config = bot_store.fetch_bot_details(bot_id="4f338efc-95c3-4528-849b-49cd863821b5")

        self._llm = LLMExecutor(
            primary_config=primary_bot_config["llm"],  # Lấy llm config từ bot details
            config_store=bot_store
        )

        self._alt_llm = LLMExecutor(
            primary_config=LLMConfig.from_yaml_file(
                BEEGEN_ROOT / "config/llms/beegen_v1.yaml"),
            config_store=bot_store
        )

        # Primary LLM for streaming responses
        # self._alt_llm = LLMExecutor(
        #     primary_config=LLMConfig.from_yaml_file(
        #         BEEGEN_ROOT / "config/llms/azure.yaml"),
        #     config_store=bot_store
        # )

        # Alternative LLM for non-streaming tasks

        # Semaphore for rate limiting
        self._llm_semaphore = asyncio.Semaphore(15)


    def create_attached_docs(self, documents: List[Dict]) -> List[Dict]:
        """
        Tạo metadata cho tài liệu để đính kèm vào yêu cầu LLM.

        Args:
            documents: Danh sách tài liệu được cung cấp dưới dạng từ điển

        Returns:
            Danh sách các đối tượng metadata có thể đính kèm LLM
        """
        if not documents:
            return []

        attached_docs = []
        for doc in documents:
            # Xử lý trường hợp document có thể là chuỗi hoặc đối tượng
            if isinstance(doc, str):
                attached_docs.append({"id": doc})
                continue

            # Trường hợp document là đối tượng
            doc_meta = {"id": doc.get('id', doc.get('chunk_id', str(uuid.uuid4())))}

            # Thêm trường source nếu có
            if 'doc' in doc:
                doc_meta['source'] = doc['doc']
            elif 'source' in doc:
                doc_meta['source'] = doc['source']
            elif 'document_id' in doc:
                doc_meta['source'] = doc['document_id']

            attached_docs.append(doc_meta)

        return attached_docs

    async def llm_stream(
            self,
            prompt_template: str,
            inputs: Dict[str, Any] = {},
            docs: List[Dict] = None,
            buffer_size: int = 50,
            timeout: float = 60.0,  # Thời gian timeout dài hơn cho stream
            **kwargs
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Execute an LLM task with streaming mode và buffer tối ưu."""
        # Format the prompt
        formatted_prompt = prompt_template.format(**inputs) if inputs else prompt_template
        messages = [{'role': 'user', 'content': formatted_prompt}]

        # Xử lý document attachments nếu có
        attached_docs = docs

        try:
            # Sử dụng một task riêng để có thể áp dụng timeout
            async def _stream_with_timeout():
                # Cố gắng lấy semaphore với timeout riêng
                try:
                    # Đợi semaphore với timeout
                    await asyncio.wait_for(self._llm_semaphore.acquire(), timeout=10.0)

                    try:
                        # Optimize streaming with adaptive buffer
                        buffer = []
                        buffer_size_local = min(buffer_size, 100)  # Giới hạn buffer size

                        # Gọi LLM với docs nếu có
                        if attached_docs and isinstance(attached_docs, list):
                            LOGGER.debug(f"Streaming LLM with {len(attached_docs)} attached documents")
                            kwargs['docs'] = attached_docs
                            stream_generator = self._llm.run(messages=messages, **kwargs)
                        else:
                            LOGGER.debug("Streaming LLM without document attachments")
                            stream_generator = self._llm.run(messages=messages, **kwargs)

                        async for chunk in stream_generator:
                            buffer.append(chunk)

                            # Cơ chế adaptive buffering
                            if len(buffer) >= buffer_size_local:
                                for buffered_chunk in buffer:
                                    yield buffered_chunk
                                buffer.clear()

                                # Động điều chỉnh buffer size dựa trên tốc độ phản hồi
                                if 'sleep' in kwargs and kwargs['sleep'] < 0.01:
                                    buffer_size_local = min(buffer_size_local * 2, 100)
                                elif 'sleep' in kwargs and kwargs['sleep'] > 0.05:
                                    buffer_size_local = max(buffer_size_local // 2, 10)

                        # Yield any remaining chunks
                        for chunk in buffer:
                            yield chunk

                    finally:
                        # Nhớ release semaphore khi hoàn thành
                        self._llm_semaphore.release()

                except asyncio.TimeoutError:
                    LOGGER.error("Timeout waiting for LLM semaphore")
                    error_chunk = ChatCompletionChunk(
                        id="semaphore_timeout_error",
                        choices=[{
                            "index": 0,
                            "delta": {"content": "\n\nXin lỗi, hệ thống đang quá tải. Vui lòng thử lại sau ít phút."},
                            "finish_reason": None
                        }],
                        created=int(time.time())
                    )
                    yield error_chunk

            # Tạo task và áp dụng timeout
            generator = _stream_with_timeout()

            # Sử dụng asyncio.wait_for để áp dụng timeout
            # Lưu ý: Đối với generator, cần xử lý timeout trên từng item
            start_time = time.time()

            async for chunk in generator:
                # Kiểm tra nếu quá timeout
                if time.time() - start_time > timeout:
                    raise asyncio.TimeoutError("Stream timeout")

                yield chunk

        except asyncio.TimeoutError:
            LOGGER.error(f"Timeout ({timeout}s) during LLM stream execution")
            error_chunk = ChatCompletionChunk(
                id="timeout_error",
                choices=[{
                    "index": 0,
                    "delta": {
                        "content": "\n\nXin lỗi, quá trình xử lý mất nhiều thời gian hơn dự kiến. Vui lòng thử lại với câu hỏi ngắn gọn hơn."},
                    "finish_reason": "timeout"
                }],
                created=int(time.time())
            )
            yield error_chunk

        except Exception as e:
            LOGGER.error(f"Unexpected error in llm_stream: {str(e)}")
            error_chunk = ChatCompletionChunk(
                id="error",
                choices=[{
                    "index": 0,
                    "delta": {"content": "\n\nXin lỗi, đã xảy ra lỗi trong quá trình xử lý. Vui lòng thử lại."},
                    "finish_reason": "error"
                }],
                created=int(time.time())
            )
            yield error_chunk

    async def llm_task(
            self,
            inputs: Dict[str, Any],
            prompt_template: str,
            stops: List[str] = None,
            timeout: float = 30.0,
            **kwargs
    ) -> str:
        """Execute an LLM task and return complete response with timeout handling."""
        # Format the prompt
        formatted_prompt = prompt_template.format(**inputs) if inputs else prompt_template
        messages = [{'role': 'user', 'content': formatted_prompt}]

        try:
            # Sử dụng asyncio.wait_for thay cho asyncio.timeout
            async def _process_task():
                # Sử dụng semaphore để giới hạn số lượng cuộc gọi đồng thời
                try:
                    # Cố gắng lấy semaphore với timeout riêng
                    semaphore_acquire = asyncio.wait_for(self._llm_semaphore.acquire(), timeout=10.0)
                    await semaphore_acquire

                    try:
                        # Non-stream mode: collect response efficiently
                        content_chunks = []
                        try:
                            async for chunk in self._alt_llm.run(messages=messages, **kwargs):
                                if chunk.choices and (content := chunk.choices[0].delta.content):
                                    if stops and content in stops:
                                        return ''.join(content_chunks)
                                    content_chunks.append(content)
                        except Exception as e:
                            LOGGER.error(f"Error during LLM task execution: {e}")
                            raise

                        # Join all content chunks
                        return ''.join(content_chunks)
                    finally:
                        # Nhớ release semaphore khi hoàn thành
                        self._llm_semaphore.release()

                except asyncio.TimeoutError:
                    LOGGER.error("Timeout waiting for LLM semaphore")
                    return "Xin lỗi, hệ thống đang quá tải. Vui lòng thử lại sau ít phút."

            # Sử dụng timeout cho toàn bộ quá trình
            return await asyncio.wait_for(_process_task(), timeout=timeout)

        except asyncio.TimeoutError:
            LOGGER.error(f"Timeout ({timeout}s) during LLM task execution")
            return "Xin lỗi, quá trình xử lý mất nhiều thời gian hơn dự kiến. Vui lòng thử lại với câu hỏi ngắn gọn hơn."

