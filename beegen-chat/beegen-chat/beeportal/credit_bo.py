from beegenerate.prompts import (
    CREDIT_SYSTEM_PROMPT,
    CREDIT_VERIFY_DOCUMENT_PROMPT,
    QUERY_COMPLEXITY_ANALYSIS_PROMPT,
    CREDIT_REASONING_PROMPT
)
from beegenerate.utils.abbreviationHandler import AbbreviationHandler
from beegenerate.embeddings import EmbeddingFactory
from beegenerate.retrievers.vector_retriever import VectorRetriever
from beegenerate.vectordb import MilvusStorage
from beegenerate.reranks import RerankingFactory
from beegenerate.storage import (
    DocumentStore,
    BotStore
)

from beegenerate.llms.llm_executor import LLMExecutor
from openai import AsyncStream
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from openai.types.chat import ChatCompletionChunk

from typing import List, Dict, TypeVar, Optional, AsyncGenerator, Any, Tuple
from typing_extensions import AsyncIterator

import time
import re
import json
import asyncio
from pydantic import BaseModel
from pathlib import Path
from datetime import datetime
from beegenerate.utils.common import transform_bot_id

from beegenerate.loggings import LOGGER
from langfuse.decorators import observe, langfuse_context

# Create a generic type that must be a subclass of BaseModel
T = TypeVar('T', bound=BaseModel)


class QueryInfo(BaseModel):
    query: str
    purpose: str

class QueryAnalysisResult(BaseModel):
    complexity: str  # "simple" or "complex"
    queries: List[QueryInfo]

class DocumentResult(BaseModel):
    docs: List[Dict]
    relevance_score: float


