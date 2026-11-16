import asyncio
import hashlib
import json
import re
import time
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from langfuse.decorators import observe
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from beechat.services.card_service_v2 import CardService
from beechat.services.content_filter_service import ContentFilterService
from beechat.services.document_service import DocumentService
from beechat.services.llm_service import LLMService
from beechat.services.location_service import LocationService
from beechat.services.qa_service import QAService
from beechat.services.scenario_service import ScenarioService
from beechat.services.simple_complaint_handler import SimpleComplaintHandler, extract_transaction_complaint_info
from beechat.utils.abbreviation import AbbreviationHandler
from beechat.utils.dialouge_state_manager import DialogueStateManager
from beechat.utils.prompt_loader import get_prompt
from beechat.utils.pyinstrument_profiler import profile_async_block, profile_async_func
from beegen_v1.parser.implementations.xml import XMLOutputParser
from beegenerate.loggings import LOGGER

# Prompt để yêu cầu LLM trả về y nguyên văn bản
VERBATIM_PROMPT = (
    "Trả về y nguyên nội dung sau đây, không thêm bất kỳ lời dẫn, giải thích hay định dạng nào "
    "khác:\n\n{script} "
)


# =============================================================================
# 1. CONFIGURATION & CONSTANTS
# =============================================================================
class AppConfig:
    """Centralized configuration management for high concurrency"""

    # Status codes
    STATUS_CODES = {
        'success': (200, "Success!"),
        'no_data': (204, "No data"),
        'meet_consultant': (206, "Meet Consultant"),
        'bad_request': (400, "Bad request"),
    }

    # Concurrency settings
    LLM_SEMAPHORE_SIZE = 150
    DOC_SEMAPHORE_SIZE = 100
    ANALYSIS_SEMAPHORE_SIZE = 200
    CACHE_SEMAPHORE_SIZE = 250

    # Cache settings
    CACHE_MAX_SIZE = 500
    CACHE_TTL = 600
    MEMORY_CACHE_SIZE = 200

    # Connection pooling
    DB_POOL_SIZE = 50
    DB_MAX_OVERFLOW = 25

    # Request limiting
    MAX_REQUEST_SIZE_MB = 2

    # Location mappings
    LOCATION_MAPPING = {
        "chi nhánh": "cn_pgd",
        "phòng giao dịch": "cn_pgd",
        "atm": "atm",
        "cdm": "cdm_crm",
        "crm": "cdm_crm",
        "smart bank": "smart_bank",
    }


from collections import OrderedDict


# =============================================================================
# 2. CORE UTILITIES
# =============================================================================
class CacheManager:
    """High-performance O(1) async LRU cache manager with TTL eviction"""

    def __init__(self, max_size: int = 5000, ttl: int = 1800):
        self.max_size = max_size
        self.ttl = ttl
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.hit_count = 0
        self.miss_count = 0

    async def get(self, key: str, default: Any = None) -> Any:
        """Fast O(1) get method with TTL eviction and LRU move-to-end"""
        if key not in self._cache:
            self.miss_count += 1
            return default

        entry = self._cache[key]
        current_time = time.time()

        if current_time - entry['timestamp'] > self.ttl:
            del self._cache[key]
            self.miss_count += 1
            return default

        self._cache.move_to_end(key)
        self.hit_count += 1
        return entry['data']

    async def set(self, key: str, value: Any) -> None:
        """Fast O(1) set method with LRU eviction when capacity reached"""
        current_time = time.time()

        if key in self._cache:
            self._cache.move_to_end(key)
        elif len(self._cache) >= self.max_size:
            # Evict least recently used entry in O(1) constant time
            self._cache.popitem(last=False)

        self._cache[key] = {
            'data': value,
            'timestamp': current_time,
        }

    def generate_key(self, *args) -> str:
        """Simplified key generation for cache"""
        key_parts = [arg[:50] if isinstance(arg, str) else str(hash(str(arg)))[:8] for arg in args]
        combined = "|".join(key_parts)
        return hashlib.md5(combined.encode()).hexdigest()[:16]

    async def get_stats(self) -> Dict:
        """Simple stats"""
        total_requests = self.hit_count + self.miss_count
        hit_rate = self.hit_count / max(total_requests, 1)

        return {
            "total_items": len(self._cache),
            "hit_count": self.hit_count,
            "miss_count": self.miss_count,
            "hit_rate": hit_rate,
        }


