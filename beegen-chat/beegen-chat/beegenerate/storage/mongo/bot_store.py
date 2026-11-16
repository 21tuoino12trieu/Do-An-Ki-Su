from beegenerate.configs.db.mongo_config import MongoConfig
from typing import Dict, List, Optional, Any
import json
from .mongodb import MongoStorage
from beegenerate.configs import (
    LLMConfig,
    EmbeddingConfig,
    RerankingConfig,
    RetrievalConfig
)
from beegenerate.loggings import LOGGER


class BotStore(MongoStorage):
    """
    A class for managing bot configurations using MongoDB as the storage backend.
    
    This class provides functionality to store, retrieve, and manage bot configurations
    including their LLM settings, embedding parameters, reranking configurations,
    and retrieval settings.
    
    Attributes:
        config (Optional[MongoConfig]): MongoDB configuration settings
    """
    
    def __init__(
        self, 
        config: Optional[MongoConfig] = None
    ) -> None:
        """
        Initialize the BotStore instance.
        
        Args:
            config (Optional[MongoConfig]): Configuration for MongoDB connection.
                If None, default configuration will be used.
        """
        super().__init__(config)
        
    def fetch_active_bots(self) -> Dict[str, Dict]:
        """
        Retrieve and process configurations for all available bots.
        
        This method fetches all bot records from the database that have metadata
        and attempts to load their configurations. Failed configurations are logged
        but don't prevent other configurations from being loaded.
        
        Returns:
            Dict[str, Dict[str, Any]]: A dictionary mapping bot IDs to their 
                respective configurations.
        
        Example:
            >>> bot_store = BotStore()
            >>> configs = bot_store.get_all_bot_configs()
            >>> print(configs['bot_id']['llm'].base_url)
        """
        bot_records = self.find(
            collection_name="botinfo",
            query={"metadata": {"$exists": True}}
        )

        bot_manager: Dict[str, Dict[str, Any]] = {}

        for record in bot_records:
            if record['metadata']:  # Check if metadata is not empty
                bot_id = record['_id']
                try:
                    bot_manager[bot_id] = self.fetch_bot_details(bot_id=bot_id)
                    LOGGER.info(
                        f"Successfully added bot id: {bot_id} "
                        f"base llm = {bot_manager[bot_id]['llm'].base_url}"
                    )
                except Exception as e:
                    LOGGER.error(f"Error initializing bot_id {bot_id}: {str(e)}")

        return bot_manager
        
    def fetch_bot_details(
        self,
        bot_id: str
    ) -> Dict[str, Any]:
        """
        Retrieve and process bot-specific configuration from MongoDB.
        
        This method fetches configuration parameters including LLM configuration,
        embedding generation settings, reranking parameters, document retrieval
        settings, and bot definition/system prompt.
        
        Args:
            bot_id (str): The unique identifier for the bot whose configuration
                should be retrieved.
        
        Returns:
            Dict[str, Any]: A dictionary containing processed configuration settings
                with the following keys:
                - id: bot identifier
                - llm: LLM configuration
                - reranking: reranking parameters
                - retrieval: document retrieval settings
                - definition: bot system prompt
        
        Raises:
            ValueError: If the specified bot doesn't exist or is not configured.
        
        Example:
            >>> bot_store = BotStore()
            >>> config = bot_store.acquire_config('my_bot_id')
            >>> print(config['llm'].base_url)
        """
        bot_info = self.find(
            collection_name="botinfo",
            query={"_id": bot_id}
        )
        
        if not bot_info:
            error_msg = f"Bot {bot_id} does not exist."
            LOGGER.error(error_msg)
            raise ValueError(error_msg)
        
        bot_info = bot_info[0]
        metadata = bot_info.pop('metadata', None)
        
        if not metadata:
            error_msg = f"Bot {bot_id} is not configured yet."
            LOGGER.error(error_msg)
            raise ValueError(error_msg)

        # Restructure completion settings
        metadata["llm"]['completion'] = metadata.pop("completion")
        
        return {
            "id": bot_id,
            "llm": LLMConfig.create_config(metadata['llm']),
            "reranking": RerankingConfig(
                **metadata['reranking'],
                threshold=metadata['retrieval']['rerank_threshold'],
                top_k=metadata['retrieval']['rerank_top_k']
            ),
            "retrieval": RetrievalConfig(
                embedding=EmbeddingConfig(**metadata['embedding']),
                threshold=metadata['retrieval']['retrieval_threshold'],
                top_k=metadata['retrieval']['retrieval_top_k']
            ),
            "definition": metadata.get('system_prompt', "không có mô tả nào được cung cấp"),
            "mongo": metadata.get('mongo', {})
        }


if __name__ == "__main__":
    from beegenerate.configs import MongoConfig
    import json

    # Khởi tạo BotStore
    bot_store = BotStore(config=MongoConfig.default())

    # ID của bot bạn muốn kiểm tra
    bot_id = "4f338efc-95c3-4528-849b-49cd863821b5"  # Thay thế bằng ID thực tế

    try:
        # Lấy config của bot
        bot_config = bot_store.fetch_bot_details(bot_id=bot_id)

        # In ra các khóa chính của config
        print(f"\nBot ID: {bot_id}")
        print("Config Keys:", list(bot_config.keys()))

        # In ra thông tin LLM
        llm_config = bot_config["llm"]
        print("\nLLM Config:")
        print(f"- base_url: {llm_config.base_url}")
        print(f"- model: {llm_config.model}")
        print(f"- provider: {llm_config.provider}")

        # In ra một phần system prompt
        definition = bot_config.get("definition", "")
        print("\nSystem Prompt (first 100 chars):", definition[:100], "...")

    except Exception as e:
        print(f"Error: {str(e)}")