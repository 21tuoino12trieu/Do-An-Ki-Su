from beegenerate.storage import MongoStorage
from beegenerate.configs import MongoConfig, MilvusConfig
import uuid
from bson import Binary
from bson.binary import UuidRepresentation
from beegenerate.const import BEEGEN_ROOT


MONGO_STORAGE = MongoStorage(
    MongoConfig.default()
)

# # Milvus
# MONGO_STORAGE.insert(
#     collection_name="beegen_configurations",
#     document={
#         "_id": f"{uuid.uuid4()}",
#         "type": "MILVUS",
#         "config": MilvusConfig.default().model_dump()
#     }
# )

# Mongo
# MONGO_STORAGE.insert(
#     collection_name="beegen_configurations",
#     document={
#         "_id": f"{uuid.uuid4()}",
#         "type": "MONGO",
#         "config": MongoConfig.default().model_dump()
#     }
# )

# MONGO_STORAGE.insert(
#     collection_name="beegen_configurations",
#     document={
#         "_id": f"{uuid.uuid4()}",
#         "type": "PARSER",
#         "config": ParserConfig().model_dump()
#     }
# )

from beegenerate.configs import LLMConfig
from beegenerate.const import BEEGEN_ROOT

gemini_config = LLMConfig.from_yaml_file(BEEGEN_ROOT / "config/llms/gemini.yaml")

# LLMs
MONGO_STORAGE.insert(
    collection_name="beegen_configurations",
    document={
        "_id": str(uuid.uuid4()),
        "type": "LLM",
        "config": {
            "api_key": "REPLACE_WITH_LOCAL_SECRET",
            "api_type": "azure",
            "api_version": "2025-01-01-preview",
            "base_url": "https://10.1.13.168:9443/bee247dev",
            "frequency_penalty": 0,
            "max_tokens": 4096,
            "model": "gpt-4.1",
            "model_alias": "Mô hình azure gpt-4.1",
            "n": 1,
            "presence_penalty": 0,
            "stream": True,
            "top_p": 1
        },
        "system_prompt": "hihihaha"
    }
)

# # LLMs
# MONGO_STORAGE.insert(
#     collection_name="beegen_configurations",
#     document={
#         "_id": f"{uuid.uuid4()}",
#         "type": "LLM",
#         "config": {
#             "api_type": "gemini",
#             "temperature": 0.0,
#             "top_p": 0.1,
#             "stream": True,
#             "project_id": "mb-data-science-production",
#             "private_key_id": "66068598a2ed1aaf3432ced41ba8eebf492885e5",
#             "private_key": "REPLACE_WITH_LOCAL_SECRET",
#             "client_email": "vertex-ai-access@mb-data-science-production.iam.gserviceaccount.com",
#             "client_id": "103724194458338450863",
#             "auth_uri": "https://accounts.google.com/o/oauth2/auth",
#             "token_uri": "https://oauth2.googleapis.com/token",
#             "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
#             "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/vertex-ai-access%40mb-data-science-production.iam.gserviceaccount.com",
#             "universe_domain": "googleapis.com",
#             "location": "us-central1",
#             "model": "gemini-2.0-flash-001",
#             "model_alias": "mô hình gemini-2.0-flash-001"
#         },
#         "system_prompt": "hihihaha"
#     }
# )

# client.insert(
#     collection_name="beegen_configurations",
#     document={
#         "_id": f"{uuid.uuid4()}",
#         "type": "LLM",
#         "config": {
#             "api_key": "mb123456789",
#             "api_type": "vllm",
#             "base_url": "http://10.1.39.127:30040/v1",
#             "model": "model/Qwen2.5-72B-Instruct-AWQ",
#             "model_alias": "mô hình qwen - dev",
#             "temperature": 0.0,
#             "top_p": 0.001,
#             "frequency_penalty": 0.0,
#             "max_tokens": None,
#             "n": 1,
#             "presence_penalty": 0.0
#         }
#     }
# )

# MONGO_STORAGE.insert(
#     collection_name="beegen_configurations",
#     document={
#         "_id": f"{uuid.uuid4()}",
#         "type": "EMBEDDING",
#         "config": {
#             "api_type": "vllm",
#             "api_key": "mb123456789",
#             "base_url": "http://10.1.87.71:30044/v1/embeddings",
#             "model": "model/bge-m3",
#             "embed_batch_size": 32,
#             "dimensions": 1024,
#             "model_alias": "mô hình bge-m3 (vllm)",
#             "retrieval_threshold": 0,
#             "retrieval_top_k": 16,
#         }
#     }
# )

# MONGO_STORAGE.insert(
#     collection_name="beegen_configurations",
#     document={
#         "_id": f"{uuid.uuid4()}",
#         "type": "RERANKING",
#         "config": {
#             "api_type": "vllm",
#             "api_key": "mb123456789",
#             "base_url": "http://10.1.87.71:30043/v1/rerank",
#             "model": "model/bge-reranker-v2-m3",
#             "model_alias": "mô hình bge-m3-rerank (vllm)",
#             "rerank_threshold": 0.00,
#             "rerank_top_k": 4
#         }
#     }
# )

# client.insert(
#     collection_name="beegen_configurations",
#     document={
#         "_id": f"{uuid.uuid4()}",
#         "type": "LLM",
#         "config":{
#             'api_key': 'REPLACE_WITH_LOCAL_SECRET',
#             'api_type': 'azure',
#             'api_version': '2024-02-15-preview',
#             'base_url': 'https://10.1.13.168:8443/mbdevai',
#             'frequency_penalty': 0.0,
#             'max_tokens': 4096,
#             'model': 'azure-chat-engine-gpt-4o-base',
#             'model_alias': "mô hình azure openai dev",
#             'n': 1,
#             'presence_penalty': 0.0,
#             'stream': True,
#             'temperature': 0.0,
#             'top_p': 1.0
#         }
#     }
# )