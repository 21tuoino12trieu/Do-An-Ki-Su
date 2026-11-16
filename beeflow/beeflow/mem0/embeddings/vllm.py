import asyncio
from typing import Literal, Optional

from mem0.configs.embeddings.base import BaseEmbedderConfig
from mem0.embeddings.base import EmbeddingBase

from beegen.embeddings.vllm_embedding import VLLMEmbedding as BeegenVLLMEmbedding
from beegen.configs import EmbeddingConfig as BeegenEmbeddingConfig

class VLLMEmbedding(EmbeddingBase):
    """
    An ASYNCHRONOUS mem0-compatible wrapper that uses the existing
    `beegen.embeddings.vllm_embedding.VLLMEmbedding` client.
    """
    def __init__(self, config: Optional[BaseEmbedderConfig] = None):
        """
        Initializes the VLLMEmbedding wrapper.
        
        Args:
            config (Optional[BaseEmbedderConfig]): Configuration object for the embedder.
        """
        super().__init__(config)

        model = self.config.model
        base_url = self.config.vllm_base_url
        api_key = self.config.api_key
        dimensions = self.config.embedding_dims

        beegen_config = BeegenEmbeddingConfig(
            model=model,
            base_url=base_url,
            api_key=api_key,
            dimensions=dimensions
        )

        self.client = BeegenVLLMEmbedding(config=beegen_config)

    def embed(self, text: str, memory_action: Optional[Literal["add", "search", "update"]] = None) -> list[float]:
        """
        Get the embedding for the given text by calling the beegen client.
        This method is synchronous but calls an underlying async method.

        Args:
            text (str): The text to embed.
            memory_action (Optional): The type of memory action (unused).

        Returns:
            list[float]: The embedding vector.
        """
        text = text.replace("\n", " ")
        
        # Since this sync method is called from a thread without a running
        # event loop (via asyncio.to_thread), we can use asyncio.run().
        result = asyncio.run(self.client.run(texts=[text]))
        
        # Assuming the result is a dict with an "embeddings" key holding a list of lists
        return result["embeddings"][0]

def main():
    """
    A simple test function to demonstrate the VLLMEmbedding wrapper.
    """
    from mem0.configs.embeddings.base import BaseEmbedderConfig

    print("--- Testing VLLMEmbedding Wrapper ---")
    
    # This simulates how mem0's factory would create the config object.
    embedder_config = BaseEmbedderConfig(
        model="model/bge-m3",
        vllm_base_url="http://10.1.87.71:30044/v1/embeddings",
        api_key="mb123456789",
        embedding_dims=1024
    )
    
    # Instantiate the wrapper with the config
    embedder = VLLMEmbedding(config=embedder_config)
    
    print(f"✅ Embedder instance of type '{type(embedder).__name__}' created.")
    print(f"✅ Underlying beegen client of type '{type(embedder.client).__name__}' is being used.")

    test_text = "Tổng giám đốc của MBBank là ai?"
    print(f"\nEmbedding text: '{test_text}'")
    
    try:
        embedding_vector = embedder.embed(test_text)
        print(f"✅ Successfully generated embedding vector.")
        print(f"Vector dimensions: {len(embedding_vector)}")
        print(f"Vector preview: {embedding_vector[:5]}...")
    except Exception as e:
        print(f"❌ Failed to generate embedding: {e}")


if __name__ == "__main__":
    main()
