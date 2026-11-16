import time
import uuid
import asyncio
import re
from typing import List, Dict, AsyncGenerator, Optional, Tuple
from datetime import datetime

from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from beegenerate.loggings import LOGGER
from beektnb.prompts.beektnb_prompt import (
    BALANCED_AUDIT_RESPONSE_PROMPT,
    BALANCED_INTENT_CLASSIFICATION_PROMPT,
    ENHANCED_SECURITY_RESPONSE_PROMPT,
    AUDIT_CHIT_CHAT_PROMPT,
    AUDIT_REFUSE_PROMPT,
    AUDIT_CLARIFICATION_PROMPT, BALANCED_DOCUMENT_ASSESSMENT_PROMPT
)
from beektnb.services.document_service import DocumentService
from beektnb.services.llm_service import LLMService
from beektnb.utils.abbreviation import AbbreviationHandler
from beektnb.utils.instruction_tree import Instruction_tree


class QualityMonitor:
    """Monitor chất lượng response với các metrics đơn giản"""

    def __init__(self):
        self.quality_log = []

    def evaluate_response_quality(self, query: str, response: str, analysis: Dict) -> Dict:
        """Đánh giá chất lượng response theo 5 tiêu chí cơ bản"""

        # 1. Length appropriateness
        length_score = self._evaluate_length(query, response)

        # 2. Structure quality
        structure_score = self._evaluate_structure(response)

        # 3. Confidence alignment
        confidence_score = self._evaluate_confidence_alignment(response, analysis)

        # 4. Error indicators
        error_score = self._check_error_indicators(response)

        # 5. Completeness
        completeness_score = self._evaluate_completeness(query, response)

        overall_score = (length_score + structure_score + confidence_score +
                         error_score + completeness_score) / 5

        quality_result = {
            'timestamp': datetime.now().isoformat(),
            'query': query[:100],  # Truncate for logging
            'overall_score': round(overall_score, 2),
            'metrics': {
                'length': length_score,
                'structure': structure_score,
                'confidence': confidence_score,
                'error_free': error_score,
                'completeness': completeness_score
            },
            'analysis_confidence': analysis.get('confidence', 0.0)
        }

        self.quality_log.append(quality_result)

        # Log if quality is concerning
        if overall_score < 0.6:
            LOGGER.warning(f"Low quality response detected: {overall_score:.2f}")

        return quality_result

    def _evaluate_length(self, query: str, response: str) -> float:
        """Đánh giá độ dài phù hợp"""
        query_len = len(query.split())
        response_len = len(response.split())

        # Simple heuristic: response should be 2-20x query length
        ratio = response_len / max(query_len, 1)

        if 2 <= ratio <= 20:
            return 1.0
        elif 1 <= ratio < 2 or 20 < ratio <= 30:
            return 0.7
        else:
            return 0.3

    def _evaluate_structure(self, response: str) -> float:
        """Đánh giá cấu trúc response"""
        score = 0.0

        # Has clear sections/paragraphs
        if '\n\n' in response or '**' in response or '###' in response:
            score += 0.3

        # Has bullet points or numbered lists when appropriate
        if ('- ' in response or '• ' in response or
                re.search(r'\d+\.', response)):
            score += 0.3

        # Has logical flow (connecting words)
        connecting_words = ['do đó', 'vì vậy', 'tuy nhiên', 'ngoài ra', 'đầu tiên', 'tiếp theo']
        if any(word in response.lower() for word in connecting_words):
            score += 0.2

        # Not too fragmented
        sentences = response.split('.')
        if 3 <= len(sentences) <= 20:
            score += 0.2

        return min(score, 1.0)

    def _evaluate_confidence_alignment(self, response: str, analysis: Dict) -> float:
        """Kiểm tra alignment giữa confidence và response"""
        analysis_confidence = analysis.get('confidence', 0.5)

        # Check for uncertainty markers in response
        uncertainty_markers = ['có thể', 'thường', 'một cách chung', 'thông thường',
                               'không chắc chắn', 'cần xác nhận']

        uncertainty_count = sum(1 for marker in uncertainty_markers
                                if marker in response.lower())

        # High confidence should have few uncertainty markers
        if analysis_confidence > 0.8:
            return 1.0 if uncertainty_count <= 1 else 0.6
        elif analysis_confidence > 0.6:
            return 1.0 if uncertainty_count <= 2 else 0.7
        else:
            return 1.0 if uncertainty_count >= 1 else 0.8

    def _check_error_indicators(self, response: str) -> float:
        """Kiểm tra các indicator lỗi"""
        error_indicators = [
            'xin lỗi, tôi không thể',
            'không có thông tin',
            'tôi không biết',
            'không thể trả lời',
            'error', 'lỗi'
        ]

        has_errors = any(indicator in response.lower()
                         for indicator in error_indicators)

        return 0.0 if has_errors else 1.0

    def _evaluate_completeness(self, query: str, response: str) -> float:
        """Đánh giá tính đầy đủ của response"""
        query_words = set(query.lower().split())
        response_words = set(response.lower().split())

        # Key query terms should appear in response
        key_terms = [word for word in query_words
                     if len(word) > 3 and word not in ['của', 'trong', 'với', 'theo']]

        if not key_terms:
            return 1.0

        covered_terms = sum(1 for term in key_terms if term in response_words)
        coverage_ratio = covered_terms / len(key_terms)

        return coverage_ratio

    def get_quality_stats(self) -> Dict:
        """Lấy thống kê chất lượng"""
        if not self.quality_log:
            return {'total_responses': 0}

        recent_scores = [entry['overall_score'] for entry in self.quality_log[-100:]]

        return {
            'total_responses': len(self.quality_log),
            'recent_avg_quality': sum(recent_scores) / len(recent_scores),
            'low_quality_count': sum(1 for score in recent_scores if score < 0.6),
            'high_quality_count': sum(1 for score in recent_scores if score > 0.8),
            'last_updated': datetime.now().isoformat()
        }

