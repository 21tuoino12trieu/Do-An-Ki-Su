import json
import math
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from openai.types.chat.chat_completion import ChatCompletion
from typing import Any, Callable, Dict, List, AsyncGenerator, Optional, Sequence, Tuple, Union
from .base_llm import BaseLLM
from beegen.configs import OpenAIConfig
import httpx
import asyncio
import os

# Before importing OpenAI, add this:
import openai._base_client
openai._base_client.get_platform = lambda: "Windows"


# Set proxy bypass for internal services
# os.environ['NO_PROXY'] = 'llm-gateway-dev.mbbank.com.vn,10.1.47.71,10.1.13.168'
os.environ['NO_PROXY'] = 'llm-gateway-dev.mbbank.com.vn'


class OpenAISDKModel(BaseLLM):
    """OpenAI model (SDK) with tool calls and multimodal support."""
    
    def __init__(self, config: OpenAIConfig):
        super().__init__(config)
        
        # Configure HTTP client with timeout and no SSL verification
        self.http_client = httpx.AsyncClient(
            verify=False,
            timeout=httpx.Timeout(
                connect=10.0,
                read=1200.0,
                write=10.0,
                pool=5.0
            ),
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=10
            )
        )
        
        # Initialize OpenAI client
        if hasattr(config, 'base_url'):
            self.client = AsyncOpenAI(
                base_url=config.base_url,
                api_key=config.api_key,
                http_client=self.http_client
            )

        self.model = config.model
    
    def sanitize_for_gpt5(self, params, generate=False):
        # Azure GPT-5 unsupported params
        # UNSUPPORTED = {"top_p", "frequency_penalty", "presence_penalty", "temperature", "docs", "top_k", "repetition_penalty", "status_code", "chat_template_kwargs", "stop_sequences", "safety_settings", "content_filter_level", "retry_delay", "custom_data"}
        UNSUPPORTED = {"top_k", "status_code", "custom_data", "docs", "repetition_penalty", "chat_template_kwargs", "stop_sequences", "safety_settings", "content_filter_level", "retry_delay", ""}

        if generate:
            UNSUPPORTED.add("stream_options")

        if self.model.startswith("gpt-5") or "gpt-5" in self.model:
            for key in UNSUPPORTED:
                params.pop(key, None)
                params.get("extra_body").pop(key, None)
        
        return params

    async def stream(
        self,
        messages: List[ChatCompletionMessageParam],
        temperature: float = 0.0,
        top_p: float = 0.1,
        n: Optional[int] = None,
        stop: Optional[Union[str, Sequence[str]]] = None,
        max_tokens: Optional[int] = None,
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        response_format: Optional[dict] = None,
        tools: Optional[dict] = None,
        **kwargs
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """
        Stream chat completion responses with Chinese character filtering.
        
        Processes messages to handle local image paths, then streams responses
        from the OpenAI-compatible API. Automatically raises an exception if
        any response chunk contains Chinese characters.
        
        Args:
            messages: List of chat messages to process in the conversation
            temperature: Controls randomness in response generation (0.0-2.0). 
                        Lower values make output more focused and deterministic.
            top_p: Controls diversity via nucleus sampling (0.0-1.0). 
                Only tokens with top_p probability mass are considered.
            n: Number of chat completion choices to generate for each input message.
                Only the first choice is typically used in streaming.
            stop: Up to 4 sequences where the API will stop generating further tokens.
                Can be a string or list of strings.
            max_tokens: Maximum number of tokens to generate in the chat completion.
                    Total length is limited by model's context length.
            frequency_penalty: Penalizes new tokens based on their existing frequency 
                            in the text so far (-2.0 to 2.0).
            presence_penalty: Penalizes new tokens based on whether they appear 
                            in the text so far (-2.0 to 2.0).
            response_format: Object specifying the format that the model must output.
                            Compatible with GPT-4 Turbo and gpt-3.5-turbo-1106.
            **kwargs: Additional streaming options specific to the implementation
            
        Returns:
            AsyncGenerator yielding ChatCompletionChunk objects containing partial 
                response data as it becomes available
            
        Raises:
            ValueError: If any response chunk contains Chinese characters
            
        Note:
            - Local image file paths are automatically converted to base64 data URLs
            - Chinese character detection covers CJK Unified Ideographs (U+4E00-U+9FFF)
        """
        # Prepare parameters
        params = self._prepare_params(
            model=self.config.model,
            messages=messages,
            stream=True,
            temperature=temperature,
            top_p=top_p,
            n=n,
            stop=stop,
            max_tokens=max_tokens,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            response_format=response_format,
            tools=tools,
            extra_body=kwargs
        )

        params = self.sanitize_for_gpt5(params)    
        sleep = kwargs.pop("sleep", 0.0)

        client = self.client.with_options(
            max_retries=params.get("extra_body", {}).get("max_retries", 1)
        )
        stream_response = await client.chat.completions.create(**params)

        async for chunk in stream_response:
            if not self.check_chinese_characters(chunk, raise_on_found=False):
                # Update kwargs onto chunk
                for key, value in kwargs.items():
                    setattr(chunk, key, value)
                await asyncio.sleep(sleep)
                
                yield chunk
            
    async def generate(
        self,
        messages: List[ChatCompletionMessageParam],
        temperature: float = 0.0,
        top_p: float = 0.1,
        n: Optional[int] = None,
        stop: Optional[Union[str, Sequence[str]]] = None,
        max_tokens: Optional[int] = None,
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        response_format: Optional[dict] = None,
        tools: Optional[dict] = None,
        **kwargs
    ) -> ChatCompletion:
        """
        Generate a complete chat completion response with Chinese character filtering.
        
        Processes messages to handle local image paths, then generates a complete
        response from the OpenAI-compatible API. Automatically raises an exception
        if the response contains Chinese characters.
        
        Args:
            messages: List of chat messages to process in the conversation
            temperature: Controls randomness in response generation (0.0-2.0). 
                        Lower values make output more focused and deterministic.
            top_p: Controls diversity via nucleus sampling (0.0-1.0). 
                Only tokens with top_p probability mass are considered.
            n: Number of chat completion choices to generate for each input message.
                Only the first choice is typically used in streaming.
            stop: Up to 4 sequences where the API will stop generating further tokens.
                Can be a string or list of strings.
            max_tokens: Maximum number of tokens to generate in the chat completion.
                    Total length is limited by model's context length.
            frequency_penalty: Penalizes new tokens based on their existing frequency 
                            in the text so far (-2.0 to 2.0).
            presence_penalty: Penalizes new tokens based on whether they appear 
                            in the text so far (-2.0 to 2.0).
            response_format: Object specifying the format that the model must output.
                            Compatible with GPT-4 Turbo and gpt-3.5-turbo-1106.
            **kwargs: Additional streaming options specific to the implementation
            
        Returns:
            ChatCompletion: The complete response from the API
            
        Raises:
            ValueError: If the response contains Chinese characters
            
        Note:
            - Local image file paths are automatically converted to base64 data URLs
            - Chinese character detection covers CJK Unified Ideographs (U+4E00-U+9FFF)
        """
        # Prepare parameters
        params = self._prepare_params(
            model=self.config.model,
            messages=messages,
            stream=False,
            temperature=temperature,
            top_p=top_p,
            n=n,
            stop=stop,
            max_tokens=max_tokens,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            response_format=response_format,
            tools=tools,
            extra_body=kwargs
        )
        
        params = self.sanitize_for_gpt5(params, generate=True)

        client = self.client.with_options(
            max_retries=params.get("extra_body", {}).get("max_retries", 1)
        )
        completion = await client.chat.completions.create(**params)
        
        self.check_chinese_characters(completion, raise_on_found=False)
        
        # Update kwargs onto chunk
        for key, value in kwargs.items():
            setattr(completion, key, value)
        
        return completion
        
    async def close(self):
        """Clean up resources"""
        await self.client.close()
        await self.http_client.aclose()

    # async def generate_batch(
    #     self,
    #     messages_list: List[List[ChatCompletionMessageParam]],
    #     *,
    #     temperature: float = 0.0,
    #     top_p: float = 0.1,
    #     n: Optional[int] = None,
    #     stop: Optional[Union[str, Sequence[str]]] = None,
    #     max_tokens: Optional[int] = None,
    #     frequency_penalty: Optional[float] = None,
    #     presence_penalty: Optional[float] = None,
    #     response_format: Optional[dict] = None,
    #     tools: Optional[dict] = None,
    #     # Batch controls:
    #     max_concurrency: int = 8,
    #     max_retries: int = 3,
    #     retry_base_delay: float = 0.8,
    #     # Optional per-item kwargs (overrides **kwargs for that index)
    #     per_request_kwargs: Optional[List[Dict[str, Any]]] = None,
    #     # Optional progress callback: cb(done, total)
    #     progress_cb: Optional[Callable[[int, int], None]] = None,
    #     **kwargs: Any,
    # ) -> List[Tuple[bool, Union[ChatCompletion, Exception]]]:
    #     """
    #     Run multiple generate() calls concurrently with ordering preserved.

    #     Returns:
    #         List[Tuple[success, result_or_exception]] aligned with messages_list.
    #         - If success is True: result_or_exception is ChatCompletion
    #         - If success is False: result_or_exception is the Exception raised
    #     """
    #     total = len(messages_list)
    #     if per_request_kwargs and len(per_request_kwargs) != total:
    #         raise ValueError("per_request_kwargs length must match messages_list length.")

    #     sem = asyncio.Semaphore(max(1, int(max_concurrency)))
    #     results: List[Tuple[bool, Union[ChatCompletion, Exception]]] = [None] * total  # type: ignore
    #     done_count = 0

    #     async def _sleep_backoff(attempt: int):
    #         delay = retry_base_delay * (2 ** attempt)  # simple exponential backoff
    #         # jitter
    #         await asyncio.sleep(delay * (0.75 + 0.5 * math.random()))

    #     def _is_transient(e: Exception) -> bool:
    #         # Heuristics for retryable cases
    #         if isinstance(e, (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.NetworkError)):
    #             return True
    #         # OpenAI/compatible errors often have .status_code or .response
    #         status = getattr(e, "status_code", None)
    #         if status in (429, 500, 502, 503, 504):
    #             return True
    #         # Fallback: check message text
    #         msg = str(e).lower()
    #         return any(k in msg for k in ["rate limit", "timeout", "temporar", "connection reset"])

    #     async def _run_one(idx: int):
    #         nonlocal done_count
    #         attempt = 0

    #         base_params: Dict[str, Any] = {
    #             "temperature": temperature,
    #             "top_p": top_p,
    #             "n": n,
    #             "stop": stop,
    #             "max_tokens": max_tokens,
    #             "frequency_penalty": frequency_penalty,
    #             "presence_penalty": presence_penalty,
    #             "response_format": response_format,
    #             "tools": tools,
    #         }
    #         base_params = {k: v for k, v in base_params.items() if v is not None}
    #         base_params.update(kwargs or {})

    #         # per-item override
    #         if per_request_kwargs and per_request_kwargs[idx]:
    #             base_params.update(per_request_kwargs[idx])

    #         while True:
    #             try:
    #                 async with sem:
    #                     final_params = {"messages": messages_list[idx], **base_params}
    #                     completion = await self.generate(**final_params)
    #                 results[idx] = (True, completion)
    #                 break
    #             except Exception as e:
    #                 attempt += 1
    #                 if attempt > max_retries or not _is_transient(e):
    #                     results[idx] = (False, e)
    #                     break
    #                 # backoff
    #                 delay = retry_base_delay * (2 ** (attempt - 1))
    #                 # small jitter without importing random
    #                 jitter = 0.25 + (idx % 50) / 100.0  # deterministic-ish jitter
    #                 await asyncio.sleep(delay * jitter)
    #             finally:
    #                 # progress update only when item finished (success or final failure)
    #                 if results[idx] is not None:
    #                     done_count += 1
    #                     if progress_cb:
    #                         try:
    #                             progress_cb(done_count, total)
    #                         except Exception:
    #                             pass

    #     await asyncio.gather(*[ _run_one(i) for i in range(total) ])
    #     return results    

async def main():
    from beegen.const import BEEGEN_ROOT
    from beegen.configs import LLMConfig
    from beegen.registry.resource_hub import RESOURCE_HUB

    # model = OpenAISDKModel(LLMConfig.from_yaml_file(BEEGEN_ROOT / "config/llms/beegen_v1.yaml"))
    model = RESOURCE_HUB.llm("gpt-5.1-chat")
    
    # response = await model.generate(messages=[{"role": "user", "content": "xin chào"}])
    # print(response)
    
    async for chunk in model.stream(
        messages=[{"role": "user", "content": "say hi"}],
        status_code=200,
        drop_params=True
    ):
        print(chunk)
        

async def test_tool_callings():
    import json
    from beegen.registry.resource_hub import RESOURCE_HUB
    model = RESOURCE_HUB.llm("gpt-5.1-chat")

    # Define some example tools
    weather_tool = {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather in a given location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state, e.g. San Francisco, CA"
                    }
                },
                "required": ["location"]
            }
        }
    }
    
    calculator_tool = {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Perform a calculation",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The mathematical expression to evaluate"
                    }
                },
                "required": ["expression"]
            }
        }
    }
    
    tools = [weather_tool, calculator_tool]
    
    # Text-only example with tools
    print("Text-only example with tools:")
    completion = await model.generate(
        messages=[{"role": "user", "content": "What's the weather like in San Francisco?"}],
        tools=tools,
        drop_params=True
    )
    print(json.dumps(completion.model_dump(), indent=2))
    
    # Text-only example with tools
    print("Text-only example with tools (streaming):")
    async for chunk in model.stream(
        messages=[{"role": "user", "content": "What's the weather like in San Francisco?"}],
        tools=tools,
        drop_params=True
    ):
        if chunk.choices:
            content = chunk.choices[0].delta.content
            if content:
                pass
            
            tool_calls = chunk.choices[0].delta.tool_calls
            if tool_calls:
                print(tool_calls)


