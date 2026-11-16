"""
Simplified document service
Unified document search, filtering, and formatting
"""

import asyncio
from typing import List, Dict, Optional, Any

from beegenerate.retrievers import VectorRetriever
from beegenerate.reranks import RerankingFactory
from beegenerate.vectordb import MilvusStorage
from beegenerate.storage import DocumentStore
from beegenerate.configs import RetrievalConfig, RerankingConfig, MilvusConfig, MongoConfig
from beegenerate.loggings import LOGGER


class DocumentService:
    """Simplified document service with unified search and filtering"""

    def __init__(self, bot_id: str, llm_service):
        """
        Initialize document service

        Args:
            bot_id: Bot identifier
            llm_service: LLM service for advanced processing
        """
        self.bot_id = bot_id
        self.collection = f"bot_{bot_id.replace('-', '_')}"
        self.llm_service = llm_service

        # Simple in-memory cache
        self._cache = {}

        # Initialize retrieval components
        self.retriever = VectorRetriever(
            config=RetrievalConfig.default(),
            vec_store=MilvusStorage(config=MilvusConfig.default()),
            doc_store=DocumentStore(config=MongoConfig.default())
        )
        self.reranker = RerankingFactory.create(config=RerankingConfig.default())

    async def search_and_filter(self, query: str, top_k: int = 8) -> List[Dict]:
        """
        Unified search and filtering in single operation
        Combines retrieval, ranking, and relevance filtering

        Args:
            query: Search query
            top_k: Maximum number of documents to return

        Returns:
            List of relevant documents
        """
        cache_key = f"search_filter_{hash(query)}_{top_k}"
        if cache_key in self._cache:
            LOGGER.debug(f"Document cache hit for: {query[:30]}")
            return self._cache[cache_key]

        # Direct search with unified logic
        raw_docs = await self._fetch_and_rank(
            query=query,
            collection=self.collection,
            retrieval_top_k=top_k * 2,
            rerank_top_k=top_k,
            partition_names=['QA', 'document']
        )

        # Apply relevance filtering with list comprehension (faster)
        filtered_docs = [doc for doc in raw_docs if self._is_relevant(query, doc)][:top_k]

        # Cache results
        self._cache[cache_key] = filtered_docs

        LOGGER.info(f"Document search complete: {len(filtered_docs)}/{len(raw_docs)} relevant docs")
        return filtered_docs

    def _is_relevant(self, query: str, doc: Dict) -> bool:
        """
        Simple relevance check

        Args:
            query: Search query
            doc: Document to check

        Returns:
            True if document is relevant
        """
        # Simple relevance check based on score threshold
        score = doc.get('score', 0)
        return score > 0.5

    async def search_documents(self, state: Dict) -> Dict:
        """
        Main document search method for compatibility

        Args:
            state: Current conversation state

        Returns:
            Updated state with document results
        """
        query = state.get('query', '')
        docs = await self.search_and_filter(query, top_k=8)

        state['document_results'] = {
            'final_docs': docs,
            'total_found': len(docs)
        }

        return state

    async def filter_documents_batch(self, docs: List[Dict], query: str) -> Dict:
        """
        Filter documents for compatibility

        Args:
            docs: List of documents to filter
            query: Search query

        Returns:
            Dict with filtered documents
        """
        filtered_docs = [doc for doc in docs if self._is_relevant(query, doc)]

        return {
            'filtered_docs': filtered_docs,
            'total_filtered': len(filtered_docs)
        }

    def _extract_content_simple(self, documents: List[Dict]) -> str:
        """
        Extract content from documents for LLM

        Args:
            documents: List of documents

        Returns:
            Formatted content string
        """
        if not documents:
            return "Không có tài liệu liên quan."

        content_parts = [
            f"Tài liệu {i}:\n{doc.get('content', '')}"
            for i, doc in enumerate(documents[:5], 1)
            if doc.get('content', '')
        ]
        return "\n\n".join(content_parts) if content_parts else "Không có nội dung tài liệu."

    def create_attached_docs_for_llm(self, documents: List[Dict]) -> List[Dict]:
        """
        Create document metadata for LLM

        Args:
            documents: List of documents

        Returns:
            List of document metadata
        """
        return [
            {
                'id': doc.get('id', doc.get('chunk_id', 'unknown')),
                'source': doc.get('source', doc.get('doc', 'unknown')),
                'score': doc.get('score', 0)
            }
            for doc in documents
        ]

    async def _fetch_and_rank(self,
                             query: str,
                             collection: str,
                             retrieval_top_k: int = 20,
                             rerank_top_k: int = 10,
                             partition_names: List[str] = None) -> List[Dict]:
        """
        Fetch and rank documents from specific collection

        Args:
            query: Search query
            collection: Collection name
            retrieval_top_k: Number of docs to retrieve
            rerank_top_k: Number of docs after reranking
            partition_names: List of partition names

        Returns:
            List of ranked documents
        """
        try:
            results = await self.retriever.run(
                query=query,
                bot_id=self.bot_id,
                collection=collection,
                top_k=retrieval_top_k,
                partition_names=partition_names or [],
                # allowed_roles=["L1"]
            )

            if not results:
                return []

            # Rerank if we have more docs than needed
            if len(results) > rerank_top_k:
                reranked = await self.reranker.run(
                    query=query,
                    texts=[doc.get('content', '') for doc in results],
                    top_k=rerank_top_k
                )

                # Map back to original docs
                final_docs = []
                for r in reranked:
                    if r['index'] < len(results):
                        doc = results[r['index']]
                        doc['score'] = r['score']
                        final_docs.append(doc)

                return final_docs

            return results[:rerank_top_k]

        except Exception as e:
            LOGGER.error(f"Fetch and rank failed: {e}")
            return []