"""
Simplified Unified Intent Analysis Service
Đơn giản hóa logic analyzer, loại bỏ redundancy
"""

from typing import Dict, Optional, List, Union, Tuple
from datetime import datetime, date

from beechat_khcn.models.conversation_model import DepositIntent
from beechat_khcn.models.deposit_model import DepositAttributes, DepositProductType
from beechat_khcn.models.balance_retrieve_model import BalanceIntent, BalanceAttributes
from beechat_khcn.models.loan_management_model import LoanManagementIntent
from beechat_khcn.models.topic_model import TopicCategory
from beechat_khcn.models.total_revenue_model import TotalRevenueIntent

from beegen_v1.parser.implementations.xml import XMLOutputParser
from beegenerate.loggings import LOGGER
from beegenerate.loggings.loggers import lf


class ContinuationAnalysisResult:
    """Simplified continuation analysis result"""

    def __init__(self):
        self.is_continuation: bool = False
        self.is_switching: bool = False
        self.is_clarification: bool = False
        self.confidence: float = 0.0

        # Chỉ set khi switching
        self.new_topic: Optional[TopicCategory] = None
        self.new_intent: Optional[Union[DepositIntent, BalanceIntent, str]] = None

    def get_classification(self) -> str:
        """Get primary classification"""
        if self.is_continuation:
            return "continuation"
        elif self.is_switching:
            return "switching"
        elif self.is_clarification:
            return "clarification"
        else:
            return "unknown"


class UnifiedAnalysisResult:
    """Simplified unified result với continuation info"""

    def __init__(self):
        self.topic: TopicCategory = TopicCategory.CHITCHAT
        self.intent: Union[DepositIntent, BalanceIntent, TotalRevenueIntent, str] = "chitchat"
        self.enhanced_query: str = ""
        self.continuation_analysis: Optional[ContinuationAnalysisResult] = None

    def __repr__(self):
        return f"UnifiedAnalysisResult(topic={self.topic}, intent={self.intent})"


