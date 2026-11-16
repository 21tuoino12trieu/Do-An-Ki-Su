import asyncio
import time
from typing import List, Dict, AsyncGenerator, Any

from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from beechat.prompts import NORMAL_RAG_ANSWER_PROMPT, EMB_RAG_ANSWER_PROMPT, EKYC_RAG_ANSWER_PROMPT
from beechat.services.llm_service import LLMService
from beechat.utils.error_message import stream_error_message
from beegenerate.vectordb import MilvusStorage
from beegenerate.storage import DocumentStore
from beegenerate.reranks import RerankingFactory
from beegenerate.retrievers import VectorRetriever
from beegenerate.configs import RetrievalConfig, RerankingConfig, MongoConfig, MilvusConfig
from datetime import datetime

from beegenerate.loggings import LOGGER


class DocumentService:
    """
    Service for document retrieval and response generation.
    Simplified to work with dictionary-based state.
    """

    def __init__(self, bot_id: str, llm_service: LLMService):
        """
        Initialize document service with required components.

        Args:
            bot_id: ID of the bot
            llm_service: LLM service for generating responses
        """
        self.bot_id = bot_id
        self.collection_master = f"bot_{bot_id.replace('-', '_')}"
        self.llm_service = llm_service

        # Initialize retrieval components
        self._retriever = VectorRetriever(
            config=RetrievalConfig.default(),
            vec_store=MilvusStorage(config=MilvusConfig.default()),
            doc_store=DocumentStore(config=MongoConfig.default())
        )
        self._reranker = RerankingFactory.create(
            config=RerankingConfig.default()
        )

        # Semaphore for rate limiting
        self._retrieval_semaphore = asyncio.Semaphore(150)

    async def search_documents(self, state: Dict) -> Dict:
        """
        Search for relevant documents based on query.

        Args:
            state: Dictionary containing conversation state

        Returns:
            Updated state with document search results
        """
        query = state['query']
        LOGGER.info(f"Searching documents for query: {query}")

        try:
            async with self._retrieval_semaphore:
                # Search in multiple collections concurrently
                search_tasks = [
                    self._fetch_and_rank(
                        query=query,
                        collection=self.collection_master,
                        retrieval_top_k=16,
                        rerank_top_k=7,
                        partition_names=['document']
                    ),
                    self._fetch_and_rank(
                        query=query,
                        collection=self.collection_master,
                        retrieval_top_k=16,
                        rerank_top_k=7,
                        partition_names=['QA']
                    )
                ]

                # Execute all search tasks concurrently
                search_results = await asyncio.gather(*search_tasks)

                # Combine results
                all_results = []
                for result in search_results:
                    all_results.extend(result)

                # Rerank across all collections
                chunks = [r['content'] for r in all_results]
                ids = [r['id'] for r in all_results]

                final_docs = await self._rank(query=query, chunks_to_rerank=chunks, chunk_ids=ids)

                # Update state with results
                new_state = state.copy()
                new_state['document_results'] = {
                    'search_results': all_results,
                    'final_docs': final_docs,
                    'relevance_score': max([doc.get('score', 0) for doc in final_docs], default=0)
                }

                LOGGER.info(f"Found {len(final_docs)} relevant documents")
                return new_state

        except Exception as e:
            LOGGER.error(f"Error searching documents: {str(e)}")
            # Return original state with empty results on error
            new_state = state.copy()
            new_state['document_results'] = {
                'search_results': [],
                'final_docs': [],
                'relevance_score': 0.0
            }
            return new_state

    async def search_documents_with_summary_query(self, state: Dict) -> Dict:
        """
        Search for relevant documents using both original and summary queries.

        Args:
            state: Dictionary containing conversation state

        Returns:
            Updated state with document search results
        """
        query = state['query']
        summary_query = state.get('conversation_summary_query', query)
        LOGGER.info(f"Searching documents with queries:\nOriginal: {query}\nSummary: {summary_query}")

        try:
            async with self._retrieval_semaphore:
                # Search in multiple collections concurrently
                search_tasks = [
                    # Original query search tasks
                    self._fetch_and_rank(
                        query=query,
                        collection=self.collection_master,
                        retrieval_top_k=12,
                        rerank_top_k=3,
                        partition_names=['document']
                    ),
                    self._fetch_and_rank(
                        query=query,
                        collection=self.collection_master,
                        retrieval_top_k=12,
                        rerank_top_k=3,
                        partition_names=['QA']
                    ),

                    # Summary query search tasks
                    self._fetch_and_rank(
                        query=summary_query,
                        collection=self.collection_master,
                        retrieval_top_k=12,
                        rerank_top_k=3,
                        partition_names=['document']
                    ),
                    self._fetch_and_rank(
                        query=summary_query,
                        collection=self.collection_master,
                        retrieval_top_k=12,
                        rerank_top_k=3,
                        partition_names=['QA']
                    )
                ]

                # Execute all search tasks concurrently
                all_results = await asyncio.gather(*search_tasks)

                # Process results by query type
                original_results = []
                for results in all_results[:2]:  # First 2 tasks are for original query
                    original_results.extend(results)

                summary_results = []
                for results in all_results[2:]:  # Last 2 tasks are for summary query
                    summary_results.extend(results)

                # Combine results with weighting
                # Create a map of document IDs to documents with scores
                combined_docs = {}

                # Process original query results
                for doc in original_results:
                    doc_id = doc['id']
                    if doc_id not in combined_docs:
                        combined_docs[doc_id] = doc.copy()
                    else:
                        combined_docs[doc_id]['score'] = max(combined_docs[doc_id]['score'], doc['score'])

                # Process summary query results with slightly higher weight
                for doc in summary_results:
                    doc_id = doc['id']
                    if doc_id not in combined_docs:
                        combined_docs[doc_id] = doc.copy()
                        # Give slightly higher weight to summary query results for new documents
                        combined_docs[doc_id]['score'] *= 1.05
                    else:
                        # For documents found by both queries, take max score and boost
                        combined_docs[doc_id]['score'] = max(combined_docs[doc_id]['score'], doc['score']) * 1.1

                # Convert back to list and sort by score
                result_list = list(combined_docs.values())
                result_list.sort(key=lambda x: x['score'], reverse=True)

                # Get top results
                final_docs = result_list[:5]

                # Update state with results
                new_state = state.copy()
                new_state['document_results'] = {
                    'original_results': original_results,
                    'summary_results': summary_results,
                    'final_docs': final_docs,
                    'relevance_score': max([doc.get('score', 0) for doc in final_docs], default=0)
                }

                LOGGER.info(f"Found {len(final_docs)} relevant documents using hybrid approach")
                return new_state

        except Exception as e:
            LOGGER.error(f"Error searching documents with summary query: {str(e)}")
            # Return original state with empty results on error
            new_state = state.copy()
            new_state['document_results'] = {
                'original_results': [],
                'summary_results': [],
                'final_docs': [],
                'relevance_score': 0.0
            }
            return new_state

    async def prepare_response(self, state: Dict) -> Dict:
        """
        Prepare response prompt based on retrieved documents.

        Args:
            state: Dictionary containing conversation state

        Returns:
            Updated state with prepared response prompt
        """
        query = state['conversation_summary_query']

        try:
            # Ensure greeting exists in state with a default value
            greeting = state.get('greeting', False)

            # Get document results from state
            document_results = state.get('document_results', {})
            final_docs = document_results.get('final_docs', [])

            if not final_docs:
                LOGGER.warning("No document results available for preparing response")
                new_state = state.copy()
                new_state['prepared_prompt'] = NORMAL_RAG_ANSWER_PROMPT.format(
                    documents="không tìm thấy tài liệu phù hợp",
                    date=datetime.now().date(),
                    question=query,
                    greeting=greeting  # Include greeting parameter
                )
                return new_state

            # Format document texts with numbering
            formatted_docs = []
            for i, doc in enumerate(final_docs):
                # Kiểm tra cả hai trường 'chunk' và 'content' để tránh lỗi
                content = doc.get('chunk', doc.get('content', ''))
                formatted_docs.append(f'TÀI LIỆU {i}:\n{content}')

            # Extract document titles and scores
            doc_topics = {}
            for i, doc in enumerate(final_docs):
                title = formatted_docs[i].split("\n")[1] if i < len(formatted_docs) and "\n" in formatted_docs[
                    i] else ""
                score = doc['score']
                doc_topics[title] = max(doc_topics.get(title, 0), score)

            # Get top document title
            top_doc_title = formatted_docs[0].split("\n")[1] if formatted_docs and "\n" in formatted_docs[0] else ""

            # Select appropriate prompt template
            docs_to_include = formatted_docs  # Include all docs
            template = NORMAL_RAG_ANSWER_PROMPT

            if "Các gói dịch vụ và hạn mức giao dịch của eMB (Internet Banking)" in doc_topics:
                # Use eMB-specific template
                template = EMB_RAG_ANSWER_PROMPT
                docs_to_include = formatted_docs[:3]  # Only include top 3 docs
            elif "Cẩm nang hỗ trợ định danh Khách hàng" in doc_topics:
                if (top_doc_title == "Cẩm nang hỗ trợ định danh Khách hàng" or
                        doc_topics.get("Cẩm nang hỗ trợ định danh Khách hàng", 0) > 0.85):
                    # Use eKYC-specific template
                    template = EKYC_RAG_ANSWER_PROMPT

            # Combine documents with separator
            documents_text = '\n------------------\n'.join(
                docs_to_include) if docs_to_include else "không tìm thấy tài liệu phù hợp"

            # Format the final prompt
            prepared_prompt = template.format(
                documents=documents_text,
                date=datetime.now().date(),
                question=query,
                greeting=greeting  # Include greeting parameter
            )

            # Update state with prepared prompt
            new_state = state.copy()
            new_state['prepared_prompt'] = prepared_prompt

            return new_state

        except Exception as e:
            LOGGER.error(f"Error preparing response: {str(e)}")
            # Return original state with a default prompt on error
            new_state = state.copy()
            # Ensure we include greeting even in error case
            new_state['prepared_prompt'] = NORMAL_RAG_ANSWER_PROMPT.format(
                documents="không tìm thấy tài liệu phù hợp",
                date=datetime.now().date(),
                question=query,
                greeting=state.get('greeting', False)  # Include greeting with fallback
            )
            return new_state

    async def generate_standard_response(self, state: Dict) -> AsyncGenerator[ChatCompletionChunk, None]:
        """
        Generate and stream response based on documents.

        Args:
            state: Dictionary containing conversation state

        Yields:
            ChatCompletionChunk: Streamed response chunks
        """
        try:
            # Check if we need to search for documents
            if 'document_results' not in state or not state['document_results'].get('final_docs'):
                LOGGER.info("No document search results, searching with summary query")
                state = await self.search_documents_with_summary_query(state)

            # Check if we need to prepare prompt
            if 'prepared_prompt' not in state:
                LOGGER.info("No prepared prompt, preparing now")
                state = await self.prepare_response(state)

            # Get prompt and document references
            prompt = state.get('prepared_prompt', '')
            docs = state.get('document_results', {}).get('final_docs', [])

            if not prompt:
                LOGGER.error("No prompt available for response generation")
                async for chunk in stream_error_message(self.llm_service,
                                                        "Xin lỗi, tôi không thể tạo câu trả lời phù hợp."):
                    yield chunk
                return

            async for chunk in self.llm_service.llm_stream(
                    prompt_template=prompt,
                    docs=docs,
                    sleep=0.01
            ):
                yield chunk

        except Exception as e:
            LOGGER.error(f"Error generating standard response: {str(e)}")
            async for chunk in stream_error_message(self.llm_service,
                                                    "Xin lỗi, tôi không thể tạo câu trả lời phù hợp."):
                yield chunk

    async def _fetch_and_rank(
            self,
            query: str,
            collection: str,
            role: str = "L1",
            topic: str = "default",
            retrieval_top_k: int = 1,
            retrieval_threshold: float = 0,
            rerank_top_k: int = 1,
            rerank_threshold: float = 0,
            **kwargs
    ) -> List[Dict]:
        """
        Retrieve and rank documents from vector database.

        Args:
            query: Search query
            collection: Collection name
            role: User role
            topic: Topic category
            retrieval_top_k: Number of documents to retrieve
            retrieval_threshold: Minimum retrieval score
            rerank_top_k: Number of documents after reranking
            rerank_threshold: Minimum reranking score
            **kwargs: Additional parameters for retriever

        Returns:
            List of ranked documents search_documents_with_summary_query
        """
        # Get role hierarchy
        roles = [role]
        if role == "L2":
            roles.append("L1")
        elif role == "L3":
            roles.extend(["L1", "L2"])

        # Perform retrieval
        records = await self._retriever.run(
            query=query,
            collection=collection,
            top_k=retrieval_top_k,
            threshold=retrieval_threshold,
            allowed_roles=roles,
            **kwargs
        )

        # # Perform reranking
        # import json
        # LOGGER.info(json.dumps([r['content'] for r in records], indent=2, ensure_ascii=False))
        
        reranked_records = await self._reranker.run(
            query=query,
            texts=[r['content'] for r in records],
            top_k=rerank_top_k,
            threshold=rerank_threshold
        )
        
        # LOGGER.info(f"Reranks: {reranked_records}")

        # Construct final documents
        final_docs = []
        for r in reranked_records:
            record = records[r['index']]
            record['score'] = r['score']
            final_docs.append(record)

        return final_docs

    async def _rank(self, query: str, chunks_to_rerank: List[str], chunk_ids: List[str]) -> List[Dict]:
        """
        Rerank document chunks.

        Args:
            query: Search query
            chunks_to_rerank: List of document chunks
            chunk_ids: List of chunk IDs

        Returns:
            List of ranked document chunks
        """
        if not chunks_to_rerank:
            return []

        # Get reranking scores
        reranked_scores = await self._reranker.run(
            query=query,
            texts=chunks_to_rerank,
            top_k=min(5, len(chunks_to_rerank))
        )

        # Map scores to original chunks
        return [
            {
                "id": chunk_ids[score_info["index"]],
                "chunk": chunks_to_rerank[score_info["index"]],
                "score": score_info["score"]
            }
            for score_info in reranked_scores
        ]