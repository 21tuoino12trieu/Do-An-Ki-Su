import asyncio
import json
import uuid
from typing import Dict, List, AsyncGenerator, Any

from openai import AsyncOpenAI
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from beechat.config import load_settings
from beegenerate.loggings import LOGGER
from langfuse.decorators import observe, langfuse_context
from langfuse.model import PromptClient


_PRIORITY_HEADERS = {
    "X-Vertex-AI-LLM-Request-Type": "shared",
    "X-Vertex-AI-LLM-Shared-Request-Type": "priority"
}


class LLMService:
    def __init__(self, bot_id: str = "default"):
        """Initialize LLM service with direct LiteLLM Gateway connection."""
        self.bot_id = bot_id
        settings = load_settings()
        
        base_url = settings.openai_base_url.rstrip('/')
        if not base_url.endswith('/v1'):
            base_url = f"{base_url}/v1"

        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=settings.openai_api_key,
            default_headers=_PRIORITY_HEADERS,
            timeout=30.0
        )
        self.heavy_model = settings.heavy_model
        self.light_model = settings.light_model
        LOGGER.info(f"Initialized LLMService with base_url={base_url}, heavy={self.heavy_model}, light={self.light_model}")

    @observe()
    def create_attached_docs(self, documents: List[Dict]) -> List[Dict]:
        """Tạo metadata cho tài liệu để đính kèm vào yêu cầu LLM."""
        if not documents:
            return []

        attached_docs = []
        for doc in documents:
            if isinstance(doc, str):
                attached_docs.append({"id": doc})
                continue

            doc_meta = {"id": doc.get('id', doc.get('chunk_id', str(uuid.uuid4())))}

            if 'doc' in doc:
                doc_meta['source'] = doc['doc']
            elif 'source' in doc:
                doc_meta['source'] = doc['source']
            elif 'document_id' in doc:
                doc_meta['source'] = doc['document_id']

            attached_docs.append(doc_meta)

        return attached_docs

    @observe(as_type="generation")
    async def llm_stream(
            self,
            prompt_template: Any,
            inputs: Dict[str, Any] = None,
            docs: List[Dict] = None,
            buffer_size: int = 50,
            model: str = None,
            **kwargs
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Execute heavy LLM task with streaming mode using litellm_proxy/gemini-3.6-flash."""
        if inputs is None:
            inputs = {}

        selected_model = model or self.heavy_model

        if isinstance(prompt_template, PromptClient):
            formatted_prompt = prompt_template.compile(**inputs) if inputs else prompt_template.prompt
            langfuse_context.update_current_observation(prompt=prompt_template)
        elif isinstance(prompt_template, str):
            formatted_prompt = prompt_template.format(**inputs) if inputs else prompt_template
        else:
            formatted_prompt = str(prompt_template)

        messages = [{'role': 'user', 'content': formatted_prompt}]

        LOGGER.info(f"[LLM Stream] Direct LiteLLM call | Model: {selected_model} | Input length: {len(formatted_prompt)}")
        LOGGER.debug(f"Input Prompt: {formatted_prompt[:200]}...")

        langfuse_context.update_current_observation(
            input=messages,
            model=selected_model,
            metadata={"docs": docs, "inputs": inputs}
        )

        final_response_chunks = []
        try:
            extra_params = {}
            if 'temperature' in kwargs:
                extra_params['temperature'] = kwargs['temperature']
            if 'max_tokens' in kwargs:
                extra_params['max_tokens'] = kwargs['max_tokens']
            if 'stop' in kwargs:
                extra_params['stop'] = kwargs['stop']

            response_stream = await self.client.chat.completions.create(
                model=selected_model,
                messages=messages,
                stream=True,
                **extra_params
            )

            async for chunk in response_stream:
                if hasattr(chunk, 'choices') and chunk.choices:
                    if chunk.choices[0].delta and chunk.choices[0].delta.content:
                        final_response_chunks.append(chunk.choices[0].delta.content)
                yield chunk

        except Exception as e:
            LOGGER.error(f"[LLM Stream Error] Model: '{selected_model}' | Base URL: {self.client.base_url} | Error: {e}", exc_info=True)
            raise e
        finally:
            full_text = "".join(final_response_chunks)
            LOGGER.info(f"[LLM Stream Finish] Output length: {len(full_text)} chars")
            langfuse_context.update_current_observation(output=full_text)

    @observe(as_type="generation")
    async def llm_task(
            self,
            inputs: Dict[str, Any] = None,
            prompt_template: Any = None,
            stops: List[str] = None,
            use_primary: bool = False,
            model: str = None,
            **kwargs
    ) -> str:
        """Execute light LLM task returning complete string using gemini-3.5-flash-lite."""
        if inputs is None:
            inputs = {}

        selected_model = model or self.light_model

        if isinstance(prompt_template, PromptClient):
            formatted_prompt = prompt_template.compile(**inputs) if inputs else prompt_template.prompt
            langfuse_context.update_current_observation(prompt=prompt_template)
        elif isinstance(prompt_template, str):
            formatted_prompt = prompt_template.format(**inputs) if inputs else prompt_template
        else:
            formatted_prompt = str(prompt_template) if prompt_template else ""

        messages = [{'role': 'user', 'content': formatted_prompt}]

        LOGGER.info(f"[LLM Task] Direct LiteLLM call | Model: {selected_model} | Input length: {len(formatted_prompt)}")
        LOGGER.debug(f"Input Prompt: {formatted_prompt[:200]}...")

        langfuse_context.update_current_observation(
            input=messages,
            model=selected_model,
            metadata={"inputs": inputs, "stops": stops}
        )

        try:
            extra_params = {}
            if stops:
                extra_params['stop'] = stops
            if 'temperature' in kwargs:
                extra_params['temperature'] = kwargs['temperature']
            if 'max_tokens' in kwargs:
                extra_params['max_tokens'] = kwargs['max_tokens']

            response = await self.client.chat.completions.create(
                model=selected_model,
                messages=messages,
                stream=False,
                **extra_params
            )

            result_text = response.choices[0].message.content or ""
            LOGGER.info(f"[LLM Task Finish] Output length: {len(result_text)} chars | Preview: {result_text[:100]}...")
            langfuse_context.update_current_observation(output=result_text)
            return result_text

        except Exception as e:
            LOGGER.error(f"[LLM Task Error] Model: '{selected_model}' | Base URL: {self.client.base_url} | Error: {e}", exc_info=True)
            return "Xin lỗi, hệ thống đang gặp sự cố. Vui lòng thử lại sau."


async def main():
    import sys
    sys.stdout.reconfigure(encoding='utf-8')

    print("==================================================")
    print(" TESTING LLM SERVICE (DIRECT LITELLM GATEWAY)")
    print("==================================================")

    llm_service = LLMService(bot_id="test_bot")

    print("\n--- 1. Testing Light Task (llm_task - gemini-3.5-flash-lite) ---")
    prompt_task = "Hãy cho biết 3 lợi ích chính của thẻ tín dụng MB Bank trong 2 câu ngắn gọn."
    print(f"Prompt: '{prompt_task}'")
    task_res = await llm_service.llm_task(prompt_template=prompt_task)
    print(f"Response: {task_res}")

    print("\n--- 2. Testing Streaming Heavy Task (llm_stream - gemini-3.6-flash) ---")
    prompt_stream = "Xin chào Bee! Bạn có thể giới thiệu ngắn gọn về ngân hàng MB Bank không?"
    print(f"Prompt: '{prompt_stream}'")
    print("Streaming output: ", end="", flush=True)
    async for chunk in llm_service.llm_stream(prompt_template=prompt_stream):
        if hasattr(chunk, 'choices') and chunk.choices and chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="", flush=True)
    print("\n\n LLM Service Test Complete!")


if __name__ == "__main__":
    asyncio.run(main())
