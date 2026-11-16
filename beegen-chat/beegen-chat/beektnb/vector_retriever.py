from beegenerate.embeddings import BaseEmbedder
from beegenerate.vectordb import BaseVectorStore

from beegenerate.vectordb.base import VDBQuery
from typing import List, Dict, Any, Optional

from beegenerate.storage import (
    DocumentStore
)
from beegenerate.retrievers.base import BaseRetriever
from beegenerate.utils.common import join_dicts, transform_bot_id

from beegenerate.loggings import LOGGER
from beegenerate.configs import RetrievalConfig
from beegenerate.embeddings import EmbeddingFactory


class VectorRetriever(BaseRetriever):
    """Retrieves documents using vector similarity search.
    
    Combines vector embeddings, vector storage, and document storage to perform
    semantic similarity search and return matching documents.
    """
    
    def __init__(
        self,
        config: RetrievalConfig,
        vec_store: BaseVectorStore,
        doc_store: DocumentStore
    ) -> None:
        self._embedder = EmbeddingFactory.create(config=config.embedding)
        self._vec_store = vec_store
        self._doc_store = doc_store
        self._config = config
        
    async def run(
        self,
        query: str,
        bot_id: str,
        collection_mongo: str="chunk_data",
        allowed_roles: List[str] = ["L1"],
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Search for similar documents based on query text.

        Args:
            query: Search query text
            bot_id: Id of bot to search in
            **kwargs: Additional search parameters

        Returns:
            List of matching documents, each containing metadata and content
        """
        try:
            # 1. Generate embedding for the query
            embedded_query = await self._embedder.run(query)
            if not embedded_query or len(embedded_query) == 0:
                raise ValueError(f"Failed to generate embedding for query: {query}")
            embedded_query = embedded_query[0]

            # 2. Perform vector similarity search in vector store
            output_fields = ['chunk_id']
            extra_fields = kwargs.get('extra_fields', ['role'])
            output_fields.extend(extra_fields)

            role_ids = self._doc_store.find(
                collection_name="roles",
                query={
                    "role_name": {
                        "$in": allowed_roles
                    },
                    "bot_id": bot_id
                }
            )

            role_ids = [r["_id"] for r in role_ids]
            
            matches = await self._vec_store.run(
                query=VDBQuery(
                    collection=collection_mongo,
                    query_vector=embedded_query,
                    top_k=self._config.top_k,
                    threshold=self._config.threshold,
                    output_fields=output_fields
                ),
                **kwargs
            )
            
            if not matches:
                return []
            
            # 3. Format the matches with Response format: 
            #       {"id":, "score", ....} 
            formatted_chunks = []
            chunk_ids = []
            for _match in matches:
                # if _match.similarity >= threshold:
                # 3.1. Append record dict to result
                _r = {
                    "id": _match.record.id,
                    "score": _match.similarity
                }
                _r.update(_match.record.payload)

                formatted_chunks.append(_r)

                # 3.2. Append the chunk id to list ids
                chunk_ids.append(_r['id'])
                    
            # 4. Mapping Chunk id to its content 
            # milvus does not contain the real content
            # we'll connect to mongo to get 
            mongo_chunks = self._doc_store.find_document_chunks(
                chunk_ids=chunk_ids,
                collection_name=collection_mongo,
                allowed_roles=role_ids
            )
            # join milvus chunks and mongo chunks on 'id'
            results = join_dicts(
                source_data=formatted_chunks,
                lookup_data=mongo_chunks,
                join_key="id"
            )
            return results
            
        except Exception as e:
            LOGGER.error(f"Error during vector search: {str(e)}")
            raise
        
        
async def main():
    from beegenerate.configs import MilvusConfig, EmbeddingConfig, MongoConfig
    from beegenerate.vectordb import MilvusStorage
    import json
    
    retriever = VectorRetriever(
        config=RetrievalConfig(
            embedding=EmbeddingConfig.default(),
            threshold=0,
            top_k=10
        ),
        vec_store = MilvusStorage(config=MilvusConfig.default()),
        doc_store = DocumentStore(config=MongoConfig.default())
    )
    
    docs = await retriever.run(
        query = "Ngân hàng khởi kiện, Tòa án đã thụ lý để giải quyết. Tuy nhiên, trong quá trình tống đạt Giấy báo/Giấy triệu tập cho Bị đơn và Người liên quan Tòa án yêu cầu “Ngân hàng phải tự trực tiếp gửi Giấy triệu tập/Giấy báo của Tòa án cho bị đơn, người liên quan và phải có ký nhận của những người được tống đạt”. Yêu cầu của Tòa án có đúng không?",
        collection = "bot_31b323e9_9946_4e9f_bc4c_84762bae2303",
        top_k=1,
        threshold=0.0,
        allowed_roles=["L1"],
        # extra_fields=['role', 'topic', 'chunk_id'],
        # partition_names=["QA"]
    )
    
    print('-------------------START----------------------')
    for doc in docs:
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        print('-----------------------------------------')
        

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())