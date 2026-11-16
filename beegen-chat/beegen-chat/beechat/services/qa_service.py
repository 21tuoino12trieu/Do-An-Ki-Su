import asyncio
import re
import time
import httpx
from typing import Dict, AsyncGenerator, Optional, List
from datetime import datetime
from difflib import SequenceMatcher

from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from beechat.config import load_settings
from beechat.utils.error_message import stream_error_message
from beechat.utils.prompt_loader import get_prompt
from beegenerate.loggings import LOGGER
from beegen_v1.parser.implementations.xml import XMLOutputParser
from langfuse.decorators import observe, langfuse_context


from collections import OrderedDict

class QAService:
    """
    Service chuyên biệt cho QnA Engine với 3 ngưỡng score:
      - Score > 0.95: Trả lời trực tiếp qua Fast Path (Direct match)
      - Score trong khoảng [0.8, 0.95]: Gọi LLM task kiểm duyệt ngữ nghĩa. Nếu đạt -> Direct match; Nếu không -> Loại bỏ direct match, chuyển luồng search documents
      - Score trong khoảng [0.4, 0.8): Gom thành tài liệu tham khảo cung cấp cho luồng Search Documents (Document RAG)
      - Score < 0.4: Loại bỏ hoàn toàn
    """

    def __init__(self, bot_id: str, llm_service, document_service, max_cache_size: int = 2000):
        self.bot_id = bot_id
        self.llm_service = llm_service
        self.document_service = document_service
        self.max_cache_size = max_cache_size
        self._memory_cache: OrderedDict[str, Dict] = OrderedDict()  # O(1) LRU in-memory cache

        self.config = {
            "similarity_threshold": 0.8,
            "high_confidence_threshold": 0.95,
            "match_confidence": 0.8,
            "cache_ttl": 3600
        }

        LOGGER.info(f"Initialized QAService (QnA Engine Only) for bot: {bot_id}")

    def configure(self, **kwargs):
        """Cập nhật cấu hình service."""
        for key, value in kwargs.items():
            if key in self.config:
                self.config[key] = value
                LOGGER.info(f"Updated cache config: {key}={value}")
        return self.config

    async def search_qna_engine(self, query: str) -> Dict:
        """Gọi trực tiếp REST API Discovery Engine (hợp nhất QnA và KB) trên Vertex AI qua LiteLLM gateway."""
        settings = load_settings()
        PROJECT_NUMBER = settings.kb_vector_prj_number
        ENGINE_ID = getattr(settings, "kb_engine_id", settings.kb_qna_engine_id)
        API_VERSION = settings.kb_api_version
        base_url = settings.openai_base_url.rstrip('/')

        headers = {
            "x-litellm-api-key": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json"
        }

        qna_payload = {
            "query": query,
            "pageSize": 5,
            "relevanceThreshold": "HIGH",
            "relevanceScoreSpec": {
                "returnRelevanceScore": True
            }
        }

        qna_url = (
            f"{base_url}/vertex_ai/discovery/{API_VERSION}/projects/{PROJECT_NUMBER}"
            f"/locations/global/collections/default_collection"
            f"/engines/{ENGINE_ID}/servingConfigs/default_search:search"
        )

        try:
            async with httpx.AsyncClient(verify=False, timeout=10.0, trust_env=False) as client:
                try:
                    resp = await client.post(qna_url, headers=headers, json=qna_payload)
                    resp.raise_for_status()
                    return resp.json()
                except Exception as api_err:
                    LOGGER.warning(f"[QnA Search] Fallback calling QnA without relevanceScoreSpec: {api_err}")
                    qna_payload_fallback = {
                        "query": query,
                        "pageSize": 5,
                        "relevanceThreshold": "HIGH"
                    }
                    resp = await client.post(qna_url, headers=headers, json=qna_payload_fallback)
                    resp.raise_for_status()
                    return resp.json()
        except Exception as e:
            LOGGER.error(f"[QnA Search Error]: {e}")
            return {"results": []}

    @observe()
    async def check_cached_qa(self, state: Dict) -> Dict:
        """
        Kiểm tra QnA Engine:
          - score > 0.95: Direct match (Fast Path)
          - 0.8 <= score <= 0.95: Kiểm duyệt qua LLM task. Nếu đạt -> Direct match; Nếu không -> Loại bỏ direct match, chuyển luồng search documents
          - 0.4 <= score < 0.8: Gom vào qna_docs để cung cấp làm tài liệu cho luồng Search Documents
          - score < 0.4: Loại bỏ hoàn toàn
        """
        enhanced_query = state.get('enhanced_query', '')
        original_query = state.get('original_query', state.get('query', ''))
        expanded_query = state.get('expanded_query', '')
        query = expanded_query if expanded_query else (enhanced_query if enhanced_query else original_query)

        if not query:
            return {'check': False, 'ref': None, 'qna_docs': []}

        LOGGER.info(f"Starting QnA Engine search for query: '{query[:50]}...'")

        # 1. Kiểm tra memory cache với O(1) LRU
        cache_key = self._generate_cache_key(query)
        if cache_key in self._memory_cache:
            cached_item = self._memory_cache[cache_key]
            if time.time() - cached_item.get('timestamp', 0) < self.config['cache_ttl']:
                self._memory_cache.move_to_end(cache_key)
                LOGGER.info("Memory cache hit for query")
                return cached_item['data']
            else:
                del self._memory_cache[cache_key]

        # Dual-query search when expanded_query differs from enhanced_query to maximize recall
        if expanded_query and enhanced_query and expanded_query != enhanced_query:
            LOGGER.info(f"Dual-query QnA search: expanded='{expanded_query[:40]}' + enhanced='{enhanced_query[:40]}'")
            raw_data_expanded, raw_data_enhanced = await asyncio.gather(
                self.search_qna_engine(expanded_query),
                self.search_qna_engine(enhanced_query),
                return_exceptions=True
            )

            # Merge kết quả, loại trùng bằng doc ID
            seen_ids = set()
            merged_results = []
            for raw in (raw_data_expanded, raw_data_enhanced):
                if isinstance(raw, Exception):
                    continue
                for item in raw.get("results", []):
                    doc_id = item.get("document", {}).get("id", "")
                    if doc_id not in seen_ids:
                        seen_ids.add(doc_id)
                        merged_results.append(item)
            all_results = merged_results
        else:
            # 2. Single query search (default path)
            raw_data = await self.search_qna_engine(query)
            all_results = raw_data.get("results", [])


        # Phân loại và lấy các tài liệu QnA
        qna_results = []
        for item in all_results:
            doc = item.get("document", {})
            struct_data = doc.get("structData", {})
            doc_id = doc.get("id", "")
            has_qa = bool(struct_data.get("Question") or struct_data.get("question") or
                          struct_data.get("Answer") or struct_data.get("answer") or
                          doc_id.startswith("qa-"))
            if has_qa:
                qna_results.append(item)

        qna_docs_to_inject = []
        best_match = None
        best_score = 0.0

        if qna_results:
            best_match = qna_results[0]
            doc = best_match.get("document", {})
            struct_data = doc.get("structData", {})
            matched_question = struct_data.get("Question") or struct_data.get("question") or ""
            answer = struct_data.get("Answer") or struct_data.get("answer") or ""

            if not answer:
                derived = doc.get("derivedStructData", {})
                answer = derived.get("Answer") or derived.get("answer") or ""

            scores = best_match.get("modelScores", {})
            relevance_score = scores.get("relevance_score", {}).get("values", [None])[0]
            sim_ratio = SequenceMatcher(None, query.casefold(), matched_question.casefold()).ratio()
            best_score = relevance_score if relevance_score is not None else sim_ratio

            # Thu thập các QnA matches trong khoảng [0.4, 0.8) để phục vụ cung cấp cho luồng Document Search
            for item in qna_results:
                q_doc = item.get("document", {})
                q_struct = q_doc.get("structData", {})
                q_q = q_struct.get("Question") or q_struct.get("question") or ""
                q_a = q_struct.get("Answer") or q_struct.get("answer") or ""
                if not q_a:
                    q_dev = q_doc.get("derivedStructData", {})
                    q_a = q_dev.get("Answer") or q_dev.get("answer") or ""

                if not q_q or not q_a:
                    continue

                q_sc = item.get("modelScores", {}).get("relevance_score", {}).get("values", [None])[0]
                q_sim = SequenceMatcher(None, query.casefold(), q_q.casefold()).ratio()
                q_actual_score = q_sc if q_sc is not None else q_sim

                if 0.4 <= q_actual_score < 0.8:
                    qna_docs_to_inject.append({
                        "title": f"QnA: {q_q}",
                        "link": "QnA Database",
                        "content": f"Hỏi: {q_q}\nĐáp: {q_a}",
                        "score": q_actual_score
                    })
                    LOGGER.info(f"  [QnA Inject] Retaining QnA score={q_actual_score:.2f} in [0.4, 0.8) for Document Search.")

        high_threshold = self.config.get("high_confidence_threshold", 0.95)
        min_threshold = self.config.get("similarity_threshold", 0.8)

        is_match = False
        confidence = best_score
        candidate = None

        if best_match and best_score >= min_threshold:
            doc = best_match.get("document", {})
            struct_data = doc.get("structData", {})
            matched_question = struct_data.get("Question") or struct_data.get("question") or ""
            answer = struct_data.get("Answer") or struct_data.get("answer") or ""
            if not answer:
                derived = doc.get("derivedStructData", {})
                answer = derived.get("Answer") or derived.get("answer") or ""

            if best_score > high_threshold:
                LOGGER.info(f"[QnA exact match] score={best_score:.2f} > {high_threshold} -> Direct Fast Path.")
                is_match = True
                confidence = 1.0
            else:
                LOGGER.info(f"[QnA score] {best_score:.2f} in [{min_threshold}, {high_threshold}] -> Calling LLM verification task.")
                candidate_text = f"Hỏi: {matched_question}\nĐáp: {answer}"
                match_result = await self._verify_semantic_match(enhanced_query, original_query, candidate_text)
                confidence = match_result['confidence']
                is_match = confidence >= self.config.get("match_confidence", 0.8)

                if not is_match:
                    LOGGER.info(f"[QnA LLM verification failed] confidence={confidence:.2f} < {self.config.get('match_confidence', 0.8)} -> Rejected direct match, proceeding to document search.")

            if is_match:
                candidate = {
                    'id': f"qa_vertex_{hash(query)}",
                    'content': f"[QnA Exact Match]:\nQuestion: {matched_question}\nScore: {best_score:.2f}\nAnswer: {answer}",
                    'score': best_score
                }
        else:
            LOGGER.info(f"[QnA score] {best_score:.2f} < {min_threshold} -> Cache miss / Proceed to document search.")

        result = {
            'check': is_match,
            'ref': candidate,
            'confidence': confidence,
            'qna_docs': qna_docs_to_inject
        }

        if is_match:
            if cache_key in self._memory_cache:
                self._memory_cache.move_to_end(cache_key)
            elif len(self._memory_cache) >= self.max_cache_size:
                self._memory_cache.popitem(last=False)

            self._memory_cache[cache_key] = {
                'data': result,
                'timestamp': time.time()
            }

        return result

    async def _verify_semantic_match(self, enhanced_query: str, original_query: str, candidate_content: str) -> Dict:
        """Kiểm tra semantic match giữa query và candidate qua LLM task khi score nằm trong [0.8, 0.95)."""
        response = await self.llm_service.llm_task(
            inputs={
                "enhanced_question": enhanced_query,
                "original_question": original_query,
                "document": candidate_content[:2000]
            },
            prompt_template=get_prompt("QA_FILTER_PROMPT"),
            use_primary=False
        )

        try:
            xml_parser = XMLOutputParser()
            xml_result = await xml_parser.parse(text=response)
            confidence = float(xml_result.get('confidence', '0.0').strip())
        except Exception:
            confidence = 0.8

        return {'confidence': confidence}

    async def stream_cached_answer(self, state: Dict) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Stream phản hồi từ nội dung QA đã cache."""
        cache_check = state.get('cache_check', {})
        cached_qa = cache_check.get('ref')

        if not cached_qa or 'content' not in cached_qa:
            async for chunk in stream_error_message(self.llm_service, "Không tìm thấy dữ liệu cache phù hợp."):
                yield chunk
            return

        query = state.get('query', 'Không có câu hỏi')
        greeting = state.get('greeting', False)
        current_date = datetime.now().date()

        LOGGER.info(f"Streaming response from cached QA for: '{query[:30]}...'")

        async for chunk in self.llm_service.llm_stream(
                inputs={
                    "question": query,
                    "documents": cached_qa['content'],
                    "date": current_date,
                    "greeting": greeting
                },
                prompt_template=get_prompt("QA_RESPONSE_PROMPT"),
                docs=[{'id': cached_qa.get('id', 'cached_id')}]
        ):
            yield chunk

    def _generate_cache_key(self, query: str) -> str:
        import hashlib
        normalized_query = query.lower().strip()
        return f"qa:{hashlib.md5(normalized_query.encode()).hexdigest()}"

    def clear_cache(self, older_than: int = None):
        if older_than is None:
            count = len(self._memory_cache)
            self._memory_cache.clear()
            LOGGER.info(f"Cleared all {count} items from cache")
        else:
            current_time = time.time()
            to_delete = [key for key, value in self._memory_cache.items()
                         if current_time - value.get('timestamp', 0) > older_than]
            for key in to_delete:
                del self._memory_cache[key]
            LOGGER.info(f"Cleared {len(to_delete)} items from cache (older than {older_than}s)")

    def get_cache_stats(self) -> Dict:
        current_time = time.time()
        active_items = sum(1 for v in self._memory_cache.values()
                           if current_time - v.get('timestamp', 0) < self.config['cache_ttl'])
        return {
            "total_items": len(self._memory_cache),
            "active_items": active_items,
            "expired_items": len(self._memory_cache) - active_items,
            "config": self.config
        }


async def main():
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    from beechat.services.llm_service import LLMService
    from beechat.services.document_service import DocumentService

    print("==================================================")
    print(" TESTING QA SERVICE (QNA ENGINE ONLY)")
    print("==================================================")

    llm_service = LLMService(bot_id="test_bot")
    doc_service = DocumentService(bot_id="test_bot", llm_service=llm_service)
    qa_service = QAService(bot_id="test_bot", llm_service=llm_service, document_service=doc_service)

    test_queries = [
        "Cách đổi mật khẩu app MB Bank?",
        "Hạn mức thẻ tín dụng MB là bao nhiêu?"
    ]

    for q in test_queries:
        print(f"\n Testing query: '{q}'")
        res = await qa_service.check_cached_qa({'query': q})
        print(f"Result match: {res.get('check')}, QnA Docs to inject count: {len(res.get('qna_docs', []))}")


if __name__ == "__main__":
    asyncio.run(main())
