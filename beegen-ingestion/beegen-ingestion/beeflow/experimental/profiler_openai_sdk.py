# Install: pip install line_profiler

# test_openai_profile.py
import asyncio
from line_profiler import profile
from openai import AsyncOpenAI
import httpx
import os
import cProfile
import pstats

# Before importing OpenAI, add this:
import openai._base_client
openai._base_client.get_platform = lambda: "Windows"


os.environ['NO_PROXY'] = 'llm-gateway-dev.mbbank.com.vn'

http_client = httpx.AsyncClient(
    verify=False,
    timeout=httpx.Timeout(
        connect=10.0,
        read=120.0,
        write=10.0,
        pool=5.0
    ),
    limits=httpx.Limits(
        max_connections=100,
        max_keepalive_connections=10
    )
)

client = AsyncOpenAI(
    base_url="https://llm-gateway-dev.mbbank.com.vn/v1",
    api_key="REPLACE_WITH_LOCAL_SECRET",
    http_client=http_client
)


async def test():
    
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
    
    response = await client.chat.completions.create(
        model="Qwen3-4B",
        messages=[{"role": "user", "content": query}],
        stream=True
    )
    
    async for chunk in response:
        break

def profile_it():
    profiler = cProfile.Profile()
    profiler.enable()
    asyncio.run(test())
    profiler.disable()
    
    # Show only OpenAI-related functions
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative')
    print("=== OpenAI Functions ===")
    stats.print_stats('openai', 15)


if __name__ == "__main__":
    profile_it()