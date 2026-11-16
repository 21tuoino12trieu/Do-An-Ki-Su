import os
from typing import Dict, Optional, ClassVar, TypeVar, Generic, Any, Type, Union
from beegen_v1.loggings import LOGGER
from beegen_v1.configs.yaml_model import YamlModel
from beegen_v1.configs import *
from beegen_v1.llms.factory import LLMFactory
from beegen_v1.embeddings.emb_factory import EmbeddingFactory
from beegen_v1.reranks.rerank_factory import RerankingFactory
from beegen_v1.vectordb.milvus_engine import MilvusEngine
from beegen_v1.storage.mongo.mongo_engine import AsyncMongoEngine
from beegen_v1.cache.redis_connector import RedisConnector
from beegen_v1.const import BEEGEN_ROOT
from langfuse import Langfuse


# Option 3: More general purpose
BeegenModule = Union[
    LLMFactory,
    EmbeddingFactory,
    RerankingFactory,
    MilvusEngine,
    AsyncMongoEngine,
    RedisConnector,
    Langfuse
]


class ModelFactory:
    """Enhanced factory that track instances across processes."""
    
    @classmethod
    def create(cls, config: YamlModel) -> BeegenModule:
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
            model = RedisConnector(config)
        elif isinstance(config, LangfuseConfig):
            os.environ.update({"NO_PROXY": config.no_proxy})
            model = Langfuse(
                public_key=config.public_key,
                secret_key=config.secret_key,
                host=config.host
            )
        else:
            raise ValueError(f"Unsupport Model: {config}")
                
        return model
        
        
if __name__ == "__main__":
    from beegen_v1.const import BEEGEN_ROOT
    

    config1 = LangfuseConfig.default()
        
    a1 = ModelFactory.create(config=config1)
    
    print(a1)