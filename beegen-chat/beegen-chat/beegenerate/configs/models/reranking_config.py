from enum import Enum
from typing import Optional
from beegenerate.configs.yaml_model import YamlModel
from beegenerate.const import BEEGEN_ROOT


class RerankingType(Enum):
    COHERE = "cohere"
    TEXT_EMBEDDING_INFERENCE = "tei"
    VLLM = "vllm"


class RerankingConfig(YamlModel):
    """
    Configuration for text reranking services.

    This class defines the configuration parameters for text reranking APIs,
    which are used to improve the relevance of search results or document rankings.

    Attributes:
        api_key (str): The API key for authenticating with the reranking service.
            Default is "YOUR_RERANK_API_KEY". This must be set to a valid API key.

        base_url (Optional[str]): The base URL for the API endpoint.
            Default is None. If not provided, the default URL of the service will be used.

        model (Optional[str]): The specific model to use for reranking.
            Default is None. If not provided, the default model of the service will be used.

    The class includes a field validator for the api_key to ensure it's properly set.

    Examples:
        Basic configuration:
        ```yaml
        api_key: "your_actual_api_key_here"
        ```

        Advanced configuration:
        ```yaml
        api_key: "your_actual_api_key_here"
        base_url: "https://api.rerank-service.com/v1"
        model: "rerank-v2"
        ```

    Note:
        The api_key must be set to a valid key. If it's not set or set to the default value,
        an error will be raised with instructions on how to properly set it in the configuration file.
    """
    api_type: RerankingType = RerankingType.TEXT_EMBEDDING_INFERENCE
    api_key: str
    base_url: Optional[str] = None
    model: Optional[str] = None
    threshold: Optional[float] = 0
    top_k: Optional[int] = 3
    
    @classmethod
    def default(cls) -> 'RerankingConfig':
        """Load default config"""
        dict = RerankingConfig.read_yaml(BEEGEN_ROOT / "config/reranker.yaml")
        
        return RerankingConfig(**dict)
    

if __name__ == "__main__":
    # log_config.to_yaml_file(Path('log_config.yaml'))
    log_config = RerankingConfig.default()
    print(log_config)