# =============================================================================
# 1. OPTIMIZED INSTRUCTION TREE PROCESSOR
# =============================================================================
class InstructionTreeProcessor:
    """Optimized processor for extracting relevant headings from instruction tree"""

    def __init__(self, llm_service, cache):
        self.llm_service = llm_service
        self.cache = cache
        self._tree_summary = self._build_tree_summary()
        self._heading_map = self._build_heading_map()

    def _build_tree_summary(self) -> str:
        """Build concise tree summary for context"""
        summary_parts = []
        for main_key, main_value in Instruction_tree.items():
            if isinstance(main_value, dict):
                main_clean = main_key.replace("HƯỚNG DẪN KIỂM TOÁN NỘI BỘ", "").strip()
                for sub_key in list(main_value.keys())[:12]:  # Limit to prevent token overflow
                    sub_clean = sub_key.replace("HƯỚNG DẪN", "").replace("Kiểm Toán Nội Bộ", "").strip()
                    if sub_clean and len(sub_clean) > 5:
                        summary_parts.append(f"- {sub_clean}")
        return "\n".join(summary_parts[:20])  # Top 20 most relevant

    def _build_heading_map(self) -> Dict[str, List[str]]:
        """Build mapping of keywords to relevant headings"""
        keyword_map = {}

        for main_key, main_value in Instruction_tree.items():
            if isinstance(main_value, dict):
                for sub_key, sub_value in main_value.items():
                    # Extract key terms from headings
                    terms = self._extract_key_terms(sub_key)
                    for term in terms:
                        if term not in keyword_map:
                            keyword_map[term] = []
                        keyword_map[term].append(sub_key)

        return keyword_map

    def _extract_key_terms(self, heading: str) -> List[str]:
        """Extract key terms from heading for matching"""
        # Remove common prefixes and clean
        cleaned = heading.replace("HƯỚNG DẪN", "").replace("Kiểm Toán Nội Bộ", "")
        cleaned = re.sub(r'\d+\.', '', cleaned).strip()

        # Extract meaningful terms
        terms = []
        words = cleaned.lower().split()

        for word in words:
            if len(word) > 3 and word not in ['hoạt động', 'kiểm', 'toán', 'hướng', 'dẫn']:
                terms.append(word)

        return terms

    async def extract_relevant_headings(self, query: str) -> List[str]:
        """Extract relevant headings from instruction tree - CORE OPTIMIZATION"""
        cache_key = f"tree_headings:{hash(query)}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        # Fast keyword matching first
        query_lower = query.lower()
        quick_matches = []

        for keyword, headings in self._heading_map.items():
            if keyword in query_lower:
                quick_matches.extend(headings[:2])  # Limit per keyword

        # If we have good keyword matches, use them
        if len(quick_matches) >= 3:
            result = list(set(quick_matches))[:5]  # Deduplicate and limit
            await self.cache.set(cache_key, result)
            return result

        # Fallback to LLM analysis for complex queries
        llm_prompt = f"""
Từ câu hỏi kiểm toán, xác định 3-5 mục liên quan nhất:

Các mục có sẵn:
{self._tree_summary}

Câu hỏi: {query}

Trả về danh sách tên mục (mỗi mục một dòng, hoặc "NONE" nếu không liên quan):
        """

        try:
            response = await self.llm_service.llm_task(
                inputs={"query": query, "tree_summary": self._tree_summary},
                prompt_template=llm_prompt,
                timeout=10.0  # Quick timeout for this task
            )

            headings = [line.strip() for line in response.split('\n')
                        if line.strip() and line.strip() != "NONE"][:5]

            await self.cache.set(cache_key, headings)
            return headings

        except Exception as e:
            LOGGER.warning(f"Tree extraction fallback error: {e}")
            await self.cache.set(cache_key, [])
            return []


