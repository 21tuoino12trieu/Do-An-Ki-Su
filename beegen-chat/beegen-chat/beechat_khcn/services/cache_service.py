"""
Simplified cache service for deposit domain"""

import time
import hashlib
from typing import Dict, Any, Optional, AsyncGenerator

from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from datetime import datetime


from beegenerate.loggings import LOGGER
from beegen_v1.parser.implementations.xml import XMLOutputParser
from beegenerate.loggings.loggers import lf


class CacheService:
    """
    Simplified cache service với unified configuration
    Loại bỏ config class dư thừa, tập trung vào core caching logic
    """

    def __init__(self, bot_id: str, llm_service, document_service):
        self.bot_id = bot_id
        self.collection_master = f"bot_{bot_id.replace('-', '_')}"
        self.llm_service = llm_service
        self.document_service = document_service

        # Simple in-memory cache
        self._cache = {}

        # Config values directly embedded
        self.similarity_threshold = 0.75
        self.match_confidence = 0.9
        self.retrieval_top_k = 20
        self.rerank_top_k = 10
        self.cache_ttl = 3600
        self._query_cache = {}
        self._cache_ttl = 300

        LOGGER.info(f"Initialized CacheService for bot: {bot_id}")

    def _is_cache_valid(self, cache_entry: Dict) -> bool:
        """Check if cache entry is still valid"""
        import time
        return time.time() - cache_entry.get('timestamp', 0) < self._cache_ttl

    async def check_cached_qa(self, context: Dict) -> Dict:
        """Enhanced cache check với in-memory caching"""
        enhanced_query = context.get('query', '')
        if not enhanced_query:
            return {'check': False, 'ref': None}

        # Check in-memory cache first
        cache_key = f"qa_check:{hash(enhanced_query)}"
        if cache_key in self._query_cache:
            cache_entry = self._query_cache[cache_key]
            if self._is_cache_valid(cache_entry):
                LOGGER.info("In-memory cache hit for QA check")
                return cache_entry['data']

        LOGGER.info(f"Checking cache for enhanced query: {enhanced_query}")

        try:
            # Check memory cache first
            cache_key_old = self._generate_cache_key(enhanced_query)
            cached_item = self._get_from_cache(cache_key_old)

            if cached_item:
                LOGGER.info("Memory cache hit")
                result = cached_item
            else:
                # Get top candidate từ vector DB
                candidate = await self._get_top_candidate(enhanced_query)

                if not candidate:
                    result = {'check': False, 'ref': None}
                else:
                    candidate_score = candidate.get('score', 0)
                    if candidate_score < self.similarity_threshold:
                        result = {'check': False, 'ref': None}
                    else:
                        # CRITICAL: Verify semantic match với proper error handling
                        try:
                            match_result = await self._verify_semantic_match_via_llm(
                                enhanced_query,
                                candidate.get('content', '')
                            )
                            confidence = match_result.get('confidence', 0.0)
                            is_match = confidence >= self.match_confidence

                            result = {
                                'check': is_match,
                                'ref': candidate if is_match else None,
                                'confidence': confidence
                            }
                        except Exception as e:
                            LOGGER.error(f"Semantic verification failed: {e}")
                            result = {'check': False, 'ref': None}

                # Cache result in old system
                self._set_to_cache(cache_key_old, result)

            # Store in new system
            self._query_cache[cache_key] = {
                'data': result,
                'timestamp': time.time()
            }

            # Cleanup old cache entries
            if len(self._query_cache) > 1000:
                self._cleanup_cache()

            return result

        except Exception as e:
            # TOP-LEVEL error handling
            LOGGER.error(f"Unexpected error in cache check - Query: {enhanced_query[:50]}, Error: {str(e)}")
            return {'check': False, 'ref': None}

    def _cleanup_cache(self):
        """Remove expired cache entries"""
        import time
        current_time = time.time()
        expired_keys = [
            key for key, entry in self._query_cache.items()
            if current_time - entry.get('timestamp', 0) > self._cache_ttl
        ]
        for key in expired_keys:
            del self._query_cache[key]

    async def _get_top_candidate(self, query: str) -> Optional[Dict]:
        """Get top candidate từ vector DB"""

        try:
            candidates = await self.document_service._fetch_and_rank(
                query=query,
                collection=self.collection_master,
                retrieval_top_k=self.retrieval_top_k,
                rerank_top_k=self.rerank_top_k,
                partition_names=['QA']
            )

            if not candidates:
                return None

            top_candidate = candidates[0]
            top_score = top_candidate.get('score', 0)

            # VALIDATION: Ensure candidate has required fields
            if 'content' not in top_candidate:
                LOGGER.warning(f"Top candidate missing 'content' field: {top_candidate.keys()}")
                return None

            return top_candidate if top_score >= self.similarity_threshold else None

        except Exception as e:
            LOGGER.error(f"Error getting top candidate - Query: {query[:50]}, Error: {str(e)}")
            return None

    async def _verify_semantic_match_via_llm(self, query: str, candidate_content: str) -> Dict:
        """Verify semantic match sử dụng LLM thay vì keyword matching"""

        response = await self.llm_service.llm_task(
            inputs={"question": query, "document": candidate_content},
            prompt_template=lf.get_prompt("BEECHAT_QA_FILTER_PROMPT"),
            use_primary=True
        )

        # Parse XML để lấy confidence
        xml_parser = XMLOutputParser()
        xml_result = await xml_parser.parse(text=response)

        confidence = 0.0

        # SỬA: Kiểm tra tất cả possible keys
        confidence_str = xml_result.get('confidence') or xml_result.get('enhanced_question', '0.0')

        # SỬA: Xử lý trường hợp confidence_str None
        if confidence_str is None:
            confidence_str = '0.0'

        try:
            confidence = float(str(confidence_str).strip())
        except (ValueError, AttributeError, TypeError):
            LOGGER.warning(f"Invalid confidence value: {confidence_str}, using 0.0")
            confidence = 0.0

        return {'confidence': confidence}

    async def stream_cached_answer(self, state: Dict) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Stream phản hồi từ nội dung QA đã cache"""

        cache_check = state.get('cache_check', {})
        cached_qa = cache_check.get('ref')

        if not cached_qa or 'content' not in cached_qa:
            # Return error response
            error_chunk = ChatCompletionChunk(
                id="cache_error",
                choices=[],
                created=int(time.time()),
                model="cache_service",
                object="chat.completion.chunk"
            )
            yield error_chunk
            return

        # Prepare data cho streaming
        query = state.get('query', 'Không có câu hỏi')
        greeting = state.get('greeting', False)
        current_date = datetime.now().date()

        LOGGER.info(f"Streaming response from cached QA for: {query[:30]}...")

        # Stream response using QA_RESPONSE_PROMPT
        async for chunk in self.llm_service.llm_stream(
                inputs={
                    "question": query,
                    "documents": cached_qa['content'],
                    "date": current_date,
                    "greeting": greeting
                },
                prompt_template=lf.get_prompt("BEECHAT_QA_RESPONSE_PROMPT"),
                sleep=0.01,
                docs=[{'id': cached_qa['id']}]
        ):
            yield chunk

    def _generate_cache_key(self, query: str) -> str:
        """Generate cache key từ query"""
        normalized_query = query.lower().strip()
        return f"qa:{hashlib.md5(normalized_query.encode('utf-8')).hexdigest()[:16]}"

    def _get_from_cache(self, key: str) -> Any:
        """Get item từ cache với TTL check"""
        if key not in self._cache:
            return None

        entry = self._cache[key]
        if time.time() - entry.get('timestamp', 0) > self.cache_ttl:
            del self._cache[key]
            return None

        return entry['data']

    def _set_to_cache(self, key: str, value: Any):
        """Set item vào cache với cleanup"""
        self._cache[key] = {
            'data': value,
            'timestamp': time.time()
        }

        # Simple cleanup khi cache quá lớn
        if len(self._cache) > 100:
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k]['timestamp'])
            del self._cache[oldest_key]

    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        current_time = time.time()

        active_items = sum(1 for v in self._cache.values()
                           if current_time - v.get('timestamp', 0) < self.cache_ttl)

        return {
            "total_items": len(self._cache),
            "active_items": active_items,
            "expired_items": len(self._cache) - active_items,
            "config": {
                "similarity_threshold": self.similarity_threshold,
                "match_confidence": self.match_confidence,
                "cache_ttl": self.cache_ttl
            }
        }