async def test_time_to_first_token():
    """Test time to first token latency for the OpenAI SDK model."""
    import time
    from beegen.registry.resource_hub import ResourceHub
    
    print("Starting Time to First Token Test...")
    
    # Initialize model
    model_init_start = time.perf_counter()
    model = ResourceHub.self().llm("gpt-5.1-chat")
    model_init_time = time.perf_counter() - model_init_start
    print(f"Model initialization time: {model_init_time:.3f}s")
    
    query = """Mục tiêu: 
        - Viết lại đoạn hội thoại của người dùng thành một câu, vẫn mang đủ ý của khách hàng.

        Đầu ra định dạng (xml format):
        <rewrite>câu query ngắn gọn được viết lại cho đủ ý của khách hàng</rewrite>

        Example:
        Input:
        - lịch sử trò chuyện:
        ['Người dùng: chủ tịch của MB là ai ?', 'BOT: chủ tịch của MB là anh Lưu Trung Thái']
        - câu chat gần nhất: anh ấy tại vị được bao lâu rồi?

        Output (xml format):
        <rewrite>Chủ tịch Lưu Trung Thái đã tại vị được bao lâu?</rewrite>

        Các thông tin đầu vào:
        - lịch sử trò chuyện: 
        [{'role': 'user', 'content': 'tổng giám đốc MB là ai ?'}, {'role': 'assistant', 'content': 'là anh Phạm Như Ánh đấy.'}]
        - câu chat gần nhất: anh ấy có già không ?"""
    
    # Test message
    messages = [{"role": "user", "content": query}]
    
    # Measure time to first token
    start_time = time.perf_counter()
    first_token_time = None
    
    try:
        async for chunk in model.stream(messages=messages, drop_params=True):
            if first_token_time is None:
                first_token_time = time.perf_counter() - start_time
                print(f"⚡ Time to First Token: {first_token_time:.3f}s")
                
            # Print first chunk content if available
            if chunk.choices and chunk.choices[0].delta.content:
                print(f"First content: '{chunk.choices[0].delta.content}'")
                break
                
    except Exception as e:
        print(f"Error during streaming: {e}")
        
    finally:
        await model.close()
    
    return first_token_time

