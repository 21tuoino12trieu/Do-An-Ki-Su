import hashlib
from typing import Dict, Optional, ClassVar, Any
from beegen_v1.loggings import LOGGER
from beegen_v1.configs.yaml_model import YamlModel
from .model_factory import ModelFactory
from beegen_v1.configs.authen.keycloak_config import KeycloakConfig
from beegen_v1.configs.cache.redis_config import RedisConfig
from beegen_v1.configs.db.vectordb.milvus_config import MilvusConfig
from beegen_v1.configs.db.mongo_config import MongoConfig
from beegen_v1.configs.models.llm_config import AzureConfig, GeminiConfig, OpenAIConfig
from beegen_v1.configs.models.embedding_config import EmbeddingConfig
from beegen_v1.configs.models.reranking_config import RerankingConfig
from beegen_v1.configs.monitor.langfuse_config import LangfuseConfig
from beegen_v1.llms.base_llm import BaseLLM
from beegen_v1.embeddings.base_embedding import BaseEmbedder
from beegen_v1.reranks.base_reranker import BaseReranker
from beegen_v1.vectordb.milvus_engine import MilvusEngine
from beegen_v1.storage.mongo.mongo_engine import AsyncMongoEngine, MongoEngine
from langfuse import Langfuse
from enum import Enum
import sys
import json
from pymongo import MongoClient
from pymongo.errors import PyMongoError


