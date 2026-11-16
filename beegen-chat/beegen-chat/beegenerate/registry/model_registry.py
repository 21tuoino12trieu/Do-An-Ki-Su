import hashlib
from typing import Dict, Optional, ClassVar, Any
from beegenerate.loggings import LOGGER
from beegenerate.configs.yaml_model import YamlModel
import asyncio
from .model_factory import ModelFactory
from beegenerate.configs.authen.keycloak_config import KeycloakConfig
from beegenerate.configs.cache.redis_config import RedisConfig
from beegenerate.configs.db.vectordb.milvus_config import MilvusConfig
from beegenerate.configs.db.mongo_config import MongoConfig
from beegenerate.configs.logging.log_config import LogConfig
from beegenerate.configs.models.llm_config import AzureConfig, GeminiConfig, OpenAIConfig, LiteLLMConfig
from beegenerate.configs.models.embedding_config import EmbeddingConfig
from beegenerate.configs.models.reranking_config import RerankingConfig
from beegenerate.configs.logging.langfuse_config import LangfuseConfig
from beegenerate.storage.mongo.mongodb_v2 import MongoExecutor, MongoOperation
from beegenerate.llms.core_v2.base import BaseLLM
from beegenerate.embeddings.base import BaseEmbedder
from beegenerate.reranks.base import BaseReranker
from beegenerate.vectordb.milvus_v2 import MilvusExecutor
from beegenerate.storage.mongo.mongodb_v2 import MongoExecutor
from enum import Enum
import sys
import json


class ConfigType(str, Enum):
    KEYCLOAK = "keycloak"
    REDIS = "redis"
    MILVUS = "milvus"
    MONGO = "mongo"
    AZURE = "llm:azure"
    GEMINI = "llm:gemini"
    OPENAI = "llm:openai"
    LITELLM = "llm:litellm"
    EMBEDDING = "embedding"
    RERANKING = "reranking"
    LANGFUSE = "langfuse"


def config_type_of(config_obj):
    """
    Maps a config object to its corresponding ConfigType enum value.

    Args:
        config_obj: An instance of a configuration class

    Returns:
        ConfigType: The corresponding ConfigType enum value

    Raises:
        ValueError: If the config object type is not recognized
    """
    config_type_mapping = {
        KeycloakConfig: ConfigType.KEYCLOAK,
        RedisConfig: ConfigType.REDIS,
        MilvusConfig: ConfigType.MILVUS,
        MongoConfig: ConfigType.MONGO,
        AzureConfig: ConfigType.AZURE,
        GeminiConfig: ConfigType.GEMINI,
        OpenAIConfig: ConfigType.OPENAI,
        LiteLLMConfig: ConfigType.LITELLM,
        EmbeddingConfig: ConfigType.EMBEDDING,
        RerankingConfig: ConfigType.RERANKING,
        LangfuseConfig: ConfigType.LANGFUSE
    }

    config_class = type(config_obj)
    if config_class in config_type_mapping:
        return config_type_mapping[config_class]
    else:
        raise ValueError(f"Unrecognized config type: {config_class.__name__}")


