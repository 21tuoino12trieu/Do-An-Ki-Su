import httpx
import json
import time
import asyncio
import os

# Set proxy bypass
os.environ['NO_PROXY'] = 'llm-gateway-dev.mbbank.com.vn'

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
- câu chat gần nhất: anh ấy có dài không ?"""

async def test_raw_http_ttft():
    """Test time to first token using raw HTTP requests."""
    
    url = "https://llm-gateway-dev.mbbank.com.vn/v1/chat/completions"
    headers = {
        "Authorization": "Bearer REPLACE_WITH_LOCAL_SECRET",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "Qwen3-4B",
        "messages": [
            {"role": "user", "content": query}
        ],
        "stream": True,
        "temperature": 0.0,
        "top_p": 0.1
    }
    
    print("Testing Raw HTTP Time to First Token...")
    
    # Test HTTP client initialization
    client_init_start = time.perf_counter()
    async with httpx.AsyncClient(
        verify=False,
        timeout=httpx.Timeout(
            connect=10.0,
            read=120.0,
            write=10.0,
            pool=5.0
        )
    ) as client:
        client_init_time = time.perf_counter() - client_init_start
        print(f"HTTP Client init time: {client_init_time:.3f}s")
        
        # Test actual request
        request_start = time.perf_counter()
        first_chunk_time = None
        
        try:
            async with client.stream(
                "POST", 
                url, 
                headers=headers, 
                json=payload
            ) as response:
                
                if response.status_code != 200:
                    print(f"Error: HTTP {response.status_code}")
                    print(await response.aread())
                    return
                
                async for line in response.aiter_lines():
                    if first_chunk_time is None:
                        first_chunk_time = time.perf_counter() - request_start
                        print(f"⚡ Raw HTTP Time to First Token: {first_chunk_time:.3f}s")
                    
                    if line.strip():
                        # Parse SSE format
                        if line.startswith("data: "):
                            data = line[6:].strip()
                            if data and data != "[DONE]":
                                try:
                                    chunk_data = json.loads(data)
                                    if chunk_data.get("choices") and chunk_data["choices"][0].get("delta", {}).get("content"):
                                        content = chunk_data["choices"][0]["delta"]["content"]
                                        print(f"First content: '{content}'")
                                        break
                                except json.JSONDecodeError:
                                    pass
                        
        except Exception as e:
            print(f"Error during request: {e}")
    
    return first_chunk_time


async def test_simple_http_ttft():
    """Simplified version using basic httpx without custom config."""
    
    url = "https://llm-gateway-dev.mbbank.com.vn/v1/chat/completions"
    headers = {
        "Authorization": "Bearer REPLACE_WITH_LOCAL_SECRET",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "Qwen3-4B",
        "messages": [
            {"role": "user", "content": query}
        ],
        "stream": True
    }
    
    print("\nTesting Simple HTTP Time to First Token...")
    
    request_start = time.perf_counter()
    first_chunk_time = None
    
    try:
        async with httpx.AsyncClient(verify=False) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                async for line in response.aiter_lines():
                    if first_chunk_time is None:
                        first_chunk_time = time.perf_counter() - request_start
                        print(f"⚡ Simple HTTP Time to First Token: {first_chunk_time:.3f}s")
                        break
                        
    except Exception as e:
        print(f"Error: {e}")
    
    return first_chunk_time


async def main():
    """Run both tests for comparison."""
    print("Python version:", __import__('sys').version)
    print("httpx version:", httpx.__version__)
    print("=" * 50)
    
    # Test 1: Full configuration
    await test_raw_http_ttft()
    
    # Small delay between tests
    await asyncio.sleep(1)
    
    # Test 2: Simple configuration
    await test_simple_http_ttft()


if __name__ == "__main__":
    asyncio.run(main())