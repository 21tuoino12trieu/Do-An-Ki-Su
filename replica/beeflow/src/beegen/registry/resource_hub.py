import hashlib
from pathlib import Path
import os
from typing import Dict, Optional, ClassVar, Any
from beegen.cache.redis_engine import RedisEngine
from beegen.configs.event_streaming.kafka_config import KafkaConfig
from beegen.configs.mcp.mcp_config import MCPConfig
from beegen.configs.memory.memory_config import MemoryConfig
from beegen.event_streaming.kafka_engine import KafkaEngine
from beegen.loggings import LOGGER
from beegen.configs.yaml_model import YamlModel
from beegen.mcp.base_server import BaseMCPServer
from beegen.memory.base import BaseMemory
from beegen.storage.s3.s3_engine import S3Engine
from beegen.storage.sql.base_adapter import BaseSQLAdapter
from beegen.utils.crypto import Crypto
from beegen.registry.resource_factory import ResourceFactory
from beegen.configs.authen.keycloak_config import KeycloakConfig
from beegen.configs.cache.redis_config import RedisConfig
from beegen.configs.storage.vectordb.milvus_config import MilvusConfig
from beegen.configs.storage.mongo_config import MongoConfig
from beegen.configs.models.llm_config import AzureConfig, GeminiConfig, LLMConfig, OpenAIConfig
from beegen.configs.models.embedding_config import EmbeddingConfig
from beegen.configs.models.reranking_config import RerankingConfig
from beegen.configs.monitor.langfuse_config import LangfuseConfig
from beegen.configs.storage.s3_config import S3Config
from beegen.configs.memory.mem0_config import Mem0MemoryConfig
from beegen.configs.storage.sql_config import SQLConfig
from beegen.llms.base_llm import BaseLLM
from beegen.embeddings.base_embedding import BaseEmbedder
from beegen.reranks.base_reranker import BaseReranker
from beegen.vectordb.milvus_engine import MilvusEngine
from beegen.storage.mongo.mongo_engine import AsyncMongoEngine, MongoEngine
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
    S3 = "s3"
    MCP = "mcp"
    MEM0 = "mem0"
    SQL = "sql"
    KAFKA = "kafka"
    
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
        LangfuseConfig: ConfigType.LANGFUSE,
        S3Config: ConfigType.S3,
        RedisConfig: ConfigType.REDIS,
        MCPConfig: ConfigType.MCP,
        Mem0MemoryConfig: ConfigType.MEM0,
        SQLConfig: ConfigType.SQL,
        KafkaConfig: ConfigType.KAFKA
    }
    
    config_class = type(config_obj)
    if config_class in config_type_mapping:
        return config_type_mapping[config_class]
    else:
        raise ValueError(f"Unrecognized config type: {config_class.__name__}")


