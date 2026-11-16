from beegenerate.prompts import (
    SYSTEM_PROMPT_INTENT,
    SYSTEM_PROMPT_CHIT_CHAT,
    SYSTEM_PROMPT_VERIFY_DOCUMENT,
    SYSTEM_PROMPT_NON_CHIT_CHAT,
    SYSTEM_PROMPT_REFUSE,
    SYSTEM_PROMPT_RELEVANCE_TOPIC,
    SYSTEM_PROMPT_QUERY_CLARITY
)

from beegenerate.embeddings import EmbeddingFactory
from beegenerate.retrievers.vector_retriever import VectorRetriever
from beegenerate.vectordb import MilvusStorage
from beegenerate.reranks import RerankingFactory
from beegenerate.storage import (
    DocumentStore,
    BotStore
)

from beegenerate.llms.llm_executor_langfuse import LLMExecutor

from openai import AsyncStream
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from typing import (List,Dict,TypeVar,Optional,AsyncGenerator, Any)

import time

import re
import json
import asyncio
from pydantic import BaseModel
from pathlib import Path
from datetime import datetime
from beegenerate.utils.common import transform_bot_id

from beegenerate.loggings import LOGGER
from prometheus_client import Counter, Histogram
from langfuse.decorators import observe, langfuse_context


# Create a generic type that must be a subclass of BaseModel
T = TypeVar('T', bound=BaseModel)

# Metrics
LATENCY = Histogram('bot_latency_seconds', 'Time spent processing request')
ERRORS = Counter('bot_errors_total', 'Total errors by type')
REQUESTS = Counter('bot_requests_total', 'Total requests processed')
INTENT_METRICS = Counter('bot_intent_total', 'Total intents by type', ['intent'])


class InputQuery(BaseModel):
    query: str
    intent: str
    greeting: bool


class DocumentResult(BaseModel):
    docs: List[Dict]
    relevance_score: float


