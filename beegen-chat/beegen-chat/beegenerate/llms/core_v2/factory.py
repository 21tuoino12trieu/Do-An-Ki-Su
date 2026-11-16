from beegenerate.configs import (
    LLMType, 
    LLMConfig, 
    CompletionConfig
)
from .base import BaseLLM
from .openai_model import OpenAICompatibleModel
from .azure_model import AzureModel
from .gemini_model import GeminiCompatibleModel
from beegenerate.utils.common import raise_error


class LLMFactory:
    r"""Factory class for llm backends."""
    
    @staticmethod
    def create(
        config: LLMConfig,
    ) -> BaseLLM:   
        if config.api_type in [LLMType.VLLM, LLMType.OPENAI]:
            model_class = OpenAICompatibleModel
        elif config.api_type == LLMType.AZURE:
            model_class = AzureModel
        elif config.api_type == LLMType.GEMINI:
            model_class = GeminiCompatibleModel
        else:
            raise_error(ValueError(f"Unsupport Model: {config.api_type}"))
            
        return model_class(
            config=config
        )
        

async def main():
    llm = LLMFactory.create(LLMConfig.default())
    
    async for chunk in llm.stream(
        messages=[{"role": "user", "content": "Hello"}]
    ):
        print(chunk)
        
        
if __name__ == "__main__":
    import asyncio
    asyncio.run(main())