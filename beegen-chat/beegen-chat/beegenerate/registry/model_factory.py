import hashlib
from typing import Dict, Optional, ClassVar, TypeVar, Generic, Any, Type, Union
from beegenerate.loggings import LOGGER
from beegenerate.configs.yaml_model import YamlModel
from beegenerate.configs import *
from beegenerate.llms.core_v2.factory import LLMFactory
from beegenerate.embeddings.emb_factory import EmbeddingFactory
from beegenerate.reranks.rerank_factory import RerankingFactory
from beegenerate.vectordb.milvus_v2 import MilvusExecutor
from beegenerate.storage.mongo.mongodb_v2 import MongoExecutor
from beegenerate.cache.redis_connector import RedisConnector
from beegenerate.const import BEEGEN_ROOT


# Option 3: More general purpose
BeegenModule = Union[
    LLMFactory,
    EmbeddingFactory,
    RerankingFactory,
    MilvusExecutor,
    MongoExecutor,
    RedisConnector
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
            model = MilvusExecutor(config)
        elif isinstance(config, MongoConfig):
            model = MongoExecutor(config)
        elif isinstance(config, RedisConfig):
            model = RedisConnector(config)
        else:
            raise ValueError(f"Unsupport Model: {config}")
                
        return model
        
        
if __name__ == "__main__":
    from beegenerate.const import BEEGEN_ROOT
    

    config1 = LLMConfig.default()
    config2 = EmbeddingConfig.default()
    config3 = RerankingConfig.default()
    config4 = MilvusConfig.default()
    config5 = LLMConfig.from_yaml_file(BEEGEN_ROOT / "config/llms/azure.yaml")
    config6 = LLMConfig.from_yaml_file(BEEGEN_ROOT / "config/llms/azure.yaml")
        
    a1 = ModelFactory.create(config=config1)
    a2 = ModelFactory.create(config=config2)
    a3 = ModelFactory.create(config=config3)
    a4 = ModelFactory.create(config=config4)
    a5 = ModelFactory.create(config=config5)
    a6 = ModelFactory.create(config=config6)
    
    print(a1)
    print(a2)
    print(a3)
    print(a4)
    print(a5)
    print(a6)