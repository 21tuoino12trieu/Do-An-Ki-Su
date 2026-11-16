from beegen_v1.configs import (
    LLMType, 
    LLMConfig, 
    CompletionConfig
)
from .base_llm import BaseLLM
# from .openai_model import OpenAICompatibleModel
# from .azure_model import AzureModel
# from .gemini_model import GeminiCompatibleModel
from .openai_sdk_model import OpenAISDKModel
from .azure_sdk_model import AzureSDKModel
from .gemini_sdk_model import GeminiOpenAISDKModel
from beegen_v1.utils.common import raise_error


class LLMFactory:
    r"""Factory class for llm backends."""
    
    @staticmethod
    def create(
        config: LLMConfig,
    ) -> BaseLLM:   
        if config.api_type in [LLMType.VLLM, LLMType.OPENAI]:
            model_class = OpenAISDKModel
        elif config.api_type == LLMType.AZURE:
            model_class = AzureSDKModel
        elif config.api_type == LLMType.GEMINI:
            model_class = GeminiOpenAISDKModel
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