# =============================================================================
# 3. RESPONSE ANALYSIS & PROCESSING
# =============================================================================
class ResponseAnalyzer:
    """Simplified response analysis"""

    def __init__(self, cache_manager: CacheManager):
        self.cache = cache_manager
        self.xml_parser = XMLOutputParser()

    async def analyze_intent(self, query: str, llm_service) -> Dict:
        """Analyze user intent with simple caching"""
        cache_key = self.cache.generate_key("intent", query)

        cached_result = await self.cache.get(cache_key)
        if cached_result:
            return cached_result

        response = await llm_service.llm_task(
            inputs={"query": query},
            prompt_template=get_prompt("ANALIZE_TOPIC_AND_SENTIMENT_PROMPT")
        )

        result = await self._parse_analysis_xml(response)
        await self.cache.set(cache_key, result)
        return result

    async def analyze_conversation_context(self, messages: List[Dict], llm_service) -> Dict:
        """Analyze conversation context and create enhanced query with flow decision"""
        if not messages or len(messages) <= 1:
            return {
                'enhanced_query': messages[-1]['content'].strip() if messages else "",
                'flow_decision': 'new_flow',
                'conversation_state': 'normal'
            }

        recent_messages = messages[-6:] if len(messages) > 1 else messages
        current_message = messages[-1]['content'].strip()

        conversation_text = self._format_conversation_for_analysis(recent_messages)

        response = await llm_service.llm_task(
            inputs={
                "conversation_history": conversation_text,
                "current_message": current_message
            },
            prompt_template=get_prompt("CONVERSATION_ANALYSIS_PROMPT"),
            use_primary=False
        )

        return self._parse_conversation_analysis_with_flow(response, current_message)

    def _parse_conversation_analysis_with_flow(self, response: str, fallback_query: str) -> Dict:
        """Parse response from conversation analysis including flow decision"""
        result = {
            'enhanced_query': fallback_query,
            'flow_decision': 'new_flow',
            'conversation_state': 'normal'
        }

        lines = response.strip().split('\n')

        for line in lines:
            if "Enhanced Query" in line and ":" in line:
                enhanced_query = line.split(":", 1)[1].strip()
                if enhanced_query:
                    result['enhanced_query'] = enhanced_query
            elif "Flow Decision" in line and ":" in line:
                flow_decision = line.split(":", 1)[1].strip()
                if flow_decision:
                    result['flow_decision'] = flow_decision

        # Determine conversation state based on flow decision
        if result['flow_decision'] in ['continue_collecting', 'complete_collecting']:
            result['conversation_state'] = 'complaint_collection'
        elif result['flow_decision'] == 'new_intent':
            result['conversation_state'] = 'intent_switch'
        else:
            result['conversation_state'] = 'normal'

        return result

    def _parse_conversation_analysis(self, response: str, fallback_query: str) -> str:
        """Parse response from conversation analysis"""
        lines = response.strip().split('\n')

        for line in lines:
            if "Enhanced Query" in line and ":" in line:
                enhanced_query = line.split(":", 1)[1].strip()
                if enhanced_query:
                    return enhanced_query

        return fallback_query

    def _format_conversation_for_analysis(self, messages: List[Dict]) -> str:
        """Format conversation messages for LLM analysis"""
        formatted = []
        for i, msg in enumerate(messages):
            role = "USER" if msg.get("role") == "user" else "BOT"
            content = msg.get("content", "").strip()
            if content:
                formatted.append(f"[{i + 1}] {role}: {content}")
        return "\n".join(formatted)

    async def check_document_relevance(self, query: str, documents_text: str, llm_service) -> bool:
        if not documents_text or "không tìm thấy tài liệu phù hợp" in documents_text:
            return False

        response = await llm_service.llm_task(
            inputs={"question": query, "documents": documents_text[:3000]},
            prompt_template=get_prompt("DOCUMENT_RELEVANCE_CHECK_PROMPT"),
            use_primary=False
        )

        return response.strip().lower() == "có"

    async def _parse_analysis_xml(self, response: str) -> Dict:
        """Parse XML analysis response"""
        result = {
            'greeting': False,
            'intent_type': 'banking_service',
            'topic_category': 'standard'
        }

        try:
            parsed_data = await self.xml_parser.parse(text=response)

            if 'complaint_type' in parsed_data:
                result.update({
                    'intent_type': 'transaction_complaint',
                    'complaint_type': parsed_data.get('complaint_type', '').strip(),
                    'topic_category': 'complaint'
                })
            elif 'end_type' in parsed_data:
                result.update({
                    'intent_type': 'end_customer_support',
                    'end_type': parsed_data.get('end_type', '').strip()
                })

            else:
                result.update({
                    'intent_type': parsed_data.get('intent', 'banking_service').strip(),
                    'topic_category': parsed_data.get('topic', 'standard').strip()
                })

        except Exception as e:
            LOGGER.warning(f"Error parsing analysis XML: {str(e)}")
        return result


# =============================================================================
# 4. DOCUMENT PROCESSING
# =============================================================================
class DocumentProcessor:
    """Unified document operations and formatting"""

    def __init__(self, cache_manager: CacheManager, document_service):
        self.cache = cache_manager
        self.document_service = document_service

    def format_documents(self, docs: List[Dict]) -> str:
        """Format documents for display with integrated sorting"""
        if not docs:
            return "không tìm thấy tài liệu phù hợp"

        sorted_docs = sorted(docs, key=lambda d: d.get('score', 0) if isinstance(d, dict) else 0, reverse=True)

        formatted_docs = []
        for idx, doc in enumerate(sorted_docs, 1):
            content = self._extract_content(doc)
            if content:
                source_info = f" [Nguồn: {doc['source']}]" if isinstance(doc, dict) and 'source' in doc else ""
                formatted_docs.append(f"--- TÀI LIỆU {idx}{source_info} ---\n{content}")

        return (
            "\n-----------------------------\n".join(formatted_docs)
            if formatted_docs
            else "không tìm thấy tài liệu phù hợp"
        )

    def prepare_docs_for_llm(self, docs: List[Dict]) -> List[Dict]:
        """Prepare document references for LLM"""
        if not docs:
            return []

        references = []
        for doc in docs:
            if isinstance(doc, str):
                references.append({"id": str(uuid.uuid4())})
                continue

            if not isinstance(doc, dict):
                continue

            doc_id = doc.get('id') or doc.get('chunk_id') or str(uuid.uuid4())
            doc_meta = {"id": doc_id}

            for source_field in ['doc', 'source', 'document_id']:
                if source_field in doc:
                    doc_meta['source'] = doc[source_field]
                    break

            references.append(doc_meta)

        return references

    def _extract_content(self, doc) -> str:
        """Extract content from document"""
        if isinstance(doc, str):
            return doc
        if isinstance(doc, dict):
            for field in ['content', 'chunk', 'text']:
                if field in doc and doc[field]:
                    return doc[field]
        return ''


