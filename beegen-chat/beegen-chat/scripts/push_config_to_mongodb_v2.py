from beegen_v1.const import BEEGEN_ROOT
from beegen_v1.registry.model_registry import ModelRegistry
from beegen_v1.configs import *
import asyncio


async def main():
    registry = ModelRegistry.self()
        
    for key in registry.keys():
        print(key, registry.get(key))
                
    registry.clear()
    
    configs = [
        ("embedding:bge-m3", EmbeddingConfig.default()),
        ("reranker:bge-m3", RerankingConfig.default()),
        ("milvus:chatbot-libra", MilvusConfig.default()),
        ("mongo:aicenter-chatbot", MongoConfig.default()),
        ("mongo:search-semantic", MongoConfig.from_yaml_file(BEEGEN_ROOT / "config/mongo_247.yaml")),
        ("llm:beegen-v1", OpenAIConfig.from_yaml_file(BEEGEN_ROOT / "config/llms/beegen_v1.yaml")),
        ("llm:gpt-4o", AzureConfig.from_yaml_file(BEEGEN_ROOT / "config/llms/azure.yaml")),
        ("llm:gpt-4.1", AzureConfig.from_yaml_file(BEEGEN_ROOT / "config/llms/azure_gpt41.yaml")),
        ("llm:gemini-2.0-flash-lite", GeminiConfig.from_yaml_file(BEEGEN_ROOT / "config/llms/gemini_2.0_flash_lite.yaml")),
        ("langfuse:beegen", LangfuseConfig.default())
    ]
    
    # for item in configs:
    #     print(item)
    
    # register all configs
    for key, config in configs:
        registry.register(config=config, registry_key=key)


if __name__ == "__main__":
    asyncio.run(main())
