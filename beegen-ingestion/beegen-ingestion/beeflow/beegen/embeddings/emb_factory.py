from beegen.configs import (
    EmbeddingConfig, 
    EmbeddingType
)
from beegen.embeddings import (
    BaseEmbedder,
    TEIEmbedding,
    VLLMEmbedding
)
from beegen.utils.common import raise_error


class EmbeddingFactory:
    r"""Factory class for embedding model backends
    
    Raises:
        ValueError: in case the provided model type is unknown.
    """
    
    @staticmethod
    def create(
        config: EmbeddingConfig
    ) -> BaseEmbedder:
        if config.api_type == EmbeddingType.TEXT_EMBEDDING_INFERENCE:
            model_class = TEIEmbedding
        elif config.api_type == EmbeddingType.VLLM:
            model_class = VLLMEmbedding
        else:
            raise_error(ValueError(f"Unsupport Model: {config.api_type}"))
        return model_class(config)
    
    
async def main():
    
    embed = EmbeddingFactory.create(
        config=EmbeddingConfig.default()
    )
    
    # Test with Vietnamese text
    test_text = "tổng giám đốc của MB là ai ?"
    vectors = await embed.run(test_text)
    print(f"Generated embedding vectors: {vectors}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())