# =============================================================================
# 5. BATCH PROCESSING
# =============================================================================
class BatchProcessor:
    """High-performance batch processing for parallel operations"""

    def __init__(self, app):
        self.app = app

    async def execute_analysis_batch(self, request_state: Dict) -> Dict:
        """Execute analysis batch with optimized conversation context evaluation."""
        query = request_state['query']
        messages = request_state.get('messages', [])

        # Analyze conversation context for multi-turn requests
        if len(messages) > 1:
            try:
                conversation_result = await self.app.analyzer.analyze_conversation_context(
                    messages,
                    self.app.llm_service
                )
                request_state['enhanced_query'] = conversation_result['enhanced_query']
                request_state['original_query'] = query
                request_state['flow_decision'] = conversation_result['flow_decision']
                request_state['conversation_state'] = conversation_result['conversation_state']
            except Exception as e:
                LOGGER.warning(f"Conversation analysis failed: {e}")
                request_state['enhanced_query'] = query
                request_state['flow_decision'] = 'new_flow'
                request_state['conversation_state'] = 'normal'
        else:
            request_state['enhanced_query'] = query
            request_state['flow_decision'] = 'new_flow'
            request_state['conversation_state'] = 'normal'

        enhanced_query = request_state['enhanced_query']

        # Parallel analysis, cache check, content filter, and query expansion
        async def get_analysis():
            return await self.app.analyzer.analyze_intent(enhanced_query, self.app.llm_service)

        async def get_cache():
            cache_context = {
                'query': query,
                'enhanced_query': enhanced_query,
                'original_query': query
            }
            return await self.app.cache_service.check_cached_qa(cache_context)

        async def get_filter():
            return await self.app.content_filter_service.check_content(enhanced_query)

        async def get_expanded_query():
            """Standardize query abbreviations and slang concurrently."""
            if len(messages) > 1:
                return enhanced_query
            try:
                expanded = await self.app.llm_service.llm_task(
                    inputs={"query": enhanced_query},
                    prompt_template=get_prompt("QUERY_EXPANSION_PROMPT"),
                    max_tokens=80
                )
                result = expanded.strip() if expanded and expanded.strip() else enhanced_query
                if result != enhanced_query:
                    LOGGER.info(f"Query expanded: '{enhanced_query[:60]}' -> '{result[:60]}'")
                return result
            except Exception as e:
                LOGGER.warning(f"Query expansion skipped: {e}")
                return enhanced_query

        results = await asyncio.gather(
            get_analysis(),
            get_cache(),
            get_filter(),
            get_expanded_query(),
            return_exceptions=True
        )

        analysis = self._extract_result_or_default(
            results[0],
            {'greeting': False, 'intent_type': 'banking_service', 'topic_category': 'standard'},
            "analysis"
        )

        cache_check = self._extract_result_or_default(
            results[1],
            {'check': False, 'ref': None},
            "cache_check"
        )

        filter_check = self._extract_result_or_default(
            results[2],
            {'filter_needed': 'no', 'filter_type': 'none'},
            "filter_check"
        )

        expanded_query = results[3] if not isinstance(results[3], Exception) else enhanced_query
        request_state['expanded_query'] = expanded_query

        return {
            'state': request_state,
            'analysis': analysis,
            'cache_check': cache_check,
            'filter_check': filter_check
        }

    async def execute_document_batch(self, request_state: Dict, topic_category: str) -> Dict:
        """Execute parallel document operations using expanded_query or enhanced_query."""
        best_query = (
            request_state.get('expanded_query')
            or request_state.get('enhanced_query')
            or request_state.get('query', '')
        )
        request_state['expanded_query'] = best_query


        tasks = []
        task_names = []

        tasks.append(self._safe_document_search(request_state))
        task_names.append('main_documents')

        if topic_category in ["specific_card", "generic_card"]:
            tasks.append(self._safe_card_service(request_state))
            task_names.append('card_result')

        results = await asyncio.gather(*tasks, return_exceptions=True)

        results_dict = {}
        for i, result in enumerate(results):
            if not isinstance(result, Exception):
                results_dict[task_names[i]] = result
            else:
                LOGGER.warning(f"Task {task_names[i]} failed: {str(result)}")
                results_dict[task_names[i]] = [] if 'documents' in task_names[i] else {}

        if 'main_documents' in results_dict:
            doc_results = results_dict['main_documents'].get('document_results', {})
            results_dict['documents'] = doc_results.get('final_docs', [])

        return results_dict

    async def _safe_document_search(self, request_state: Dict) -> Dict:
        """Safe document search using DocumentService"""
        return await self.app.document_service.search_documents(request_state)

    async def _safe_card_service(self, request_state: Dict) -> Dict:
        """Safe card service execution"""
        return await self.app.card_service.run(request_state)

    def _extract_result_or_default(self, result: Any, default: Any, operation_name: str = "operation") -> Any:
        """Extract result or return default if exception"""
        if isinstance(result, Exception) or result is None:
            LOGGER.warning(f"{operation_name} failed, using default")
            return default
        return result


