from typing import Optional
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
import json
from openai import AsyncStream
import aiohttp
import asyncio
import uuid
import time
from typing import (
    List,
    TypeVar,
    AsyncIterator
)

from beegenerate.loggings import LOGGER


def chunk_from(line: str, **kwargs) -> Optional[ChatCompletionChunk]:
    """Convert a line of response to a ChatCompletionChunk object."""
    if not line or line.isspace():
        return None

    line = line.strip()
    
    try:
        if line.startswith('data: '):
            line = line[6:]  # Remove 'data: ' prefix
        if line == '[DONE]':
            return None
        
        data = json.loads(line)
        data.update(kwargs)
        
        if len(data['choices']) == 0:
            return None
        
        return ChatCompletionChunk(**data)
    except json.JSONDecodeError:
        LOGGER.warning(f"Failed to decode JSON from line: {line}")
        return None
    except Exception as e:
        LOGGER.error(f"Error processing chunk: {str(e)} \nAt {line}")
        return None
    
    
def create_error_chunk() -> ChatCompletionChunk:
    params = {
        "id": "chatcmpl-AfR0XHVcMkcrSuU2FvG5LxDIIV6lD",
        "choices": [
            {
                "delta": {
                    "content": "?",
                    "function_call": None,
                    "refusal": None,
                    "role": None,
                    "tool_calls": None
                },
                "finish_reason": None,
                "index": 0,
                "logprobs": None,
                "content_filter_results": {
                    "hate": {
                    "filtered": True,
                    "severity": "safe"
                    },
                    "self_harm": {
                    "filtered": True,
                    "severity": "safe"
                    },
                    "sexual": {
                    "filtered": True,
                    "severity": "safe"
                    },
                    "violence": {
                    "filtered": True,
                    "severity": "safe"
                    }
                }
            }
        ],
        "created": 1734438629,
        "model": "gpt-4o-2024-08-06",
        "object": "chat.completion.chunk",
        "service_tier": None,
        "system_fingerprint": "fp_04751d0b65",
        "usage": None
    }
    return ChatCompletionChunk(**params)


from datetime import datetime


def fake_chunk_from(
    content: str,
    model: str,
    chat_id: str = "",
    current_time: int = 0,
    last=False,
    **kwargs
) -> ChatCompletionChunk:
    chat_id = chat_id or f"chat-{uuid.uuid4()}"
    current_time = current_time or int(datetime.now().timestamp())
    params = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": current_time,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {
                    "content": content
                },
                "logprobs": None,
                "finish_reason": None
            }
        ]
    }
    
    if last:
        if 'choices' in params:
            for choice in params['choices']:
                if "delta" in choice:
                    choice["delta"]["content"] = ""
                
                choice["logprobs"] = None
                choice["finish_reason"] = "stop"
                choice["stop_reason"] = None
    params.update(**kwargs)
    return ChatCompletionChunk(**params)


def has_chinese_chars(text: str) -> bool:
    """Check if text contains Chinese characters."""
    if text:
        for char in text:
            if '\u4e00' <= char <= '\u9fff':  # Range for most common Chinese characters
                return True
    return False


async def stream_chunks(
    response: aiohttp.ClientResponse,
    model: str,
    **kwargs
) -> AsyncStream[ChatCompletionChunk]: # type: ignore
    """Process the API response and yield chunks."""
    # Read the first chunk to check for errors
    first_chunk = await response.content.readline()
    if first_chunk:
        decoded_first = first_chunk.decode("utf-8")
        try:
            data = json.loads(decoded_first)
            # check if it's an error message
            if data.get('object') == 'error':
                message = data.get('message', 'xin lỗi bạn nha, mình đang gặp một chút trục trặc, bạn vui lòng thử lại sau nhé.')
                chat_id = f"chat-{str(uuid.uuid4())}"
                current_time = int(time.time())
                
                for token in message.split():
                    yield fake_chunk_from(
                        content=token + " ",
                        model=model,
                        chat_id=chat_id,
                        current_time=current_time
                    )
                    await asyncio.sleep(kwargs.get("sleep", 0.0))
                return # if error, then stop the process after yield error message
        except Exception as e:
            pass # Not JSON or incomplete JSON, treat as normal chunk
        
        # Process the first chunk if it wasn't an error
        chunk = chunk_from(decoded_first, **kwargs)
        if chunk and not has_chinese_chars(chunk.choices[0].delta.content if hasattr(chunk.choices[0].delta, 'content') else ""):
            yield chunk
        
        # Process remaining chunks
        async for line in response.content:
            decoded_line = line.decode('utf-8')
            chunk = chunk_from(decoded_line, **kwargs)
            if chunk:
                content = chunk.choices[0].delta.content if hasattr(chunk.choices[0].delta, 'content') else ""
                if not has_chinese_chars(content):
                    yield chunk
                    await asyncio.sleep(kwargs.get("sleep", 0.0))
                
                
ERROR_DEFAULT_MESSAGE = """Xin lỗi bạn nhé, hệ thống hiện tại đang một chút trục trặc, bạn vui lòng thử lại sau"""

T = TypeVar('T')

async def async_iterate(items: List[T]) -> AsyncIterator[T]:
    for item in items:
        yield item
        

async def simulate_error_streaming() -> AsyncStream[ChatCompletionChunk]: # type: ignore
    chat_id = f"chat-{uuid.uuid4()}"
    current_time = int(time.time())
    chars = list(ERROR_DEFAULT_MESSAGE)
    
    async for char in async_iterate(chars):
        chunk = fake_chunk_from(
            content=char,
            model="default",
            chat_id=chat_id,
            current_time=current_time
        )
        await asyncio.sleep(0.00001)
        yield chunk
    
    # Send the final chunk
    final_chunk = fake_chunk_from(
        content="",
        model="default",
        chat_id=chat_id,
        current_time=current_time,
        last=True
    )
    yield final_chunk
    

async def word_generator(text):
    words = text.split(" ")
    
    for word in words:
        yield word
    
    
async def simulate_message_streaming(
    msg: str,
    sleep: float = 0.0000001
) -> AsyncStream[ChatCompletionChunk]: # type: ignore
    chat_id = f"chat-{uuid.uuid4()}"
    current_time = int(time.time())
    
    async for char in word_generator(msg):
        chunk = fake_chunk_from(
            content=char + " ",
            model="default",
            chat_id=chat_id,
            current_time=current_time
        )
        await asyncio.sleep(sleep)
        yield chunk  
    
    # Send the final chunk
    final_chunk = fake_chunk_from(
        content="",
        model="default",
        chat_id=chat_id,
        current_time=current_time,
        last=True
    )
    yield final_chunk
                

async def main():
    text = """Hình thức mua hàng hóa của doanh nghiệp A không phù hợp với giao dịch nhập khẩu, xuất khẩu, chuyển khẩu, quá cảnh hay bất kỳ hình thức thương mại quốc tế nào khác 
theo quy định pháp luật Việt Nam hiện hành, do đó chưa đủ cơ sở để thực hiện giao dịch thanh toán của doanh nghiệp A."""
    async for chunk in simulate_message_streaming(text):
        print(chunk.choices[0].delta.content, end="")
        

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())