# async def test_generate_batch_basic():
#     """Run multiple non-streaming requests concurrently and collect full results."""
#     from beegen.registry.resource_hub import RESOURCE_HUB
#     model = RESOURCE_HUB.llm("gpt-5.1-chat")

#     # Prepare batch messages (order matters; results will align to this order)
#     batch_messages: List[List[ChatCompletionMessageParam]] = [
#         [{"role": "user", "content": "Say hi in one short sentence."}],
#         [{"role": "user", "content": "Summarize in 1 sentence: Large Language Models are neural networks trained on text."}],
#         [{"role": "user", "content": "Translate to English: Xin chào, tôi tên là Minh."}],
#         [{"role": "user", "content": "Give me 3 bullet points about caching strategies."}],
#     ]

#     # Optional: per-request overrides (length must match batch size if provided)
#     per_request_kwargs: List[Dict[str, Any]] = [
#         {"temperature": 0.2},            # item 0 override
#         {"max_tokens": 48},              # item 1 override
#         {},                               # item 2 uses defaults
#         {"temperature": 0.0, "top_p": 1} # item 3 override
#     ]

#     # Optional progress callback
#     def progress_cb(done: int, total: int):
#         print(f"[Progress] {done}/{total} finished")

#     results = await model.generate_batch(
#         messages_list=batch_messages,
#         max_concurrency=6,
#         max_retries=3,
#         retry_base_delay=0.8,
#         per_request_kwargs=per_request_kwargs,
#         progress_cb=progress_cb,
#         # default params applied to all unless overridden above
#         temperature=0.0,
#         top_p=0.9,
#         max_tokens=128,
#         status_code=200,  # custom kwarg you may be passing through in your codebase
#     )

