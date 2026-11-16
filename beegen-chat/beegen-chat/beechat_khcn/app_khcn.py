"""
Enhanced Banking Application - Optimized Version
Main orchestrator for unified banking services including deposits, cards, and balance retrieval.
"""
import asyncio
import json
import time
from typing import List, Dict, Optional, AsyncGenerator, Union, Tuple

# Core service imports
from beechat.services.card_service_v2 import CardService
from beechat.services.llm_service import LLMService
from beechat_khcn.models.loan_management_model import LoanManagementIntent
from beechat_khcn.models.total_revenue_model import TotalRevenueIntent
from beechat_khcn.services.bank_statement_service import BalanceApiService
from beechat_khcn.services.cache_service import CacheService
from beechat_khcn.services.content_filter_service import ContentFilterService
from beechat_khcn.services.document_service import DocumentService
from beechat_khcn.services.conversation_processor import ConversationProcessor

# Unified services
from beechat_khcn.services.loan_management_api import LoanManagementApiService
from beechat_khcn.services.total_revenue_api import TotalRevenueApiService
from beechat_khcn.services.unified_attribute_coordinator import UnifiedAttributeCoordinator
from beechat_khcn.services.unified_session_manager import UnifiedSessionManager
from beechat_khcn.services.unified_information_collector import UnifiedInformationCollector
from beechat_khcn.services.unified_response_generator import UnifiedResponseGenerator
from beechat_khcn.services.unified_analyzer import UnifiedIntentAnalyzer

# Model imports
from beechat_khcn.models.conversation_model import DepositIntent
from beechat_khcn.models.balance_retrieve_model import BalanceIntent
from beechat_khcn.models.topic_model import TopicCategory

# Utility imports
from beechat.utils.abbreviation import AbbreviationHandler
from beechat_khcn.services.user_profile_service import UserProfileService

from beegenerate.loggings import LOGGER
from beegenerate.loggings.loggers import lf
from langfuse.decorators import observe, langfuse_context

import sys

sys.stdout.reconfigure(encoding='utf-8')

import uuid

langfuse_app_name = "BeeBankingApp"
langfuse_session_id = langfuse_app_name + "_" + str(uuid.uuid4())