# =============================================================================
# 6. PROCESSING PIPELINE
# =============================================================================
class ProcessingPipeline:
    """Optimized processing pipeline"""

    def __init__(self, app):
        self.app = app

    async def execute(self, request_state: Dict) -> Dict:
        """Streamlined pipeline execution with Early Exit for simple greetings & active scenarios"""
        query = request_state['query']

        # Early Exit 1: Simple greetings / thanks / short chit-chat:
        # Bypasses heavy LLM Analysis Batch & Vertex AI Search, but STILL calls LLM via CHIT_CHAT prompt
        # (Chỉ kích hoạt khi không nằm trong luồng scenario đang chạy để bảo đảm KH nhập '1', '0đ', 'uh', 'ok' được thu thập đúng slot)
        if 'scenario_context' not in request_state and self._is_simple_case(query):
            LOGGER.info(f"[Early Exit] Simple greeting/chit-chat query detected ('{query[:30]}'). Streaming LLM via CHIT_CHAT prompt.")
            return {
                'type': 'chit_chat',
                'status_code': 205,
                'context': {
                    'query': query,
                    'messages': request_state.get('messages', []),
                    'greeting': True
                }
            }

        #  Early Exit 2: Active Scenario Continuation:
        # If user is in an active scenario form, handle scenario directly without heavy analysis batch
        if 'scenario_context' in request_state:
            scenario_resp = await self._handle_collecting_information(request_state)
            if scenario_resp is not None:
                LOGGER.info(" [Early Exit] Active scenario continued successfully.")
                return scenario_resp

        analysis_result = await self.app.batch_processor.execute_analysis_batch(request_state)

        special_response = await self._check_special_cases(analysis_result)
        if special_response:
            return special_response

        doc_result = await self._process_documents(analysis_result)

        return self._prepare_response_context(doc_result, request_state)

    async def _handle_collecting_information(self, state: Dict) -> Dict:
        """Xử lý thu thập thông tin (Nâng cấp: Soft Accept Non-blocking & Chained Streaming)"""
        try:
            current_scenario = state.get('scenario_context', {}).get('scenario')
            scenario = await self.app.scenario_service.select_scenario(state)

            if scenario is None and current_scenario:
                # Nếu đang trong luồng scenario chưa hoàn thành, giữ nguyên scenario đang chạy
                if not state.get('scenario_context', {}).get('is_complete', False):
                    LOGGER.info(f"[ScenarioService] Maintaining ongoing scenario '{current_scenario}' for multi-turn input.")
                    scenario = current_scenario

            if scenario is None:
                scenario_context = state.get('scenario_context')
                if scenario_context:
                    del state['scenario_context']
                return None
            else:
                state['scenario_context'] = state.get('scenario_context', {})
                state['scenario_context'].update({'scenario': scenario})

            reply_generator, scenario_state = await self.app.scenario_service.run(state, scenario)
            if scenario_state:
                state["scenario_context"].update(scenario_state)

            if scenario_state and scenario_state.get('is_complete'):
                # Sau khi hoàn thành scenario, xóa context để câu hỏi tiếp theo bắt đầu luồng mới
                del state['scenario_context']
                return {'type': 'complete_script', 'context': {'generator': reply_generator}, 'status_code': 207}
            else:
                return {'type': 'scenario', 'context': {'generator': reply_generator}, 'status_code': 205}

        except Exception as e:
            LOGGER.error(f"Error: {e}", exc_info=True)

        return None

    async def _check_special_cases(self, analysis_result: Dict) -> Optional[Dict]:
        """Check for special case handling with simplified complaint logic"""
        state = analysis_result['state']
        analysis = analysis_result['analysis']
        cache_check = analysis_result['cache_check']
        filter_check = analysis_result['filter_check']

        # Save QnA reference docs in [0.4, 0.8) into state for Document RAG injection
        if cache_check.get('qna_docs'):
            state['qna_docs'] = cache_check.get('qna_docs', [])

        query = state['query']
        intent_type = analysis.get('intent_type')
        complaint_type = analysis.get('complaint_type')
        topic_category = analysis.get('topic_category')
        state['intent_type'] = intent_type
        state['complaint_type'] = complaint_type
        state['topic_category'] = topic_category

        if intent_type == 'end_customer_support':
            if 'thanks' in analysis.get('end_type', ''):
                return {
                    'type': 'verbatim_script',
                    'context': {
                        'script_text': "Bee rất vui khi được hỗ trợ bạn ạ. Bee cảm ơn bạn đã tin tưởng và sử dụng dịch vụ MB. Nếu cần thêm thông tin, bạn cứ nhắn Bee nhé!"
                    },
                    'status_code': 200,
                }
            elif 'no_support_needed' in analysis.get('end_type', ''):
                if 'scenario_context' in state:
                    del state['scenario_context']
                return {
                    'type': 'verbatim_script',
                    'context': {
                        'script_text': "Dạ Bee ghi nhận bạn chưa cần hỗ trợ thêm ạ. Khi cần, bạn cứ liên hệ Bee nhé!"
                    },
                    'status_code': 200,
                }
            elif 'goodbye' in analysis.get('end_type', ''):
                return {
                    'type': 'verbatim_script',
                    'context': {
                        'script_text': "Bee cảm ơn bạn đã tin tưởng và sử dụng dịch vụ MB. Bee luôn sẵn sàng khi bạn cần!"
                    },
                    'status_code': 200,
                }

        # 1. Prioritize ScenarioService execution
        try:
            result = await self._handle_collecting_information(state)
            if result is not None:
                return result
        except Exception as e:
            LOGGER.warning(f"Scenario processing failed during handling: {str(e)}", exc_info=True)

        if intent_type == 'chit_chat' and topic_category == 'unclear_input':
            return {
                'type': 'no_data',
                'status_code': 204,
                'context': {
                    'generator': None
                }
            }

        # 1. Transaction complaint handling - Simplified version
        is_transaction_complaint = False
        final_complaint_type = None

        if "<transaction_complaint>" in query:
            xml_complaint_info = extract_transaction_complaint_info(query)
            is_transaction_complaint = True
            final_complaint_type = xml_complaint_info.get('complaint_type', 'other_complaint')

        if not is_transaction_complaint and intent_type == "transaction_complaint":
            is_transaction_complaint = True
            final_complaint_type = complaint_type or 'other_complaint'

        if is_transaction_complaint:
            # Tất cả complaint types đều sử dụng kịch bản có sẵn
            if self.app.complaint_handler.has_complaint_mapping(final_complaint_type):
                try:
                    return {
                        'type': 'complaint',
                        'status_code': 206,
                        'context': {
                            'generator': self.app.complaint_handler.handle_complaint(final_complaint_type, query)
                        }
                    }
                except Exception as e:
                    LOGGER.error(f"Error handling complaint '{final_complaint_type}': {str(e)}")
                    # Fallback to normal processing
                    analysis['intent_type'] = 'banking_service'
                    analysis['topic_category'] = 'standard'
            else:
                # No mapping for this complaint type, use normal RAG
                analysis['intent_type'] = 'banking_service'
                analysis['topic_category'] = 'standard'

        # 2. Other special cases (existing logic)
        if cache_check.get('check', False):
            state['cache_check'] = cache_check
            return {
                'type': 'cache',
                'status_code': 205,
                'context': {
                    'generator': self.app.cache_service.stream_cached_answer(state)
                }
            }

        if filter_check.get('filter_needed') == 'yes':
            filter_type = filter_check.get('filter_type', '1')
            return {
                'type': 'filtered',
                'status_code': 205,
                'context': {
                    'generator': self.app.content_filter_service.create_refusal_response(filter_type)
                }
            }

        if intent_type in ["chit_chat", "self_description", "off_topic"]:
            return {
                'type': intent_type,
                'status_code': 205,
                'context': {
                    'generator': None
                }
            }

        if self._is_simple_case(query):
            return {
                'type': 'chit_chat',
                'status_code': 205,
                'context': {
                    'generator': None
                }
            }

        return None

    def _is_simple_case(self, query: str) -> bool:
        """Consolidated simple case detection"""
        q_strip = query.strip()
        if not q_strip:
            return True

        # Do not classify single digits, choice options or currency/amounts (e.g. '1', '0đ', '500k') as simple chit-chat
        if q_strip.isdigit() or any(c.isdigit() for c in q_strip):
            return False

        if len(q_strip) < 3 and not any(p in q_strip.lower() for p in ["hi", "chào", "hey"]):
            return False

        if "<feedback>" in query:
            return True

        simple_patterns = {
            "greeting": (["xin chào", "hello", "hi", "chào", "hey"], 3),
            "thanks": (["cảm ơn", "thank", "thanks", "tks"], 5)
        }

        for pattern_type, (patterns, max_words) in simple_patterns.items():
            if any(p in query.lower() for p in patterns) and len(query.split()) <= max_words:
                return True

        return False

    async def _process_documents(self, analysis_result: Dict) -> Dict:
        """Streamlined document processing"""
        state = analysis_result['state']
        analysis = analysis_result['analysis']

        state.update(analysis)
        state['cache_check'] = analysis_result['cache_check']

        topic_category = analysis.get('topic_category', 'standard')
        query = state.get('enhanced_query', state['query'])

        location_doc_id = self._get_location_doc_id(topic_category)
        if location_doc_id:
            return {
                'type': 'location',
                'context': {'location_doc_id': location_doc_id, 'state': state},
                'status_code': 205
            }

        results_dict = await self.app.batch_processor.execute_document_batch(state, topic_category)

        if topic_category in ["specific_card", "generic_card"]:
            return await self._process_combined_card_documents(results_dict, query, topic_category)

        docs = results_dict.get('documents', [])
        return await self._process_standard_documents(docs, query)

    async def _process_combined_card_documents(self, results_dict: Dict, query: str, topic_category: str) -> Dict:
        """Optimized combined card document processing without LLM filtering"""
        standard_docs = results_dict.get('documents', [])
        card_result = results_dict.get('card_result', {})
        card_docs = []

        if card_result and not card_result.get('unknown', False) and card_result.get('is_leaf', False):
            card_docs = card_result.get('value', [])

        if topic_category == "specific_card" and card_docs:
            combined_docs = card_docs + standard_docs
            is_card_context = True
        else:
            combined_docs = standard_docs + card_docs
            is_card_context = False

        if not combined_docs:
            return {'type': 'no_data', 'status_code': 204}

        LOGGER.info(f"[Process Card Docs] Passing {len(combined_docs)} card & standard docs directly (LLM filter disabled).")
        formatted_docs = self.app.doc_processor.format_documents(combined_docs)

        return {
            'type': 'combined_card_documents',
            'context': {
                'docs': combined_docs,
                'formatted_docs': formatted_docs,
                'is_relevant': True,
                'is_card_context': is_card_context,
                'topic_category': topic_category
            },
            'status_code': 205
        }

    async def _process_standard_documents(self, docs: List[Dict], query: str) -> Dict:
        """Optimized standard document processing without LLM filtering"""
        if not docs:
            return {'type': 'no_data', 'status_code': 204}

        LOGGER.info(f"[Process Standard Docs] Passing {len(docs)} docs directly (LLM filter disabled).")
        formatted_docs = self.app.doc_processor.format_documents(docs)

        return {
            'type': 'standard_documents',
            'context': {
                'docs': docs,
                'formatted_docs': formatted_docs,
                'is_relevant': True
            },
            'status_code': 205
        }

    def _prepare_response_context(self, doc_result: Dict, request_state: Dict) -> Dict:
        """Simplified response context preparation"""
        if doc_result['type'] == 'location':
            return doc_result

        if doc_result['status_code'] == 204:
            return {'type': 'no_data', 'status_code': 204}

        context = doc_result['context']
        if context.get('is_relevant', False):
            is_card = context.get('is_card_context', False)

            return {
                'type': 'standard_rag',
                'context': {
                    'documents': context['formatted_docs'],
                    'docs_refs': self.app.doc_processor.prepare_docs_for_llm(context['docs']),
                    'query': request_state['query'],
                    'enhanced_query': request_state.get('enhanced_query'),
                    'messages': request_state.get('messages', []),
                    'greeting': request_state.get('greeting', False),
                    'is_card': is_card,
                    'response_type': 'card_rag' if is_card else 'standard_rag'
                },
                'status_code': 205
            }
        else:
            return {'type': 'no_data', 'status_code': 204}

    def _get_location_doc_id(self, topic: str) -> Optional[str]:
        """Fast location mapping"""
        location_map = {
            'chi_nhanh': 'cn_pgd',
            'atm': 'atm',
            'cdm_crm': 'cdm_crm',
            'smart_bank': 'smart_bank'
        }
        return location_map.get(topic)


