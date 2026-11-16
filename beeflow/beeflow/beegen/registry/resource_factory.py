import os
from typing import Dict, Optional, ClassVar, TypeVar, Generic, Any, Type, Union
from beegen.configs.event_streaming.kafka_config import KafkaConfig
from beegen.configs.mcp.mcp_config import MCPConfig
from beegen.configs.memory.memory_config import MemoryConfig
from beegen.configs.storage.sql_config import SQLConfig
from beegen.configs.yaml_model import YamlModel
from beegen.configs import *
from beegen.event_streaming.kafka_engine import KafkaEngine
from beegen.llms.factory import LLMFactory
from beegen.embeddings.emb_factory import EmbeddingFactory
from beegen.mcp.factory import MCPFactory
from beegen.memory.factory import MemoryFactory
from beegen.reranks.rerank_factory import RerankingFactory
from beegen.storage.sql.factory import SQLFactory
from beegen.vectordb.milvus_engine import MilvusEngine
from beegen.storage.mongo.mongo_engine import AsyncMongoEngine
from beegen.cache.redis_engine import RedisEngine
from beegen.storage.s3.s3_engine import S3Engine
from beegen.observations.bee_langfuse import BeeLangfuse
import httpx


class ResourceFactory:
    """Enhanced factory that track instances across processes."""
    
    @classmethod
    def create(cls, config: YamlModel):
        """Create or retrieve an BeegenModule for the given configuration."""
        if isinstance(config, LLMConfig):
            model = LLMFactory.create(config)
        elif isinstance(config, EmbeddingConfig):
            model = EmbeddingFactory.create(config)
        elif isinstance(config, RerankingConfig):
            model = RerankingFactory.create(config)
        elif isinstance(config, MilvusConfig):
            model = MilvusEngine(config)
        elif isinstance(config, MongoConfig):
            model = AsyncMongoEngine(config)
        elif isinstance(config, RedisConfig):
            model = RedisEngine(config)
        elif isinstance(config, S3Config):
            model = S3Engine(config)
        elif isinstance(config, LangfuseConfig):
            model = BeeLangfuse(
                public_key=config.public_key,
                secret_key=config.secret_key,
                host=config.host
            )
        elif isinstance(config, MCPConfig):
            model = MCPFactory.create(config)
        elif isinstance(config, MemoryConfig):
            model = MemoryFactory.create(config)
        elif isinstance(config, SQLConfig):
            model = SQLFactory.create(config)
        elif isinstance(config, KafkaConfig):
            model = KafkaEngine(config)
        else:
            raise ValueError(f"Unsupport Model: {type(config)}")
        
                
        return model
        
        
if __name__ == "__main__":
    config = EmbeddingConfig.default()
        
    a1 = ResourceFactory.create(config=config)
    
    print(a1)