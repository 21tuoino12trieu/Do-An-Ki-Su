from beegenerate.configs import (
    LLMType, 
    LLMConfig, 
    CompletionConfig
)
from .base import BaseLLM
from .vllm_model import VllmOpenAIModel
from .azure_model import AzureOpenAIModel
from beegenerate.utils.common import raise_error


class LLMFactory:
    r"""Factory class for llm backends."""
    
    @staticmethod
    def create(
        config: LLMConfig,
    ) -> BaseLLM:   
        if config.api_type == LLMType.VLLM:
            model_class = VllmOpenAIModel
        elif config.api_type == LLMType.AZURE:
            model_class = AzureOpenAIModel
        else:
            raise_error(ValueError(f"Unsupport Model: {config.api_type}"))
            
        return model_class(
            config=config
        )