# =============================================================================
# 7. RESPONSE GENERATION
# =============================================================================
class ResponseGenerator:
    """Unified response generation"""

    def __init__(self, app):
        self.app = app
        self.prompt_templates = {
            'chit_chat': "CHIT_CHAT",
            'self_description': "DESCRIPTION_BEE_PROMPT",
            'off_topic': "PROMPT_REFUSE",
            'standard_rag': "NORMAL_RAG_ANSWER_PROMPT",
            'card_rag': "CARD_RAG_ANSWER_PROMPT"
        }

    async def _generate_static_response(self, script_text: str) -> AsyncGenerator:
        """Helper to generate a static response using VERBATIM_PROMPT."""
        async for chunk in self.app.llm_service.llm_stream(
                inputs={'script': script_text},
                prompt_template=get_prompt("VERBATIM_PROMPT")
        ):
            yield chunk

    def generate(self, response_type: str, context: Dict) -> AsyncGenerator:
        """Generate appropriate response based on type"""
        if response_type == 'no_data':
            return self._generate_no_data_response()

        if response_type == 'location':
            return self.app.location_service.generate_location_response(
                context['state'], context['location_doc_id']
            )

        if response_type in ['chit_chat', 'self_description', 'off_topic']:
            return self._generate_simple_response(response_type, context)

        if response_type == 'standard_rag':
            if not context or 'documents' not in context:
                return self._generate_no_data_response()
            return self._generate_rag_response(context)

        # Handle script-based responses from scenario service
        if response_type in ['complete_script', 'verbatim_script']:
            return self._generate_static_response(context.get('script_text', ''))

        return self._generate_no_data_response()

    def _generate_no_data_response(self) -> AsyncGenerator:
        """Generate no data available response"""

        async def no_data_generator():
            fallback_prompt = """
          Vai trò: Bạn là Bee - trợ lý ảo của ngân hàng MB

          Nhiệm vụ: Thông báo không tìm thấy thông tin phù hợp

          Hướng dẫn: Trả lời CHÍNH XÁC câu: "Xin lỗi, Bee chưa thể trả lời câu hỏi này. Bạn vui lòng mô tả cụ thể 
          hơn được không, Bee rất sẵn lòng hỗ trợ!" - KHÔNG thêm thắt gì khác
          """

            async for chunk in self.app.llm_service.llm_stream(prompt_template=fallback_prompt):
                chunk_dict = chunk.model_dump()
                chunk_dict["status_code"] = 204
                chunk_dict["status_message"] = "no_data"
                modified_chunk = ChatCompletionChunk(**chunk_dict)
                yield modified_chunk

        return no_data_generator()

    def _generate_simple_response(self, response_type: str, context: Dict) -> AsyncGenerator:
        """Generate simple response types"""
        query = context.get('query', '')

        if 'feedback_type' in context:
            base_response = self.app.llm_service.llm_stream(
                prompt_template=get_prompt(self.prompt_templates['chit_chat']),
                inputs={
                    "documents": "",
                    "greeting": True,
                    "query": query,
                    "conversation_history": ""
                }
            )
            return self._wrap_response_with_status_check(base_response, query)

        if response_type == "self_description":
            prompt = get_prompt(self.prompt_templates['self_description']) + f"\n\nCâu hỏi: {query}"
            base_response = self.app.llm_service.llm_stream(prompt_template=prompt)
            return self._wrap_response_with_status_check(base_response, query)

        if response_type == "off_topic":
            base_response = self.app.llm_service.llm_stream(
                prompt_template=get_prompt(self.prompt_templates['off_topic']),
                inputs={"query": query}
            )
            return self._wrap_response_with_status_check(base_response, query)

        messages = context.get('messages', [])
        conversation_history = self._format_conversation_history(messages)

        base_response = self.app.llm_service.llm_stream(
            prompt_template=get_prompt(self.prompt_templates['chit_chat']),
            inputs={
                "query": query,
                "conversation_history": conversation_history
            }
        )
        return self._wrap_response_with_status_check(base_response, query)

    def _format_conversation_history(self, messages: List[Dict]) -> str:
        """Format conversation history for chit_chat prompt"""
        if not messages or len(messages) <= 1:
            return ""

        recent_messages = [messages[-2]] if len(messages) > 1 else []

        formatted = []
        for i, msg in enumerate(recent_messages):
            role = "Người dùng" if msg.get("role") == "user" else "BOT"
            content = msg.get("content", "").strip()
            if content:
                formatted.append(f"{role} ({i + 1}): {content}")

        return "\n".join(formatted) if formatted else ""

    def _generate_rag_response(self, context: Dict) -> AsyncGenerator:
        """Generate RAG response with optional Fact Grounding Verification."""
        prompt_type = context.get('response_type', 'standard_rag')
        if prompt_type not in ['card_rag', 'standard_rag']:
            prompt_type = 'card_rag' if context.get('is_card', False) else 'standard_rag'

        base_prompt = get_prompt(self.prompt_templates[prompt_type])

        query = context.get('query')
        if not query:
            return self._generate_no_data_response()

        messages = context.get('messages', [])
        conv_history = ""
        if len(messages) > 1:
            recent = messages[-10:-1]
            conv_history = "\n".join(
                f"{'User' if m['role'] == 'user' else 'Bot'}: {m['content'][:800]}"
                for m in recent
            )

        prompt = base_prompt.format(
            documents=context['documents'],
            date=datetime.now().date(),
            question=query,
            greeting=context.get('greeting', False),
            conversation_history=conv_history
        )

        base_response = self.app.llm_service.llm_stream(
            prompt_template=prompt,
            docs=context.get('docs_refs', [])
        )

        rag_context = context.get('documents', '')
        return self._wrap_rag_response_with_verification(base_response, query, rag_context)

    def _wrap_response_with_status_check(self, response_stream: AsyncGenerator, query: str) -> AsyncGenerator:
        """Wrap response stream to check for standard no-info message and set status code"""

        async def wrapped_generator():
            full_response = ""
            chunks_buffer = []
            no_info_detected = False

            async for chunk in response_stream:
                try:
                    if not hasattr(chunk, 'choices') or not chunk.choices:
                        continue

                    chunks_buffer.append(chunk)

                    if (chunk.choices and
                            chunk.choices[0].delta and
                            chunk.choices[0].delta.content):
                        content = chunk.choices[0].delta.content
                        full_response += content

                except Exception as e:
                    LOGGER.error(f"RESPONSE_CHUNK_ERROR: {str(e)}")
                    continue

            if "Xin lỗi, Bee chưa thể trả lời câu hỏi này" in full_response:
                no_info_detected = True

            for chunk in chunks_buffer:
                if no_info_detected:
                    chunk_dict = chunk.model_dump()
                    chunk_dict["status_code"] = 204
                    chunk_dict["status_message"] = "no_data"
                    chunk = ChatCompletionChunk(**chunk_dict)
                yield chunk

        return wrapped_generator()

    # -------------------------------------------------------------------------
    # Fact Grounding Verification Engine
    # -------------------------------------------------------------------------
    _CLAIM_PATTERN = re.compile(
        r'\d+[%đồngVND]|'
        r'\b(\d+\.\d+|\d{1,3}(?:[.,]\d{3})+)\b|'   # numbers with thousands sep
        r'\b(tối đa|tối thiểu|không được|được phép|chỉ|không quá|ít nhất|bắt buộc|'
        r'priority|tất toán|không giới hạn|miễn phí|lãi suất|lợi nhuận|kỳ vọng|nfc|iphone|hạn mức|hết hạn|hiệu lực)\b',
        re.IGNORECASE
    )

    def _needs_fact_verification(self, response_text: str, rag_context: str) -> bool:
        """Fast Python heuristic (0ms overhead) to trigger verification when response contains policy/numerical claims."""
        if not rag_context or not response_text:
            return False
        if "Bee chưa thể trả lời" in response_text:
            return False
        return bool(self._CLAIM_PATTERN.search(response_text))

    def _wrap_rag_response_with_verification(
        self,
        response_stream: AsyncGenerator,
        query: str,
        rag_context: str
    ) -> AsyncGenerator:
        """Wrap RAG stream with Fact Grounding Verification."""
        app = self.app

        async def wrapped_generator():
            full_response = ""
            chunks_buffer = []
            no_info_detected = False

            async for chunk in response_stream:
                try:
                    if not hasattr(chunk, 'choices') or not chunk.choices:
                        continue
                    chunks_buffer.append(chunk)
                    if (
                        chunk.choices
                        and chunk.choices[0].delta
                        and chunk.choices[0].delta.content
                    ):
                        full_response += chunk.choices[0].delta.content
                except Exception as e:
                    LOGGER.error(f"RESPONSE_CHUNK_ERROR: {str(e)}")
                    continue

            if "Xin lỗi, Bee chưa thể trả lời câu hỏi này" in full_response:
                no_info_detected = True

            if not no_info_detected and self._needs_fact_verification(full_response, rag_context):
                try:
                    verification_result = await app.llm_service.llm_task(
                        inputs={
                            "rag_context": rag_context[:3000],
                            "bot_response": full_response[:2000]
                        },
                        prompt_template=get_prompt("FACT_GROUNDING_VERIFICATION_PROMPT"),
                        max_tokens=20
                    )
                    verdict = (verification_result or "").strip().upper()
                    if verdict.startswith("FAIL"):
                        LOGGER.warning(
                            f"Fact verification FAIL detected. "
                            f"Query='{query[:60]}' | Verdict='{verdict[:100]}'"
                        )
                        no_info_detected = True
                    else:
                        LOGGER.info(f"Fact verification PASS. Query='{query[:60]}'")
                except Exception as e:
                    LOGGER.warning(f"Fact verification error (skip): {e}")

            for chunk in chunks_buffer:
                if no_info_detected:
                    chunk_dict = chunk.model_dump()
                    chunk_dict["status_code"] = 204
                    chunk_dict["status_message"] = "no_data"
                    chunk = ChatCompletionChunk(**chunk_dict)
                yield chunk

        return wrapped_generator()



