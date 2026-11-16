from typing import Optional
from beegen_v1.configs.yaml_model import YamlModel
from beegen_v1.configs import EmbeddingConfig


class RetrievalConfig(YamlModel):
    """
    Configuration for vector-based document retrieval.

    This class defines the parameters used to control the behavior of document
    retrieval using vector embeddings for semantic similarity search.

    Attributes:
        embedding (EmbeddingConfig): Configuration for the embedding model used
            to convert text into vector representations.

        threshold (Optional[float]): Minimum similarity score threshold for retrieved
            documents. Documents with scores below this threshold will be filtered out.
            Defaults to 0, meaning no filtering based on similarity score.

        top_k (Optional[int]): Maximum number of documents to retrieve. This limits
            the number of results returned by the vector similarity search.
            Defaults to 10.
    """
    embedding: EmbeddingConfig
    threshold: Optional[float] = 0
    top_k: Optional[int] = 10
    

    @classmethod
    def default(cls) -> 'RetrievalConfig':
        """Load default config"""        
        return RetrievalConfig(
            embedding=EmbeddingConfig.default()
        )
    

if __name__ == "__main__":
    log_config = RetrievalConfig.default()
    print(log_config)