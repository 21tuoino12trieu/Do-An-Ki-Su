"""
Unified Information Collector - Thu thập attribute cho tất cả domains.

Enhanced version with simplified logic and better error handling.
Centralized attribute collection service thay thế logic phân tán.
"""

from typing import Dict, List, Optional, Union, Tuple
from dataclasses import dataclass

from beechat_khcn.models.conversation_model import DepositIntent
from beechat_khcn.models.deposit_model import DepositAttributes
from beechat_khcn.models.balance_retrieve_model import (
    BalanceIntent,
    BalanceAttributes,
    get_intent_requirements,
    validate_balance_request,
    create_empty_balance_attributes,
)
from beechat_khcn.models.loan_management_model import (
    LoanManagementIntent,
    LoanManagementAttributes,
    create_empty_loan_management_attributes,
    LoanManagementValidationUtils
)
from beechat_khcn.models.topic_model import TopicCategory
from beechat_khcn.models.total_revenue_model import (
    TotalRevenueIntent,
    TotalRevenueAttributes,
    create_empty_total_revenue_attributes,
    TotalRevenueValidationUtils
)
from beegen_v1.parser.implementations.xml import XMLOutputParser
from beegenerate.loggings import LOGGER
from beegenerate.loggings.loggers import lf


@dataclass
class CollectionResult:
    """Result of attribute collection process."""
    status: str  # "complete", "collecting", "error"
    attributes: Optional[Union[DepositAttributes, BalanceAttributes, TotalRevenueAttributes, LoanManagementAttributes]] = None
    collection_question: Optional[str] = None
    missing_attributes: List[str] = None
    should_proceed: bool = False
    error_message: Optional[str] = None


class AttributeRequirement:
    """Định nghĩa requirements cho từng intent."""

    DEPOSIT_REQUIREMENTS = {
        DepositIntent.CALCULATE_INTEREST: ['amount', 'term', 'product_type'],
        DepositIntent.OPEN_SAVING_ACCOUNT: ['amount', 'term', 'product_type'],
        DepositIntent.REQUEST_PERSONALIZED_RECOMMENDATION: ['amount', 'preferred_term_range'],
        DepositIntent.INQUIRE_MATURITY_DATE: ['saving_account_name'],
        DepositIntent.CHECK_ACCOUNT_BALANCE: ['saving_account_name'],
        DepositIntent.CHECK_INTEREST_EARNED: ['saving_account_name'],
        DepositIntent.WITHDRAW_PRINCIPAL: ['saving_account_name'],
        DepositIntent.CHANGE_INTEREST_PAYOUT_METHOD: ['saving_account_name'],
        DepositIntent.TERMINATE_EARLY: ['saving_account_name'],
        DepositIntent.MAKE_ADDITIONAL_DEPOSIT: ['saving_account_name'],
        DepositIntent.MATURITY_NOTIFICATION: ['saving_account_name'],
        DepositIntent.WITHDRAW_PRINCIPAL_INTEREST: ['saving_account_name'],
        DepositIntent.REQUEST_REINVESTMENT_OPTIONS: ['saving_account_name'],
        DepositIntent.INQUIRE_INTEREST_RATES: [],
        DepositIntent.INQUIRE_SAVING_ACCOUNT_TYPES: [],
        DepositIntent.ELIGIBILITY_CRITERIA: [],
        DepositIntent.PROMOTION_INQUIRY: [],
        DepositIntent.COMPARE_PRODUCTS: [],
    }

    TOTAL_REVENUE_REQUIREMENTS = {
        TotalRevenueIntent.GET_TOTAL_ASSETS: ['customer_code'],
        TotalRevenueIntent.GET_NET_WORTH: ['customer_code'],
        TotalRevenueIntent.GET_INCOME_PROJECTION: ['customer_code'],
        TotalRevenueIntent.GET_TOTAL_DEBT: ['customer_code'],
        TotalRevenueIntent.TRIGGER_ASSET_SUMMARY_NOTIFICATION: [],
    }

    LOAN_MANAGEMENT_REQUIREMENTS = {
        LoanManagementIntent.GET_ALL_LD: ['customer_code'],
        LoanManagementIntent.GET_LD_INFO: ['customer_code', 'loan_id'],
        LoanManagementIntent.GET_LD_PAYMENT_SCHEDULE: ['customer_code', 'loan_id'],
        LoanManagementIntent.GET_TOTAL_OVERDUE_DEBT: ['customer_code'],
        LoanManagementIntent.GET_LD_PAYMENT_HISTORY: ['customer_code', 'loan_id'],
        LoanManagementIntent.GET_LD_ADDITIONAL_LOAN_AMOUNT: ['customer_code'],
        LoanManagementIntent.GET_AC_OVERDRAFT_LIST: ['customer_code'],
        LoanManagementIntent.OUT_OF_SCOPE: [],
    }

    @classmethod
    def get_required_attributes(
        cls,
        intent: Union[DepositIntent, BalanceIntent, TotalRevenueIntent, LoanManagementIntent],
        topic: TopicCategory
    ) -> List[str]:
        """Get required attributes for intent."""
        if topic == TopicCategory.DEPOSIT and isinstance(intent, DepositIntent):
            return cls.DEPOSIT_REQUIREMENTS.get(intent, [])
        elif topic == TopicCategory.BALANCE_RETRIEVE and isinstance(intent, BalanceIntent):
            return get_intent_requirements(intent)
        elif topic == TopicCategory.TOTAL_REVENUE and isinstance(intent, TotalRevenueIntent):
            return cls.TOTAL_REVENUE_REQUIREMENTS.get(intent, [])
        elif topic == TopicCategory.LOAN_MANAGEMENT and isinstance(intent, LoanManagementIntent):
            return cls.LOAN_MANAGEMENT_REQUIREMENTS.get(intent, [])
        return []


