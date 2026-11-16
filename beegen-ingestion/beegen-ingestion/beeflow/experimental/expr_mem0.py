import ssl
import urllib3
import os

import sys

if sys.platform == "win32":
    import msvcrt
    # Use msvcrt functionality
else:
    # Provide alternative functionality for non-Windows platforms
    pass

os.environ["VLLM_API_KEY"] = "REPLACE_WITH_LOCAL_SECRET"
os.environ["OPENAI_API_KEY"] = "REPLACE_WITH_LOCAL_SECRET"
os.environ['NO_PROXY'] = 'llm-gateway-dev.mbbank.com.vn'
os.environ["MEM0_TELEMETRY"] = "false"

# Disable SSL warnings and verification
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ssl._create_default_https_context = ssl._create_unverified_context


from mem0 import Memory


memory = Memory.from_config(
    config_dict={
        "llm": {
            "provider": "vllm",
            "config": {
                "model": "gpt-4.1",
                "vllm_base_url": "https://llm-gateway-dev.mbbank.com.vn/v1",
                "temperature": 0.0
            }
        },
        "embedder": {
            "provider": "openai",
            "config": {
                "openai_base_url": "http://10.1.47.71:30044/v1",
                "api_key": "mb123456789",
                "model": "model/bge-m3",
                "embedding_dims": 1024
            }
        },
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "embedding_model_dims": 1024,
                "on_disk": True
            }
        }
    }
)

memory.add(
    messages=[
        {"role": "user", "content": "Có tất cả bao nhiêu tổng giám đốc"},
        {"role": "assistant", "content": "2 người, anh Phạm Như Ánh và Lưu Trung Thái"}
    ],
    user_id="1234"
)

response = memory.search(query="người thứ 2 có đẹp trai ko", user_id="1234")

print(response)

# Explicitly close the connection
if hasattr(memory.vector_store, 'client'):
    memory.vector_store.client.close()