#     # Print aligned outputs
#     for idx, (ok, value) in enumerate(results):
#         print(f"\n=== Item #{idx} ===")
#         if ok:
#             # value is ChatCompletion
#             msg = value.choices[0].message
#             # Show structured object or just content
#             print("Role:", getattr(msg, "role", "assistant"))
#             print("Content:", getattr(msg, "content", ""))
#             # If you need raw JSON:
#             # print(json.dumps(value.model_dump(), indent=2, ensure_ascii=False))
#         else:
#             # value is Exception
#             print("Error:", repr(value))

#     await model.close()


# async def test_generate_batch_with_tools():
#     """Same as above but demonstrating tool definitions + overrides per request."""
#     from beegen.registry.resource_hub import RESOURCE_HUB
#     model = RESOURCE_HUB.llm("gpt-5.1-chat")

#     weather_tool = {
#         "type": "function",
#         "function": {
#             "name": "get_weather",
#             "description": "Get the current weather in a given location",
#             "parameters": {
#                 "type": "object",
#                 "properties": {
#                     "location": {
#                         "type": "string",
#                         "description": "The city and state, e.g. San Francisco, CA"
#                     }
#                 },
#                 "required": ["location"]
#             }
#         }
#     }

#     calculator_tool = {
#         "type": "function",
#         "function": {
#             "name": "calculate",
#             "description": "Perform a calculation",
#             "parameters": {
#                 "type": "object",
#                 "properties": {
#                     "expression": {
#                         "type": "string",
#                         "description": "The mathematical expression to evaluate"
#                     }
#                 },
#                 "required": ["expression"]
#             }
#         }
#     }