class BeeBankingApp:
    """
    Main orchestrator for unified banking services.

    Handles all banking operations including:
    - Deposit services (savings accounts, interest calculations)
    - Card services (credit, debit, and other card products)
    - Balance retrieval (transaction history, account inquiries)
    - General chat interactions

    Architecture uses unified services pattern to eliminate code duplication
    and provide consistent experience across all banking domains.
    """

    def __init__(self, bot_id: str) -> None:
        """
        Initialize banking application with all required services.

        Args:
            bot_id: Unique identifier for the bot instance
        """
        self.bot_id = bot_id

        self._initialize_core_services()
        self._initialize_utilities()
        self._initialize_unified_services()
        self._initialize_domain_services()
        self._initialize_balance_coordinator()

        LOGGER.info(f"BeeBankingApp initialized with bot_id: {bot_id}")

    def _initialize_core_services(self) -> None:
        """Initialize core infrastructure services."""
        self.llm_service = LLMService(self.bot_id)
        self.content_filter = ContentFilterService(self.llm_service)
        self.document_service = DocumentService(self.bot_id, self.llm_service)
        self.cache_service = CacheService(self.bot_id, self.llm_service, self.document_service)
        self.conversation_processor = ConversationProcessor(self.llm_service)

    def _initialize_utilities(self) -> None:
        """Initialize utility services."""
        self.abbr_handler = AbbreviationHandler()
        self.user_profile_service = UserProfileService()

    def _initialize_unified_services(self) -> None:
        """Initialize unified services for cross-domain operations."""
        self.session_manager = UnifiedSessionManager()
        self.information_collector = UnifiedInformationCollector(
            self.llm_service,
            self.session_manager
        )
        self.response_generator = UnifiedResponseGenerator(
            self.llm_service,
            self.document_service
        )
        self.response_generator.user_profile_service = None
        self.unified_analyzer = UnifiedIntentAnalyzer(self.llm_service)

    def _initialize_domain_services(self) -> None:
        """Initialize domain-specific services with enhanced capabilities."""
        self.card_service = CardService(self.bot_id, self.llm_service)

        self.balance_api = BalanceApiService(
            llm_service=self.llm_service,
            user_profile_service=self.user_profile_service
        )

        self.total_revenue_api = TotalRevenueApiService(
            llm_service=self.llm_service
        )
        self.loan_management_api = LoanManagementApiService(
            llm_service=self.llm_service
        )

    def _initialize_balance_coordinator(self) -> None:
        """
        Initialize unified coordinator and inject into dependent services.
        Enhanced version with unified architecture.
        """
        self.unified_coordinator = UnifiedAttributeCoordinator(
            user_profile_service=self.user_profile_service,
            llm_service=self.llm_service
        )

        self.balance_coordinator = self.unified_coordinator.get_balance_coordinator_interface()
        self.total_revenue_coordinator = self.unified_coordinator.get_total_revenue_coordinator_interface()
        self.loan_management_coordinator = self.unified_coordinator.get_loan_management_coordinator_interface()
        self.conversation_processor.set_balance_coordinator(self.balance_coordinator)
        self.conversation_processor.set_user_profile_service(self.user_profile_service)

        if hasattr(self, 'balance_api'):
            self.balance_api.balance_coordinator = self.balance_coordinator

        if hasattr(self, 'information_collector'):
            self.information_collector.set_balance_coordinator(self.balance_coordinator)
            self.information_collector.set_user_profile_service(self.user_profile_service)
            self.information_collector.set_total_revenue_coordinator(self.total_revenue_coordinator)
            self.information_collector.set_loan_management_coordinator(self.loan_management_coordinator)

        self.response_generator.user_profile_service = self.user_profile_service
        self.response_generator.total_revenue_coordinator = self.total_revenue_coordinator
        self.response_generator.loan_management_coordinator = self.loan_management_coordinator

    # -----------------------
    # MAIN EXECUTION METHODS
    # -----------------------
    @observe(name=langfuse_app_name)
    async def run(
            self,
            messages: List[Dict],
            role_ids=None,
            topic: str = "default",
            session_id: Optional[str] = None,
            response_status: Dict = None,
            **kwargs
    ) -> AsyncGenerator:
        if role_ids is None:
            role_ids = []
        langfuse_context.update_current_trace(name=langfuse_app_name, session_id=langfuse_session_id)
        """Main entry point for processing banking requests."""
        start_time = time.time()

        if not session_id:
            session_id = f"session_{int(time.time())}"

        LOGGER.info(f"Processing message - session: {session_id}, role: {role_ids}")

        current_user_message = ""
        if messages and len(messages) > 0:
            last_message = messages[-1]
            if last_message.get("role") == "user":
                current_user_message = last_message.get("content", "")
                LOGGER.info(f"USER MESSAGE: {current_user_message}")

        preprocessing_tasks = [
            self._process_user_profile(topic, session_id),
            self._preload_session_context(session_id)
        ]

        preprocessing_results = await asyncio.gather(*preprocessing_tasks, return_exceptions=True)
        user_name = preprocessing_results[0] if isinstance(preprocessing_results[0], str) else "bạn"

        enhanced_query, flow_decision = await self._process_conversation_context(
            messages, session_id, user_name
        )
        final_response = ""

        filter_result = {'filter_needed': 'no'}
        cache_check = {'check': False}

        if current_user_message:
            combined_input = f"RAW: {current_user_message} | ENHANCED: {enhanced_query}"

            try:
                filter_result, cache_check = await asyncio.gather(
                    self.content_filter.check_content(combined_input),
                    self.cache_service.check_cached_qa({'query': enhanced_query}),
                    return_exceptions=False
                )
            except Exception as e:
                LOGGER.warning(f"Validation error: {e}")

            if filter_result.get('filter_needed') == "yes":
                LOGGER.warning(f"Content filtered: {filter_result.get('filter_type', 'unknown')}")
                async for chunk in self._handle_filtered_content(current_user_message):
                    final_response += str(chunk.choices[0].delta.content)
                    yield chunk
                LOGGER.info(f"⏱️ Total processing time: {time.time() - start_time:.2f}s")
                langfuse_context.update_current_trace(output=final_response, session_id=langfuse_session_id)

                return
            else:
                LOGGER.info("Content passed filter")

        # Handle account change request
        if flow_decision == "new_flow" and any(pattern in enhanced_query.lower()
                                               for pattern in
                                               ["đổi tài khoản", "tài khoản khác", "chọn tài khoản khác", "đổi tk"]):
            LOGGER.info("Account change request detected - showing fresh account selection")

            if not session_id or not self.user_profile_service:
                async for chunk in self.response_generator.generate_chitchat_response("Lỗi hệ thống, vui lòng thử lại"):
                    final_response += str(chunk.choices[0].delta.content)
                    yield chunk

                langfuse_context.update_current_trace(output=final_response, session_id=langfuse_session_id)

                return

            LOGGER.info("DIRECT CALL -> _generate_account_selection_only")
            async for chunk in self.response_generator._generate_account_selection_response(
                    user_name=user_name,
                    session_id=session_id,
            ):
                final_response += str(chunk.choices[0].delta.content)
                yield chunk

            LOGGER.info(f"⏱️ Total processing time: {time.time() - start_time:.2f}s")
            langfuse_context.update_current_trace(output=final_response, session_id=langfuse_session_id)

            LOGGER.info(f"Total processing time: {time.time() - start_time:.2f}s")

        # QA cache check
        if cache_check.get('check', False) and cache_check.get('confidence', 0) > 0.6:
            async for chunk in self._handle_cached_response(enhanced_query, user_name):
                final_response += str(chunk.choices[0].delta.content)
                yield chunk
            langfuse_context.update_current_trace(output=final_response, session_id=langfuse_session_id)

        # Flow control and continuation handling
        collection_state = self.session_manager.get_collection_state(session_id)
        should_terminate_flow = await self._evaluate_flow_termination(
            collection_state, enhanced_query, flow_decision, session_id
        )

        if collection_state and not should_terminate_flow:
            async for chunk in self._handle_continuation_flow(
                    enhanced_query, session_id, user_name, messages
            ):
                final_response += str(chunk.choices[0].delta.content)
                yield chunk
            langfuse_context.update_current_trace(output=final_response, session_id=langfuse_session_id)

            return

        # Fresh analysis for new requests
        async for chunk in self._handle_fresh_analysis(
                enhanced_query, session_id, user_name, messages
        ):
            final_response += str(chunk.choices[0].delta.content)
            yield chunk

        LOGGER.info(f"⏱️ Total processing time: {time.time() - start_time:.2f}s")
        langfuse_context.update_current_trace(output=final_response, session_id=langfuse_session_id)

    @observe()
    async def _process_user_profile(self, topic: str, session_id: str) -> str:
        """
        Process user profile from topic JSON and extract user name.

        Args:
            topic: JSON string containing user profile
            session_id: Session identifier

        Returns:
            User name from profile or fallback "bạn"
        """
        if not topic or topic == "default":
            return "bạn"

        profile = self.user_profile_service.parse_topic_json(topic)
        if profile:
            self.user_profile_service.store_profile(session_id, profile)
            return profile.get_display_name() or "bạn"
        return "bạn"

    @observe()
    async def _process_conversation_context(
            self,
            messages: List[Dict],
            session_id: str,
            user_name: Optional[str]
    ) -> Tuple[str, str]:
        """
        Process conversation context with enhanced account context injection.

        Args:
            messages: Conversation messages
            session_id: Session identifier
            user_name: User's name

        Returns:
            Tuple of enhanced query and flow decision
        """
        self.conversation_processor.set_user_profile_service(self.user_profile_service)

        return await self.conversation_processor.process_messages(
            messages=messages,
            session_id=session_id,
            session_manager=self.session_manager,
            user_profile_service=self.user_profile_service
        )

    @observe()
    async def _handle_filtered_content(self, enhanced_query: str) -> AsyncGenerator:
        """
        Handle filtered content by generating appropriate refusal response.

        Args:
            enhanced_query: Original query that was filtered

        Yields:
            Refusal response chunks
        """
        filter_result = await self.content_filter.check_content(enhanced_query)
        final_response = ""
        async for chunk in self.content_filter.create_refusal_response(
                filter_result['filter_type']
        ):
            final_response += str(chunk.choices[0].delta.content)
            yield chunk

    @observe()
    async def _handle_cached_response(self, enhanced_query: str, user_name: str) -> AsyncGenerator:
        """
        Handle cached Q&A response.

        Args:
            enhanced_query: Original query
            user_name: User's name

        Yields:
            Cached response chunks
        """
        cache_check = await self.cache_service.check_cached_qa({'query': enhanced_query})
        LOGGER.info(f"Cache hit detected for query")

        final_response = ""
        async for chunk in self.response_generator.generate_qa_cache_response(
                enhanced_query=enhanced_query,
                cached_qa=cache_check.get('ref'),
                greeting=False,
                user_name=user_name
        ):
            final_response += str(chunk.choices[0].delta.content)
            yield chunk

    @observe()
    async def _preload_session_context(self, session_id: str) -> Dict:
        """Preload session context data trong parallel phase"""
        session_context = {
            'collection_state': self.session_manager.get_collection_state(session_id),
            'session_state': self.session_manager.get_session_state(session_id),
            'user_context': self.session_manager.get_user_context(session_id)
        }
        return session_context

    @observe()
    async def _evaluate_flow_termination(
            self,
            collection_state: Dict,
            enhanced_query: str,
            flow_decision: str,
            session_id: str
    ) -> bool:
        """
        Evaluate whether current collection flow should be terminated.

        Args:
            collection_state: Current collection state
            enhanced_query: Enhanced query
            flow_decision: LLM flow decision
            session_id: Session identifier

        Returns:
            True if flow should be terminated
        """
        if not collection_state:
            return False

        last_state = self.session_manager.get_session_state(session_id)
        should_terminate = await self._should_terminate_flow(
            last_state, enhanced_query, flow_decision, session_id
        )

        if should_terminate:
            LOGGER.info("Flow termination confirmed - clearing context")
            self.session_manager.clear_collection_state(session_id)
        else:
            LOGGER.info("Flow continuation confirmed - maintaining context")

        return should_terminate

    @observe()
    async def _should_terminate_flow(
            self,
            session_state: Dict,
            enhanced_query: str,
            flow_decision: str,
            session_id: str
    ) -> bool:
        """
        Determine if current flow should be terminated based on LLM analysis.

        Args:
            session_state: Current session state
            enhanced_query: Enhanced query
            flow_decision: LLM flow decision
            session_id: Session identifier

        Returns:
            True if flow should be terminated
        """
        if flow_decision == "new_flow":
            LOGGER.info(f"LLM determined new_flow - terminating current flow")
            return True

        # Time-based termination for safety
        last_response_time = session_state.get('last_updated')
        if last_response_time:
            try:
                from datetime import datetime, timedelta
                last_time = datetime.fromisoformat(last_response_time)
                if datetime.now() - last_time > timedelta(minutes=10):
                    LOGGER.info("Session timeout detected, terminating flow")
                    return True
            except Exception as e:
                LOGGER.warning(f"Time parsing error: {e}")

        LOGGER.info(f"LLM determined continue - maintaining current context")
        return False

    @observe()
    async def _handle_continuation_flow(
            self,
            enhanced_query: str,
            session_id: str,
            user_name: str,
            messages: List[Dict]
    ) -> AsyncGenerator:
        """
        Handle continuation of existing collection flow.

        Args:
            enhanced_query: Enhanced query
            session_id: Session identifier
            user_name: User's name
            messages: Conversation messages

        Yields:
            Response chunks for continuation
        """
        collection_state = self.session_manager.get_collection_state(session_id)
        LOGGER.info(f"Continuing collection - topic: {collection_state['topic']}, "
                    f"intent: {collection_state['active_intent']}")

        conversation_context = {
            'messages': messages[-5:] if len(messages) > 5 else messages,
            'summary': 'Cuộc hội thoại về dịch vụ ngân hàng'
        }

        analysis_result = await self.unified_analyzer.analyze_with_continuation_detection(
            enhanced_query, conversation_context, collection_state
        )

        continuation_analysis = analysis_result.continuation_analysis
        final_response = ""
        if continuation_analysis and continuation_analysis.is_switching:
            await self._handle_intent_switching(enhanced_query, session_id, user_name, messages)
            async for chunk in self._handle_fresh_analysis(
                    enhanced_query, session_id, user_name, messages
            ):
                final_response += str(chunk.choices[0].delta.content)
                yield chunk

        elif continuation_analysis and continuation_analysis.is_clarification:
            async for chunk in self._handle_clarification_request(
                    enhanced_query, collection_state, session_id
            ):
                final_response += str(chunk.choices[0].delta.content)
                yield chunk

        elif continuation_analysis and continuation_analysis.is_continuation:
            async for chunk in self._handle_attribute_continuation(
                    enhanced_query, session_id, user_name, collection_state
            ):
                final_response += str(chunk.choices[0].delta.content)
                yield chunk

    @observe()
    async def _handle_intent_switching(
            self,
            enhanced_query: str,
            session_id: str,
            user_name: str,
            messages: List[Dict]
    ) -> None:
        """
        Handle intent switching by clearing state and preparing for new analysis.

        Args:
            enhanced_query: Enhanced query
            session_id: Session identifier
            user_name: User's name
            messages: Conversation messages
        """
        LOGGER.info("Intent switching detected by enhanced LLM analysis")
        self.session_manager.clear_collection_state(session_id)

    @observe()
    async def _handle_clarification_request(
            self,
            enhanced_query: str,
            collection_state: Dict,
            session_id: str
    ) -> AsyncGenerator:
        """
        Handle clarification request from user.

        Args:
            enhanced_query: Enhanced query
            collection_state: Current collection state
            session_id: Session identifier

        Yields:
            Clarification response chunks
        """
        LOGGER.info("Clarification request detected by enhanced analysis")

        current_intent = collection_state['active_intent']
        topic_value = collection_state['topic']

        clarification_response = await self._generate_clarification_response(
            current_intent, topic_value, enhanced_query
        )

        user_name = self._get_user_name_from_session(session_id)
        final_response = ""
        async for chunk in self.response_generator.generate_collection_response(
                clarification_response, user_name
        ):
            final_response += str(chunk.choices[0].delta.content)
            yield chunk

    @observe()
    async def _handle_attribute_continuation(
            self,
            enhanced_query: str,
            session_id: str,
            user_name: str,
            collection_state: Dict
    ) -> AsyncGenerator:
        """
        Handle continuation of attribute collection.

        Args:
            enhanced_query: Enhanced query
            session_id: Session identifier
            user_name: User's name
            collection_state: Current collection state

        Yields:
            Continuation response chunks
        """
        LOGGER.info("Continuation confirmed by enhanced LLM analysis")

        collection_result = await self.information_collector.continue_collection(
            enhanced_query, session_id
        )
        final_response = ""
        if collection_result.status == "complete":
            intent_str = collection_state['active_intent']
            topic_value = collection_state['topic']

            if topic_value == 'deposit':
                intent = DepositIntent(intent_str)
                documents = await self.document_service.search_and_filter(enhanced_query, top_k=8)
                async for chunk in self.response_generator.generate_deposit_response(
                        intent=intent,
                        enhanced_query=enhanced_query,
                        attributes=collection_result.attributes,
                        documents=documents
                ):
                    final_response += str(chunk.choices[0].delta.content)
                    yield chunk

            elif topic_value == 'balance_retrieve':
                intent = BalanceIntent(intent_str)
                async for chunk in self.response_generator.generate_balance_response(
                        intent=intent,
                        enhanced_query=enhanced_query,
                        attributes=collection_result.attributes,
                        user_name=user_name,
                        conversation_state={}
                ):
                    final_response += str(chunk.choices[0].delta.content)
                    yield chunk

            elif topic_value == 'total_revenue':
                intent = TotalRevenueIntent(intent_str)
                async for chunk in self.response_generator.generate_total_revenue_response(
                        intent=intent,
                        enhanced_query=enhanced_query,
                        attributes=collection_result.attributes,
                        user_name=user_name
                ):
                    final_response += str(chunk.choices[0].delta.content)
                    yield chunk

            elif topic_value == 'loan_management':
                intent = LoanManagementIntent(intent_str)
                async for chunk in self.response_generator.generate_loan_management_response(
                        intent=intent,
                        enhanced_query=enhanced_query,
                        attributes=collection_result.attributes,
                        user_name=user_name
                ):
                    final_response += str(chunk.choices[0].delta.content)
                    yield chunk

        else:
            async for chunk in self.response_generator.generate_collection_response(
                    collection_result.collection_question, user_name
            ):
                final_response += str(chunk.choices[0].delta.content)
                yield chunk

    @observe()
    async def _handle_fresh_analysis(
            self,
            enhanced_query: str,
            session_id: str,
            user_name: str,
            messages: List[Dict]
    ) -> AsyncGenerator:
        """Handle fresh analysis for new requests with parallel processing."""
        conversation_context = {
            'messages': messages[-5:] if len(messages) > 5 else messages,
            'summary': 'Cuộc hội thoại về dịch vụ ngân hàng'
        }

        analysis_tasks = [
            self.unified_analyzer.analyze_unified(enhanced_query, conversation_context),
            self.document_service.search_and_filter(enhanced_query, top_k=8)
        ]

        analysis_results = await asyncio.gather(*analysis_tasks, return_exceptions=True)

        analysis_result = analysis_results[0]
        if isinstance(analysis_result, Exception):
            LOGGER.error(f"Analysis exception: {analysis_result}")
            analysis_result = None
        elif not hasattr(analysis_result, 'topic') or not hasattr(analysis_result, 'intent'):
            LOGGER.error(f"Invalid analysis_result structure: {type(analysis_result)}")
            analysis_result = None

        prefetched_documents = analysis_results[1] if not isinstance(analysis_results[1], Exception) else []
        final_response = ""
        if not analysis_result:
            LOGGER.error("Analysis result is None - falling back to chitchat")
            async for chunk in self.response_generator.generate_chitchat_response(enhanced_query):
                final_response += str(chunk.choices[0].delta.content)
                yield chunk
            return

        try:
            topic = getattr(analysis_result, 'topic', None)
            intent = getattr(analysis_result, 'intent', None)
            final_response = ""
            if not topic or not intent:
                LOGGER.error(f"Missing topic or intent: topic={topic}, intent={intent}")
                async for chunk in self.response_generator.generate_chitchat_response(enhanced_query):
                    final_response += str(chunk.choices[0].delta.content)
                    yield chunk
                return

            topic_value = getattr(topic, 'value', str(topic)) if hasattr(topic, 'value') else str(topic)
            intent_str = getattr(intent, 'value', str(intent)) if hasattr(intent, 'value') else str(intent)

            LOGGER.info(f"Fresh analysis - topic: {topic_value}, intent: {intent_str}")

            self.session_manager.update_session_state(session_id, {
                'current_topic': topic_value,
                'current_intent': intent_str,
                'enhanced_query': enhanced_query,
                'user_name': user_name
            })

            async for chunk in self._generate_domain_response(
                    analysis_result, enhanced_query, session_id, user_name, prefetched_documents
            ):
                final_response += str(chunk.choices[0].delta.content)
                yield chunk

        except AttributeError as e:
            LOGGER.error(f"AttributeError in fresh analysis: {e}")
            async for chunk in self.response_generator.generate_chitchat_response(enhanced_query):
                final_response += str(chunk.choices[0].delta.content)
                yield chunk
        except Exception as e:
            LOGGER.error(f"Unexpected error in fresh analysis: {e}")
            async for chunk in self.response_generator.generate_chitchat_response(enhanced_query):
                final_response += str(chunk.choices[0].delta.content)
                yield chunk

    @observe()
    async def _generate_domain_response(
            self,
            analysis_result,
            enhanced_query: str,
            session_id: str,
            user_name: Optional[str],
            prefetched_documents: List[Dict] = None
    ) -> AsyncGenerator:
        """Generate response based on domain analysis with prefetched documents."""
        final_response = ""
        try:
            if analysis_result is None or isinstance(analysis_result, (str, int, float, bool)):
                LOGGER.error(f"Invalid analysis_result type: {type(analysis_result)} - falling back to chitchat")
                async for chunk in self.response_generator.generate_chitchat_response(enhanced_query):
                    final_response += str(chunk.choices[0].delta.content)
                    yield chunk
                return

            if not hasattr(analysis_result, 'topic') or not hasattr(analysis_result, 'intent'):
                LOGGER.error(f"analysis_result missing required attributes (topic/intent): {dir(analysis_result)}")
                async for chunk in self.response_generator.generate_chitchat_response(enhanced_query):
                    final_response += str(chunk.choices[0].delta.content)
                    yield chunk
                return

            topic = getattr(analysis_result, 'topic', None)
            intent = getattr(analysis_result, 'intent', None)
            final_response = ""

            if not topic or not intent:
                LOGGER.error(f"Missing topic or intent in domain response: topic={topic}, intent={intent}")
                async for chunk in self.response_generator.generate_chitchat_response(enhanced_query):
                    final_response += str(chunk.choices[0].delta.content)
                    yield chunk
                return

            if topic == TopicCategory.CARD:
                async for chunk in self._handle_card_domain(enhanced_query, session_id):
                    final_response += str(chunk.choices[0].delta.content)
                    yield chunk


            elif topic in [TopicCategory.DEPOSIT, TopicCategory.BALANCE_RETRIEVE, TopicCategory.TOTAL_REVENUE, TopicCategory.LOAN_MANAGEMENT]:
                async for chunk in self._handle_unified_domain(
                        topic, intent, enhanced_query, session_id, prefetched_documents
                ):
                    final_response += str(chunk.choices[0].delta.content)
                    yield chunk

            elif topic == TopicCategory.CHITCHAT and intent == "chitchat":
                # Kiểm tra document relevance cho chitchat
                relevant_documents = prefetched_documents or []
                if len(relevant_documents) == 0:
                    LOGGER.info("CHITCHAT: No relevant documents found, using standard chitchat prompt")
                    async for chunk in self.response_generator.generate_chitchat_response(enhanced_query):
                        final_response += str(chunk.choices[0].delta.content)
                        yield chunk
                else:
                    LOGGER.info(
                        f"CHITCHAT: {len(relevant_documents)} relevant documents found, using document-aware chitchat")
                    async for chunk in self.response_generator.generate_chitchat_with_documents_response(
                            enhanced_query, relevant_documents
                    ):
                        final_response += str(chunk.choices[0].delta.content)
                        yield chunk

            else:
                async for chunk in self.response_generator.generate_chitchat_response(enhanced_query):
                    final_response += str(chunk.choices[0].delta.content)
                    yield chunk

        except Exception as e:
            final_response = ""
            LOGGER.error(f"Error in domain response generation: {e}")
            async for chunk in self.response_generator.generate_chitchat_response(enhanced_query):
                final_response += str(chunk.choices[0].delta.content)
                yield chunk

    @observe()
    async def _handle_unified_domain(
            self,
            topic: TopicCategory,
            intent: Union[DepositIntent, BalanceIntent, TotalRevenueIntent, LoanManagementIntent],
            enhanced_query: str,
            session_id: str,
            prefetched_documents: List[Dict] = None
    ) -> AsyncGenerator:
        """Handle unified domain processing with parallel optimization."""
        LOGGER.info(f"Unified domain handler: {topic.value}, intent: {intent}")

        needs_attributes = self._check_if_needs_attributes(topic, intent)
        user_name = self._get_user_name_from_session(session_id)
        final_response = ""
        if not needs_attributes:
            if topic == TopicCategory.DEPOSIT:
                documents = prefetched_documents or await self.document_service.search_and_filter(enhanced_query,
                                                                                                  top_k=8)
                async for chunk in self.response_generator.generate_deposit_response(
                        intent=intent,
                        enhanced_query=enhanced_query,
                        attributes=None,
                        documents=documents
                ):
                    final_response += str(chunk.choices[0].delta.content)
                    yield chunk

            elif topic == TopicCategory.BALANCE_RETRIEVE:
                async for chunk in self.response_generator.generate_balance_response(
                        intent=intent,
                        enhanced_query=enhanced_query,
                        attributes=None,
                        user_name=user_name,
                        conversation_state={}
                ):
                    final_response += str(chunk.choices[0].delta.content)
                    yield chunk

            elif topic == TopicCategory.TOTAL_REVENUE:
                async for chunk in self.response_generator.generate_total_revenue_response(
                        intent=intent,
                        attributes=None,
                        enhanced_query=enhanced_query,
                        documents=None,
                        user_name=user_name,
                ):
                    final_response += str(chunk.choices[0].delta.content)
                    yield chunk

            elif topic == TopicCategory.LOAN_MANAGEMENT:
                async for chunk in self.response_generator.generate_loan_management_response(
                        intent=intent,
                        attributes=None,
                        enhanced_query=enhanced_query,
                        documents=None,
                        user_name=user_name,
                ):
                    final_response += str(chunk.choices[0].delta.content)
                    yield chunk
            return

        # Collection flow for attribute-requiring intents
        collection_result = await self.information_collector.collect_all_required_attributes(
            enhanced_query, intent, topic, session_id
        )

        if collection_result.should_proceed:
            if collection_result.attributes and hasattr(collection_result.attributes,
                                                        'account_number') and collection_result.attributes.account_number:
                LOGGER.info(
                    f"Using account: {collection_result.attributes.account_number} (auto-selected or extracted)")

            if topic == TopicCategory.DEPOSIT:
                documents = prefetched_documents or await self.document_service.search_and_filter(enhanced_query,
                                                                                                  top_k=8)
                async for chunk in self.response_generator.generate_deposit_response(
                        intent=intent,
                        enhanced_query=enhanced_query,
                        attributes=collection_result.attributes,
                        documents=documents
                ):
                    # final_response += str(chunk.choices[0].delta.content)
                    yield chunk

            elif topic == TopicCategory.BALANCE_RETRIEVE:
                async for chunk in self.response_generator.generate_balance_response(
                        intent=intent,
                        enhanced_query=enhanced_query,
                        attributes=collection_result.attributes,
                        user_name=user_name,
                        conversation_state={}
                ):
                    # final_response += str(chunk.choices[0].delta.content)
                    yield chunk

            elif topic == TopicCategory.TOTAL_REVENUE:

                async for chunk in self.response_generator.generate_total_revenue_response(
                        intent=intent,
                        enhanced_query=enhanced_query,
                        attributes=collection_result.attributes,
                        documents=None,
                        user_name=user_name
                ):
                    final_response += str(chunk.choices[0].delta.content)
                    yield chunk

            elif topic == TopicCategory.LOAN_MANAGEMENT:

                async for chunk in self.response_generator.generate_loan_management_response(
                        intent=intent,
                        enhanced_query=enhanced_query,
                        attributes=collection_result.attributes,
                        documents=None,
                        user_name=user_name
                ):
                    yield chunk

        else:
            async for chunk in self.response_generator.generate_collection_response(
                    collection_result.collection_question, user_name
            ):
                final_response += str(chunk.choices[0].delta.content)
                yield chunk

    @observe()
    async def _handle_card_domain(self, enhanced_query: str, session_id: str) -> AsyncGenerator:
        """
        Handle card domain processing.

        Args:
            enhanced_query: Enhanced query
            session_id: Session identifier

        Yields:
            Card domain response chunks
        """
        LOGGER.info(f"Handling card domain: {enhanced_query}")

        user_name = self._get_user_name_from_session(session_id)
        state = {'query': enhanced_query}
        card_result = await self.card_service.run(state)
        final_response = ""
        if card_result:
            async for chunk in self.response_generator.generate_card_response(enhanced_query, card_result, user_name):
                final_response += str(chunk.choices[0].delta.content)
                yield chunk
        else:
            async for chunk in self.response_generator.generate_chitchat_response(enhanced_query):
                final_response += str(chunk.choices[0].delta.content)
                yield chunk


    @observe()
    def _check_if_needs_attributes(
            self,
            topic: TopicCategory,
            intent: Union[DepositIntent, BalanceIntent, TotalRevenueIntent, LoanManagementIntent]
    ) -> bool:
        """
        Check if intent requires attribute collection.

        Args:
            topic: Topic category
            intent: Specific intent

        Returns:
            True if attributes needed, False otherwise
        """
        if topic == TopicCategory.DEPOSIT:
            return DepositIntent.requires_attributes(intent)
        elif topic == TopicCategory.BALANCE_RETRIEVE:
            return BalanceIntent.requires_attributes(intent)
        elif topic == TopicCategory.TOTAL_REVENUE:
            return TotalRevenueIntent.requires_attributes(intent)
        elif topic == TopicCategory.LOAN_MANAGEMENT:
            return LoanManagementIntent.requires_attributes(intent)
        return False

    @observe()
    def _get_user_name_from_session(self, session_id: str) -> str:
        """Get user name from session."""
        if self.user_profile_service:
            user_name = self.user_profile_service.get_user_name(session_id)
            return user_name if user_name else "bạn"
        return "bạn"

    @observe()
    async def _generate_clarification_response(
            self,
            current_intent: str,
            topic: str,
            enhanced_query: str
    ) -> str:
        """Generate clarification response for current collection."""
        return await self.llm_service.llm_task(
            inputs={
                'current_intent': current_intent,
                'topic': topic,
                'enhanced_query': enhanced_query
            },
            prompt_template=lf.get_prompt(name="BEECHAT_KHCN_CLARIFICATION_RESPONSE_PROMPT"),
            use_primary=False
        )


