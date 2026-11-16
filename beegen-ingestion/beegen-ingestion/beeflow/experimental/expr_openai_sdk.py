import os
import httpx
from openai import OpenAI

os.environ['NO_PROXY'] = 'llm-gateway-dev.mbbank.com.vn'

http_client = httpx.Client(
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

client = OpenAI(
    base_url="https://llm-gateway-dev.mbbank.com.vn/v1",
    api_key="REPLACE_WITH_LOCAL_SECRET",
    # http_client=http_client
)

response = client.chat.completions.create(
    model="Qwen3-4B",
    messages=[
        {"role": "user", "content": "Có tất cả bao nhiêu tổng giám đốc"},
        {"role": "assistant", "content": "2 người, anh Phạm Như Ánh và Lưu Trung Thái"}
    ],
    extra_body={"chat_template_kwargs": {'enable_thinking': False}}
)

client2 = OpenAI(
    base_url="http://10.1.47.71:30044/v1",
    api_key="mb123456789",
    # http_client=http_client
)

emb = client2.embeddings.create(input=["hello"], model="model/bge-m3")

print(emb)