#     tools = [weather_tool, calculator_tool]

#     batch_messages: List[List[ChatCompletionMessageParam]] = [
#         [{"role": "user", "content": "What's the weather like in San Francisco today?"}],
#         [{"role": "user", "content": "Use a tool to compute: (2+3)*7 - 4 / 2"}],
#         [{"role": "user", "content": "List three use-cases of function calling."}],
#     ]

#     # Per-item overrides (e.g., nudging the tool-use behavior or token limit)
#     per_request_kwargs = [
#         {"max_tokens": 120},
#         {"max_tokens": 80},
#         {"temperature": 0.3}
#     ]

#     results = await model.generate_batch(
#         messages_list=batch_messages,
#         tools=tools,
#         max_concurrency=4,
#         max_retries=3,
#         per_request_kwargs=per_request_kwargs,
#         temperature=0.0,
#         top_p=0.9,
#         status_code=200
#     )

#     for idx, (ok, value) in enumerate(results):
#         print(f"\n=== Tools Item #{idx} ===")
#         if ok:
#             # You can inspect tool call decisions or final content
#             print(json.dumps(value.model_dump(), indent=2, ensure_ascii=False))
#         else:
#             print("Error:", repr(value))

#     await model.close()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
    asyncio.run(test_tool_callings())
    asyncio.run(test_time_to_first_token())
    # asyncio.run(test_generate_batch_basic())
    # asyncio.run(test_generate_batch_with_tools())