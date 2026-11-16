"""
Unified Response Generator - Centralized response generation for all banking domains

Provides unified response generation with enhanced balance API integration,
comprehensive error handling, and metadata enrichment for all banking services.
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, AsyncGenerator, Union
from ag_ui.core import EventType

from beechat_khcn.models.balance_retrieve_model import (
    BalanceIntent, BalanceAttributes, BalanceValidationUtils, create_empty_balance_attributes
)
from beechat_khcn.models.conversation_model import DepositIntent
from beechat_khcn.models.loan_management_model import LoanManagementIntent, LoanManagementAttributes
from beechat_khcn.models.total_revenue_model import TotalRevenueIntent, TotalRevenueAttributes
from beechat_khcn.services.bank_statement_service import BalanceApiService
from beechat_khcn.services.loan_management_api import LoanManagementApiService
from beegenerate.loggings import LOGGER
from beegenerate.loggings.loggers import lf
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from streaming.decorators import agui_astep_event, with_step


class UnifiedResponseGenerator:
    """Centralized response generation service for all banking domains."""

    TECHNICAL_ERROR_MESSAGE = "Mister Bụt hiện đang có vấn đề kĩ thuật, xin vui lòng thử lại sau vài phút."

    def __init__(self, llm_service, document_service) -> None:
        self.llm_service = llm_service
        self.document_service = document_service
        self.balance_api = BalanceApiService(llm_service)
        self.user_profile_service = None
        self._get_display_name = lambda name: name or "bạn"

    # ==================== CORE RESPONSE GENERATION ====================

    async def generate_qa_cache_response(
            self,
            enhanced_query: str,
            cached_qa: Dict,
            greeting: bool = False,
            user_name: Optional[str] = None
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Generate response from cached QA data."""
        if not cached_qa or 'content' not in cached_qa:
            async for chunk in self.generate_chitchat_response(enhanced_query):
                yield chunk
            return

        context = {
            "question": enhanced_query,
            "documents": cached_qa['content'],
            "date": datetime.now().date(),
            "greeting": greeting,
            "user_name": user_name
        }

        async for chunk in self.llm_service.llm_stream(
                inputs=context,
                prompt_template=lf.get_prompt("BEECHAT_QA_RESPONSE_PROMPT"),
                sleep=0.01,
                docs=[{'id': cached_qa.get('id', 'cached_qa')}]
        ):
            yield chunk

    async def generate_deposit_response(
            self,
            intent: DepositIntent,
            enhanced_query: str,
            attributes,
            documents: List[Dict]
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Generate response for deposit intents."""
        documents_text = self.document_service._extract_content_simple(documents)
        docs_refs = self.document_service.create_attached_docs_for_llm(documents)
        intent_stage = DepositIntent.get_stage(intent)

        if intent_stage == "pre_opening":
            context, prompt_template = self._build_deposit_context(
                intent, enhanced_query, attributes, documents_text, is_pre_opening=True
            )
        else:
            context, prompt_template = self._build_deposit_context(
                intent, enhanced_query, attributes, documents_text, is_pre_opening=False
            )

        async for chunk in self.llm_service.llm_stream(
                inputs=context,
                prompt_template=prompt_template,
                docs=docs_refs
        ):
            yield chunk

    async def generate_balance_response(
            self,
            intent: BalanceIntent,
            enhanced_query: str,
            attributes: Optional[BalanceAttributes],
            user_name: Optional[str] = None,
            conversation_state: Optional[Dict] = None
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Generate response for balance intents."""
        LOGGER.info(f"Generating balance response for intent: {intent}")

        # Handle navigation intents
        if intent == BalanceIntent.ACCOUNT_SELECTION or enhanced_query == "account_selection":
            async for chunk in self._generate_account_selection_response(
                    user_name=user_name,
                    session_id=conversation_state.get('session_id') if conversation_state else None
            ):
                yield chunk
            return

        if intent == BalanceIntent.BALANCE_RETRIEVE_MENU:
            async for chunk in self._generate_menu_response("balance_retrieve_menu", enhanced_query, user_name):
                yield chunk
            return

        # Handle unrecognized queries
        if (hasattr(BalanceIntent, 'UNRECOGNIZED_TRANSACTION_QUERY') and
                intent == BalanceIntent.UNRECOGNIZED_TRANSACTION_QUERY):
            async for chunk in self._generate_unrecognized_query_response(enhanced_query, user_name):
                yield chunk
            return

        if intent in [BalanceIntent.QUERY_TRANSACTION_EXPORT, BalanceIntent.INITIATE_TRANSACTION_DISPUTE]:
            async for chunk in self._generate_balance_no_api_response(intent, enhanced_query, user_name):
                yield chunk
            return

        if BalanceIntent.requires_attributes(intent):
            if attributes is None:
                async for chunk in self._generate_error_response("Thiếu thông tin cần thiết. Vui lòng thử lại."):
                    yield chunk
                return

            # Validate attributes
            if not isinstance(attributes, BalanceAttributes):
                LOGGER.error(f"Wrong attribute type for balance domain: {type(attributes).__name__}")
                attributes = create_empty_balance_attributes()

            self._apply_smart_defaults_to_attributes(attributes, intent)

            if not attributes.is_valid_for_intent(intent):
                missing = attributes.get_missing_attributes(intent)
                if missing:
                    error_msg = f"Thiếu thông tin: {', '.join(missing)}"
                    async for chunk in self._generate_error_response(error_msg):
                        yield chunk
                    return

            async for chunk in self._handle_transaction_query(intent, attributes, enhanced_query, user_name):
                yield chunk
        else:
            async for chunk in self._generate_error_response("Intent không được hỗ trợ."):
                yield chunk

    async def generate_total_revenue_response(
            self,
            intent: TotalRevenueIntent,
            attributes: Optional[TotalRevenueAttributes],
            enhanced_query: str,
            documents: List[Dict] = None,
            user_name: Optional[str] = None
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Generate response for total revenue intents."""
        async for chunk in self._generate_api_domain_response(
                domain_type="total_revenue",
                intent=intent,
                attributes=attributes,
                enhanced_query=enhanced_query,
                documents=documents,
                user_name=user_name
        ):
            yield chunk

    async def generate_loan_management_response(
            self,
            intent: LoanManagementIntent,
            attributes: Optional[LoanManagementAttributes],
            enhanced_query: str,
            documents: List[Dict] = None,
            user_name: Optional[str] = None
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Generate response for loan management intents."""
        async for chunk in self._generate_api_domain_response(
                domain_type="loan_management",
                intent=intent,
                attributes=attributes,
                enhanced_query=enhanced_query,
                documents=documents,
                user_name=user_name
        ):
            yield chunk

    async def generate_card_response(
            self,
            enhanced_query: str,
            card_result: Dict,
            user_name: Optional[str] = None
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Generate response for card-related queries."""
        display_name = self._get_display_name(user_name)
        current_date = datetime.now().date()

        if card_result.get('unknown', False):
            documents = await self.document_service.search_and_filter(enhanced_query, top_k=10)
            documents_text = self.document_service._extract_content_simple(documents)

            context = {
                "question": enhanced_query,
                "documents": documents_text,
                "date": current_date,
                "greeting": False,
                "user_name": display_name
            }

            async for chunk in self.llm_service.llm_stream(
                    inputs=context,
                    prompt_template=lf.get_prompt("BEECHAT_KHCN_NORMAL_RAG_ANSWER_PROMPT")
            ):
                yield chunk
            return

        if card_result.get('special_keyword', False):
            keyword = card_result.get('keyword', 'thẻ')
            prompt_template = f"""
        Vai trò: Mister Bụt - trợ lý ảo tư vấn tài chính cá nhân của MB Bank
    
        Khách hàng hỏi về: {keyword}
        Câu hỏi: {enhanced_query}
    
        Tôi sẽ tìm hiểu thông tin về {keyword} và hỗ trợ {display_name} tốt nhất có thể.
        """
            async for chunk in self.llm_service.llm_stream(inputs={}, prompt_template=prompt_template):
                yield chunk
            return

        if not card_result.get('is_leaf', False):
            children = card_result.get('children', [])
            if children:
                children_text = ", ".join(children)
                prompt_template = f"""
        Vai trò: Mister Bụt - trợ lý ảo MB Bank
    
        {display_name} hỏi về thẻ: {enhanced_query}
    
        Các loại thẻ có sẵn: {children_text}
    
        Tôi sẽ giúp {display_name} tìm hiểu về các loại thẻ này. Bạn muốn biết thông tin cụ thể về loại thẻ nào?
        """
                async for chunk in self.llm_service.llm_stream(inputs={}, prompt_template=prompt_template):
                    yield chunk
            return

        # Handle specific card
        card_docs = card_result.get('value', [])
        if not card_docs:
            async for chunk in self.generate_chitchat_response(enhanced_query):
                yield chunk
            return

        documents_text = self.document_service._extract_content_simple(card_docs)
        docs_refs = self.document_service.create_attached_docs_for_llm(card_docs)

        context = {
            "question": enhanced_query,
            "documents": documents_text,
            "date": current_date,
            "greeting": False,
            "user_name": display_name
        }

        async for chunk in self.llm_service.llm_stream(
                inputs=context,
                prompt_template=lf.get_prompt("BEECHAT_KHCN_CARD_RAG_ANSWER_PROMPT"),
                docs=docs_refs
        ):
            yield chunk

    async def generate_collection_response(
            self,
            collection_question: str,
            user_name: Optional[str] = None
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Generate response for collection queries."""
        system_prompt = f"""You are a content display system.
Your only job is to output the exact content provided below without any modification, interpretation, or reformatting.

OUTPUT EXACTLY:
{collection_question}"""

        async for chunk in self.llm_service.llm_stream(
                inputs={},
                prompt_template=system_prompt,
                sleep=0.0001,
                temperature=0.0
        ):
            yield chunk

    async def generate_chitchat_response(self, enhanced_query: str) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Generate chitchat response for general queries."""
        async for chunk in self.llm_service.llm_stream(
                inputs={"query": enhanced_query},
                prompt_template=lf.get_prompt("BEECHAT_KHCN_APP_KHCN_CHIT_CHAT"),
                sleep=0.01
        ):
            yield chunk

    # ==================== UNIFIED API DOMAIN HANDLER ====================

    async def _generate_api_domain_response(
            self,
            domain_type: str,
            intent: Union[TotalRevenueIntent, LoanManagementIntent],
            attributes: Optional[Union[TotalRevenueAttributes, LoanManagementAttributes]],
            enhanced_query: str,
            documents: List[Dict] = None,
            user_name: Optional[str] = None
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Unified handler for API-based domains (Total Revenue, Loan Management)."""
        LOGGER.info(f"Generating {domain_type} response: intent={intent.value}")

        # Fetch API data
        api_result = await self._fetch_domain_api_data(domain_type, intent, attributes)
        LOGGER.info(f"api_result:{api_result}")
        if not api_result:
            async for chunk in self._generate_error_response("Lỗi hệ thống - không có dữ liệu API"):
                yield chunk
            return

        # Validate data
        if not self._validate_domain_data(domain_type, intent, api_result):
            error_message = api_result.get("error", "Không có dữ liệu khả dụng")
            async for chunk in self._generate_error_response(error_message):
                yield chunk
            return

        try:
            # Build context and get prompt
            prompt_template, inputs = self._build_domain_context(
                domain_type, intent, api_result, enhanced_query, user_name
            )

            if not prompt_template:
                LOGGER.warning(f"No prompt template found for {intent.value}, using default response")
                async for chunk in self.generate_chitchat_response(enhanced_query):
                    yield chunk
                return

            # Generate response
            async for chunk in self.llm_service.llm_stream(
                    inputs=inputs,
                    prompt_template=prompt_template,
                    sleep=0.0001,
                    docs=documents
            ):
                yield chunk

        except Exception as e:
            LOGGER.error(f"{domain_type.title()} Response Generation Error: {str(e)}")
            async for chunk in self._generate_error_response(f"Lỗi trong quá trình xử lý: {str(e)[:100]}"):
                yield chunk

    async def _fetch_domain_api_data(
            self,
            domain_type: str,
            intent: Union[TotalRevenueIntent, LoanManagementIntent],
            attributes: Optional[Union[TotalRevenueAttributes, LoanManagementAttributes]]
    ) -> Dict:
        """Fetch API data based on domain type."""
        if domain_type == "total_revenue":
            async with agui_astep_event(step_name="fetch_total_assets",type=EventType.TOOL_CALL_START):
                if not hasattr(self, 'total_revenue_api'):
                    from beechat_khcn.services.total_revenue_api import TotalRevenueApiService
                    self.total_revenue_api = TotalRevenueApiService(llm_service=self.llm_service)
                return await self.total_revenue_api.get_data_for_intent(intent, attributes)

        elif domain_type == "loan_management":
            async with agui_astep_event(step_name="fetch_loan_information",type=EventType.TOOL_CALL_START):
                if not hasattr(self, 'loan_management_api'):
                    self.loan_management_api = LoanManagementApiService(llm_service=self.llm_service)
                return await self.loan_management_api.get_data_for_intent(intent, attributes)

        return {}

    def _validate_domain_data(
            self,
            domain_type: str,
            intent: Union[TotalRevenueIntent, LoanManagementIntent],
            api_result: Dict
    ) -> bool:
        """Validate API result data based on domain and intent type."""
        if domain_type == "total_revenue":
            if intent in [TotalRevenueIntent.GET_TOTAL_ASSETS, TotalRevenueIntent.GET_NET_WORTH,
                          TotalRevenueIntent.GET_TOTAL_DEBT, TotalRevenueIntent.ASSET_HEALTH_CHECK,
                          TotalRevenueIntent.GET_INCOME_PROJECTION]:
                return api_result.get("success") == True and api_result.get("formatted_data")
            if intent == TotalRevenueIntent.TRIGGER_ASSET_SUMMARY_NOTIFICATION:
                return True

        elif domain_type == "loan_management":
            if intent in [LoanManagementIntent.GET_ALL_LD, LoanManagementIntent.GET_LD_INFO,
                          LoanManagementIntent.GET_LD_PAYMENT_SCHEDULE, LoanManagementIntent.GET_TOTAL_OVERDUE_DEBT,
                          LoanManagementIntent.GET_AC_OVERDRAFT_LIST]:
                has_formatted_data = api_result.get("formatted_data") is not None
                is_success = api_result.get("success") == True
                is_loan_not_found = api_result.get("error_type") == "loan_not_found"

                # Cho phép cả success=True hoặc loan_not_found với formatted_data
                return (is_success and has_formatted_data) or (is_loan_not_found and has_formatted_data)

            if intent == LoanManagementIntent.OUT_OF_SCOPE:
                return True

        return False

    def _build_domain_context(
            self,
            domain_type: str,
            intent: Union[TotalRevenueIntent, LoanManagementIntent],
            api_result: Dict,
            enhanced_query: str,
            user_name: Optional[str]
    ) -> tuple:
        """Build context and get prompt template for domain response."""
        if domain_type == "total_revenue":
            return self._build_total_revenue_context(intent, api_result, enhanced_query, user_name)
        elif domain_type == "loan_management":
            return self._build_loan_management_context(intent, api_result, enhanced_query, user_name)
        return None, {}

    def _build_total_revenue_context(
            self,
            intent: TotalRevenueIntent,
            api_result: Dict,
            enhanced_query: str,
            user_name: Optional[str]
    ) -> tuple:
        """Build context for total revenue response."""
        prompt_mapping = {
            TotalRevenueIntent.GET_TOTAL_ASSETS: "BEECHAT_KHCN_TOTAL_REVENUE_GET_TOTAL_ASSETS_PROMPT",
            TotalRevenueIntent.GET_NET_WORTH: "BEECHAT_KHCN_TOTAL_REVENUE_GET_NET_WORTH_PROMPT",
            TotalRevenueIntent.GET_TOTAL_DEBT: "BEECHAT_KHCN_TOTAL_REVENUE_GET_TOTAL_DEBT_PROMPT",
            TotalRevenueIntent.ASSET_HEALTH_CHECK: "BEECHAT_KHCN_TOTAL_REVENUE_ASSET_HEALTH_CHECK",
            TotalRevenueIntent.GET_INCOME_PROJECTION: "BEECHAT_KHCN_TOTAL_REVENUE_GET_INCOME_PROJECTION_PROMPT",
            TotalRevenueIntent.TRIGGER_ASSET_SUMMARY_NOTIFICATION: "BEECHAT_KHCN_TOTAL_REVENUE_TRIGGER_NOTIFICATION_PROMPT",
            TotalRevenueIntent.OUT_OF_SCOPE: "BEECHAT_KHCN_TOTAL_REVENUE_OUT_OF_SCOPE_PROMPT"
        }

        prompt_template = lf.get_prompt(prompt_mapping.get(intent))

        if intent == TotalRevenueIntent.GET_INCOME_PROJECTION:
            inputs = {
                "savings_data": api_result.get("formatted_data", ""),
                "user_query": enhanced_query,
                "user_name": user_name
            }
        elif intent == TotalRevenueIntent.TRIGGER_ASSET_SUMMARY_NOTIFICATION:
            inputs = {"user_query": enhanced_query}
        else:
            inputs = {
                "api_data": api_result.get("formatted_data", ""),
                "user_query": enhanced_query,
                "user_name": user_name,
                "current_time": datetime.now()
            }

        return prompt_template, inputs

    def _build_loan_management_context(
            self,
            intent: LoanManagementIntent,
            api_result: Dict,
            enhanced_query: str,
            user_name: Optional[str]
    ) -> tuple:
        """Build context for loan management response."""
        prompt_mapping = {
            LoanManagementIntent.GET_ALL_LD: "BEECHAT_KHCN_LOAN_MANAGEMENT_GET_ALL_LD_PROMPT",
            LoanManagementIntent.GET_LD_INFO: "BEECHAT_KHCN_LOAN_MANAGEMENT_GET_LD_INFO_PROMPT",
            LoanManagementIntent.GET_LD_PAYMENT_SCHEDULE: "BEECHAT_KHCN_LOAN_MANAGEMENT_GET_LD_PAYMENT_SCHEDULE_PROMPT",
            LoanManagementIntent.GET_TOTAL_OVERDUE_DEBT: "BEECHAT_KHCN_LOAN_MANAGEMENT_GET_TOTAL_OVERDUE_DEBT_PROMPT",
            LoanManagementIntent.GET_AC_OVERDRAFT_LIST: "BEECHAT_KHCN_LOAN_MANAGEMENT_GET_AC_OVERDRAFT_LIST_PROMPT",
            LoanManagementIntent.OUT_OF_SCOPE: "BEECHAT_KHCN_LOAN_MANAGEMENT_OUT_OF_SCOPE_PROMPT"
        }

        is_loan_not_found = api_result.get("error_type") == "loan_not_found"

        if is_loan_not_found:
            if intent == LoanManagementIntent.GET_LD_PAYMENT_SCHEDULE:
                prompt_template = lf.get_prompt("BEECHAT_KHCN_LOAN_MANAGEMENT_LOAN_NOT_FOUND_PROMPT")
            else:
                prompt_template = lf.get_prompt(prompt_mapping.get(intent))
        else:
            prompt_template = lf.get_prompt(prompt_mapping.get(intent))

        if intent == LoanManagementIntent.OUT_OF_SCOPE:
            inputs = {
                "user_query": enhanced_query,
                "user_name": user_name
            }
        else:
            inputs = {
                "api_data": api_result.get("formatted_data", ""),
                "user_query": enhanced_query,
                "user_name": user_name,
                "customer_code": api_result.get("customer_code", ""),
                "intent": api_result.get("intent", ""),
                "current_time": datetime.now(),
                "is_loan_not_found": is_loan_not_found,
                "requested_loan_id": api_result.get("loan_id", "") if is_loan_not_found else "",
                "available_loans": api_result.get("available_loans", []) if is_loan_not_found else []
            }
            if intent == LoanManagementIntent.GET_LD_PAYMENT_SCHEDULE:
                inputs["date_range"] = api_result.get("date_range", "")

        return prompt_template, inputs

    # ==================== BALANCE DOMAIN HANDLERS ====================

    async def _generate_balance_no_api_response(
            self,
            intent: BalanceIntent,
            enhanced_query: str,
            user_name: Optional[str] = None
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Handle balance intents that don't require API calls."""
        display_name = self._get_display_name(user_name)
        context = {"user_name": display_name, "enhanced_query": enhanced_query}

        if intent == BalanceIntent.QUERY_TRANSACTION_EXPORT:
            prompt_template = lf.get_prompt("BEECHAT_KHCN_QUERY_TRANSACTION_EXPORT_PROMPT")
            intent_value = "query_transaction_export"
        else:
            prompt_template = lf.get_prompt("BEECHAT_KHCN_INITIATE_TRANSACTION_DISPUTE_PROMPT")
            intent_value = "initiate_transaction_dispute"

        async for chunk in self.llm_service.llm_stream(inputs=context, prompt_template=prompt_template):
            chunk_dict = chunk.model_dump()
            chunk_dict["status_code"] = 200
            chunk_dict["status_message"] = "Success!"
            chunk_dict["intent"] = intent_value
            yield ChatCompletionChunk(**chunk_dict)

    @with_step(step_name="fetch_transaction_list",type=EventType.TOOL_CALL_START)
    async def _handle_transaction_query(
            self,
            intent: BalanceIntent,
            attributes: BalanceAttributes,
            enhanced_query: str,
            user_name: Optional[str] = None,
            limit: int = 1500
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Handle unified transaction queries."""
        LOGGER.info(f"Processing unified transaction query: {intent.value}")

        account_number = attributes.account_number

        # Get date range with defaults
        from_date = (
            attributes.from_date if attributes.from_date and attributes.from_date.upper() != 'NULL'
            else (datetime.now() - timedelta(days=6)).strftime("%Y%m%d 00:00:00")
        )
        to_date = (
            attributes.to_date if attributes.to_date and attributes.to_date.upper() != 'NULL'
            else datetime.now().strftime("%Y%m%d 23:59:59")
        )

        LOGGER.info(f"Account: {account_number}, Date range: {from_date} to {to_date}")

        # Fetch transactions
        api_response = await self.balance_api.fetch_transactions(
            account_number=account_number,
            from_date=from_date,
            to_date=to_date,
            limit=limit
        )

        if "error" in api_response:
            error_msg = api_response.get("error", "Không thể lấy thông tin giao dịch")
            LOGGER.error(f"API Error: {error_msg}")
            async for chunk in self._generate_error_response(error_msg):
                yield chunk
            return

        # Build context for LLM
        transactions = api_response.get("transactions", [])
        display_name = self._get_display_name(user_name)
        used_defaults = not (attributes.from_date and attributes.to_date)
        date_range_desc = "7 ngày gần nhất" if used_defaults else f"từ {from_date} đến {to_date}"
        criteria = self._build_filtering_criteria(intent, attributes)

        context = {
            'user_name': display_name,
            'account_number': account_number,
            'query': enhanced_query,
            'intent_type': intent.value,
            'current_datetime': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'date_range_desc': date_range_desc,
            'transaction_count': len(transactions),
            'original_count': len(transactions),
            'used_defaults': "Có" if used_defaults else "Không",
            'filtering_criteria': json.dumps(criteria, ensure_ascii=False) if criteria else "Không có điều kiện lọc",
            'transactions_data': json.dumps(transactions, ensure_ascii=False)
        }

        async for chunk in self.llm_service.llm_stream(
                inputs=context,
                prompt_template=lf.get_prompt("BEECHAT_KHCN_UNIFIED_TRANSACTION_ANALYSIS_PROMPT"),
                sleep=0.0001,
                temperature=0,
                max_tokens=100000,
                timeout=180
        ):
            chunk_dict = chunk.model_dump()
            chunk_dict["status_code"] = 200
            chunk_dict["status_message"] = "Success!"
            chunk_dict["intent"] = intent.value
            yield ChatCompletionChunk(**chunk_dict)

    async def _generate_unrecognized_query_response(
            self,
            enhanced_query: str,
            user_name: Optional[str] = None
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Handle unrecognized transaction queries."""
        LOGGER.info("Processing unrecognized transaction query")

        context = {
            "user_query": enhanced_query,
            "friendly_name": self._get_display_name(user_name)
        }

        async for chunk in self.llm_service.llm_stream(
                inputs=context,
                prompt_template=lf.get_prompt("BEECHAT_KHCN_UNRECOGNIZED_TRANSACTION_ANALYSIS_PROMPT"),
                sleep=0.01
        ):
            chunk_dict = chunk.model_dump()
            chunk_dict["status_code"] = 200
            chunk_dict["status_message"] = "Unrecognized Transaction Query"
            chunk_dict["intent"] = "unrecognized_transaction_query"
            yield ChatCompletionChunk(**chunk_dict)

    async def _generate_menu_response(
            self,
            menu_type: str,
            enhanced_query: str,
            user_name: Optional[str] = None
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Generate menu response."""
        LOGGER.info(f"Generating {menu_type} response")

        context = {"user_name": self._get_display_name(user_name)}

        async for chunk in self.llm_service.llm_stream(
                inputs=context,
                prompt_template=lf.get_prompt("BEECHAT_KHCN_BALANCE_RETRIEVE_MENU_PROMPT")
        ):
            chunk_dict = chunk.model_dump()
            chunk_dict["status_code"] = 200
            chunk_dict["status_message"] = "Success!"
            chunk_dict["intent"] = menu_type
            yield ChatCompletionChunk(**chunk_dict)

    async def _generate_account_selection_response(
            self,
            user_name: Optional[str] = None,
            session_id: Optional[str] = None
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Generate unified account selection response."""
        LOGGER.info("Generating unified account selection")

        # Check for invalid account scenario
        if session_id and self.user_profile_service:
            account_list = self.user_profile_service.get_sorted_user_accounts(session_id)
            account_number = getattr(self, '_invalid_account_context', None)

            if account_number and account_list and account_number not in account_list:
                LOGGER.info(f"Handling invalid account selection: {account_number}")

                accounts_display = self._format_accounts_display(account_list)

                invalid_prompt_content = await self.llm_service.llm_task(
                    inputs={
                        'invalid_account': account_number,
                        'accounts_list': accounts_display
                    },
                    prompt_template=lf.get_prompt("BEECHAT_KHCN_BALANCE_INVALID_ACCOUNT_SELECTION_PROMPT"),
                    use_primary=False
                )

                async for chunk in self.llm_service.llm_stream(
                        inputs={},
                        prompt_template=f"Display this content exactly as provided:\n\n{invalid_prompt_content}",
                        temperature=0.0,
                        sleep=0.01
                ):
                    chunk_dict = chunk.model_dump()
                    chunk_dict["status_code"] = 200
                    chunk_dict["status_message"] = "Invalid Account Selection"
                    chunk_dict["intent"] = "account_selection"
                    chunk_dict["require_reselection"] = True
                    yield ChatCompletionChunk(**chunk_dict)
                return

        # Normal account selection flow
        context = {"user_name": self._get_display_name(user_name)}

        async for chunk in self.llm_service.llm_stream(
                inputs=context,
                prompt_template=lf.get_prompt("BEECHAT_KHCN_BALANCE_ACCOUNT_SELECTION_PROMPT")
        ):
            chunk_dict = chunk.model_dump()
            chunk_dict["status_code"] = 200
            chunk_dict["status_message"] = "Success!"
            chunk_dict["intent"] = "account_selection"
            yield ChatCompletionChunk(**chunk_dict)

    # ==================== DEPOSIT DOMAIN HELPERS ====================

    def _build_deposit_context(
            self,
            intent: DepositIntent,
            enhanced_query: str,
            attributes,
            documents_text: str,
            is_pre_opening: bool = True
    ) -> tuple:
        """Build unified context for deposit intents."""
        base_context = {
            "intent": intent.value,
            "intent_display_name": intent.value.replace('_', ' ').title(),
            "query": enhanced_query,
            "question": enhanced_query,
            "documents": documents_text,
        }

        if is_pre_opening:
            if attributes:
                attrs_info = ", ".join([
                    f"Số tiền: {getattr(attributes, 'amount', 'N/A'):,.0f} VND" if getattr(attributes, 'amount',
                                                                                           None) else "",
                    f"Kỳ hạn: {getattr(attributes, 'term', 'N/A')}" if getattr(attributes, 'term', None) else "",
                    f"Loại sản phẩm: {getattr(attributes, 'product_type', 'N/A').value}" if getattr(attributes,
                                                                                                    'product_type',
                                                                                                    None) else ""
                ]).strip(', ') or "Chưa có thông tin chi tiết"

                base_context["attributes_info"] = attrs_info
                prompt_template = lf.get_prompt("BEECHAT_KHCN_ACTION_WITH_ATTRIBUTES_PROMPT")
            else:
                prompt_template = lf.get_prompt("BEECHAT_KHCN_PRE_OPENING_INFORMATION_PROMPT")
        else:
            base_context["account_info"] = "Thông tin tài khoản khách hàng"
            prompt_template = lf.get_prompt("BEECHAT_KHCN_ACCOUNT_MANAGEMENT_PROMPT")

        return base_context, prompt_template

    # ==================== UTILITY METHODS ====================

    def _apply_smart_defaults_to_attributes(self, attributes: BalanceAttributes, intent: BalanceIntent) -> None:
        """Apply smart defaults to avoid unnecessary missing attributes."""
        date_required_intents = {
            BalanceIntent.QUERY_TRANSACTION_NORMAL,
            BalanceIntent.QUERY_TRANSACTION_DESCRIPTIVE,
            BalanceIntent.QUERY_TRANSACTION_BY_TYPE,
            BalanceIntent.QUERY_TRANSACTION_BY_AMOUNT,
            BalanceIntent.QUERY_TRANSACTION_BY_BENEFICIARY,
            BalanceIntent.QUERY_TRANSACTION_BY_CHANNEL,
            BalanceIntent.QUERY_TRANSACTION_MULTI_CONDITIONS,
        }

        if intent in date_required_intents:
            if not attributes.from_date:
                attributes.from_date = BalanceValidationUtils._get_default_from_date()
            if not attributes.to_date:
                attributes.to_date = BalanceValidationUtils._get_default_to_date()

    def _build_filtering_criteria(self, intent: BalanceIntent, attributes: BalanceAttributes) -> Dict:
        """Build filtering criteria for API calls."""
        criteria = {}

        if getattr(attributes, 'min_amount', None) is not None:
            criteria['min_amount'] = attributes.min_amount
        if getattr(attributes, 'max_amount', None) is not None:
            criteria['max_amount'] = attributes.max_amount
        if getattr(attributes, 'transaction_type', None):
            criteria['transaction_type'] = attributes.transaction_type
        if getattr(attributes, 'beneficiary_name', None):
            criteria['beneficiary_name'] = attributes.beneficiary_name

        return criteria

    def _format_accounts_display(self, accounts: List[str]) -> str:
        """Format account list for display."""
        if not accounts:
            return "Không có tài khoản khả dụng"

        return "\n".join([
            f"{i}. **{account}** (TK{i})"
            for i, account in enumerate(sorted(accounts), 1)
        ])

    async def _generate_error_response(self, error_message: str) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Generate error response with intelligent error processing."""
        try:
            LOGGER.error(f"Generating error response: {error_message}")

            ERROR_PROMPT = """
            🎯 VAI TRÒ: Mister Bụt - Hỗ trợ xử lý lỗi thông minh
        
            NHIỆM VỤ: Thông báo chính xác lỗi gặp phải
        
            NGUYÊN TẮC:
            - Giữ thông tin lỗi chính xác nhưng dễ hiểu
            - Tông giọng đồng cảm, không gây lo lắng
            - Kết thúc bằng câu hỏi hỗ trợ tiếp theo
            Lỗi gốc: {error_message}
            Hãy trả về phản hồi thân thiện và hướng dẫn cụ thể cho khách hàng.
            """

            async for chunk in self.llm_service.llm_stream(
                    inputs={"error_message": error_message},
                    prompt_template=ERROR_PROMPT
            ):
                chunk_dict = chunk.model_dump()
                chunk_dict["status_code"] = 500
                chunk_dict["status_message"] = "api_error"
                yield ChatCompletionChunk(**chunk_dict)

        except Exception as e:
            LOGGER.error(f"Failed to generate smart error response: {str(e)}")
            fallback_chunk = ChatCompletionChunk(
                choices=[{
                    "delta": {"content": self.TECHNICAL_ERROR_MESSAGE},
                    "finish_reason": None
                }],
                status_code=500,
                status_message="critical_error"
            )
            yield fallback_chunk