class ResourceHub:
    """Registry for model instances using local storage.
    
    This class is implemented as a singleton to ensure only one instance exists
    throughout the application. It can register any type of model with any type
    of configuration that supports model_dump_json().
    """
    
    # Singleton instance
    _self: ClassVar[Optional['ResourceHub']] = None
    
    # Dictionary to store model instances by their configuration hash
    _instances: Dict[str, Any] = {}
    _configs: Dict[str, Any] = {}
    
    # MongoDB collection name for storing configurations
    _BASE_COLLECTION = "beegen_resource_configs"
    
    # MongoDB client for data persistence
    _mongo_client: Optional[MongoClient] = None
    _mongo_db = None
    _mongo_collection = None
    
    @classmethod
    def self(cls) -> 'ResourceHub':
        """Get the singleton instance of the registry.
        
        Returns:
            The singleton ModelRegistry instance
        """
        if cls._self is None:
            cls._self = cls()
        return cls._self
    
    def __init__(self):
        """Initialize the model registry.

        If a secret is provided (or env BEEGEN_RESOURCE_HUB_SECRET exists), configs are
        stored encrypted. If not, plaintext is stored (backward compatible).
        
        Note: This constructor should not be called directly.
        Use ModelRegistry.self() instead.
        """
        if ResourceHub._self is not None:
            LOGGER.warning("ModelRegistry initialized directly instead of using self() method")
        
        secret = os.getenv("BEEGEN_RESOURCE_HUB_SECRET")
        self._crypto = Crypto(secret) if secret else None

        # Initialize MongoDB connection
        self._init_mongo_connection()


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
            LOGGER.error("MongoDB not connected, skipping config loading")
            return
            
        try:
            # Fetch all configurations
            documents = list(self._mongo_collection.find({}))
            
            for doc in documents:
                key = doc['_id']
                cls_name = doc['config_class']

                raw = doc.get("config_data")   # legacy plaintext
                enc = doc.get("enc")           # new encrypted bundle
                
                if enc is not None:
                    if not self._crypto:
                        LOGGER.warning("Encrypted config found but no secret set: %s", key)
                        continue
                    try:
                        config_data = self._crypto.decrypt(enc)
                    except Exception as e:
                        LOGGER.warning("Decrypt failed for %s: %s", key, e)
                        continue
                else:
                    config_data = raw

                # Dynamically get the config class
                try:
                    # Try to get from current module first
                    if hasattr(sys.modules[__name__], cls_name):
                        config_class = getattr(sys.modules[__name__], cls_name)
                    else:
                        # Try to import from the appropriate module
                        module_mapping = {
                            # 'KeycloakConfig': 'beegen.configs.authen.keycloak_config',
                            # 'RedisConfig': 'beegen.configs.cache.redis_config',
                            # 'MilvusConfig': 'beegen.configs.db.vectordb.milvus_config',
                            # 'MongoConfig': 'beegen.configs.db.mongo_config',
                            # 'AzureConfig': 'beegen.configs.models.llm_config',
                            # 'GeminiConfig': 'beegen.configs.models.llm_config',
                            # 'OpenAIConfig': 'beegen.configs.models.llm_config',
                            # 'EmbeddingConfig': 'beegen.configs.models.embedding_config',
                            # 'RerankingConfig': 'beegen.configs.models.reranking_config',
                            # 'LangfuseConfig': 'beegen.configs.monitor.langfuse_config',
                            # 'S3Config': 'beegen'
                        }
                        
                        if cls_name in module_mapping:
                            module = __import__(module_mapping[cls_name], fromlist=[cls_name])
                            config_class = getattr(module, cls_name)
                        else:
                            LOGGER.warning("Unknown config class: %s", cls_name)
                            continue
                    
                    config = config_class.model_validate(config_data)
                    self._configs[key] = config
                    self._instances[key] = ResourceFactory.create(config)
                    LOGGER.info("Loaded config for key: %s", key)
                    
                except Exception as e:
                    LOGGER.error("Failed to load config for key %s: %s", key, str(e))
                    
        except PyMongoError as e:
            LOGGER.error("Failed to load configurations from MongoDB: %s", str(e))

    def _load_single_config(self, key: str) -> bool:
        """Load a single configuration from MongoDB.

        Args:
            key: The registry key to load

        Returns:
            True if loaded successfully, False otherwise
        """
        if self._mongo_collection is None:
            LOGGER.error("MongoDB not connected, cannot load config: %s", key)
            return False

        try:
            doc = self._mongo_collection.find_one({"_id": key})

            if not doc:
                LOGGER.error("Config not found in MongoDB: %s", key)
                return False

            cls_name = doc['config_class']
            raw = doc.get("config_data")
            enc = doc.get("enc")

            if enc is not None:
                if not self._crypto:
                    LOGGER.error("Encrypted config found but no secret set: %s", key)
                    return False
                try:
                    config_data = self._crypto.decrypt(enc)
                except Exception as e:
                    LOGGER.error("Decrypt failed for %s: %s", key, e)
                    return False
            else:
                config_data = raw

            # Get config class
            try:
                if hasattr(sys.modules[__name__], cls_name):
                    config_class = getattr(sys.modules[__name__], cls_name)
                else:
                    module_mapping = {}
                    if cls_name in module_mapping:
                        module = __import__(module_mapping[cls_name], fromlist=[cls_name])
                        config_class = getattr(module, cls_name)
                    else:
                        LOGGER.error("Unknown config class: %s", cls_name)
                        return False

                # Create instance
                config = config_class.model_validate(config_data)
                self._configs[key] = config
                self._instances[key] = ResourceFactory.create(config)
                LOGGER.info("Lazy loaded config: %s", key)
                return True

            except Exception as e:
                LOGGER.error("Failed to load config %s: %s", key, str(e))
                return False

        except PyMongoError as e:
            LOGGER.error("MongoDB error loading config %s: %s", key, str(e))
            return False
        
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
            cfg = json.loads(config.model_dump_json(exclude_none=True))
            if self._crypto:
                doc = {
                    "_id": registry_key,
                    "config_type": config_type_of(config).value,
                    "config_class": type(config).__name__,
                    "enc": self._crypto.encrypt(cfg),   # encrypted storage
                }
            else:
                doc = {
                    "_id": registry_key,
                    "config_type": config_type_of(config).value,
                    "config_class": type(config).__name__,
                    "config_data": cfg,                 # legacy plaintext
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
    
    def rotate_encryption_key(self, old_secret: str) -> int:
        """
        Re-encrypt all documents with a new passphrase. Plaintext docs will
        also be encrypted.

        Returns:
            number of documents successfully updated.
        """
        if self._mongo_collection is None:
            LOGGER.error("MongoDB not connected")
            return 0

        old_box = Crypto(old_secret) if old_secret else None
        new_box = Crypto(os.getenv("BEEGEN_RESOURCE_HUB_SECRET"))

        updated = 0
        for doc in self._mongo_collection.find({}):
            _id = doc["_id"]

            # get plaintext dict
            if "enc" in doc and doc["enc"] is not None:
                if not old_box:
                    LOGGER.error("Doc %s is encrypted but no old_secret supplied", _id)
                    continue
                try:
                    cfg = old_box.decrypt(doc["enc"])
                except Exception as e:
                    LOGGER.error("Skip %s: cannot decrypt with old_secret (%s)", _id, e)
                    continue
            else:
                cfg = doc.get("config_data")
                if cfg is None:
                    continue

            # write back encrypted with new_secret
            self._mongo_collection.replace_one(
                {"_id": _id},
                {
                    "_id": _id,
                    "config_type": doc.get("config_type"),
                    "config_class": doc.get("config_class"),
                    "enc": new_box.encrypt(cfg),
                },
                upsert=True,
            )
            updated += 1

        # switch runtime secret so future reads/writes use the new key
        self._crypto = new_box
        LOGGER.info("Key rotation done: %d documents updated", updated)
        return updated
    
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
            # Try lazy loading if not cached
            if not self._load_single_config(key):
                raise KeyError(f"key '{key}' not found in registry or MongoDB!")

        return self._instances[key]
    
    def langfuse(self, key: str) -> Langfuse:
        """Get a Langfuse client instance for the given key."""
        _key = key
        if not _key.startswith("langfuse:"):
            _key = f"langfuse:{key}"
            
        return self.get(_key)
    
    def s3(self, key: str) -> S3Engine:
        """Get a S3 client instance for the given key."""
        _key = key
        if not _key.startswith("s3:"):
            _key = f"s3:{key}"
            
        return self.get(_key)

    def kafka(self, key: str) -> KafkaEngine:
        """Get a kafka instance for the given key."""
        _key = key
        if not key.startswith("kafka:"):
            _key = f"kafka:{key}"
        
        return self.get(_key)
    
    def redis(self, key: str) -> RedisEngine:
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

        if _key not in self._configs:
            self.get(_key)
        
        return MongoEngine(self._configs[_key])
    
    def sql(self, key: str) -> BaseSQLAdapter:
        """Get a sql adapter instance for the given key."""
        _key = key
        if not key.startswith("sql:"):
            _key = f"sql:{key}"
        
        return self.get(_key)


    def mcp(self, key: str) -> BaseMCPServer:
        """Get a mcp server instance for the given key."""
        _key = key
        if not key.startswith("mcp:"):
            _key = f"mcp:{key}"
        
        return self.get(_key)
    
    def mem(self, key: str) -> BaseMemory:
        """Get a Memory client instance for the given key."""
        _key = key
        if not _key.startswith("mem:"):
            _key = f"mem:{key}"
            
        return self.get(_key)
    
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
            
        self._instances[registry_key] = ResourceFactory.create(config)
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
        

RESOURCE_HUB = ResourceHub.self()


def main():
    """
    Main function to demonstrate registering a memory configuration.
    This will load the default mem0 configuration and register it in the ResourceHub,
    which also saves it to the MongoDB collection.
    """
    # Load the default memory configuration (which is mem0)
    config = Mem0MemoryConfig.default()
    
    registry = ResourceHub.self()
    
    # Register the configuration with a specific key.
    registry_key = "mem:mem0"
    register_result = registry.register(config=config, registry_key=registry_key)
    
    print(f"Registered memory config with key: {register_result}")

    # Verify it was registered
    if registry.has(registry_key):
        print(f"Successfully verified that key '{registry_key}' exists in the registry.")
        # Retrieve using the shorthand method
        retrieved_instance = registry.mem("mem0")
        print(f"Successfully retrieved instance via mem('default'): {type(retrieved_instance)}")
    else:
        print(f"Failed to find key '{registry_key}' in the registry.")
        
def main():    
    RESOURCE_HUB.register(LangfuseConfig.default(), "langfuse:beepaste")
    print(RESOURCE_HUB.langfuse("beepaste"))
    # RESOURCE_HUB.rotate_encryption_key("beegen")

if __name__ == "__main__":
    main()