class CreditBot:
    def __init__(
            self,
            bot_config: Dict,
            vec_store: MilvusStorage,
            doc_store: DocumentStore,
            bot_store: BotStore
    ):
        """Initialize CreditBot with required components and configurations."""
        self.bot_config = bot_config
        self._llm = LLMExecutor(
            primary_config=self.bot_config['llm'],
            config_store=bot_store
        )
        self._retriever = VectorRetriever(
            config=bot_config['retrieval'],
            vec_store=vec_store,
            doc_store=doc_store
        )
        self._reranker = RerankingFactory.create(config=bot_config['reranking'])

        # Semaphores for rate limiting
        self._retrieval_semaphore = asyncio.Semaphore(20)
        self._llm_semaphore = asyncio.Semaphore(10)
        self._analysis_semaphore = asyncio.Semaphore(5)  # For query analysis
        self._verify_semaphore = asyncio.Semaphore(5)  # For document verification

        # Cache for document results
        self._doc_cache = {}

        # Initialize abbreviation handler
        self._abbr_handler = AbbreviationHandler()

    @observe()
    def _format_documents(self, documents: List[Dict]) -> str:
        """Format a list of documents into a single string with separators."""
        return "\n-----------------------------\n".join(
            [d['content'] for d in documents]
        )

    @observe()
    def _create_attached_docs(self, documents: List[Dict]) -> List[Dict]:
        """Create metadata for documents to be attached to LLM requests."""
        return [
            {
                "id": doc['id'],
                "source": doc.get('doc', '')
            }
            for doc in documents
        ]

    @observe()
    async def _stream_llm_response(self, messages: List[Dict]) -> str:
        """Stream response from LLM and concatenate chunks into a single string."""
        try:
            response_text = ""
            async for chunk in self._llm.run(messages=messages):
                if chunk.choices and chunk.choices[0].delta.content:
                    response_text += chunk.choices[0].delta.content
            return response_text
        except Exception as e:
            LOGGER.error(f"Error streaming LLM response: {e}")
            raise RuntimeError(f"Failed to get LLM response: {str(e)}")

    @staticmethod
    @observe()
    def _get_role_hierarchy(role: str) -> List[str]:
        """Get list of roles based on hierarchy."""
        role_hierarchy = {
            "L1": ["L1"],
            "L2": ["L2", "L1"],
            "L3": ["L3", "L2", "L1"]
        }
        return role_hierarchy.get(role, ["L1"])

    @observe()
    async def _analyze_query_complexity(
            self,
            query: str,
            initial_docs: DocumentResult
    ) -> QueryAnalysisResult:
        """
        Analyze query complexity based on initial documents.
        Determine if query is simple or needs to be broken down.
        """
        async with self._analysis_semaphore:
            try:
                # If no documents found, we need to break down the query
                if not initial_docs.docs:
                    return QueryAnalysisResult(
                        complexity="complex",
                        queries=[QueryInfo(query=query, purpose="original query")]
                    )

                # Prepare the complexity analysis request
                doc_text = self._format_documents(initial_docs.docs)

                messages = [
                    {"role": "system", "content": QUERY_COMPLEXITY_ANALYSIS_PROMPT},
                    {"role": "user", "content": f"Câu hỏi: {query}\n\nTài liệu đã tìm thấy:\n{doc_text}"}
                ]

                response_text = await self._stream_llm_response(messages)

                try:
                    # Parse the JSON response
                    result = json.loads(response_text)

                    # Validate the structure
                    if "complexity" not in result or "queries" not in result:
                        raise ValueError("Missing required fields in response")

                    # Convert to our model
                    queries = [QueryInfo(**q) for q in result["queries"]]

                    return QueryAnalysisResult(
                        complexity=result["complexity"],
                        queries=queries
                    )
                except Exception as e:
                    LOGGER.warning(f"Failed to parse query complexity analysis: {e}")
                    # Default to treating as simple query if parsing fails
                    return QueryAnalysisResult(
                        complexity="simple",
                        queries=[QueryInfo(query=query, purpose="original query")]
                    )

            except Exception as e:
                LOGGER.error(f"Error in query complexity analysis: {e}")
                # Safe fallback
                return QueryAnalysisResult(
                    complexity="simple",
                    queries=[QueryInfo(query=query, purpose="original query")]
                )

    @observe()
    async def _verify_documents_batch(self, query: str, documents: List[Dict]) -> List[bool]:
        """
        Verify multiple documents' relevance in a single LLM request.

        Args:
            query: The user's query
            documents: List of documents to verify

        Returns:
            List of boolean values indicating relevance of each document
        """
        async with self._verify_semaphore:
            try:
                if not documents:
                    return []

                # Format all documents into a single message
                verification_prompt = CREDIT_VERIFY_DOCUMENT_PROMPT
                formatted_docs = []
                for idx, doc in enumerate(documents, 1):
                    formatted_docs.append(f"Document {idx}:\n{doc['content']}")

                all_docs = "\n\n".join(formatted_docs)

                # Create a single verification message
                messages = [
                    {"role": "system", "content": verification_prompt},
                    {"role": "user", "content": f"Query: {query}\n\nDocuments to evaluate:\n{all_docs}\n\n" +
                                                "Requirement: Evaluate each document and return results in format <output>doc1:co_lien_quan/khong_lien_quan|doc2:co_lien_quan/khong_lien_quan|...</output>"}
                ]

                response_text = await self._stream_llm_response(messages)

                # Extract verification results
                match = re.search(r'<output>(.*?)</output>', response_text)
                if not match:
                    return [False] * len(documents)

                results = match.group(1).strip().split('|')
                return [result.split(':')[1].strip() == "co_lien_quan" for result in results]

            except Exception as e:
                LOGGER.error(f"Error in batch document verification: {e}")
                return [False] * len(documents)

    @observe()
    async def _get_relevant_documents(
            self,
            queries: List[QueryInfo],
            role_ids: List[str],
            topic: str,
            cache_key: Optional[str] = None
    ) -> DocumentResult:
        """
        Retrieve and verify relevant documents for queries.
        """
        if cache_key and cache_key in self._doc_cache:
            return self._doc_cache[cache_key]

        async with self._retrieval_semaphore:
            try:
                all_docs = []
                max_score = 0.0

                # Process each query
                for query_info in queries:
                    retrieval_results = await self._retriever.run(
                        query=query_info.query,
                        bot_id=self.bot_config['id'],
                        collection=f"bot_{transform_bot_id(self.bot_config['id'])}",
                        top_k=self.bot_config['retrieval'].top_k,
                        threshold=self.bot_config['retrieval'].threshold,
                        allowed_roles=role_ids
                    )

                    # Rerank results
                    reranked = await self._reranker.run(
                        query=query_info.query,
                        texts=[r['content'] for r in retrieval_results],
                        top_k=self.bot_config['reranking'].top_k,
                        threshold=self.bot_config['reranking'].threshold
                    )

                    # Update documents with reranking scores
                    for rank_result in reranked:
                        doc = retrieval_results[rank_result['index']]
                        doc['score'] = rank_result['score']
                        all_docs.append(doc)
                        max_score = max(max_score, rank_result['score'])

                # Batch verify documents
                verification_results = await self._verify_documents_batch(
                    query=queries[0].query,  # Use primary query for verification
                    documents=all_docs
                )

                # Filter relevant documents
                verified_docs = []
                for idx, is_relevant in enumerate(verification_results):
                    if is_relevant and idx < len(all_docs):
                        verified_docs.append(all_docs[idx])
                        max_score = max(max_score, all_docs[idx]['score'])

                result = DocumentResult(
                    docs=verified_docs,
                    relevance_score=max_score
                )

                if cache_key:
                    self._doc_cache[cache_key] = result

                return result

            except Exception as e:
                LOGGER.error(f"Error retrieving documents: {e}")
                return DocumentResult(docs=[], relevance_score=0.0)

    @observe()
    async def _get_combined_documents(
            self,
            original_query: str,
            analyzed_queries: List[QueryInfo],
            role_ids: List[str],
            topic: str,
            cache_key: Optional[str] = None
    ) -> DocumentResult:
        """
        Retrieve documents from both original query and analyzed queries,
        then combine and verify them.
        """
        combined_cache_key = f"{cache_key}_combined" if cache_key else None

        if combined_cache_key and combined_cache_key in self._doc_cache:
            return self._doc_cache[combined_cache_key]

        try:
            # Get documents for original query
            original_doc_task = self._get_relevant_documents(
                queries=[QueryInfo(query=original_query, purpose="original")],
                role_ids=role_ids,
                topic=topic
            )

            # Get documents for analyzed queries
            analyzed_doc_task = self._get_relevant_documents(
                queries=analyzed_queries,
                role_ids=role_ids,
                topic=topic
            )

            # Execute tasks concurrently
            original_docs, analyzed_docs = await asyncio.gather(
                original_doc_task,
                analyzed_doc_task
            )

            # Combine documents and prepare for batch verification
            combined_docs = {}
            documents_to_verify = []

            # Process original docs
            for doc in original_docs.docs:
                doc_id = doc['id']
                if doc_id not in combined_docs or doc['score'] > combined_docs[doc_id]['score']:
                    combined_docs[doc_id] = doc
                    documents_to_verify.append(doc)

            # Process analyzed docs
            for doc in analyzed_docs.docs:
                doc_id = doc['id']
                if doc_id not in combined_docs or doc['score'] > combined_docs[doc_id]['score']:
                    combined_docs[doc_id] = doc
                    documents_to_verify.append(doc)

            # Batch verify combined documents
            verification_results = await self._verify_documents_batch(
                query=original_query,  # Use original query for verification
                documents=documents_to_verify
            )

            # Process verification results
            final_docs = []
            max_score = 0

            for idx, is_relevant in enumerate(verification_results):
                if is_relevant and idx < len(documents_to_verify):
                    doc = documents_to_verify[idx]
                    final_docs.append(doc)
                    max_score = max(max_score, doc['score'])

            result = DocumentResult(
                docs=final_docs,
                relevance_score=max_score
            )

            if combined_cache_key:
                self._doc_cache[combined_cache_key] = result

            return result

        except Exception as e:
            LOGGER.error(f"Error in combined documents retrieval: {e}")
            return DocumentResult(docs=[], relevance_score=0.0)

    @observe()
    async def _generate_reasoned_response(
            self,
            original_query: str,
            analyzed_queries: List[QueryInfo],
            doc_result: DocumentResult,
            abbreviations: Dict[str, str]
    ) -> Tuple[str, str, str]:
        """
        Generate a reasoned response based on the query, sub-queries, and documents.
        Returns reliability assessment, reasoning and final answer.
        """
        try:
            # Check if we have any documents
            if not doc_result.docs:
                LOGGER.warning("No relevant documents found for query")
                return "low", "Không tìm thấy tài liệu liên quan", "Xin lỗi, tôi không tìm thấy đủ thông tin để trả lời câu hỏi của bạn. Vui lòng liên hệ trực tiếp với bộ phận Tín dụng để được hỗ trợ."

            # Format the queries
            formatted_queries = "\n".join([
                f"- {q.query} (Purpose: {q.purpose})" for q in analyzed_queries
            ])

            # Format the documents
            formatted_docs = self._format_documents(doc_result.docs)

            # Format abbreviations
            abbr_text = self._format_abbreviations(abbreviations)

            # Prepare the reasoning request
            messages = [
                {"role": "system", "content": CREDIT_REASONING_PROMPT},
                {"role": "user", "content": f"""
                Câu hỏi gốc: {original_query}

                Các câu hỏi phân tích:
                {formatted_queries}

                Tài liệu liên quan:
                {formatted_docs}

                Từ viết tắt:
                {abbr_text}

                Yêu cầu: Phân tích tất cả thông tin trên và đưa ra câu trả lời đầy đủ với phần giải thích suy luận.
                Đánh giá độ tin cậy: high (đủ thông tin để trả lời chính xác), medium (có thông tin nhưng chưa đầy đủ), low (không đủ thông tin để trả lời)
                Nếu độ tin cậy là "low", hãy từ chối trả lời.
                """}
            ]

            response = await self._stream_llm_response(messages)

            # Extract reliability, reasoning and answer
            reliability_match = re.search(r'<reliability>(.*?)</reliability>', response, re.DOTALL)
            reasoning_match = re.search(r'<reasoning>(.*?)</reasoning>', response, re.DOTALL)
            answer_match = re.search(r'<answer>(.*?)</answer>', response, re.DOTALL)

            reliability = reliability_match.group(1).strip() if reliability_match else "low"
            reasoning = reasoning_match.group(1).strip() if reasoning_match else ""
            answer = answer_match.group(1).strip() if answer_match else response

            # Force response refusal if reliability is low
            if reliability == "low":
                LOGGER.warning(f"Low reliability assessment for query: {original_query}")
                answer = "Xin lỗi, tôi không tìm thấy đủ thông tin để trả lời câu hỏi của bạn. Vui lòng liên hệ trực tiếp với bộ phận Tín dụng để được hỗ trợ."

            return reliability, reasoning, answer

        except Exception as e:
            LOGGER.error(f"Error generating reasoned response: {e}")
            return "low", f"Error: {str(e)}", "Xin lỗi, hệ thống không thể xử lý yêu cầu của bạn lúc này. Vui lòng thử lại sau."

    def _format_abbreviations(self, abbreviations_dict: Dict[str, str]) -> str:
        """Format abbreviations dictionary into readable text."""
        if not abbreviations_dict:
            return ""
        return "\nDanh sách từ viết tắt được sử dụng:\n" + "\n".join(
            f"- {abbr}: {meaning}" for abbr, meaning in abbreviations_dict.items()
        )

    @observe()
    async def _generate_response(
            self,
            query: str,
            doc_result: DocumentResult,
            abbreviations: Dict[str, str]
    ) -> List[Dict]:
        """Generate final response messages."""
        try:
            current_date = datetime.now().strftime('%Y-%m-%d')

            # Format documents and abbreviations
            documents_text = self._format_documents(doc_result.docs)
            abbr_text = self._format_abbreviations(abbreviations)

            # Create system message with all context
            system_content = CREDIT_SYSTEM_PROMPT.format(
                date=current_date,
                documents=documents_text,
                abbreviations_explanation=abbr_text
            ).strip()

            return [
                {"role": "system", "content": system_content},
                {"role": "user", "content": query}
            ]

        except Exception as e:
            LOGGER.error(f"Error generating response: {e}")
            return [
                {"role": "system", "content": CREDIT_SYSTEM_PROMPT.format(
                    date=datetime.now().strftime('%Y-%m-%d'),
                    documents="",
                    abbreviations_explanation=""
                )},
                {"role": "user", "content": query}
            ]

    @observe(name="CreditBot")
    async def run(
            self,
            messages: List[Dict],
            role_ids: List[str] = [],
            topic: str = "default",
            **kwargs
    ) -> AsyncIterator[ChatCompletionChunk]:
        """Main execution pipeline with enhanced query analysis and strict document verification."""
        langfuse_context.update_current_trace(name="CreditBot")
        final_response_output = ""
        try:
            query = messages[-1]['content']
            LOGGER.info(f"Processing query: {query}")

            # 1. First, get initial documents based on original query
            initial_queries = [QueryInfo(query=query, purpose="original query")]
            cache_key = f"{query}_{role_ids[-1]}_{topic}"

            LOGGER.info("Retrieving initial documents...")
            initial_docs = await self._get_relevant_documents(
                queries=initial_queries,
                role_ids=role_ids,
                topic=topic,
                cache_key=f"{cache_key}_initial"
            )

            # Check if we have any documents at all - if not, immediately return "no information" response
            if not initial_docs.docs:
                LOGGER.warning("No documents found for query, responding with refusal message")
                refusal_message = "Xin lỗi, tôi không tìm thấy đủ thông tin để trả lời câu hỏi của bạn. Vui lòng liên hệ trực tiếp với bộ phận Tín dụng để được hỗ trợ."

                # Create chunks from the refusal message
                chunk_size = 10  # Characters per chunk
                for i in range(0, len(refusal_message), chunk_size):
                    content = refusal_message[i:i + chunk_size]
                    chunk = ChatCompletionChunk(
                        id="credit_bot_chunk",
                        object="chat.completion.chunk",
                        created=int(time.time()),
                        model=self.bot_config['llm'].model,
                        choices=[{
                            "index": 0,
                            "delta": {"content": content},
                            "finish_reason": None if i + chunk_size < len(refusal_message) else "stop"
                        }]
                    )
                    final_response_output += str(chunk.choices[0].delta.content)
                    yield chunk
                    await asyncio.sleep(0.01)
                langfuse_context.update_current_observation(output=final_response_output)
                return

            # 2. Analyze query complexity with initial documents
            LOGGER.info("Analyzing query complexity...")
            analysis_result = await self._analyze_query_complexity(
                query=query,
                initial_docs=initial_docs
            )

            LOGGER.info(
                f"Query complexity: {analysis_result.complexity}, Generated {len(analysis_result.queries)} sub-queries")

            # 3. For complex queries, get combined documents from all sub-queries
            doc_result = initial_docs
            if analysis_result.complexity == "complex" and len(analysis_result.queries) > 1:
                LOGGER.info("Getting combined documents for complex query...")
                doc_result = await self._get_combined_documents(
                    original_query=query,
                    analyzed_queries=analysis_result.queries,
                    role_ids=role_ids,
                    topic=topic,
                    cache_key=cache_key
                )

            LOGGER.info(f"Retrieved {len(doc_result.docs)} relevant documents")

            # Recheck document count after combined retrieval
            if not doc_result.docs:
                LOGGER.warning("No relevant documents found after combined retrieval, responding with refusal")
                refusal_message = "Xin lỗi, tôi không tìm thấy đủ thông tin để trả lời câu hỏi của bạn. Vui lòng liên hệ trực tiếp với bộ phận Tín dụng để được hỗ trợ."
                # Create chunks from the refusal message
                chunk_size = 10
                for i in range(0, len(refusal_message), chunk_size):
                    content = refusal_message[i:i + chunk_size]
                    chunk = ChatCompletionChunk(
                        id="credit_bot_chunk",
                        object="chat.completion.chunk",
                        created=int(time.time()),
                        model=self.bot_config['llm'].model,
                        choices=[{
                            "index": 0,
                            "delta": {"content": content},
                            "finish_reason": None if i + chunk_size < len(refusal_message) else "stop"
                        }]
                    )
                    final_response_output += str(chunk.choices[0].delta.content)
                    yield chunk
                    await asyncio.sleep(0.01)
                langfuse_context.update_current_observation(output=final_response_output)
                return

            # 4. Process abbreviations
            all_text = "\n".join(d['content'] for d in doc_result.docs)
            abbreviations = self._abbr_handler.find_unique_abbreviations(all_text)

            # 5. Generate reasoned response for complex queries, or direct response for simple ones
            final_response = ""
            if analysis_result.complexity == "complex" and len(analysis_result.queries) > 1:
                LOGGER.info("Generating reasoned response for complex query...")
                reliability, reasoning, final_response = await self._generate_reasoned_response(
                    original_query=query,
                    analyzed_queries=analysis_result.queries,
                    doc_result=doc_result,
                    abbreviations=abbreviations
                )
                LOGGER.info(f"Generated response with reliability: {reliability}, reasoning: {reasoning[:100]}...")

                # For low reliability, log this fact
                if reliability == "low":
                    LOGGER.warning(f"Low reliability assessment for query: {query}")
            else:
                # For simple queries, use the standard response generator but still verify document completeness
                LOGGER.info("Generating direct response for simple query...")
                # First check if the documents are sufficient
                reliability, reasoning, direct_answer = await self._generate_reasoned_response(
                    original_query=query,
                    analyzed_queries=[QueryInfo(query=query, purpose="original")],
                    doc_result=doc_result,
                    abbreviations=abbreviations
                )

                if reliability == "low":
                    LOGGER.warning(f"Low reliability for simple query: {query}")
                    final_response = direct_answer
                else:
                    # Use the standard response generator for normal flow
                    response_messages = await self._generate_response(
                        query=query,
                        doc_result=doc_result,
                        abbreviations=abbreviations
                    )

                    # Stream the response if no pre-generated response
                    async with self._llm_semaphore:
                        if not final_response:
                            # Use the normal streaming path
                            async for chunk in self._llm.run(
                                    messages=response_messages,
                                    docs=self._create_attached_docs(doc_result.docs)
                            ):
                                yield chunk
                            return

            # If we have a pre-generated response, we need to convert it into chunks
            # to maintain compatibility with the expected return type
            if final_response:
                # Simulate chunks for the pre-generated response
                LOGGER.info("Converting pre-generated response to chunks...")
                chunk_size = 10  # Characters per chunk
                for i in range(0, len(final_response), chunk_size):
                    content = final_response[i:i + chunk_size]
                    # Create a simple ChatCompletionChunk with the content
                    chunk = ChatCompletionChunk(
                        id="credit_bot_chunk",
                        object="chat.completion.chunk",
                        created=int(time.time()),
                        model=self.bot_config['llm'].model,
                        choices=[{
                            "index": 0,
                            "delta": {"content": content},
                            "finish_reason": None if i + chunk_size < len(final_response) else "stop"
                        }]
                    )
                    final_response_output += str(chunk.choices[0].delta.content)
                    yield chunk
                    # Small delay to simulate streaming
                    await asyncio.sleep(0.01)
                langfuse_context.update_current_observation(output=final_response_output)

        except Exception as e:
            LOGGER.exception(f"Error in main pipeline: {str(e)}")
            # In case of any error, provide a safe fallback response
            refusal_message = "Xin lỗi, hệ thống không thể xử lý yêu cầu của bạn lúc này. Vui lòng thử lại sau."
            chunk = ChatCompletionChunk(
                id="credit_bot_chunk",
                object="chat.completion.chunk",
                created=int(time.time()),
                model="fallback",
                choices=[{
                    "index": 0,
                    "delta": {"content": refusal_message},
                    "finish_reason": "stop"
                }]
            )
            yield chunk
            langfuse_context.update_current_observation(level="ERROR", output=str(e))

    @observe()
    async def shutdown(self):
        """Cleanup resources during shutdown."""
        try:
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            [task.cancel() for task in tasks]
            await asyncio.gather(*tasks, return_exceptions=True)
            self._doc_cache.clear()
        except Exception as e:
            LOGGER.error(f"Error during shutdown: {str(e)}")

async def main():
    """Example usage of CreditBot."""
    from beegenerate.configs import MongoConfig, MilvusConfig
    
    bot_id = "3af716b6-4909-433c-9301-05d79b9e1f03"
    bot_store = BotStore(MongoConfig.default())
    bot_config = bot_store.fetch_bot_details(bot_id=bot_id)

    bot = CreditBot(
        bot_config=bot_config,
        vec_store=MilvusStorage(MilvusConfig.default()),
        doc_store=DocumentStore(MongoConfig.default()),
        bot_store=bot_store
    )

    try:
        response_text = ""
        async for chunk in bot.run(
                messages=[
                    {"role": "user", "content": "Đối với tài sản bảo đảm là hàng hóa luân chuyển, tần suất đơn vị kinh doanh phải trực tiếp kiểm tra kho hàng là bao nhiêu?"}
                ],
                role_ids=["L1"],
                topic="default"
        ):
            if chunk.choices and chunk.choices[0].delta.content:
                response_text += chunk.choices[0].delta.content

        LOGGER.info(f"Response: {response_text}")

    finally:
        await bot.shutdown()


if __name__ == "__main__":
    asyncio.run(main())