class ConfigType(str, Enum):
    KEYCLOAK = "keycloak"
    REDIS = "redis"
    MILVUS = "milvus"
    MONGO = "mongo"
    AZURE = "llm:azure"
    GEMINI = "llm:gemini"
    OPENAI = "llm:openai"
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
    _self: ClassVar[Optional['ModelRegistry']] = None
    
    # Dictionary to store model instances by their configuration hash
    _instances: Dict[str, Any] = {}
    _configs: Dict[str, Any] = {}
    
    # MongoDB collection name for storing configurations
    _BASE_COLLECTION = "beegen_registry_configs"
    
    # MongoDB client for data persistence
    _mongo_client: Optional[MongoClient] = None
    _mongo_db = None
    _mongo_collection = None
    
    @classmethod
    def self(cls) -> 'ModelRegistry':
        """Get the singleton instance of the registry.
        
        Returns:
            The singleton ModelRegistry instance
        """
        if cls._self is None:
            cls._self = cls()
        return cls._self
    
    def __init__(self):
        """Initialize the model registry.
        
        Note: This constructor should not be called directly.
        Use ModelRegistry.self() instead.
        """
        if ModelRegistry._self is not None:
            LOGGER.warning("ModelRegistry initialized directly instead of using self() method")
        
        # Initialize MongoDB connection
        self._init_mongo_connection()
        
        # Load all existing configurations
        self._load_all_configs()

    def _init_mongo_connection(self):
        """Initialize MongoDB connection using pymongo."""
        try:
            mongo_config = MongoConfig.default()
            self._mongo_client = MongoClient(mongo_config.uri)
                
            db_name = mongo_config.authen_source
            
            self._mongo_db = self._mongo_client[db_name]
            self._mongo_collection = self._mongo_db[self._BASE_COLLECTION]
            
            # Test connection
            self._mongo_client.admin.command('ping')
            LOGGER.info("Successfully connected to MongoDB")
            
        except PyMongoError as e:
            LOGGER.error("Failed to connect to MongoDB: %s", str(e))
            self._mongo_client = None
            self._mongo_db = None
            self._mongo_collection = None

    def _load_all_configs(self):
        """Load all configurations from MongoDB."""
        if self._mongo_collection is None:
            LOGGER.warning("MongoDB not connected, skipping config loading")
            return
            
        try:
            # Fetch all configurations
            documents = list(self._mongo_collection.find({}))
            
            for doc in documents:
                key = doc['_id']
                config_data = doc['config_data']
                config_class_name = doc['config_class']
                
                # Dynamically get the config class
                try:
                    # Try to get from current module first
                    if hasattr(sys.modules[__name__], config_class_name):
                        config_class = getattr(sys.modules[__name__], config_class_name)
                    else:
                        # Try to import from the appropriate module
                        module_mapping = {
                            'KeycloakConfig': 'beegen_v1.configs.authen.keycloak_config',
                            'RedisConfig': 'beegen_v1.configs.cache.redis_config',
                            'MilvusConfig': 'beegen_v1.configs.db.vectordb.milvus_config',
                            'MongoConfig': 'beegen_v1.configs.db.mongo_config',
                            'AzureConfig': 'beegen_v1.configs.models.llm_config',
                            'GeminiConfig': 'beegen_v1.configs.models.llm_config',
                            'OpenAIConfig': 'beegen_v1.configs.models.llm_config',
                            'EmbeddingConfig': 'beegen_v1.configs.models.embedding_config',
                            'RerankingConfig': 'beegen_v1.configs.models.reranking_config',
                            'LangfuseConfig': 'beegen_v1.configs.monitor.langfuse_config'
                        }
                        
                        if config_class_name in module_mapping:
                            module = __import__(module_mapping[config_class_name], fromlist=[config_class_name])
                            config_class = getattr(module, config_class_name)
                        else:
                            LOGGER.error("Unknown config class: %s", config_class_name)
                            continue
                    
                    config = config_class.model_validate(config_data)
                    self._configs[key] = config
                    self._instances[key] = ModelFactory.create(config)
                    LOGGER.info("Loaded config for key: %s", key)
                    
                except Exception as e:
                    LOGGER.error("Failed to load config for key %s: %s", key, str(e))
                    
        except PyMongoError as e:
            LOGGER.error("Failed to load configurations from MongoDB: %s", str(e))
        
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

    def _save_to_mongo(self, registry_key: str, config: YamlModel) -> bool:
        """Save a configuration to MongoDB.
        
        Args:
            registry_key: The registry key
            config: The model configuration
            
        Returns:
            True if successful, False otherwise
        """
        if self._mongo_collection is None:
            LOGGER.warning("MongoDB not connected, skipping save operation")
            return False
            
        try:
            # Prepare document
            doc = {
                "_id": registry_key,
                "config_type": config_type_of(config).value,
                "config_class": type(config).__name__,
                "config_data": json.loads(config.model_dump_json(exclude_none=True)),
            }
            
            # Insert or update the configuration
            result = self._mongo_collection.replace_one(
                {"_id": registry_key},
                doc,
                upsert=True
            )
            
            if result.upserted_id:
                LOGGER.info("Inserted configuration to MongoDB: %s", registry_key)
            elif result.modified_count > 0:
                LOGGER.info("Updated configuration in MongoDB: %s", registry_key)
            else:
                LOGGER.info("Configuration already exists in MongoDB: %s", registry_key)
            
            return True
            
        except PyMongoError as e:
            LOGGER.error("Failed to save configuration to MongoDB: %s", str(e))
            return False

    def _remove_from_mongo(self, registry_key: str) -> bool:
        """Remove a configuration from MongoDB.
        
        Args:
            registry_key: The registry key
            
        Returns:
            True if successful, False otherwise
        """
        if self._mongo_collection is None:
            LOGGER.warning("MongoDB not connected, skipping remove operation")
            return False
            
        try:
            result = self._mongo_collection.delete_one({"_id": registry_key})
            
            if result.deleted_count > 0:
                LOGGER.info("Removed configuration from MongoDB: %s", registry_key)
                return True
            else:
                LOGGER.warning("No configuration found in MongoDB to remove: %s", registry_key)
                return False
                
        except PyMongoError as e:
            LOGGER.error("Failed to remove configuration from MongoDB: %s", str(e))
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
    
    def langfuse(self, key: str) -> Langfuse:
        """Get a Langfuse client instance for the given key."""
        _key = key
        if not _key.startswith("langfuse:"):
            _key = f"langfuse:{key}"
            
        return self.get(_key)
    
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
    
    def milvus(self, key: str) -> MilvusEngine:
        """Get a milvus executor instance for the given key."""
        _key = key
        if not key.startswith("milvus:"):
            _key = f"milvus:{key}"
        
        return self.get(_key)
    
    def mongo(self, key: str) -> AsyncMongoEngine:
        """Get an async mongo executor instance for the given key."""
        _key = key
        if not key.startswith("mongo:"):
            _key = f"mongo:{key}"
        
        return self.get(_key)
    
    def sync_mongo(self, key: str) -> MongoEngine:
        """Get a mongo executor instance for the given key."""
        _key = key
        if not key.startswith("mongo:"):
            _key = f"mongo:{key}"
        
        return MongoEngine(self._configs[_key])
    
    def register(self, config: YamlModel, registry_key: Optional[str] = None) -> str:
        """Register a model instance.
        
        Args:
            config: The model configuration
            registry_key: Optional custom registry key
            
        Returns:
            The registry key of the registered configuration
        """
        if not registry_key:
            registry_key = self._key_of(config)
            
        self._instances[registry_key] = ModelFactory.create(config)
        self._configs[registry_key] = config
        
        # Save configuration to MongoDB synchronously
        self._save_to_mongo(registry_key, config)
        
        LOGGER.info("Registered model instance with key: %s", registry_key)
        return registry_key
    
    def remove(self, config: YamlModel) -> bool:
        """Remove a model instance if it exists.
        
        Args:
            config: The model configuration
            
        Returns:
            True if an instance was removed, False otherwise
        """
        registry_key = self._key_of(config)
        if registry_key in self._instances:
            del self._instances[registry_key]
            del self._configs[registry_key]
            
            # Remove from MongoDB synchronously
            self._remove_from_mongo(registry_key)
            
            LOGGER.info("Removed model instance with key: %s", registry_key)
            return True
        return False
    
    def clear(self) -> None:
        """Clear all cached instances and their MongoDB configurations."""
        # Get all keys before clearing
        keys = list(self._instances.keys())
        
        # Clear local cache
        self._instances.clear()
        self._configs.clear()
        
        # Remove all configurations from MongoDB
        for key in keys:
            self._remove_from_mongo(key)
        
        LOGGER.info("Cleared all model instances from registry and MongoDB")

    def close(self):
        """Close MongoDB connection."""
        if self._mongo_client:
            self._mongo_client.close()
            LOGGER.info("MongoDB connection closed")
        

def main():    
    from beegenerate.prompts.samples import DOCUMENT_FILTER_PROMPT
    registry = ModelRegistry.self()
    langfuse = registry.langfuse("beegen")
    print(langfuse)

        
if __name__ == "__main__":
    main()