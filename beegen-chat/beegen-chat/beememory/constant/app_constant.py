from beememory.db.milvus import MilvusDB

from beegenerate.embeddings import VLLMEmbedding
from beegenerate.llms.llm_executor import LLMExecutor
from beegenerate.storage.mongo.memory_store import MemoryStore

from beegenerate.configs.embedding_config import EmbeddingConfig
from beegenerate.configs import LLMConfig
from beegenerate.configs.db.mongo_config import MongoConfig

from beegenerate.const import BEEGEN_ROOT


db = MemoryStore(config=MongoConfig.from_yaml_file(
            BEEGEN_ROOT / "config/mongo_memory.yaml"
        ))
model = LLMExecutor(
            primary_config=LLMConfig.from_yaml_file(
                BEEGEN_ROOT / "config/llms/beegen_v1.yaml"
            )
        )

milvus_client = MilvusDB()

embedding_model = VLLMEmbedding(EmbeddingConfig(
        api_type = "vllm",
        api_key = "mb123456789",
        base_url = "http://10.1.87.71:30044/v1/embeddings",
        model = "model/bge-m3",
        embed_batch_size = 32,
        dimensions = 1024
    ))

