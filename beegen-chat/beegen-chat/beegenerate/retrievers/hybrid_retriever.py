from beegenerate.embeddings import BaseEmbedder
from beegenerate.reranks import BaseReranker
from beegenerate.vectordb import BaseVectorStore
from beegenerate.loggings import LOGGER

from beegenerate.configs import (
    RetrievalConfig
)
from beegenerate.vectordb.base import VDBQuery
from typing import List, Dict, Any, Optional

from beegenerate.storage import MONGO_STORAGE
from beegenerate.retrievers.base import BaseRetriever

from beegenerate.searchs.bm25_search import BM25Search

import asyncio
import time


class HybridRetriever:
    def __init__(
        self,
        storage: BaseVectorStore,
        embedding: BaseEmbedder,
        bm25search: BM25Search,
        reranker: Optional[BaseReranker] = None
    ):
        self._storage = storage
        self._embedding = embedding
        self._bm25search = bm25search
        self._reranker = reranker

    
    async def query_vector_db(
        self, 
        collection: str, 
        query_vector: List[float], 
        retrieval_top_k: int, 
        output_fields: List[str], 
        **kwargs
    ) -> List[str]:
        vector_results_header = await self._storage.run(
            VDBQuery(
                collection=collection,
                query_vector=query_vector,
                top_k=retrieval_top_k,
                output_fields=output_fields
            ),
            **kwargs
        )

        chunk_ids = [item.record.payload['chunk_id'] for item in vector_results_header]

        return chunk_ids

    async def run(
        self,
        query: str,
        collections: List[str],
        config: RetrievalConfig,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """ The function performs the task of searching for documents similar to the query
            Ideal:
                Split document with two components (Header and Content)
                Header: 
                    + Use BM25 to search top-k similar documents
                    + Use milvus to search top-k similar documents (Dense Embedding use Header Text)
                Content:
                    + Use milvus to search top-k similar documents (Dense Embedding use Content Text)

                Concat documents, forward to rerank model, select to top-k

            Args:
                query (str): The search query string used to find relevant vector embeddings
                collections: list collection use retrieved
                config (RetrievalConfig): Configuration settings for the retrieval process,
                    including parameters like search limit and similarity threshold
            Returns:
                List[Dict[str, Any]]: A list of dictionaries containing the retrieved results.
                    Each dictionary contains metadata and content from the matched
        """
        try:
            chunk_ids_vectors = []
            # 1. Generate embedding for the query
            query_vectors = await self._embedding.run(query)

            print("Type vecter: ", type(query_vectors[0]))
            # Perform matching to get list chunk_ids
            tasks = [self.query_vector_db(collection, query_vectors[0], config.retrieval_top_k, ["chunk_id"], **kwargs) for collection in collections]
            tasks.append(self._bm25search.run(query, config.retrieval_top_k))

            vector_results = await asyncio.gather(*tasks)

            for res in vector_results:
                chunk_ids_vectors += res

            # Combine chunk
            chunk_ids_retrieved = set(chunk_ids_vectors)

            documents_mongo = MONGO_STORAGE.find(
                collection_name="hybrid_documents",
                query={
                    "chunk_id": {
                        "$in": list(chunk_ids_retrieved)
                    }
                }
            )

            if len(documents_mongo) == 0:
                return []

            documents_retrieved_ids, documents_retrieved_texts = [], []
            for item in documents_mongo:
                documents_retrieved_ids.append(item['chunk_id'])
                documents_retrieved_texts.append(item['text'])

            results = await self._reranker.run(query, documents_retrieved_texts)
            
            # 5. Combine reranked results with original documents
            final_results = []
            for res in results[:config.rerank_top_k]:
                idx = res['index']
                r = {
                    "id": documents_retrieved_ids[idx],
                    "chunk": documents_retrieved_texts[idx],
                    "score": res["score"],
                }

                final_results.append(r)
            
            return final_results

        except Exception as e :
            LOGGER.error(f"Error during vector search: {str(e)}")
            raise


async def main():
    from beegenerate.configs import BotConfig, INFRA_CONFIG
    from pathlib import Path
    from beegenerate.vectordb import MilvusStorage
    from beegenerate.embeddings import EmbeddingFactory
    from beegenerate.reranks import RerankingFactory
    
    config = BotConfig.from_yaml_file(Path("config/bot.yaml"))

    bm25search = BM25Search()
    bm25search.load_model_bm25(path="external/model_bm25s")

    retriever = HybridRetriever(
        storage=MilvusStorage(config=INFRA_CONFIG.milvus),
        embedding=EmbeddingFactory.create(config.embedding),
        bm25search=bm25search,
        reranker=RerankingFactory.create(config.reranking)
    )

    docs = await retriever.run(
        query = "Gói eMB định danh mức 1 chuyển được tiền không?",
        collections = ["hybrid_search_header", "hybrid_search_content"],
        config = RetrievalConfig(
            retrieval_top_k=10,
            rerank_top_k=5
        ),
    )

    print('-------------------START----------------------')
    for doc in docs:
        print(doc['id'])
        print(doc['score'])
        print(doc['chunk'])
        print('-----------------------------------------')
        
if __name__ == "__main__":
    import asyncio
    asyncio.run(main())