async def main() -> None:
    """
   Interactive chat mode for testing the banking application.

   Provides a command-line interface for testing all banking services
   with automatic profile loading and conversation management.
   """
    print("=" * 80)
    print("🤖 BEE BANKING APP - INTERACTIVE MODE")
    print("=" * 80)

    bot_id = "0dc3beb3-beae-44f4-9b98-2aa39f4373f8"
    app = BeeBankingApp(bot_id)

    print(f"BeeBankingApp initialized with bot_id: {bot_id}")
    print("\n💡 COMMANDS:")
    print("• Type your message to chat with Bee")
    print("• 'exit' or 'quit' - Exit the conversation")
    print("• 'clear' - Clear conversation history and session")
    print("• 'help' - Show banking services examples")

    session_id = f"session_{int(time.time())}"
    user_name = input("\n👤 Enter your name (or press Enter for default): ").strip()
    if not user_name:
        user_name = "Nguyễn Văn An"

    sample_profile = {
        "name": user_name,
        "maritalStatus": "Độc thân",
        "education": "Đại học",
        "currentJob": "Làm việc toàn thời gian",
        "jobPosition": "Chuyên viên / Nhân viên",
        "workDuration": "1 – 3 năm",
        "industries": "Công nghệ thông tin / Phần mềm",
        "hasChildren": "Chưa có",
        "monthlyIncome": "25000000",
        "bankingPurposes": ["Nhận lương", "Chuyển tiền", "Chi tiêu hằng ngày"],
        "accountList": ["0778761148", "0393989068", "48695686846486", "123456789", "444448888"],
        "userId": "5868198"
    }

    topic_json = json.dumps(sample_profile, ensure_ascii=False)
    conversation_history = []
    current_role = ["L1"]

    print(f"\n🏦 Welcome! Starting conversation...")
    print(f"Session ID: {session_id}")
    print(f"👤 User: {user_name}")
    print(f"Profile: Auto-loaded with {len(sample_profile['accountList'])} accounts")
    print(f"💬 Bee is ready!")
    print("─" * 60)

    # Test profile load
    print("🔍 Loading profile...")
    test_message = [{"role": "user", "content": "test"}]
    test_chunks = []
    async for chunk in app.run(
            messages=test_message,
            role_ids=current_role,
            topic=topic_json,
            session_id=session_id,
            response_status={}
    ):
        test_chunks.append(chunk)

    profile = app.user_profile_service.get_profile(session_id)
    if profile:
        accounts = profile.get_account_list()
        print(f"Profile loaded: {len(accounts)} accounts available")
        user_name = profile.get_display_name() or user_name
    else:
        print("Profile load failed - using fallback")

    while True:
        try:
            user_input = input(f"\n👤 {user_name}: ").strip()

            if user_input.lower() in ['exit', 'quit', 'bye']:
                print(f"\n👋 Goodbye! Thank you for using Bee Banking Services!")
                break

            elif user_input.lower() == 'clear':
                print(f"Clearing conversation history...")
                conversation_history = []
                print("Conversation cleared.")
                continue

            print(f"\n🤖 Bee: ", end="", flush=True)
            start_time = time.time()

            user_message = {"role": "user", "content": user_input}
            conversation_history.append(user_message)

            full_response = ""
            chunk_count = 0
            processing_error = None

            try:
                async for chunk in app.run(
                        messages=conversation_history.copy(),
                        role_ids=current_role,
                        topic=topic_json,
                        session_id=session_id,
                        response_status={}
                ):
                    chunk_count += 1

                    if chunk.choices and chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        print(content, end="", flush=True)
                        full_response += content

            except Exception as app_run_error:
                processing_error = app_run_error
                LOGGER.error(f"APP_RUN_ERROR: {type(app_run_error).__name__} - {str(app_run_error)}")
                print(f"\nERROR: {type(app_run_error).__name__} - {str(app_run_error)}")
                print(f"   Session: {session_id}, Chunks: {chunk_count}")

            print()

            if processing_error:
                error_message = f"ERROR: {type(processing_error).__name__} - {str(processing_error)}"
                bot_message = {"role": "assistant", "content": error_message}
                conversation_history.append(bot_message)

            elif full_response.strip():
                bot_message = {"role": "assistant", "content": full_response.strip()}
                conversation_history.append(bot_message)
            else:
                LOGGER.warning(f"EMPTY_RESPONSE: {chunk_count} chunks processed")
                print(f"🔍 EMPTY RESPONSE: {chunk_count} chunks processed")
                debug_message = f"DEBUG: Empty response - {chunk_count} chunks processed"
                bot_message = {"role": "assistant", "content": debug_message}
                conversation_history.append(bot_message)

            processing_time = time.time() - start_time
            status_info = "ERROR" if processing_error else "SUCCESS"
            print(
                f"Turn #{len(conversation_history) // 2} | {processing_time:.1f}s | {chunk_count} chunks | {status_info}")

        except KeyboardInterrupt:
            print(f"\n\n👋 Conversation interrupted. Goodbye!")
            break

        except Exception as outer_error:
            print(f"\nOUTER ERROR: {type(outer_error).__name__} - {str(outer_error)}")
            LOGGER.error(f"OUTER_LOOP_ERROR: {type(outer_error).__name__} - {str(outer_error)}")

            error_response = f"OUTER_ERROR: {type(outer_error).__name__} - {str(outer_error)}"
            print(error_response)
            error_message = {"role": "assistant", "content": error_response}
            conversation_history.append(error_message)

            print("🔄 Conversation continues with detailed error information...")

    print(f"\nCONVERSATION SUMMARY:")
    print(f"  - Total messages: {len(conversation_history)}")
    print(f"  - Conversation turns: {len(conversation_history) // 2}")
    print(f"  - Session ID: {session_id}")
    print("\n🏦 Thank you for using Bee Banking Services!")


if __name__ == "__main__":
    asyncio.run(main())