class ModelRegistry:
    """Registry for model instances using local storage.

    This class is implemented as a singleton to ensure only one instance exists
    throughout the application. It can register any type of model with any type
    of configuration that supports model_dump_json().
    """

    # Singleton instance
    _instance: ClassVar[Optional['ModelRegistry']] = None

    # Dictionary to store model instances by their configuration hash
    _instances: Dict[str, Any] = {}

    # MongoDB collection name for storing configurations
    _BASE_COLLECTION = "beegen_registry_configs"

    # MongoDB executor for data persistence
    _mongo: MongoExecutor = MongoExecutor(MongoConfig.default())

    @classmethod
    def self(cls) -> 'ModelRegistry':
        """Get the singleton instance of the registry.

        Returns:
            The singleton ModelRegistry instance
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        """Initialize the model registry.

        Note: This constructor should not be called directly.
        Use ModelRegistry.self() instead.
        """
        if ModelRegistry._instance is not None:
            LOGGER.warning(
                "ModelRegistry initialized directly instead of using self() method")

    async def _load_all_configs(self):
        """Load all configurations from MongoDB."""
        # Ensure collection exists
        await self._ensure_base_collection()

        # Fetch all configurations
        result = await self._mongo.run(
            MongoOperation.FIND,
            {
                "filter": {},
                "collection_name": self._BASE_COLLECTION
            }
        )

        if result['status'] == 'success':
            for doc in result.get('data', []):
                key = doc['_id']
                config_data = doc['config_data']
                config_class = getattr(
                    sys.modules[__name__], doc['config_class'])
                config = config_class.model_validate(config_data)
                self._instances[key] = ModelFactory.create(config)

    def keys(self):
        """return the list of registry keys"""
        return list(self._instances.keys())

    def _hash_of(self, config: YamlModel) -> str:
        """Generate a unique hash for a model configuration.

        Args:
            config: The model configuration (must have model_dump_json method)

        Returns:
            A string hash that uniquely identifies this configuration
        """
        # Use model_dump_json if available, otherwise fallback to str representation
        config_str = config.model_dump_json()

        return hashlib.md5(config_str.encode()).hexdigest()

    def _key_of(self, config: YamlModel) -> str:
        """Get a registry key that combines model type and config hash.

        Args:
            config: The model configuration
            model_type: Optional model type to differentiate configs with same parameters
                        but different model types

        Returns:
            A string key for the registry
        """
        _type = config_type_of(config)
        if _type in [ConfigType.AZURE,
                     ConfigType.GEMINI,
                     ConfigType.OPENAI,
                     ConfigType.EMBEDDING,
                     ConfigType.RERANKING]:
            return f"{_type}:{config.model}"

        config_hash = self._hash_of(config)
        return f"{_type}:{config_hash}"

    async def _ensure_base_collection(self):
        """Ensure the MongoDB collection for registry exists."""
        # Check if collection exists
        collections = await self._mongo.run(
            MongoOperation.LIST_COLLECTIONS,
            {"filter": {"name": self._BASE_COLLECTION}}
        )

        # Create collection if it doesn't exist
        if collections['count'] == 0:
            LOGGER.info(
                f"Creating MongoDB collection: {self._BASE_COLLECTION}")
            await self._mongo.run(
                MongoOperation.CREATE_COLLECTION,
                {"name": self._BASE_COLLECTION}
            )

    async def save_to_mongo(self, registry_key: str, config: YamlModel) -> bool:
        """Save a configuration to MongoDB.

        Args:
            registry_key: The registry key
            config: The model configuration

        Returns:
            True if successful, False otherwise
        """
        # Ensure collection exists
        await self._ensure_base_collection()

        # Prepare document
        doc = {
            "_id": registry_key,
            "config_type": config_type_of(config).value,
            "config_class": type(config).__name__,
            "config_data": json.loads(config.model_dump_json(exclude_none=True)),
            "config_hash": self._hash_of(config)
        }

        # Insert or update the configuration
        result = await self._mongo.run(
            MongoOperation.UPDATE_ONE,
            {
                "filter": {"_id": registry_key},
                "update": {"$set": doc},
                "upsert": True,
                "collection_name": self._BASE_COLLECTION
            }
        )

        if result['status'] == 'success':
            if result.get('upserted_id'):
                LOGGER.info(
                    f"Inserted configuration to MongoDB: {registry_key}")
            else:
                LOGGER.info(
                    f"Updated configuration in MongoDB: {registry_key}")
            return True
        else:
            LOGGER.error(
                f"Failed to save configuration to MongoDB: {result['message']}")
            return False

    async def remove_from_mongo(self, registry_key: str) -> bool:
        """Remove a configuration from MongoDB.

        Args:
            registry_key: The registry key

        Returns:
            True if successful, False otherwise
        """
        result = await self._mongo.run(
            MongoOperation.DELETE_ONE,
            {
                "filter": {"_id": registry_key},
                "collection_name": self._BASE_COLLECTION
            }
        )

        if result['status'] == 'success':
            if result['deleted_count'] > 0:
                LOGGER.info(
                    f"Removed configuration from MongoDB: {registry_key}")
                return True
            else:
                LOGGER.warning(
                    f"No configuration found in MongoDB to remove: {registry_key}")
                return False
        else:
            LOGGER.error(
                f"Failed to remove configuration from MongoDB: {result['message']}")
            return False

    def has(self, key: str) -> bool:
        """Check if a model instance exists for the given registry key.

        Args:
            key: registry key of the model

        Returns:
            True if an instance exists, False otherwise
        """
        return key in self._instances

    def get(self, key: str) -> Any:
        """Get a model instance for the given registry key if it exists.

        Args:
            key: registry key of the model

        Returns:
            The model instance if it exists, None otherwise
        """
        if key not in self._instances:
            raise KeyError(f"key '{key}' not existed in registry!")
        return self._instances.get(key)

    def redis(self, key: str) -> BaseLLM:
        """Get a redis instance for the given key."""
        _key = key
        if not _key.startswith("redis:"):
            _key = f"redis:{key}"

        return self.get(_key)

    def llm(self, key: str) -> BaseLLM:
        """Get a llm instance for the given key."""
        _key = key
        if not _key.startswith("llm:"):
            _key = f"llm:{key}"

        return self.get(_key)

    def embedding(self, key: str) -> BaseEmbedder:
        """Get a embedding instance for the given key."""
        _key = key
        if not key.startswith("embedding:"):
            _key = f"embedding:{key}"

        return self.get(_key)

    def reranker(self, key: str) -> BaseReranker:
        """Get a reranker instance for the given key."""
        _key = key
        if not key.startswith("reranker:"):
            _key = f"reranker:{key}"

        return self.get(_key)

    def milvus(self, key: str) -> MilvusExecutor:
        """Get a milvus executor instance for the given key."""
        _key = key
        if not key.startswith("milvus:"):
            _key = f"milvus:{key}"

        return self.get(_key)

    def mongo(self, key: str) -> MongoExecutor:
        """Get a mongo executor instance for the given key."""
        _key = key
        if not key.startswith("mongo:"):
            _key = f"mongo:{key}"

        return self.get(_key)

    async def register(self, config: YamlModel, registry_key: Optional[str] = None) -> str:
        """Register a model instance.

        Args:
            config: The model configuration
            instance: The model instance
            model_type: Optional model type for more specific registration

        Returns:
            The registry key of the registered configuration
        """
        if not registry_key:
            registry_key = self._key_of(config)

        self._instances[registry_key] = ModelFactory.create(config)

        # Save configuration to MongoDB asynchronously
        await self.save_to_mongo(registry_key, config)

        LOGGER.info(f"Registered model instance with key: {registry_key}")
        return registry_key

    async def remove(self, config: YamlModel) -> bool:
        """Remove a model instance if it exists.

        Args:
            config: The model configuration
            model_type: Optional model type for more specific matching

        Returns:
            True if an instance was removed, False otherwise
        """
        registry_key = self._key_of(config)
        if registry_key in self._instances:
            del self._instances[registry_key]

            # Remove from MongoDB asynchronously
            await self.remove_from_mongo(registry_key)

            LOGGER.info(f"Removed model instance with key: {registry_key}")
            return True
        return False

    async def clear(self) -> None:
        """Clear all cached instances and their MongoDB configurations."""
        # Get all keys before clearing
        keys = list(self._instances.keys())

        # Clear local cache
        self._instances.clear()

        # Remove all configurations from MongoDB
        for key in keys:
            await self.remove_from_mongo(key)

        LOGGER.info("Cleared all model instances from registry and MongoDB")


async def main():
    registry = ModelRegistry.self()
    _llm = registry.llm("openai:beegen-v1")
    print(_llm)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