class UnifiedInformationCollector:
    """Centralized attribute collection service."""

    def __init__(self, llm_service, session_manager):
        """Initialize the information collector with required services."""
        self.llm_service = llm_service
        self.session_manager = session_manager
        self.xml_parser = XMLOutputParser()
        self._current_session_id = None
        self._user_profile_service = None
        self.balance_coordinator = None
        self.total_revenue_coordinator = None
        self.loan_management_coordinator = None
        LOGGER.info("UnifiedInformationCollector initialized")

    # ===== DEPENDENCY INJECTION METHODS =====

    def set_total_revenue_coordinator(self, total_revenue_coordinator) -> None:
        """Set total revenue coordinator reference from external injection."""
        self.total_revenue_coordinator = total_revenue_coordinator
        LOGGER.info("Total revenue coordinator injected")

    def set_loan_management_coordinator(self, loan_management_coordinator) -> None:
        """Set loan management coordinator reference from external injection."""
        self.loan_management_coordinator = loan_management_coordinator
        LOGGER.info("Loan management coordinator injected")

    def set_user_profile_service(self, user_profile_service) -> None:
        """Set user profile service reference."""
        self._user_profile_service = user_profile_service

    def set_balance_coordinator(self, balance_coordinator) -> None:
        """Set balance coordinator reference from external injection."""
        self.balance_coordinator = balance_coordinator

    # ===== MAIN COLLECTION METHODS =====

    async def collect_all_required_attributes(
        self,
        enhanced_query: str,
        intent: Union[DepositIntent, BalanceIntent, TotalRevenueIntent, LoanManagementIntent],
        topic: TopicCategory,
        session_id: str
    ) -> CollectionResult:
        """Collect all required attributes với complete flow."""
        self._current_session_id = session_id

        attrs = await self._extract_attributes_by_topic(enhanced_query, intent, topic)
        missing_attrs = self._find_missing_attributes(attrs, intent, topic)

        if missing_attrs:
            collection_question = await self._generate_collection_question(
                intent, missing_attrs, topic, attrs
            )
            self._save_collection_state(session_id, intent, topic, missing_attrs,
                                        AttributeRequirement.get_required_attributes(intent, topic),
                                        attrs, collection_question, 0)

            return CollectionResult(
                status="collecting",
                collection_question=collection_question,
                missing_attributes=missing_attrs,
                should_proceed=False
            )

        return CollectionResult(
            status="complete",
            attributes=attrs,
            should_proceed=True
        )

    async def continue_collection(self, enhanced_query: str, session_id: str) -> CollectionResult:
        """Continue collection process with new input from user."""
        collection_state = self.session_manager.get_collection_state(session_id)
        if not collection_state:
            LOGGER.warning("No collection state found")
            return CollectionResult(status="error", error_message="No active collection")

        intent, topic = self._reconstruct_intent_topic(collection_state)
        if intent is None or topic is None:
            LOGGER.error("Failed to reconstruct intent/topic from state")
            return CollectionResult(status="error", error_message="Invalid collection state")

        self._current_session_id = session_id

        new_attrs = await self._extract_attributes_by_topic(enhanced_query, intent, topic)
        current_attrs = self._reconstruct_attributes(collection_state.get('current_attributes', {}), topic)
        merged_attrs = self._merge_attributes(current_attrs, new_attrs, topic)

        missing_attrs = self._find_missing_attributes(merged_attrs, intent, topic)
        attempts = collection_state.get('attempts', 0) + 1

        if not missing_attrs or attempts >= 3:
            self.session_manager.clear_collection_state(session_id)
            status_msg = "completed" if not missing_attrs else "attempts limit reached"
            LOGGER.info(f"Collection {status_msg} for {intent}")

            return CollectionResult(
                status="complete",
                attributes=merged_attrs,
                should_proceed=True
            )

        collection_question = await self._generate_collection_question(
            intent, missing_attrs, topic, merged_attrs
        )

        self._save_collection_state(session_id, intent, topic, missing_attrs,
                                    collection_state['required_attributes'],
                                    merged_attrs, collection_question, attempts)

        LOGGER.info(f"Continue collection - still missing: {missing_attrs}")
        return CollectionResult(
            status="collecting",
            collection_question=collection_question,
            missing_attributes=missing_attrs,
            should_proceed=False
        )

    # ===== ATTRIBUTE EXTRACTION METHODS =====

    async def _extract_attributes_by_topic(
        self,
        enhanced_query: str,
        intent: Union[DepositIntent, BalanceIntent, TotalRevenueIntent, LoanManagementIntent],
        topic: TopicCategory
    ) -> Union[DepositAttributes, BalanceAttributes, TotalRevenueAttributes, LoanManagementAttributes]:
        """Extract attributes based on topic with unified approach."""
        if topic == TopicCategory.TOTAL_REVENUE:
            return await self._extract_total_revenue_attributes(enhanced_query, intent)
        elif topic == TopicCategory.LOAN_MANAGEMENT:
            return await self._extract_loan_management_attributes(enhanced_query, intent)
        elif topic == TopicCategory.BALANCE_RETRIEVE:
            return await self._extract_balance_attributes(enhanced_query, intent)
        elif topic == TopicCategory.DEPOSIT:
            return await self._extract_deposit_attributes(enhanced_query, intent)

        # Default fallback - create empty attributes
        if topic == TopicCategory.DEPOSIT:
            return DepositAttributes()
        elif topic == TopicCategory.BALANCE_RETRIEVE:
            return create_empty_balance_attributes()
        elif topic == TopicCategory.TOTAL_REVENUE:
            return create_empty_total_revenue_attributes()
        elif topic == TopicCategory.LOAN_MANAGEMENT:
            return create_empty_loan_management_attributes()

        return None

    async def _extract_balance_attributes(self, enhanced_query: str, intent: BalanceIntent) -> BalanceAttributes:
        """Extract balance attributes using enhanced comprehensive prompt."""
        attrs = create_empty_balance_attributes()

        try:
            extracted_account = await self._extract_and_validate_account(enhanced_query)
            time_context = self._get_time_context()

            response = await self.llm_service.llm_task(
                inputs={
                    "text": enhanced_query,
                    "time_context": time_context,
                    "intent": intent.value
                },
                prompt_template=lf.get_prompt("BEECHAT_KHCN_BALANCE_ATTRIBUTE_EXTRACTION_PROMPT"),
                use_primary=False,
                temperature=0
            )

            parsed = await self.xml_parser.parse(text=response)

            if extracted_account:
                attrs.account_number = extracted_account

            self._set_additional_balance_attributes(attrs, parsed)
            LOGGER.info(f"Extracted balance attributes: account={attrs.account_number}")

        except Exception as e:
            LOGGER.warning(f"Failed to extract balance attributes: {e}")
            if self._current_session_id and self._user_profile_service:
                available_accounts = self._user_profile_service.get_sorted_user_accounts(self._current_session_id)
                if len(available_accounts) == 1:
                    attrs.account_number = available_accounts[0]
                    LOGGER.info(f"Fallback: auto-select single account: {available_accounts[0]}")

        return attrs

    async def _extract_total_revenue_attributes(self, enhanced_query: str, intent: TotalRevenueIntent) -> TotalRevenueAttributes:
        """Extract total revenue attributes using LLM extraction."""
        attrs = create_empty_total_revenue_attributes()

        # Check customer_code from user profile first
        profile_customer_code = self._get_customer_code_from_profile()
        if profile_customer_code:
            attrs.customer_code = profile_customer_code
            LOGGER.info(f"Customer code found in profile: {profile_customer_code}")
            return attrs

        # Use LLM extraction if not found in profile
        try:
            response = await self.llm_service.llm_task(
                inputs={"enhanced_query": enhanced_query},
                prompt_template=lf.get_prompt("BEECHAT_KHCN_TOTAL_REVENUE_ATTRIBUTE_EXTRACTION_PROMPT"),
                use_primary=False,
                temperature=0
            )

            parsed = await self.xml_parser.parse(text=response)
            parsed_customer_code = parsed.get('customer_code')

            if parsed_customer_code and parsed_customer_code != 'null':
                attrs.customer_code = parsed_customer_code
                LOGGER.info(f"Customer code extracted from LLM: {parsed_customer_code}")

        except Exception as e:
            LOGGER.warning(f"Failed to extract total revenue attributes: {e}")

        return attrs

    async def _extract_loan_management_attributes(self, enhanced_query: str, intent: LoanManagementIntent) -> LoanManagementAttributes:
        """Extract loan management attributes using LLM extraction."""
        attrs = create_empty_loan_management_attributes()

        # Check customer_code from user profile first
        profile_customer_code = self._get_customer_code_from_profile()
        if profile_customer_code:
            attrs.customer_code = profile_customer_code
            LOGGER.info(f"Customer code found in profile: {profile_customer_code}")

        try:
            response = await self.llm_service.llm_task(
                inputs={"enhanced_query": enhanced_query},
                prompt_template=lf.get_prompt("BEECHAT_KHCN_LOAN_MANAGEMENT_ATTRIBUTE_EXTRACTION_PROMPT"),
                use_primary=False,
                temperature=0
            )

            parsed = await self.xml_parser.parse(text=response)

            # Extract customer_code (only if not already set from profile)
            if not attrs.customer_code:
                parsed_customer_code = parsed.get('customer_code')
                if parsed_customer_code and parsed_customer_code != 'null':
                    attrs.customer_code = parsed_customer_code
                    LOGGER.info(f"Customer code extracted from LLM: {parsed_customer_code}")

            # Extract loan_id
            parsed_loan_id = parsed.get('loan_id')
            if parsed_loan_id and parsed_loan_id != 'null':
                attrs.loan_id = parsed_loan_id
                LOGGER.info(f"Loan ID extracted from LLM: {parsed_loan_id}")

            if parsed.get('from_date'):
                attrs.from_date = parsed.get('from_date')

            if parsed.get('to_date'):
                attrs.to_date = parsed.get('to_date')

        except Exception as e:
            LOGGER.warning(f"Failed to extract loan management attributes: {e}")

        return attrs

    async def _extract_deposit_attributes(self, enhanced_query: str, intent: DepositIntent) -> DepositAttributes:
        """Extract deposit attributes using deposit prompt."""
        attrs = DepositAttributes()

        try:
            response = await self.llm_service.llm_task(
                inputs={"query": enhanced_query, "intent": intent.value},
                prompt_template=lf.get_prompt("BEECHAT_KHCN_DEPOSIT_ATTRIBUTE_EXTRACTION_PROMPT"),
                use_primary=False,
                temperature=0
            )

            parsed = await self.xml_parser.parse(text=response)

            # Parse numeric amount safely
            if parsed.get('amount') and parsed['amount'] != 'null':
                try:
                    attrs.amount = float(parsed['amount'].replace(',', '').replace('.', ''))
                except (ValueError, AttributeError):
                    pass

            # Parse string attributes
            for attr in ['product_type', 'term', 'saving_account_name']:
                if parsed.get(attr) and parsed[attr] != 'null':
                    setattr(attrs, attr, parsed[attr])

        except Exception as e:
            LOGGER.warning(f"Failed to extract deposit attributes: {e}")

        return attrs

    # ===== COLLECTION QUESTION GENERATION =====

    async def _generate_collection_question(
        self,
        intent: Union[DepositIntent, BalanceIntent, TotalRevenueIntent, LoanManagementIntent],
        missing_attrs: List[str],
        topic: TopicCategory,
        current_attrs: Union[DepositAttributes, BalanceAttributes, TotalRevenueAttributes, LoanManagementAttributes]
    ) -> str:
        """Generate collection question for missing attributes."""
        if topic == TopicCategory.BALANCE_RETRIEVE and 'account_number' in missing_attrs:
            return await self._generate_balance_account_question()

        # Format current attributes inline
        current_attributes_str = "Chưa có thông tin"
        if current_attrs and hasattr(current_attrs, 'to_dict'):
            attrs_dict = current_attrs.to_dict()
            formatted = [f"{key}: {value}" for key, value in attrs_dict.items() if value is not None and value != ""]
            current_attributes_str = "; ".join(formatted) if formatted else "Chưa có thông tin"

        response = await self.llm_service.llm_task(
            inputs={
                "intent": intent.value if hasattr(intent, 'value') else str(intent),
                "missing_attributes": ', '.join(missing_attrs),
                "topic": topic.value,
                "current_attributes": current_attributes_str
            },
            prompt_template=lf.get_prompt("BEECHAT_KHCN_COMPREHENSIVE_COLLECTION_QUESTION_PROMPT"),
            use_primary=False,
            temperature=0
        )

        return response if response else "Vui lòng cung cấp thêm thông tin."

    async def _generate_balance_account_question(self) -> str:
        """Generate balance-specific account selection question."""
        if not self._current_session_id or not self._user_profile_service:
            return "Vui lòng cung cấp số tài khoản cần tra cứu."

        available_accounts = self._user_profile_service.get_sorted_user_accounts(self._current_session_id)
        if not available_accounts:
            return "Không tìm thấy tài khoản khả dụng. Vui lòng cung cấp số tài khoản."

        # Format accounts list as buttons
        accounts_list = ""
        for i, account in enumerate(available_accounts, 1):
            accounts_list += f'<button value="{account}">{account}({i})</button>\n'

        try:
            response = await self.llm_service.llm_task(
                inputs={"accounts_list": accounts_list.strip()},
                prompt_template=lf.get_prompt("BEECHAT_KHCN_BALANCE_ACCOUNT_SELECTION_PROMPT"),
                use_primary=False,
                temperature=0
            )

            return response

        except Exception as e:
            LOGGER.warning(f"Failed to generate account question: {e}")
            account_list = "\n".join([f"{i}. {account}" for i, account in enumerate(available_accounts, 1)])
            return f"Vui lòng chọn tài khoản cần tra cứu:\n{account_list}\n\nBạn có thể trả lời bằng số thứ tự hoặc tên tài khoản."

    # ===== VALIDATION AND UTILITY METHODS =====

    def _find_missing_attributes(
        self,
        attrs: Union[DepositAttributes, BalanceAttributes, TotalRevenueAttributes, LoanManagementAttributes],
        intent: Union[DepositIntent, BalanceIntent, TotalRevenueIntent, LoanManagementIntent],
        topic: TopicCategory
    ) -> List[str]:
        """Find missing attributes using model validation methods."""
        if topic == TopicCategory.BALANCE_RETRIEVE and isinstance(attrs, BalanceAttributes):
            if attrs.account_number and self._current_session_id and self._user_profile_service:
                available_accounts = self._user_profile_service.get_sorted_user_accounts(self._current_session_id)
                if available_accounts and attrs.account_number not in available_accounts:
                    LOGGER.warning(f"Account {attrs.account_number} not in valid list")
                    attrs.account_number = None

            validation_result = validate_balance_request(attrs, intent)
            return validation_result.get('missing_attributes', [])

        elif topic == TopicCategory.DEPOSIT and isinstance(attrs, DepositAttributes):
            if hasattr(attrs, 'get_missing_attributes_for_intent'):
                return attrs.get_missing_attributes_for_intent(intent.value)

            required_attrs = AttributeRequirement.get_required_attributes(intent, topic)
            missing = []
            for attr in required_attrs:
                value = getattr(attrs, attr, None)
                if value is None or (isinstance(value, str) and not value.strip()):
                    missing.append(attr)
            return missing

        elif topic == TopicCategory.TOTAL_REVENUE and isinstance(attrs, TotalRevenueAttributes):
            missing = TotalRevenueValidationUtils.get_missing_attributes(attrs, intent)
            LOGGER.info(f"Total revenue missing attributes: {missing}")
            return missing

        elif topic == TopicCategory.LOAN_MANAGEMENT and isinstance(attrs, LoanManagementAttributes):
            missing = LoanManagementValidationUtils.get_missing_attributes(attrs, intent)
            LOGGER.info(f"Loan management missing attributes: {missing}")
            return missing

        return []

    def _merge_attributes(
        self,
        current_attrs: Union[DepositAttributes, BalanceAttributes, TotalRevenueAttributes, LoanManagementAttributes],
        new_attrs: Union[DepositAttributes, BalanceAttributes, TotalRevenueAttributes, LoanManagementAttributes],
        topic: TopicCategory
    ) -> Union[DepositAttributes, BalanceAttributes, TotalRevenueAttributes, LoanManagementAttributes]:
        """Merge current and new attributes with new values taking precedence."""
        current_dict = current_attrs.to_dict() if hasattr(current_attrs, 'to_dict') else {}
        new_dict = new_attrs.to_dict() if hasattr(new_attrs, 'to_dict') else {}

        merged_dict = current_dict.copy()
        for key, value in new_dict.items():
            if value is not None:
                merged_dict[key] = value

        return self._reconstruct_attributes(merged_dict, topic)

    def _reconstruct_attributes(
        self,
        attrs_dict: Dict,
        topic: TopicCategory
    ) -> Union[DepositAttributes, BalanceAttributes, TotalRevenueAttributes, LoanManagementAttributes]:
        """Convert dictionary back to attributes object."""
        if topic == TopicCategory.DEPOSIT:
            attrs = DepositAttributes()
        elif topic == TopicCategory.BALANCE_RETRIEVE:
            attrs = create_empty_balance_attributes()
        elif topic == TopicCategory.TOTAL_REVENUE:
            attrs = create_empty_total_revenue_attributes()
        elif topic == TopicCategory.LOAN_MANAGEMENT:
            attrs = create_empty_loan_management_attributes()
        else:
            raise ValueError(f"Unknown topic: {topic}")

        for key, value in attrs_dict.items():
            if hasattr(attrs, key) and value is not None:
                setattr(attrs, key, value)

        return attrs

    def _reconstruct_intent_topic(self, collection_state: Dict) -> Tuple[
        Optional[Union[DepositIntent, BalanceIntent, TotalRevenueIntent, LoanManagementIntent]], Optional[TopicCategory]]:
        """Reconstruct intent and topic from collection state"""
        intent_str = collection_state.get('active_intent', '')
        topic_str = collection_state.get('topic', '')

        try:
            if topic_str == 'deposit':
                topic = TopicCategory.DEPOSIT
                intent = DepositIntent(intent_str)
            elif topic_str == 'balance_retrieve':
                topic = TopicCategory.BALANCE_RETRIEVE
                intent = BalanceIntent(intent_str)
            elif topic_str == 'total_revenue':
                topic = TopicCategory.TOTAL_REVENUE
                intent = TotalRevenueIntent(intent_str)
            elif topic_str == 'loan_management':
                topic = TopicCategory.LOAN_MANAGEMENT
                intent = LoanManagementIntent(intent_str)
            else:
                LOGGER.error(f"Unknown topic: {topic_str}")
                return None, None

            return intent, topic
        except ValueError as e:
            LOGGER.error(f"Intent reconstruction failed: {e}")
            return None, None

    def _set_additional_balance_attributes(self, attrs: BalanceAttributes, parsed: Dict) -> None:
        """Set additional balance attributes from parsed data with safe assignment."""
        # Set string attributes safely
        string_attrs = ['transaction_type', 'beneficiary_name', 'channel', 'export_format']
        for attr in string_attrs:
            if parsed.get(attr) and parsed[attr] != 'null':
                setattr(attrs, attr, parsed[attr].strip())

        # Set numeric attributes safely
        for attr in ['min_amount', 'max_amount']:
            if parsed.get(attr) and parsed[attr] != 'null':
                try:
                    amount_str = str(parsed[attr]).replace(',', '').replace('.', '').strip()
                    if amount_str.isdigit():
                        setattr(attrs, attr, float(amount_str))
                except (ValueError, TypeError) as e:
                    LOGGER.debug(f"Failed to parse {attr}: {parsed[attr]}, error: {e}")

    def _save_collection_state(
        self,
        session_id: str,
        intent: Union[DepositIntent, BalanceIntent, TotalRevenueIntent, LoanManagementIntent],
        topic: TopicCategory,
        missing_attrs: List[str],
        required_attrs: List[str],
        current_attrs: Union[DepositAttributes, BalanceAttributes, TotalRevenueAttributes, LoanManagementAttributes],
        collection_question: str,
        attempts: int
    ) -> None:
        """Save collection state to session manager."""
        state = {
            'active_intent': intent.value if hasattr(intent, 'value') else str(intent),
            'topic': topic.value,
            'missing_attributes': missing_attrs,
            'required_attributes': required_attrs,
            'current_attributes': current_attrs.to_dict() if hasattr(current_attrs, 'to_dict') else {},
            'collection_question': collection_question,
            'attempts': attempts
        }

        self.session_manager.save_collection_state(session_id, state)

    # ===== HELPER METHODS =====

    def _get_customer_code_from_profile(self) -> Optional[str]:
        """Get customer code from user profile if available."""
        if self._current_session_id and self._user_profile_service:
            if self._user_profile_service.has_customer_code(self._current_session_id):
                return self._user_profile_service.get_customer_code(self._current_session_id)
        return None

    def _get_time_context(self) -> Dict:
        """Get time context from coordinator or generate default."""
        if self.balance_coordinator and hasattr(self.balance_coordinator, 'get_current_time_context'):
            return self.balance_coordinator.get_current_time_context()

        from datetime import datetime
        current_time = datetime.now()
        return {'current_time': current_time.strftime("%Y-%m-%d %H:%M:%S")}

    async def _extract_and_validate_account(self, enhanced_query: str) -> Optional[str]:
        """
        Extract and validate account - CHỈ 2 PATHS:
        Path 1: Auto-select khi có 1 account
        Path 2: LLM extraction
        """
        available_accounts = []

        if self._current_session_id and self._user_profile_service:
            available_accounts = self._user_profile_service.get_sorted_user_accounts(self._current_session_id)

        # PATH 1: Auto-select single account
        if len(available_accounts) == 1:
            extracted_account = available_accounts[0]
            LOGGER.info(f"Auto-select single account: {extracted_account}")
            return extracted_account

        # PATH 2: LLM extraction
        if self.balance_coordinator:
            try:
                extracted_account = await self.balance_coordinator.extract_account_from_enhanced_query_unified(
                    enhanced_query, self._current_session_id
                )

                if extracted_account and available_accounts and extracted_account not in available_accounts:
                    LOGGER.warning(f"Extracted account {extracted_account} not in account list")
                    return None

                return extracted_account
            except Exception as e:
                LOGGER.error(f"Error in balance coordinator extraction: {e}")
                return None

        # No balance_coordinator available
        LOGGER.warning("balance_coordinator is None, cannot extract account via LLM")
        return None