class BeehiBot:
    def __init__(
            self,
            bot_config: Dict,
            vec_store: MilvusStorage,
            doc_store: DocumentStore,
            bot_store: BotStore
    ):
        """Initialize BeehiBot with required components and configurations."""
        self.bot_config = bot_config
        self._llm = LLMExecutor(
            primary_config=self.bot_config['llm'],
            config_store=bot_store
        )

        # # Debug: Print bot_config structure
        # print("Bot config:", bot_config)
        # print("LLM config:", bot_config['llm'])

        self._retriever = VectorRetriever(
            config=bot_config['retrieval'],
            vec_store=vec_store,
            doc_store=doc_store
        )
        self._reranker = RerankingFactory.create(config=bot_config['reranking'])

        # Semaphores for rate limiting
        self._retrieval_semaphore = asyncio.Semaphore(20)
        self._llm_semaphore = asyncio.Semaphore(10)
        self._intent_semaphore = asyncio.Semaphore(5)

        # Cache for document results
        self._doc_cache = {}

        # Monitoring
        self.log_messages = []

    def _format_documents(self, documents: List[Dict]) -> str:
        """Format a list of documents into a single string with separators."""
        return "\n-----------------------------\n".join(
            [d['content'] for d in documents]
        )

    def _create_attached_docs(self, documents: List[Dict]) -> List[Dict]:
        """Create metadata for documents to be attached to LLM requests."""
        attached_docs = []
        for doc in documents:
            chunk_info = {"id": doc['id']}
            if 'doc' in doc:
                chunk_info['source'] = doc['doc']
            attached_docs.append(chunk_info)
        return attached_docs

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
    
    @observe(as_type="analysis")
    async def _analyze_query_clarity(self, query: str, doc_result: DocumentResult) -> Dict:
        """Analyze how well the query can be answered with available documents."""
        try:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT_QUERY_CLARITY},
                {"role": "user", "content": f"Question: {query}\nDocuments: {self._format_documents(doc_result.docs)}"}
            ]
            # LOGGER.info(f"Tài liệu: {doc_result.docs}")
            response = await self._stream_llm_response(messages)
            match = re.search(r'<clarity>(.*?)</clarity>', response)
            clarity = match.group(1) if match else "unclear"

            # Use maximum score for relevance check
            has_relevant_docs = (
                    len(doc_result.docs) > 0 and
                    doc_result.relevance_score > self.bot_config.get('threshold', {}).get('doc_relevance', 0.01)
            )

            return {
                "clarity_level": clarity,
                "has_relevant_docs": has_relevant_docs
            }

        except Exception as e:
            LOGGER.error(f"Error analyzing query clarity: {e}")
            return {"clarity_level": "unclear", "has_relevant_docs": False}

    async def _generate_clarification_prompt(self, query: str, doc_result: DocumentResult) -> str:
        """
        Generate clarification prompt by analyzing documents and suggesting possible topics.

        Args:
            query: Original user query
            doc_result: Document results containing relevant documents

        Returns:
            Formatted clarification prompt with suggested topics
        """
        try:
            # Analyze documents to extract main topics

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT_RELEVANCE_TOPIC},
                {"role": "user",
                 "content": f"Câu hỏi: {query}\nTài liệu cung cấp: {self._format_documents(doc_result.docs)}"}
            ]

            # Get topics from LLM
            response = await self._stream_llm_response(messages)
            match = re.search(r'<topics>(.*?)</topics>', response)
            topics = match.group(1).split('|') if match else []

            # Format topics into question
            if topics:
                topics_text = ", ".join(topics[:-1])
                if len(topics) > 1:
                    topics_text += f" hoặc {topics[-1]}"
                else:
                    topics_text = topics[0]

                return f"Bạn có thể chia sẻ rõ hơn về nhu cầu của mình được không? 🤔\nBạn muốn tìm hiểu thông tin về một trong những chủ đề sau:  {topics_text} đúng không?"

            # Fallback if no topics extracted
            return "Bạn có thể chia sẻ rõ hơn về nhu cầu của mình được không? 🤔"
        except Exception as e:
            LOGGER.error(f"Error generating clarification prompt: {e}")
            return "Bạn có thể chia sẻ rõ hơn về nhu cầu của mình được không? 🤔"

    async def _verify_document_relevance(self, query: str, document: Dict) -> bool:
        """Verify if a document is relevant to the given query using the verification prompt."""
        try:
            # Format the verification prompt
            verification_prompt = SYSTEM_PROMPT_VERIFY_DOCUMENT

            # Create messages for verification
            messages = [
                {"role": "system", "content": verification_prompt},
                {"role": "user", "content": f"Câu hỏi: {query}\nTài liệu: {document['content']}"}
            ]

            # Get verification response
            response_text = await self._stream_llm_response(messages)

            # Extract the output tag content
            match = re.search(r'<output>(.*?)</output>', response_text)
            if match:
                result = match.group(1).strip()
                return result == "co_lien_quan"

            return False
        except Exception as e:
            LOGGER.error(f"Error in document verification: {e}")
            return False

    async def _verify_documents_batch(self, query: str, documents: List[Dict]) -> List[bool]:
        """
        Verify multiple documents' relevance in a single LLM request by reusing verify_document_relevance.

        Args:
            query: The user's query
            documents: List of documents to verify

        Returns:
            List of boolean values indicating relevance of each document
        """
        try:
            if not documents:
                return []

            # Format all documents into a single message
            verification_prompt = SYSTEM_PROMPT_VERIFY_DOCUMENT
            formatted_docs = []
            for idx, doc in enumerate(documents, 1):
                formatted_docs.append(f"Document {idx}:\n{doc['content']}")

            all_docs = "\n\n".join(formatted_docs)

            # Create a single verification message
            messages = [
                {"role": "system", "content": verification_prompt},
                {"role": "user", "content": f"Câu hỏi: {query}\n\nTài liệu để đánh giá:\n{all_docs}\n\n" +
                                            "Yêu cầu: Đánh giá từng tài liệu và trả về kết quả theo định dạng <output>doc1:co_lien_quan/khong_lien_quan|doc2:co_lien_quan/khong_lien_quan|...</output>"}
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

    @observe(as_type="retrieval")
    async def _get_relevant_documents(
            self,
            query: str,
            role_ids: List[str],
            topic: str,
            cache_key: Optional[str] = None
    ) -> DocumentResult:
        """
        Retrieve, rank and verify relevant documents with caching.
        Uses batch verification for improved efficiency.
        """
        if cache_key and cache_key in self._doc_cache:
            return self._doc_cache[cache_key]

        async with self._retrieval_semaphore:
            try:
                # Initial retrieval
                retrieval_records = await self._retriever.run(
                    query=query,
                    bot_id=self.bot_config['id'],
                    collection=f"bot_{transform_bot_id(self.bot_config['id'])}",
                    allowed_roles=role_ids,
                    top_k=self.bot_config['retrieval'].top_k,
                    threshold=self.bot_config['retrieval'].threshold,
                )
                
                # Reranking
                reranked_results = await self._reranker.run(
                    query=query,
                    texts=[r['content'] for r in retrieval_records],
                    top_k=self.bot_config['reranking'].top_k,
                    threshold=self.bot_config['reranking'].threshold,
                )

                # Prepare documents for batch verification
                documents_to_verify = []
                for r in reranked_results:
                    record = retrieval_records[r['index']]
                    record['score'] = r['score']
                    documents_to_verify.append(record)

                # Batch verify all documents
                verification_results = await self._verify_documents_batch(
                    query=query,
                    documents=documents_to_verify
                )

                # Process verification results
                final_docs = []
                max_score = 0

                for idx, is_relevant in enumerate(verification_results):
                    if is_relevant:
                        record = documents_to_verify[idx]
                        final_docs.append(record)
                        max_score = max(max_score, record['score'])

                result = DocumentResult(
                    docs=final_docs,
                    relevance_score=max_score
                )

                if cache_key:
                    self._doc_cache[cache_key] = result

                return result

            except Exception as e:
                LOGGER.error(f"Error retrieving documents: {e}")
                return DocumentResult(docs=[], relevance_score=0.0)

    async def _get_combined_documents(
            self,
            original_query: str,
            intent_query: str,
            role_ids: List[str],
            topic: str,
            cache_key: Optional[str] = None
    ) -> DocumentResult:
        """
        Retrieve and combine documents from both original query and intent query.
        Implements batch verification for the combined documents.
        """
        combined_cache_key = f"{cache_key}_combined" if cache_key else None

        if combined_cache_key and combined_cache_key in self._doc_cache:
            return self._doc_cache[combined_cache_key]

        try:
            # Get documents for both queries concurrently
            original_docs_task = self._get_relevant_documents(
                query=original_query,
                role_ids=role_ids,
                topic=topic
            )
            intent_docs_task = self._get_relevant_documents(
                query=intent_query,
                role_ids=role_ids,
                topic=topic
            )

            original_docs, intent_docs = await asyncio.gather(
                original_docs_task,
                intent_docs_task
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

            # Process intent docs
            for doc in intent_docs.docs:
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
                if is_relevant:
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

    @observe(as_type="intent")
    async def _determine_intent(
            self,
            messages: List[Dict],
            doc_result: DocumentResult
    ) -> InputQuery:
        """Determine user intent with greeting status and document requirements."""
        async with self._intent_semaphore:
            try:
                query = messages[-1]['content']

                # Get last 4 pairs of messages (excluding current message)
                history = []
                message_pairs = []
                current_pair = []

                for msg in messages[:-1][::-1]:  # Reverse through messages except current
                    current_pair.append(msg)
                    if len(current_pair) == 2:  # Have a user-bot pair
                        message_pairs.append(current_pair)
                        current_pair = []
                    if len(message_pairs) == 4:  # Have 4 pairs
                        break

                # Reverse pairs and flatten
                for pair in reversed(message_pairs):
                    history.extend(pair)

                # Add any remaining single message if we have an incomplete pair
                if current_pair:
                    history.extend(reversed(current_pair))

                # Format conversation history
                formatted_history = [
                    f"{'Người dùng' if m['role'] == 'user' else 'BOT'}: {m['content']}"
                    for m in history
                ]

                docs_text = self._format_documents(doc_result.docs)

                system_prompt = SYSTEM_PROMPT_INTENT.format(
                    conversation=formatted_history,
                    documents=docs_text,
                    relevance_score=doc_result.relevance_score
                ).strip()

                user_prompt = f"Tin nhắn mới: '{query}'"

                response_text = await self._stream_llm_response(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                )

                try:
                    new_query = re.findall(r'<query>(.*?)</query>', response_text)[0]
                    intent = re.findall(r'<intent>(.*?)</intent>', response_text)[0]
                    greeting = re.findall(r'<greeting>(.*?)</greeting>', response_text)[0].lower() == 'true'

                    # Validate intent values
                    if intent not in ["is_simple_chit_chat", "require_document"]:
                        LOGGER.warning(f"Invalid intent value: {intent}, defaulting to require_document")
                        intent = "require_document"

                except IndexError:
                    LOGGER.error("Failed to parse intent response tags")
                    intent = "require_document"
                    greeting = False
                except Exception as e:
                    LOGGER.error(f"Error parsing intent response: {e}")
                    intent = "require_document"
                    greeting = False

                INTENT_METRICS.labels(intent=intent).inc()

                return InputQuery(
                    query=new_query,
                    intent=intent,
                    greeting=greeting
                )

            except Exception as e:
                LOGGER.error(f"Error determining intent: {e}")
                return InputQuery(
                    query=messages[-1]['content'],
                    intent="require_document",
                    greeting=False
                )

    async def _generate_response(
            self,
            query_clarity: Dict,
            intent_result: InputQuery,
            doc_result: DocumentResult,
            messages: List[Dict]
    ) -> List[Dict]:
        """Generate response based on query analysis and document relevance."""
        clarity_level = query_clarity["clarity_level"]
        has_relevant_docs = query_clarity["has_relevant_docs"]

        LOGGER.info(f"clarity_level: {clarity_level}")
        LOGGER.info(f"has_relevant_docs: {has_relevant_docs}")
        LOGGER.info(f"intent: {intent_result.intent}")

        if intent_result.intent == "is_simple_chit_chat":
            # Handle simple chitchat without requiring documents
            prompt_system = SYSTEM_PROMPT_CHIT_CHAT.format(
                documents="",
                greeting=intent_result.greeting
            )
        else:  # intent is "require_document"
            if has_relevant_docs:
                if clarity_level == "complete":
                    # Case 1: Clear query with relevant documents - provide direct answer
                    prompt_system = SYSTEM_PROMPT_NON_CHIT_CHAT.format(
                        date=datetime.now().strftime('%Y-%m-%d'),
                        documents=self._format_documents(doc_result.docs),
                        greeting=intent_result.greeting
                    )
                else:
                    # Case 2: Unclear query but have relevant documents - ask for clarification
                    clarification = await self._generate_clarification_prompt(
                        messages[-1]['content'],
                        doc_result
                    )
                    prompt_system = f"""
                        Vai trò: Bạn là Bee Hi - trợ lý ảo thông minh của ngân hàng MB, chuyên hỗ trợ tư vấn cho nhân viên mới
                        Đưa ra nguyên văn câu trả lời sau với một chút chỉnh sửa để làm câu trả lời mượt mà hơn:
                        {clarification}
                    """
            else:
                if clarity_level == "unclear":
                    # Case 3: Unclear query with no relevant documents - ask for more details
                    prompt_system = SYSTEM_PROMPT_CHIT_CHAT.format(
                        documents="Bạn có thể chia sẻ rõ hơn về nhu cầu của mình được không? 🤔",
                        greeting=intent_result.greeting
                    )
                else:
                    # Case 4: Clear query but no relevant documents - refuse politely
                    prompt_system = SYSTEM_PROMPT_REFUSE

        return [
            {"role": "system", "content": prompt_system},
            {"role": "user", "content": messages[-1]['content']}
        ]

    @observe(as_type="trace")
    async def run(
            self,
            messages: List[Dict],
            role_ids: List[str] = [],
            topic: str = "default",
            **kwargs
    ) -> AsyncGenerator:
        """Main pipeline with updated logic flow."""
        REQUESTS.inc()
        start_time = time.time()

        try:
            # 1. Get relevant documents
            cache_key = f"{messages[-1]['content']}_{role_ids[-1]}_{topic}"
            doc_result = await self._get_relevant_documents(
                query=messages[-1]['content'],
                role_ids=role_ids,
                topic=topic,
                cache_key=cache_key
            )
            # 2.1 Determine intent
            intent_result = await self._determine_intent(
                messages=messages,
                doc_result=doc_result
            )

            # 2.2. Get combined doc result

            combined_doc_result = await self._get_combined_documents(
                original_query=messages[-1]['content'],
                intent_query=intent_result.query,
                role_ids=role_ids,
                topic=topic,
                cache_key=cache_key
            )
            LOGGER.info(combined_doc_result)
            # 3. Analyze query clarity

            query_clarity = await self._analyze_query_clarity(
                query=messages[-1]['content'],
                doc_result=combined_doc_result
            )

            # 4. Generate appropriate response
            response_messages = await self._generate_response(
                query_clarity=query_clarity,
                intent_result=intent_result,
                doc_result=combined_doc_result,
                messages=messages
            )

            # 5. Stream response
            async with self._llm_semaphore:
                buffer = []
                async for chunk in self._llm.run(
                        messages=response_messages,
                        docs=self._create_attached_docs(doc_result.docs),
                        sleep=0.0001
                ):
                    buffer.append(chunk)
                    if len(buffer) >= 50:
                        for buffered_chunk in buffer:
                            yield buffered_chunk
                        buffer.clear()

                for chunk in buffer:
                    yield chunk

            # Record metrics
            LATENCY.observe(time.time() - start_time)

        except Exception as e:
            ERRORS.inc()
            LOGGER.exception(f"Error in main pipeline: {str(e)}")
            raise

    async def shutdown(self):
        """Cleanup resources during shutdown."""
        try:
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            [task.cancel() for task in tasks]
            await asyncio.gather(*tasks, return_exceptions=True)
            self._doc_cache.clear()
        except Exception as e:
            LOGGER.error(f"Error during shutdown: {str(e)}")

# @observe
async def main():
    from beegenerate.configs import MongoConfig, MilvusConfig
    
    """Example usage of BeehiBot."""
    bot_id = "b10f0d26-4d91-47f5-8cac-034b87e42c7f"
    bot_store = BotStore(config=MongoConfig.default())
    bot_config = bot_store.fetch_bot_details(bot_id=bot_id)

    bot = BeehiBot(
        bot_config=bot_config,
        vec_store=MilvusStorage(config=MilvusConfig.default()),
        doc_store=DocumentStore(config=MongoConfig.default()),
        bot_store=bot_store
    )

    try:
        response_text = ""
        async for chunk in bot.run(
                messages=[
                    {"role": "user", "content": "Chuyên viên phòng dịch vụ nhân sự cần làm gì khi Người lao động nghỉ ốm dài ngày hoặc nghỉ khi mang thai theo chỉ định của bác sĩ?"}

                ],
                role_ids=["L1"],
                topic="QA"
        ):
            if chunk.choices and chunk.choices[0].delta.content:
                response_text += chunk.choices[0].delta.content

        LOGGER.info(f"{response_text}")

    finally:
        await bot.shutdown()


if __name__ == "__main__":
    asyncio.run(main())