# =============================================================================
# 2. UNIFIED CACHE WITH CONSISTENT KEY GENERATION
# =============================================================================
class UnifiedCache:
    """Optimized cache with consistent key generation and automatic cleanup"""

    def __init__(self, max_size=400):
        self.cache = {}
        self.max_size = max_size
        self.access_time = {}
        self._lock = asyncio.Lock()

    def _generate_key(self, prefix: str, *args) -> str:
        """Generate consistent cache keys"""
        parts = [str(arg)[:150] for arg in args]  # Consistent truncation
        combined = "|".join(parts)
        return f"{prefix}:{hash(combined)}"

    async def get(self, key, default=None):
        async with self._lock:
            if key in self.cache:
                self.access_time[key] = time.time()
                return self.cache[key]
            return default

    async def set(self, key, value):
        async with self._lock:
            self.cache[key] = value
            self.access_time[key] = time.time()

            # Cleanup if needed
            if len(self.cache) > self.max_size:
                # Remove 20% of oldest entries
                cleanup_count = max(1, self.max_size // 5)
                oldest_keys = sorted(self.access_time.items(), key=lambda x: x[1])[:cleanup_count]
                for old_key, _ in oldest_keys:
                    self.cache.pop(old_key, None)
                    self.access_time.pop(old_key, None)


# =============================================================================
# 3. PARALLEL TASK ORCHESTRATOR
# =============================================================================
class ParallelTaskOrchestrator:
    """Orchestrates parallel execution of analysis tasks"""

    @staticmethod
    async def run_parallel_analysis(
            intent_task,
            tree_task,
            timeout: float = 15.0
    ) -> Tuple[Dict, List[str]]:
        """Run intent classification and tree extraction in parallel"""
        try:
            results = await asyncio.wait_for(
                asyncio.gather(intent_task, tree_task, return_exceptions=True),
                timeout=timeout
            )

            intent_result = results[0] if not isinstance(results[0], Exception) else {
                'primary_intent': 'INFORMATION_EXTRACTION',
                'confidence': 0.5,
                'out_of_scope': False,
                'detected_entities': [],
                'response_format': 'standard'
            }

            tree_result = results[1] if not isinstance(results[1], Exception) else []

            return intent_result, tree_result

        except asyncio.TimeoutError:
            LOGGER.warning(f"Parallel analysis timeout after {timeout}s")
            return {
                       'primary_intent': 'INFORMATION_EXTRACTION',
                       'confidence': 0.4,
                       'out_of_scope': False,
                       'detected_entities': [],
                       'response_format': 'standard'
                   }, []

    @staticmethod
    async def run_parallel_document_processing(
            doc_retrieval_task,
            assessment_task,
            timeout: float = 20.0
    ) -> Tuple[List[Dict], Dict]:
        """Run document retrieval and assessment in parallel when possible"""
        try:
            # For document processing, we need retrieval first, then assessment
            docs = await asyncio.wait_for(doc_retrieval_task, timeout=timeout / 2)

            if not docs:
                return [], {
                    'decision': 'REFUSE',
                    'score': 0.0,
                    'scope': 'IN_SCOPE',
                    'info_type': 'NO_INFO',
                    'relevance': 'NO_MATCH',
                    'reason': 'no_documents'
                }

            assessment = await asyncio.wait_for(assessment_task, timeout=timeout / 2)
            return docs, assessment

        except asyncio.TimeoutError:
            LOGGER.warning(f"Document processing timeout after {timeout}s")
            return [], {
                'decision': 'REFUSE',
                'score': 0.0,
                'scope': 'UNKNOWN',
                'info_type': 'NO_INFO',
                'relevance': 'NO_MATCH',
                'reason': 'timeout'
            }


# =============================================================================
# 4. STREAMLINED INTENT CLASSIFIER
# =============================================================================
class StreamlinedIntentClassifier:
    """Optimized intent classifier with parallel processing"""

    def __init__(self, llm_service, cache):
        self.llm_service = llm_service
        self.cache = cache

    async def classify_intent(self, query: str, tree_headings: List[str]) -> Dict:
        """Classify intent with enhanced step-by-step analysis"""
        cache_key = self.cache._generate_key("intent", query, str(tree_headings))
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        # Build focused tree context from headings
        tree_context = "\n".join(
            [f"- {heading}" for heading in tree_headings]) if tree_headings else "Không có context cụ thể"

        # THAY ĐỔI: Sử dụng prompt mới
        response = await self.llm_service.llm_task(
            inputs={
                "query": query,
                "tree_context": tree_context
            },
            prompt_template=BALANCED_INTENT_CLASSIFICATION_PROMPT,  # ← THAY ĐỔI Ở ĐÂY
            timeout=12.0
        )

        result = self._parse_balanced_classification(response, query)  # ← THAY ĐỔI TÊN METHOD
        await self.cache.set(cache_key, result)

        LOGGER.info(f"Intent: {result['primary_intent']}, Confidence: {result['confidence']:.2f}, "
                    f"Step Analysis Available: {bool(result.get('step_analysis'))}")  # ← THÊM LOG MỚI
        return result

    # THAY THẾ hoàn toàn method _parse_classification bằng:
    def _parse_balanced_classification(self, response: str, query: str) -> Dict:
        """Parse classification response với step-by-step analysis"""

        # Parse step-by-step analysis - MỚI
        step_analysis_pattern = r'<step_by_step_analysis>(.*?)</step_by_step_analysis>'
        step_match = re.search(step_analysis_pattern, response, re.DOTALL)
        step_analysis = step_match.group(1).strip() if step_match else ""

        # Parse main intent analysis
        patterns = {
            'primary_intent': r'<primary_intent>(.*?)</primary_intent>',
            'confidence': r'<confidence>(.*?)</confidence>',
            'out_of_scope': r'<out_of_scope>(.*?)</out_of_scope>',
            'detected_entities': r'<detected_entities>(.*?)</detected_entities>',
            'response_format': r'<response_format>(.*?)</response_format>',
            'needs_clarification': r'<needs_clarification>(.*?)</needs_clarification>'
        }

        result = {
            'primary_intent': 'INFORMATION_EXTRACTION',
            'confidence': 0.5,
            'out_of_scope': False,
            'needs_clarification': False,
            'detected_entities': [],
            'response_format': 'standard',
            'query': query,
            'step_analysis': step_analysis  # MỚI: Lưu quá trình phân tích
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, response, re.DOTALL)
            if match:
                value = match.group(1).strip()
                if key == 'confidence':
                    try:
                        result[key] = max(0.0, min(1.0, float(value)))
                    except ValueError:
                        result[key] = 0.5
                elif key in ['out_of_scope', 'needs_clarification']:
                    result[key] = value.lower() == 'true'
                elif key == 'detected_entities':
                    result[key] = [e.strip() for e in value.split(',') if e.strip()]
                else:
                    result[key] = value if value and value != 'None' else result[key]

        # MỚI: Enhanced confidence adjustment dựa trên step analysis
        if step_analysis:
            result = self._adjust_confidence_from_analysis(result, step_analysis)

        # MỚI: Consistency validation
        result = self._validate_classification_consistency(result)

        return result

    def _adjust_confidence_from_analysis(self, result: Dict, step_analysis: str) -> Dict:
        """Điều chỉnh confidence dựa trên chất lượng step analysis"""
        step_lower = step_analysis.lower()

        # Factors that reduce confidence
        uncertainty_factors = [
            ('không chắc', -0.2),
            ('không rõ', -0.15),
            ('mơ hồ', -0.2),
            ('thiếu', -0.1),
            ('có thể', -0.05),
            ('không đầy đủ', -0.15)
        ]

        # Factors that increase confidence
        clarity_factors = [
            ('rõ ràng', 0.1),
            ('chắc chắn', 0.15),
            ('chính xác', 0.1),
            ('đầy đủ', 0.1),
            ('phù hợp', 0.05)
        ]

        confidence_adjustment = 0.0

        for factor, adjustment in uncertainty_factors:
            if factor in step_lower:
                confidence_adjustment += adjustment

        for factor, adjustment in clarity_factors:
            if factor in step_lower:
                confidence_adjustment += adjustment

        # Apply adjustment
        original_confidence = result['confidence']
        result['confidence'] = max(0.1, min(1.0, original_confidence + confidence_adjustment))

        # Log significant changes
        if abs(confidence_adjustment) > 0.1:
            LOGGER.info(f"Confidence adjusted from {original_confidence:.2f} to {result['confidence']:.2f} "
                        f"based on step analysis")

        return result

    def _validate_classification_consistency(self, result: Dict) -> Dict:
        """Validate và fix inconsistencies trong classification"""

        # Rule 1: OUT_OF_SCOPE intent should have out_of_scope = True
        if result['primary_intent'] == 'OUT_OF_SCOPE':
            result['out_of_scope'] = True
            result['confidence'] = max(result['confidence'], 0.7)  # Should be confident about out-of-scope

        # Rule 2: Very low confidence should trigger clarification need
        if result['confidence'] < 0.4 and not result['out_of_scope']:
            result['needs_clarification'] = True
            LOGGER.info("Low confidence triggered clarification need")

        # Rule 3: CHIT_CHAT should have high confidence if detected
        if result['primary_intent'] == 'CHIT_CHAT':
            result['confidence'] = max(result['confidence'], 0.8)
            result['out_of_scope'] = False

        # Rule 4: Confidence bounds checking
        if result['confidence'] > 0.95:
            result['confidence'] = 0.95  # Cap at 95% to maintain humility
        elif result['confidence'] < 0.1:
            result['confidence'] = 0.1  # Minimum confidence floor

        return result


# =============================================================================
# 5. ENHANCED DOCUMENT PROCESSOR
# =============================================================================
class EnhancedDocumentProcessor:
    """Optimized document processor with tree-enhanced queries"""

    def __init__(self, document_service, llm_service, cache):
        self.document_service = document_service
        self.llm_service = llm_service
        self.cache = cache

        # Optimized retrieval configs
        self.retrieval_configs = {
            'SUMMARIZATION_REQUEST': {'base_k': 20, 'rerank_k': 8},
            'PROCEDURAL_GUIDANCE': {'base_k': 22, 'rerank_k': 9},
            'INFERENTIAL_REASONING': {'base_k': 18, 'rerank_k': 7},
            'COMPARISON_REQUEST': {'base_k': 20, 'rerank_k': 8},
            'INFORMATION_EXTRACTION': {'base_k': 16, 'rerank_k': 6},
            'PRACTICAL_SITUATION': {'base_k': 18, 'rerank_k': 7},
            'ADVISORY_CONSULTATION': {'base_k': 16, 'rerank_k': 6}
        }
        self.default_config = {'base_k': 16, 'rerank_k': 6}

    async def process_with_tree_enhancement(
            self,
            query: str,
            intent_info: Dict,
            tree_headings: List[str],
            collection: str
    ) -> Dict:
        """Process documents with tree-enhanced query"""

        # Early exits for efficiency
        if intent_info.get('out_of_scope', False):
            return self._create_result('out_of_scope', [], '', {
                'decision': 'REFUSE', 'score': 0.0, 'scope': 'OUT_OF_SCOPE',
                'info_type': 'NO_INFO', 'relevance': 'NO_MATCH', 'reason': 'out_of_scope'
            })

        try:
            # Parallel document processing
            enhanced_query = self._enhance_query_with_tree(query, tree_headings)

            doc_task = self._retrieve_documents(enhanced_query, intent_info, collection)

            # Get documents first
            docs = await doc_task

            if not docs:
                return self._create_result('no_documents', [], '', {
                    'decision': 'REFUSE', 'score': 0.0, 'scope': 'IN_SCOPE',
                    'info_type': 'NO_INFO', 'relevance': 'NO_MATCH', 'reason': 'no_documents'
                })

            # Format and assess
            formatted = self._format_documents(docs)

            if not formatted or len(formatted.strip()) < 50:
                return self._create_result('insufficient', docs, formatted, {
                    'decision': 'REFUSE', 'score': 0.0, 'scope': 'IN_SCOPE',
                    'info_type': 'NO_INFO', 'relevance': 'NO_MATCH', 'reason': 'insufficient_content'
                })

            # Assessment
            assessment = await self._assess_documents(query, formatted, intent_info)

            status = 'success' if assessment['decision'] == 'ANSWER' else 'insufficient'
            return self._create_result(status, docs, formatted, assessment)

        except Exception as e:
            LOGGER.error(f"Document processing error: {str(e)}")
            return self._create_result('error', [], '', {
                'decision': 'REFUSE', 'score': 0.0, 'scope': 'UNKNOWN',
                'info_type': 'NO_INFO', 'relevance': 'NO_MATCH', 'reason': 'processing_error'
            })

    def _enhance_query_with_tree(self, query: str, tree_headings: List[str]) -> str:
        """Enhance query with relevant tree headings - KEY OPTIMIZATION"""
        if not tree_headings:
            return query

        # Extract key terms from headings
        context_terms = []
        for heading in tree_headings:
            # Clean and extract meaningful terms
            clean_heading = re.sub(r'\d+\.', '', heading).strip()
            terms = [word for word in clean_heading.split()
                     if len(word) > 3 and word.lower() not in ['hướng', 'dẫn', 'kiểm', 'toán']]
            context_terms.extend(terms[:3])  # Top 3 terms per heading

        # Limit total context terms to prevent query bloat
        unique_terms = list(set(context_terms))[:8]

        if unique_terms:
            enhanced_query = f"{query} {' '.join(unique_terms)}"
            LOGGER.info(f"Enhanced query with tree context: {len(unique_terms)} terms added")
            return enhanced_query

        return query

    async def _retrieve_documents(self, query: str, intent_info: Dict, collection: str) -> List[Dict]:
        """Retrieve documents with optimized parameters"""
        cache_key = self.cache._generate_key("docs", query, intent_info.get('primary_intent', ''))
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        intent = intent_info.get('primary_intent', 'INFORMATION_EXTRACTION')
        config = self.retrieval_configs.get(intent, self.default_config)

        # Dynamic adjustment based on confidence
        confidence = intent_info.get('confidence', 0.5)
        top_k = max(8, min(25, int(config['base_k'] * (0.8 + confidence * 0.4))))
        rerank_k = config['rerank_k']

        docs = await self.document_service._fetch_and_rank(
            query=query,
            collection=collection,
            retrieval_top_k=top_k,
            rerank_top_k=rerank_k,
            partition_names=['document', 'QA']
        )

        await self.cache.set(cache_key, docs)
        return docs

    async def _assess_documents(self, query: str, documents: str, intent_info: Dict) -> Dict:
        """Assess document relevance và security với step-by-step analysis"""
        if not documents:
            return {
                'decision': 'REFUSE', 'score': 0.0, 'scope': 'IN_SCOPE',
                'info_type': 'NO_INFO', 'relevance': 'NO_MATCH',
                'reason': 'no_documents', 'assessment_steps': ''
            }

        cache_key = self.cache._generate_key("assess", query, documents[:500])
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        response = await self.llm_service.llm_task(
            inputs={
                "query": query,
                "documents": documents[:6000],
                "intent": intent_info.get('primary_intent', 'INFORMATION_EXTRACTION')
            },
            prompt_template=BALANCED_DOCUMENT_ASSESSMENT_PROMPT,
            timeout=15.0
        )

        result = self._parse_balanced_assessment(response)
        await self.cache.set(cache_key, result)
        return result

    def _parse_balanced_assessment(self, response: str) -> Dict:
        """Parse assessment response với step analysis"""
        patterns = {
            'decision': r'<decision>(ANSWER|REFUSE)</decision>',
            'score': r'<score>([\d.]+)</score>',
            'scope': r'<scope>(IN_SCOPE|OUT_OF_SCOPE)</scope>',
            'info_type': r'<info_type>(PUBLIC_INFO|CONFIDENTIAL_INFO|RESTRICTED_INFO|NO_INFO)</info_type>',
            'relevance': r'<relevance>(DIRECT_MATCH|PARTIAL_MATCH|TOPIC_MENTION|NO_MATCH)</relevance>',
            'reason': r'<reason>(.*?)</reason>'
        }

        result = {
            'decision': 'REFUSE', 'score': 0.0, 'scope': 'OUT_OF_SCOPE',
            'info_type': 'NO_INFO', 'relevance': 'NO_MATCH', 'reason': 'unknown'
        }

        # Parse assessment steps - MỚI
        steps_pattern = r'<assessment_steps>(.*?)</assessment_steps>'
        steps_match = re.search(steps_pattern, response, re.DOTALL)
        result['assessment_steps'] = steps_match.group(1) if steps_match else ""

        for key, pattern in patterns.items():
            match = re.search(pattern, response, re.DOTALL)
            if match:
                value = match.group(1).strip()
                if key == 'score':
                    try:
                        result[key] = max(0.0, min(1.0, float(value)))
                    except ValueError:
                        result[key] = 0.0
                else:
                    result[key] = value

        # MỚI: Adjust score dựa trên step analysis
        if result['assessment_steps']:
            steps_text = result['assessment_steps'].lower()

            # Boost score nếu có "trả lời trực tiếp"
            if 'trả lời trực tiếp: có' in steps_text:
                result['score'] = min(1.0, result['score'] + 0.2)

            # Reduce score nếu có "thiếu" hoặc "không"
            if any(word in steps_text for word in ['thiếu:', 'không khớp', 'một phần']):
                result['score'] = max(0.0, result['score'] - 0.1)

        return result

    def _format_documents(self, docs: List[Dict]) -> str:
        """Format documents with quality control"""
        if not docs:
            return ""

        formatted = []

        for idx, doc in enumerate(docs, 1):
            content = self._extract_content(doc)
            if content and len(content.strip()) > 30:
                # Truncate very long documents
                if len(content) > 1200:
                    content = content[:900] + "\n...[rút gọn]...\n" + content[-300:]

                formatted.append(f"--- TÀI LIỆU {idx} ---\n{content}")

                if len(formatted) >= 10:  # Limit total documents
                    break

        return "\n\n".join(formatted) if formatted else ""

    def _extract_content(self, doc) -> str:
        """Extract content from document safely"""
        if isinstance(doc, dict):
            return doc.get('content') or doc.get('chunk') or doc.get('text', '')
        elif isinstance(doc, str):
            return doc
        return ''

    def _create_result(self, status: str, docs: List[Dict], formatted: str, assessment: Dict) -> Dict:
        """Create standardized result structure"""
        return {
            'status': status,
            'documents': docs,
            'formatted': formatted,
            'assessment': assessment
        }


# =============================================================================
# 6. STREAMLINED RESPONSE GENERATOR
# =============================================================================
class StreamlinedResponseGenerator:
    """Streamlined response generator with security awareness"""

    def __init__(self, llm_service):
        self.llm_service = llm_service

    def generate_response(self, analysis_result: Dict, doc_result: Dict) -> AsyncGenerator:
        """Generate appropriate response based on analysis and documents"""

        decision = doc_result.get('assessment', {}).get('decision', 'REFUSE')
        intent = analysis_result.get('primary_intent', 'INFORMATION_EXTRACTION')
        info_type = doc_result.get('assessment', {}).get('info_type', 'PUBLIC_INFO')

        # Security check first
        if info_type in ['CONFIDENTIAL_INFO', 'RESTRICTED_INFO']:
            return self._generate_security_response(analysis_result, doc_result)

        # Decision-based routing
        if decision == 'ANSWER':
            return self._generate_answer(analysis_result, doc_result)
        elif analysis_result.get('needs_clarification', False):
            return self._generate_clarification(analysis_result)
        elif intent == 'CHIT_CHAT' or self._is_simple_chat(analysis_result['query']):
            return self._generate_chat(analysis_result)
        else:
            return self._generate_refusal(analysis_result, doc_result)

    def _generate_answer(self, analysis_result: Dict, doc_result: Dict):
        """Generate comprehensive answer với self-checking"""
        documents = doc_result.get('formatted', '')
        assessment = doc_result.get('assessment', {})

        if not documents or len(documents.strip()) < 50:
            return self._generate_refusal(analysis_result, doc_result)

        intent = analysis_result.get('primary_intent', 'INFORMATION_EXTRACTION')
        confidence = analysis_result.get('confidence', 0.5)

        # MỚI: Thêm step analysis vào context
        enriched_context = {
            'intent_analysis': analysis_result.get('step_analysis', ''),
            'doc_assessment': assessment.get('assessment_steps', ''),
            'confidence_level': 'high' if confidence > 0.7 else 'medium' if confidence > 0.4 else 'low'
        }

        return self.llm_service.llm_stream(
            prompt_template=BALANCED_AUDIT_RESPONSE_PROMPT,
            inputs={
                "query": analysis_result.get('query', ''),
                "documents": documents,
                "intent": intent,
                "relevance": assessment.get('relevance', 'NO_MATCH'),
                "confidence": confidence,
                "enriched_context": str(enriched_context),  # MỚI: Context bổ sung
                "date": datetime.now().strftime('%Y-%m-%d')
            },
            docs=self._prepare_doc_references(doc_result.get('documents', []))
        )

    def _generate_security_response(self, analysis_result: Dict, doc_result: Dict):
        """Generate security-aware response for sensitive information"""
        assessment = doc_result.get('assessment', {})

        return self.llm_service.llm_stream(
            prompt_template=ENHANCED_SECURITY_RESPONSE_PROMPT,
            inputs={
                "query": analysis_result.get('query', ''),
                "assessment": str(assessment),
                "info_type": assessment.get('info_type', 'CONFIDENTIAL_INFO'),
                "reason": assessment.get('reason', 'security_policy')
            }
        )

    def _generate_clarification(self, analysis_result: Dict):
        """Generate clarification request"""
        return self.llm_service.llm_stream(
            prompt_template=AUDIT_CLARIFICATION_PROMPT,
            inputs={
                "query": analysis_result.get('query', ''),
                "clarification_type": "ambiguous",
                "detected_entities": ', '.join(analysis_result.get('detected_entities', []))
            }
        )

    def _generate_chat(self, analysis_result: Dict):
        """Generate casual chat response"""
        return self.llm_service.llm_stream(
            prompt_template=AUDIT_CHIT_CHAT_PROMPT,
            inputs={
                "query": analysis_result['query'],
                "situation": "general_inquiry"
            }
        )

    def _generate_refusal(self, analysis_result: Dict, doc_result: Dict):
        """Generate contextual refusal"""
        refuse_reason = self._determine_refuse_reason(analysis_result, doc_result)
        scope = doc_result.get('assessment', {}).get('scope', 'UNKNOWN')

        return self.llm_service.llm_stream(
            prompt_template=AUDIT_REFUSE_PROMPT,
            inputs={
                "query": analysis_result.get('query', ''),
                "refuse_reason": refuse_reason,
                "scope": scope
            }
        )

    def _determine_refuse_reason(self, analysis_result: Dict, doc_result: Dict) -> str:
        """Determine specific refusal reason"""
        assessment = doc_result.get('assessment', {})

        if assessment.get('info_type') in ['CONFIDENTIAL_INFO', 'RESTRICTED_INFO']:
            return "CONFIDENTIAL_INFO"
        elif analysis_result.get('out_of_scope', False):
            return "OUT_OF_SCOPE"
        elif doc_result.get('status') == 'no_documents':
            return "NO_DOCUMENTS"
        elif assessment.get('score', 0) < 0.4:
            return "INSUFFICIENT_INFO"
        else:
            return "UNCLEAR_QUESTION"

    def _is_simple_chat(self, query: str) -> bool:
        """Check if query is simple chat"""
        chat_patterns = ['xin chào', 'hello', 'hi', 'chào', 'cảm ơn', 'thank', 'bạn là ai', 'bạn làm được gì']
        return any(pattern in query.lower() for pattern in chat_patterns)

    def _prepare_doc_references(self, docs: List[Dict]) -> List[Dict]:
        """Prepare document references for LLM"""
        if not docs:
            return []

        refs = []
        for doc in docs:
            if isinstance(doc, dict):
                ref = {"id": doc.get('id', str(uuid.uuid4()))}
                if 'source' in doc:
                    ref['source'] = doc['source']
                elif 'doc' in doc:
                    ref['source'] = doc['doc']
                refs.append(ref)
        return refs


# =============================================================================
# 7. MAIN OPTIMIZED BOT
# =============================================================================
class BeeKTNB:
    """
    Fully optimized BeeKTNB with:
    - Instruction tree integration
    - Parallel processing
    - Enhanced caching
    - Streamlined logic
    """

    def __init__(self, bot_id: str):
        self.bot_id = bot_id
        self.collection_master = f"bot_{bot_id.replace('-', '_')}"

        # Initialize services
        self.cache = UnifiedCache(max_size=400)
        self.llm_service = LLMService(bot_id)
        self.document_service = DocumentService(bot_id, self.llm_service)
        self.abbr_handler = AbbreviationHandler()

        # Initialize optimized components
        self.tree_processor = InstructionTreeProcessor(self.llm_service, self.cache)
        self.intent_classifier = StreamlinedIntentClassifier(self.llm_service, self.cache)
        self.doc_processor = EnhancedDocumentProcessor(self.document_service, self.llm_service, self.cache)
        self.response_generator = StreamlinedResponseGenerator(self.llm_service)
        self.quality_monitor = QualityMonitor()
        LOGGER.info(f"Optimized BeeKTNB v2 initialized: {bot_id}")

    async def _optimized_pipeline(self, state: Dict) -> AsyncGenerator:
        """Pipeline với analysis tracking cho quality monitoring"""
        query = state['query']
        start_time = time.time()

        LOGGER.info(f"=== BALANCED PIPELINE V3 START === Query: {query[:60]}...")

        # PHASE 1: Enhanced Parallel Analysis
        LOGGER.debug("Phase 1: Enhanced intent classification and tree extraction")

        intent_task = self.intent_classifier.classify_intent(query, [])
        tree_task = self.tree_processor.extract_relevant_headings(query)

        intent_result, tree_headings = await ParallelTaskOrchestrator.run_parallel_analysis(
            intent_task, tree_task, timeout=15.0
        )

        # MỚI: Lưu analysis để quality monitoring sử dụng
        self.current_analysis = intent_result

        phase1_time = time.time() - start_time
        LOGGER.info(f"Phase 1 completed in {phase1_time:.2f}s - Intent: {intent_result['primary_intent']}, "
                    f"Confidence: {intent_result['confidence']:.2f}, Tree headings: {len(tree_headings)}")

        # Early Exit Checks
        if self._should_early_exit(intent_result):
            return self._handle_early_exit(intent_result, state)

        # PHASE 3: Enhanced Document Processing
        LOGGER.debug("Phase 3: Enhanced document processing with step analysis")

        doc_result = await self.doc_processor.process_with_tree_enhancement(
            query, intent_result, tree_headings, self.collection_master
        )

        phase3_time = time.time() - start_time
        assessment = doc_result.get('assessment', {})
        LOGGER.info(f"Phase 3 completed in {phase3_time:.2f}s - Decision: {assessment.get('decision', 'N/A')}, "
                    f"Score: {assessment.get('score', 0):.2f}")

        # PHASE 4: Enhanced Response Generation
        LOGGER.debug("Phase 4: Enhanced response generation with quality checking")

        response_stream = self.response_generator.generate_response(intent_result, doc_result)

        total_time = time.time() - start_time
        LOGGER.info(f"=== PIPELINE V3 COMPLETE === Total time: {total_time:.2f}s")

        return response_stream

    def _should_early_exit(self, intent_result: Dict) -> bool:
        """Determine if we should exit early based on intent analysis"""
        return (
                (intent_result.get('out_of_scope', False) and intent_result.get('confidence', 0) > 0.75) or
                intent_result.get('primary_intent') == 'CHIT_CHAT' or
                intent_result.get('needs_clarification', False)
        )

    def _handle_early_exit(self, intent_result: Dict, state: Dict) -> AsyncGenerator:
        """Handle early exit scenarios"""
        intent = intent_result.get('primary_intent', 'UNKNOWN')

        LOGGER.info(f"Early exit: {intent}")

        if intent_result.get('needs_clarification', False):
            return self.response_generator._generate_clarification(intent_result)
        elif intent == 'CHIT_CHAT':
            return self.response_generator._generate_chat(intent_result)
        else:  # Out of scope
            return self.response_generator._generate_refusal(
                intent_result,
                {'status': 'out_of_scope', 'assessment': {'scope': 'OUT_OF_SCOPE'}}
            )

    async def run(
            self,
            messages: List[Dict],
            role: str = "L1",
            topic: str = "default",
            session_id: Optional[str] = None
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """
        Main entry point - Optimized with comprehensive error handling
        """
        start_time = time.time()
        session_id = session_id or str(uuid.uuid4())

        # Process input
        raw_query = messages[-1]['content'].strip()
        processed_query = self.abbr_handler.annotate_query(raw_query)

        state = {
            'query': processed_query,
            'original_query': raw_query,
            'session_id': session_id,
            'role': role,
            'topic': topic,
            'timestamp': start_time
        }

        LOGGER.info(f"=== BEEKTNB V2 START === Session: {session_id[:8]}...")

        try:
            # Execute optimized pipeline
            response_stream = await self._optimized_pipeline(state)

            # MỚI: Collect response for quality monitoring
            chunk_count = 0
            first_token_time = None
            full_response = ""
            start_time = time.time()

            async for chunk in response_stream:
                if chunk_count == 0 and chunk.choices and chunk.choices[0].delta.content:
                    first_token_time = time.time() - start_time

                chunk_count += 1

                # MỚI: Collect response content
                if chunk.choices and chunk.choices[0].delta.content:
                    full_response += chunk.choices[0].delta.content

                yield chunk

            # MỚI: Evaluate response quality after streaming
            if full_response and hasattr(self, 'current_analysis'):
                quality_result = self.quality_monitor.evaluate_response_quality(
                    state['query'],
                    full_response,
                    self.current_analysis
                )

                # Log quality metrics
                LOGGER.info(f"Response quality: {quality_result['overall_score']:.2f}, "
                            f"Session: {session_id[:8]}")

                processing_time = time.time() - start_time
                first_token_ms = (first_token_time * 1000) if first_token_time else 0

                LOGGER.info(f"=== BEEKTNB COMPLETE === Total: {processing_time:.2f}s, "
                            f"First token: {first_token_ms:.0f}ms, Chunks: {chunk_count}")

        except asyncio.TimeoutError:
            LOGGER.error("Pipeline timeout - generating fallback response")
            async for chunk in self._generate_timeout_response(state['query']):
                yield chunk

        except Exception as e:
            LOGGER.error(f"Pipeline error: {str(e)}", exc_info=True)
            async for chunk in self._generate_error_response(state['query'], str(e)):
                yield chunk

    async def _generate_timeout_response(self, query: str) -> AsyncGenerator:
        """Generate response when pipeline times out"""
        timeout_prompt = """
        Vai trò: Bee - trợ lý kiểm toán nội bộ

        Tình huống: Hệ thống đang xử lý chậm hơn bình thường

        Thông báo: "Xin lỗi, hệ thống đang xử lý nhiều yêu cầu nên phản hồi chậm hơn dự kiến. Bạn có thể thử lại câu hỏi hoặc diễn đạt ngắn gọn hơn để Bee hỗ trợ nhanh hơn không? 🔄"

        Câu hỏi: {query}
               """

        return self.llm_service.llm_stream(
            prompt_template=timeout_prompt,
            inputs={"query": query}
        )

    async def _generate_error_response(self, query: str, error: str) -> AsyncGenerator:
        """Generate response when pipeline encounters error"""
        error_prompt = """
        Vai trò: Bee - trợ lý kiểm toán nội bộ

        Tình huống: Gặp sự cố kỹ thuật

        Thông báo: "Xin lỗi, Bee gặp sự cố kỹ thuật khi xử lý câu hỏi của bạn. Vui lòng thử lại sau ít phút hoặc liên hệ bộ phận kỹ thuật nếu vấn đề tiếp tục xảy ra. 🔧"

        Câu hỏi: {query}
               """

        return self.llm_service.llm_stream(
            prompt_template=error_prompt,
            inputs={"query": query}
        )

    async def get_cache_stats(self) -> Dict:
        """Get cache statistics for monitoring"""
        return {
            "cache_size": len(self.cache.cache),
            "max_size": self.cache.max_size,
            "utilization": len(self.cache.cache) / self.cache.max_size,
            "components": {
                "tree_processor": "InstructionTreeProcessor",
                "intent_classifier": "StreamlinedIntentClassifier",
                "doc_processor": "EnhancedDocumentProcessor",
                "response_generator": "StreamlinedResponseGenerator"
            }
        }

    async def clear_cache(self):
        """Clear all caches for maintenance"""
        self.cache.cache.clear()
        self.cache.access_time.clear()
        LOGGER.info("All caches cleared")

    # =============================================================================
    # 8. MAIN FUNCTION FOR TESTING
    # =============================================================================


async def main():
    """Test function for the optimized BeeKTNB"""
    bot_id = "f359b089-6b2d-4c0a-8dfe-e85eca992a61"
    bot = BeeKTNB(bot_id)

    print("\n========= BeeKTNB Optimized V2 =========\n")

    messages = []

    # Display sample test queries
    sample_queries = [
        "Tôi cần kiểm toán hoạt động tín dụng KHCN, có những thủ tục nào?",
        "Trong kiểm toán mô hình, các bước kiểm định cần thực hiện là gì?",
        "Quy trình kiểm toán ICAAP bao gồm những gì?",
        "Kiểm toán phòng chống rửa tiền cần thu thập tài liệu gì?",
        "Các rủi ro trong quá trình lập kế hoạch mua sắm?"
    ]

    print("Câu hỏi mẫu để test:")
    for i, query in enumerate(sample_queries, 1):
        print(f"{i}. {query}")
    print("\nBạn có thể test với các câu hỏi trên hoặc câu hỏi tự do...\n")

    while True:
        user_input = input("You: ")
        if user_input.lower() in ["exit", "quit", "thoát"]:
            # Show cache stats before exit
            stats = await bot.get_cache_stats()
            print(f"\nCache stats: {stats['cache_size']}/{stats['max_size']} "
                  f"({stats['utilization']:.1%} utilized)")
            break

        messages.append({"role": "user", "content": user_input})
        print("\nBot: ", end="", flush=True)

        full_response = ""
        chunk_count = 0
        first_token_time = None
        start_time = time.time()

        try:
            async for chunk in bot.run(messages):
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    print(content, end="", flush=True)
                    full_response += content

                    # Capture first token time from chunk metadata hoặc tính toán local
                    if chunk_count == 0:  # First content chunk
                        first_token_time = time.time() - start_time

                    chunk_count += 1

            response_time = time.time() - start_time
            first_token_ms = (first_token_time * 1000) if first_token_time else 0

            # In thông tin với first token time
            print(f"\n[Total: {response_time:.2f}s, First token: {first_token_ms:.0f}ms, Chunks: {chunk_count}]")

        except Exception as e:
            print(f"\nError during response generation: {e}")
            full_response = "Xin lỗi, có lỗi xảy ra trong quá trình xử lý."

        messages.append({"role": "assistant", "content": full_response})
        print()

if __name__ == "__main__":
    asyncio.run(main())