# =============================================================================
# 8. MAIN APPLICATION CLASS
# =============================================================================
class BeeChatApp:
    """Optimized BeeChat application for high concurrency"""

    def __init__(self, bot_id: str):
        self.bot_id = bot_id
        self.collection_master = f"bot_{bot_id.replace('-', '_')}"
        self._initialized = False

    async def _ensure_initialized(self):
        """Fast initialization without warm-up"""
        if self._initialized:
            return

        # Core components
        self.cache_manager = CacheManager(max_size=5000, ttl=900)
        self.state_manager = DialogueStateManager()

        self.llm_service = LLMService(self.bot_id)
        self.document_service = DocumentService(self.bot_id, self.llm_service)
        self.cache_service = QAService(self.bot_id, self.llm_service, self.document_service)
        self.card_service = CardService(self.bot_id, self.llm_service)
        self.location_service = LocationService(self.bot_id, self.llm_service)
        self.content_filter_service = ContentFilterService(self.llm_service)
        self.complaint_handler = SimpleComplaintHandler(self.llm_service)
        self.scenario_service = ScenarioService(llm_service=self.llm_service)

        try:
            self.abbr_handler = AbbreviationHandler()
        except Exception:
            self.abbr_handler = None

        # Processors
        self.doc_processor = DocumentProcessor(self.cache_manager, self.document_service)
        self.analyzer = ResponseAnalyzer(self.cache_manager)
        self.batch_processor = BatchProcessor(self)
        self.pipeline = ProcessingPipeline(self)
        self.response_generator = ResponseGenerator(self)

        # Configure cache service
        self.cache_service.configure(
            similarity_threshold=0.75,
            match_confidence=0.8,
            retrieval_top_k=20,
            rerank_top_k=10
        )

        self._initialized = True

    def clean_content_messages(self, messages: List[Dict]):
        import json
        results = []
        for msg in messages:
            try:
                content = msg.get("content", "")
                if isinstance(content, str) and content.startswith("[") and content.endswith("]"):
                    try:
                        parse_content = json.loads(content)
                        if isinstance(parse_content, list) and len(parse_content) > 0 and isinstance(parse_content[0], dict) and 'text' in parse_content[0]:
                            content = parse_content[0]['text']
                    except Exception:
                        pass
                results.append({
                    'role': msg.get('role', 'user'),
                    "content": content
                })
            except Exception as e:
                LOGGER.error(f"Error during Clean Content: {e}", exc_info=True)
                results.append(msg)

        # Remove duplicate last msg
        if len(results) > 1:
            if results[-1]['role'] == results[-2]['role'] == "user" and results[-1]['content'] == results[-2]['content']:
                results.pop()
        return results

    @observe(name="BeeChatApp")
    async def run(self, messages: List[Dict], role_ids=None, topic: str = "default",
                  session_id: Optional[str] = None, response_status: Dict = None, **kwargs) -> AsyncGenerator:
        """Optimized main execution with conversation context analysis"""
        await self._ensure_initialized()

        messages = self.clean_content_messages(messages)

        query = messages[-1]['content'].strip()
        session_id = session_id or str(uuid.uuid4())

        # Load existing state from session
        loaded_state = await self.state_manager.load_state(session_id)

        try:
            if self.abbr_handler:
                try:
                    annotated_query = self.abbr_handler.annotate_query(query)
                except Exception:
                    annotated_query = query
            else:
                annotated_query = query

            # Merge loaded state with new request state
            request_state = {
                **loaded_state,
                'query': annotated_query,
                'original_query': query,
                'messages': messages,
                'session_id': session_id,
                'greeting': False
            }

            async with profile_async_block(f"Pipeline Execution (session={session_id[:8]})"):
                result = await self.pipeline.execute(request_state)

            # Cập nhật lại state với scenario_context sau khi pipeline chạy
            if 'scenario_context' in request_state:
                result['context'] = result.get('context', {})
                result['context']['scenario_context'] = request_state['scenario_context']

            # Save state after processing
            await self.state_manager.save_state(session_id, request_state)

            # Handle state cleanup for complete_script scenarios
            if result.get('type') == 'complete_script':
                await self.state_manager.delete_state(session_id)

            if not result:
                result = {'type': 'no_data', 'context': {}, 'status_code': 204}

            if "context" in result and result["context"].get('generator'):
                async for chunk in result["context"]['generator']:
                    if not hasattr(chunk, 'status_code'):
                        chunk.status_code = result.get('status_code')
                    yield chunk
                return

            if 'type' not in result:
                result = {'type': 'no_data', 'context': {}, 'status_code': 204}

            if 'FACEBOOK_MEDIA_IMAGE' in query:
                if 'scenario_context' not in request_state:
                    async for chunk in self.llm_service.llm_stream(
                            inputs={
                                'script': "Bee đã nhận được ảnh bạn gửi. Bạn vui lòng cho Bee biết bạn đang muốn kiểm tra hay xử lý vấn đề gì liên quan đến ảnh này để Bee hỗ trợ nhanh nhất nhé.\n"},
                            prompt_template=get_prompt("VERBATIM_PROMPT")
                    ):
                        chunk.status_code = 205
                        yield chunk
                    return

            response_stream = self.response_generator.generate(result['type'], result.get('context', {}))

            if response_stream is None:
                async def fallback():
                    async for chunk in self.llm_service.llm_stream(
                            inputs={
                                'script': "Xin lỗi, Bee chưa thể trả lời câu hỏi này. Bạn vui lòng mô tả cụ thể hơn được không, Bee rất sẵn lòng hỗ trợ!"},
                            prompt_template=get_prompt("VERBATIM_PROMPT")
                    ):
                        if not hasattr(chunk, 'status_code'):
                            chunk.status_code = result.get('status_code')
                        yield chunk

                response_stream = fallback()

            if not hasattr(response_stream, '__aiter__'):
                async def error_fallback():
                    async for chunk in self.llm_service.llm_stream(
                            inputs={'script': "Lỗi hệ thống, vui lòng thử lại."},
                            prompt_template=get_prompt("VERBATIM_PROMPT")
                    ):
                        if not hasattr(chunk, 'status_code'):
                            chunk.status_code = result.get('status_code')
                        yield chunk

                response_stream = error_fallback()

            chunk_count = 0
            try:
                async for chunk in response_stream:
                    chunk_count += 1
                    if not hasattr(chunk, 'status_code'):
                        chunk.status_code = result.get('status_code')
                    yield chunk
            except Exception as e:
                LOGGER.error(f"STREAM_ERROR: session={session_id[:8]}, chunks={chunk_count}, error={str(e)}")
                raise

        except Exception as e:
            LOGGER.error(f"REQUEST_ERROR: session={session_id[:8]}, error={str(e)}")
            raise