class UnifiedIntentAnalyzer:
    """
    Simplified unified analyzer - chỉ classify topic và intent
    """

    def __init__(self, llm_service):
        self.llm_service = llm_service
        self.xml_parser = XMLOutputParser()

    async def analyze_unified(self, enhanced_query: str, conversation_context: Dict) -> UnifiedAnalysisResult:
        """Main method with proper exception handling"""
        result = UnifiedAnalysisResult()
        result.enhanced_query = enhanced_query

        try:
            await self._analyze_topic_and_intent(enhanced_query, conversation_context, result)
            LOGGER.info(f"Analysis result - Topic: {result.topic.value}, Intent: {result.intent}")
        except Exception as e:
            LOGGER.error(f"Analysis failed: {e}, falling back to default values")

        return result

    async def analyze_with_continuation_detection(self,
                                                  enhanced_query: str,
                                                  conversation_context: Dict,
                                                  collection_state: Dict = None) -> UnifiedAnalysisResult:
        """Main method: Analysis with continuation detection"""
        result = UnifiedAnalysisResult()
        result.enhanced_query = enhanced_query

        if collection_state:
            continuation_result = await self._analyze_continuation_or_switching(
                enhanced_query, conversation_context, collection_state
            )
            result.continuation_analysis = continuation_result

            if continuation_result.is_continuation:
                result.topic = TopicCategory(collection_state.get('topic'))
                result.intent = self._reconstruct_intent_from_state(collection_state)
                return result
            elif continuation_result.is_switching:
                LOGGER.info("🔄 Intent switching detected")

        await self._analyze_topic_and_intent(enhanced_query, conversation_context, result)
        return result

    async def _analyze_topic_and_intent(self, enhanced_query: str, conversation_context: Dict,
                                        result: UnifiedAnalysisResult):
        """Common topic and intent analysis logic"""
        try:
            result.topic = await self._classify_topic(enhanced_query, conversation_context)
        except Exception as e:
            LOGGER.error(f"Topic classification failed: {e}, defaulting to CHITCHAT")
            result.topic = TopicCategory.CHITCHAT

        try:
            intent_methods = {
                TopicCategory.DEPOSIT: self._analyze_deposit_intent,
                TopicCategory.CARD: self._analyze_card_intent,
                TopicCategory.BALANCE_RETRIEVE: self._analyze_balance_intent,
                TopicCategory.TOTAL_REVENUE: self._analyze_total_revenue_intent,
                TopicCategory.LOAN_MANAGEMENT: self._analyze_loan_management_intent
            }

            method = intent_methods.get(result.topic)
            if method:
                result.intent = await method(enhanced_query, conversation_context)
            else:
                result.intent = "chitchat"
        except Exception as e:
            LOGGER.error(f"Intent analysis failed: {e}, defaulting to chitchat")
            result.intent = "chitchat"

    async def _analyze_continuation_or_switching(
            self,
            enhanced_query: str,
            conversation_context: Dict,
            collection_state: Dict
    ) -> ContinuationAnalysisResult:
        """Simplified LLM-based continuation analysis"""

        current_intent = collection_state.get('active_intent', '')
        current_topic = collection_state.get('topic', '')
        missing_attrs = collection_state.get('missing_attributes', [])
        completion_status = "in_progress" if missing_attrs else "just_completed"

        context = {
            'current_intent': current_intent,
            'current_topic': current_topic,
            'missing_attributes': ', '.join(missing_attrs) if missing_attrs else 'Không có',
            'completion_status': completion_status,
            'conversation_summary': conversation_context,
            'enhanced_query': enhanced_query
        }

        try:
            response = await self.llm_service.llm_task(
                inputs=context,
                prompt_template=lf.get_prompt("BEECHAT_KHCN_CONTINUATION_ANALYSIS_PROMPT"),
                use_primary=False,
                tempature=0
            )

            # Parse XML đơn giản hơn
            parsed = await self.xml_parser.parse(text=response)
            analysis_type = parsed.get('analysis_type', 'continuation')

            result = ContinuationAnalysisResult()
            result.confidence = 0.8  # Fixed confidence thay vì dynamic

            # Simplified classification logic
            if analysis_type == 'continuation':
                result.is_continuation = True
            elif analysis_type == 'switching':
                result.is_switching = True
            elif analysis_type == 'clarification':
                result.is_clarification = True

            LOGGER.info(f"Simplified Analysis: {analysis_type}")
            return result

        except Exception as e:
            LOGGER.error(f"Continuation analysis failed: {e}, defaulting to continuation")
            result = ContinuationAnalysisResult()
            result.is_continuation = True
            result.confidence = 0.8
            return result

    async def _classify_topic(self, enhanced_query: str, conversation_context: Dict) -> TopicCategory:
        """Phase 1: Classify topic only"""
        conversation_text = self._format_recent_messages(conversation_context.get('messages', []))
        response = await self.llm_service.llm_task(
            inputs={
                "query": enhanced_query,
                "conversation_context": conversation_text
            },
            prompt_template=lf.get_prompt("BEECHAT_KHCN_TOPIC_CLASSIFICATION_PROMPT"),
            use_primary=True,
            tempature=0
        )

        try:
            parsed = await self.xml_parser.parse(text=response)
            topic_str = parsed.get('topic', 'chitchat')
            return TopicCategory(topic_str.lower())
        except Exception as e:
            LOGGER.warning(f"Topic classification failed: {e}, defaulting to chitchat")
            return TopicCategory.CHITCHAT

    async def _analyze_deposit_intent(self, enhanced_query: str, conversation_context: Dict) -> DepositIntent:
        """Simplified deposit intent analysis - chỉ intent, không attributes"""

        recent_messages = self._format_recent_messages(conversation_context.get('messages', []))

        try:
            response = await self.llm_service.llm_task(
                inputs={
                    "conversation_summary": conversation_context.get('summary', 'Enhanced query ready'),
                    "recent_messages": recent_messages,
                    "query": enhanced_query,
                    "current_collection_context": "Không có context thu thập thuộc tính hiện tại"
                },
                prompt_template=lf.get_prompt("BEECHAT_KHCN_ANALIZE_DEPOSIT_TOPIC_PROMPT"),
                use_primary=True,
                tempature=0
            )

            if not response or not response.strip():
                LOGGER.error(
                    f"LLM returned empty response for deposit intent analysis - Query: {enhanced_query[:50]}")
                return DepositIntent.CHITCHAT

            parsed = await self.xml_parser.parse(text=response)
            intent_str = parsed.get('intent', 'chitchat')

            if not intent_str or intent_str == 'null':
                LOGGER.warning(f"⚠️ LLM returned null/empty intent for deposit analysis - Query: {enhanced_query[:50]}")
                return DepositIntent.CHITCHAT

            return self._convert_to_deposit_intent(intent_str)

        except ConnectionError as e:
            LOGGER.error(f"LLM connection error in deposit intent analysis: {str(e)}")
            return DepositIntent.CHITCHAT
        except TimeoutError as e:
            LOGGER.error(f"LLM timeout error in deposit intent analysis: {str(e)}")
            return DepositIntent.CHITCHAT
        except Exception as e:
            LOGGER.error(
                f"Unexpected error in deposit intent analysis - Query: {enhanced_query[:50]}, Error: {str(e)}")
            return DepositIntent.CHITCHAT

    async def _analyze_card_intent(self, enhanced_query: str, conversation_context: Dict) -> DepositIntent:
        """Simplified card intent analysis"""

        recent_messages = self._format_recent_messages(conversation_context.get('messages', []))

        response = await self.llm_service.llm_task(
            inputs={
                "conversation_summary": conversation_context.get('summary', 'Enhanced query ready'),
                "recent_messages": recent_messages,
                "query": enhanced_query,
                "current_collection_context": "Không có context thu thập thuộc tính hiện tại"
            },
            prompt_template=lf.get_prompt("BEECHAT_KHCN_ANALIZE_CARD_TOPIC_PROMPT"),
            use_primary=True,
            tempature=0
        )

        try:
            parsed = await self.xml_parser.parse(text=response)
            intent_str = parsed.get('intent', 'generic_card')

            # Map card intents to DepositIntent enum (for compatibility)
            if intent_str == 'specific_card':
                return DepositIntent.SPECIFIC_CARD
            elif intent_str == 'generic_card':
                return DepositIntent.GENERIC_CARD
            else:
                return DepositIntent.CHITCHAT

        except Exception as e:
            LOGGER.error(f"Card intent analysis failed: {e}")
            return DepositIntent.GENERIC_CARD

    async def _analyze_balance_intent(self, enhanced_query: str, conversation_context: Dict) -> BalanceIntent:
        """Simplified balance intent analysis"""

        recent_messages = self._format_recent_messages(conversation_context.get('messages', []))

        response = await self.llm_service.llm_task(
            inputs={
                "recent_messages": recent_messages,
                "query": enhanced_query,
            },
            prompt_template=lf.get_prompt("BEECHAT_KHCN_ANALIZE_BALANCE_TOPIC_PROMPT"),
            use_primary=True,
            tempature=0
        )

        try:
            parsed = await self.xml_parser.parse(text=response)
            intent_str = parsed.get('intent', 'query_transaction_normal')
            return self._convert_to_balance_intent(intent_str)
        except Exception as e:
            LOGGER.error(f"Balance intent analysis failed: {e}")
            return BalanceIntent.QUERY_TRANSACTION_NORMAL

    async def _analyze_total_revenue_intent(self, enhanced_query: str,
                                            conversation_context: Dict) -> TotalRevenueIntent:
        """Analyze total revenue intent from query using LLM"""

        current_collection_context = conversation_context.get('current_collection_context', '')
        conversation_summary = conversation_context.get('conversation_summary', '')
        recent_messages = self._format_recent_messages(conversation_context.get('messages', []))

        try:
            response = await self.llm_service.llm_task(
                inputs={
                    'current_collection_context': current_collection_context,
                    'conversation_summary': conversation_summary,
                    'recent_messages': recent_messages,
                    'query': enhanced_query,
                },
                prompt_template=lf.get_prompt("BEECHAT_KHCN_ANALYZE_TOTAL_REVENUE_TOPIC_PROMPT"),
                use_primary=True,
                tempature=0
            )

            parsed = await self.xml_parser.parse(text=response)
            intent_str = parsed.get('intent', 'get_total_assets')
            return self._convert_to_total_revenue_intent(intent_str)

        except Exception as e:
            LOGGER.error(f"Total revenue intent analysis failed: {e}")
            return TotalRevenueIntent.GET_TOTAL_ASSETS

    async def _analyze_loan_management_intent(self, enhanced_query: str,
                                              conversation_context: Dict) -> LoanManagementIntent:
        """Analyze loan management intent from query using LLM"""

        current_collection_context = conversation_context.get('current_collection_context', '')
        conversation_summary = conversation_context.get('conversation_summary', '')
        recent_messages = self._format_recent_messages(conversation_context.get('messages', []))

        try:
            response = await self.llm_service.llm_task(
                inputs={
                    'current_collection_context': current_collection_context,
                    'conversation_summary': conversation_summary,
                    'recent_messages': recent_messages,
                    'query': enhanced_query,
                },
                prompt_template=lf.get_prompt("BEECHAT_KHCN_ANALYZE_LOAN_MANAGEMENT_TOPIC_PROMPT"),
                use_primary=True,
                tempature=0
            )

            parsed = await self.xml_parser.parse(text=response)
            intent_str = parsed.get('intent', 'get_all_ld')
            return self._convert_to_loan_management_intent(intent_str)

        except Exception as e:
            LOGGER.error(f"Loan management intent analysis failed: {e}")
            return LoanManagementIntent.GET_ALL_LD

    def _format_recent_messages(self, messages: List[Dict]) -> str:
        """Unified message formatting logic"""
        if not messages:
            return "Không có tin nhắn gần đây"

        recent = messages[-10:] if len(messages) > 10 else messages
        formatted = []

        for msg in recent:
            role = "👤 User" if msg.get("role") == "user" else "🤖 Bee"
            content = msg.get("content", "").strip()

            if content:
                # Consistent length limit
                content = content[:250] + "..." if len(content) > 250 else content
                formatted.append(f"{role}: {content}")

        return "\n".join(formatted) if formatted else "Không có tin nhắn hợp lệ"

    def _reconstruct_intent_from_state(self, collection_state: Dict) -> Union[
        DepositIntent, BalanceIntent, TotalRevenueIntent, str]:
        intent_str = collection_state.get('active_intent', '')
        topic = collection_state.get('topic', '')

        try:
            if topic == 'deposit':
                return DepositIntent(intent_str)
            elif topic == 'balance_retrieve':
                return BalanceIntent(intent_str)
            elif topic == 'total_revenue':
                return TotalRevenueIntent(intent_str)
            elif topic == 'loan_management':
                return LoanManagementIntent(intent_str)
            else:
                return intent_str
        except ValueError:
            LOGGER.warning(f"Failed to reconstruct intent: {intent_str}")
            return "chitchat"

    def _convert_to_total_revenue_intent(self, intent_str: str) -> TotalRevenueIntent:
        """Convert intent string to TotalRevenueIntent enum"""
        intent_mapping = {
            'get_total_assets': TotalRevenueIntent.GET_TOTAL_ASSETS,
            'get_net_worth': TotalRevenueIntent.GET_NET_WORTH,
            'get_income_projection': TotalRevenueIntent.GET_INCOME_PROJECTION,
            'get_total_debt': TotalRevenueIntent.GET_TOTAL_DEBT,
            'trigger_asset_summary_notification': TotalRevenueIntent.TRIGGER_ASSET_SUMMARY_NOTIFICATION,
            'asset_health_check': TotalRevenueIntent.ASSET_HEALTH_CHECK,
            'out_of_scope': TotalRevenueIntent.OUT_OF_SCOPE,
            'chitchat': TotalRevenueIntent.GET_TOTAL_ASSETS  # Fallback
        }
        return intent_mapping.get(intent_str.lower(), TotalRevenueIntent.GET_TOTAL_ASSETS)

    def _convert_to_deposit_intent(self, intent_str: str) -> DepositIntent:
        """Convert string to DepositIntent enum"""
        try:
            return DepositIntent(intent_str.lower())
        except ValueError:
            LOGGER.warning(f"Unknown deposit intent: '{intent_str}', defaulting to CHITCHAT")
            return DepositIntent.CHITCHAT

    def _convert_to_balance_intent(self, intent_str: str) -> BalanceIntent:
        """Convert intent string to BalanceIntent enum"""
        intent_mapping = {
            'query_transaction_normal': BalanceIntent.QUERY_TRANSACTION_NORMAL,
            'query_transaction_descriptive': BalanceIntent.QUERY_TRANSACTION_DESCRIPTIVE,
            'query_transaction_by_type': BalanceIntent.QUERY_TRANSACTION_BY_TYPE,
            'query_transaction_by_amount': BalanceIntent.QUERY_TRANSACTION_BY_AMOUNT,
            'query_transaction_by_beneficiary': BalanceIntent.QUERY_TRANSACTION_BY_BENEFICIARY,
            'query_transaction_by_channel': BalanceIntent.QUERY_TRANSACTION_BY_CHANNEL,
            'balance_retrieve_menu': BalanceIntent.BALANCE_RETRIEVE_MENU,
            'query_transaction_export': BalanceIntent.QUERY_TRANSACTION_EXPORT,
            'initiate_transaction_dispute': BalanceIntent.INITIATE_TRANSACTION_DISPUTE,
            'unrecognized_transaction_query': BalanceIntent.UNRECOGNIZED_TRANSACTION_QUERY,
            'query_transaction_multi_conditions': BalanceIntent.QUERY_TRANSACTION_MULTI_CONDITIONS,
            'chitchat': BalanceIntent.UNRECOGNIZED_TRANSACTION_QUERY
        }
        return intent_mapping.get(intent_str.lower(), BalanceIntent.UNRECOGNIZED_TRANSACTION_QUERY)

    def _convert_to_loan_management_intent(self, intent_str: str) -> LoanManagementIntent:
        """Convert intent string to LoanManagementIntent enum"""
        intent_mapping = {
            'get_all_ld': LoanManagementIntent.GET_ALL_LD,
            'get_ld_info': LoanManagementIntent.GET_LD_INFO,
            'get_ld_payment_schedule': LoanManagementIntent.GET_LD_PAYMENT_SCHEDULE,
            'get_ld_payment_history': LoanManagementIntent.GET_LD_PAYMENT_HISTORY,
            'get_ld_additional_loan_amount': LoanManagementIntent.GET_LD_ADDITIONAL_LOAN_AMOUNT,
            'get_ac_overdraft_list': LoanManagementIntent.GET_AC_OVERDRAFT_LIST,
            'get_ac_limit_increase': LoanManagementIntent.GET_AC_LIMIT_INCREASE,
            'get_total_overdue_debt': LoanManagementIntent.GET_TOTAL_OVERDUE_DEBT,
            'get_total_additional_loan_capacity': LoanManagementIntent.GET_TOTAL_ADDITIONAL_LOAN_CAPACITY,
            'get_combined_payment_schedule': LoanManagementIntent.GET_COMBINED_PAYMENT_SCHEDULE,
            'get_combined_loan_list': LoanManagementIntent.GET_COMBINED_LOAN_LIST,
            'chitchat': LoanManagementIntent.GET_ALL_LD  # Fallback
        }
        return intent_mapping.get(intent_str.lower(), LoanManagementIntent.GET_ALL_LD)