async def main():
    bot_id = "da498399-56c2-479f-80c6-b79e605dcd66"
    bot = BeeChatApp(bot_id)
    session_id = "123"

    print("\n========= Optimized BeeChat Test =========\n")
    print("Welcome to MB Bank Virtual Assistant")
    print("Type 'exit' to end the conversation\n")

    messages = []

    while True:
        user_input = input("You: ")

        if user_input.lower() in ["exit", "quit", "bye"]:
            print("\nThank you for using MB Bank Virtual Assistant. Goodbye!")
            break

        messages.append({"role": "user", "content": user_input})

        total_start_time = time.time()
        first_token_time = None

        print("\nBot: ", end="", flush=True)
        full_response = ""
        chunk_count = 0
        status_code = None
        status_message = None

        try:
            response_generator = bot.run(messages, session_id=session_id)

            if hasattr(response_generator, '__aiter__'):
                async for chunk in response_generator:
                    chunk_count += 1

                    if first_token_time is None and chunk.choices and chunk.choices[0].delta.content:
                        first_token_time = time.time()
                        first_token_latency = first_token_time - total_start_time
                        LOGGER.info(f"FIRST_TOKEN_TIME: {first_token_latency:.3f}s")

                    if hasattr(chunk, 'status_code'):
                        status_code = chunk.status_code
                    if hasattr(chunk, 'status_message'):
                        status_message = chunk.status_message

                    if chunk.choices and chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        print(content, end="", flush=True)
                        full_response += content

            else:
                print(f"Error: Expected async generator, got {type(response_generator)}")
                continue

        except Exception as e:
            total_error_time = time.time() - total_start_time
            LOGGER.error(f"ERROR_RESPONSE_TIME: {total_error_time:.3f}s - Error: {str(e)}")
            print(f"\nError occurred: {str(e)}")
            continue

        total_end_time = time.time()
        total_response_time = total_end_time - total_start_time

        chars_per_second = len(full_response) / total_response_time if total_response_time > 0 else 0
        tokens_per_second = chunk_count / total_response_time if total_response_time > 0 else 0

        LOGGER.info(f"TOTAL_RESPONSE_TIME: {total_response_time:.3f}s")
        LOGGER.info(f"RESPONSE_METRICS: "
                    f"total_chunks={chunk_count}, "
                    f"response_length={len(full_response)}, "
                    f"chars_per_sec={chars_per_second:.1f}, "
                    f"chunks_per_sec={tokens_per_second:.1f}, "
                    f"status_code={status_code}, "
                    f"status_message='{status_message}'")

        print(f"\n[Metrics: {total_response_time:.2f}s total, {chars_per_second:.0f} chars/s, Status: {status_code}]")

        messages.append({"role": "assistant", "content": full_response})
        print("\n")


if __name__ == "__main__":
    asyncio.run(main())
