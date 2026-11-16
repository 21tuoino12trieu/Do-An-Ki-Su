"""
Unified Attribute Coordinator - Tích hợp logic từ BalanceAttributeCoordinator và TotalRevenueAttributeCoordinator
Centralized logic cho tất cả attribute operations across domains
"""

from typing import Dict, List, Optional, Tuple, Any, Union
from datetime import datetime, timedelta
import re

from beechat_khcn.models.balance_retrieve_model import (
    BalanceAttributes, BalanceIntent, create_empty_balance_attributes, BalanceValidationUtils
)
from beechat_khcn.models.loan_management_model import LoanManagementIntent, LoanManagementAttributes, \
    create_empty_loan_management_attributes, LoanManagementValidationUtils
from beechat_khcn.models.total_revenue_model import (
    TotalRevenueAttributes, TotalRevenueIntent, create_empty_total_revenue_attributes, TotalRevenueValidationUtils
)
from beechat_khcn.prompts.balance_retrieve_prompt import BALANCE_DATE_PARSING_PROMPT, BALANCE_ACCOUNT_SELECTION_PROMPT
from beegenerate.loggings import LOGGER
from beegenerate.loggings.loggers import lf


class UnifiedAttributeCoordinator:
    """TRUNG TÂM điều phối UNIFIED cho tất cả attribute operations"""

    _ACCOUNT_PATTERNS = [
        (re.compile(r'tài khoản\s+(\d{10,15})', re.IGNORECASE), 'full_account'),
        (re.compile(r'(?:cho|TK|tk)\s*(\d+)', re.IGNORECASE), 'reference'),
        (re.compile(r'\b(\d{10,15})\b'), 'direct_number')
    ]

    _DATE_PATTERN = re.compile(r'<from_date>(?P<from>.*?)</from_date>.*?<to_date>(?P<to>.*?)</to_date>', re.DOTALL)

    def __init__(self, user_profile_service=None, llm_service=None) -> None:
        self.user_profile_service = user_profile_service
        self.llm_service = llm_service
        LOGGER.info("UnifiedAttributeCoordinator initialized")

    def _get_domain_from_intent(self, intent: Union[BalanceIntent, TotalRevenueIntent, LoanManagementIntent]) -> str:
        """Determine domain from intent type"""
        if isinstance(intent, BalanceIntent):
            return "balance"
        elif isinstance(intent, TotalRevenueIntent):
            return "total_revenue"
        elif isinstance(intent, LoanManagementIntent):
            return "loan_management"
        else:
            raise ValueError(f"Unsupported intent type: {type(intent)}")

    def _route_to_domain_handler(self, method_name: str, domain: str, *args, **kwargs):
        """Route method calls to appropriate domain handler"""
        if domain == "balance":
            return getattr(self, f"_balance_{method_name}")(*args, **kwargs)
        elif domain == "total_revenue":
            return getattr(self, f"_total_revenue_{method_name}")(*args, **kwargs)
        elif domain == "loan_management":
            return getattr(self, f"_loan_management_{method_name}")(*args, **kwargs)
        else:
            raise ValueError(f"Unsupported domain: {domain}")

    def validate_and_prepare_attributes(
            self,
            attributes: Union[BalanceAttributes, TotalRevenueAttributes, LoanManagementAttributes],
            intent: Union[BalanceIntent, TotalRevenueIntent, LoanManagementIntent]
    ) -> Tuple[bool, List[str]]:
        """UNIFIED validation and preparation cho attributes"""
        domain = self._get_domain_from_intent(intent)
        return self._route_to_domain_handler("validate_and_prepare_attributes", domain, attributes, intent)

    def can_proceed_with_intent(
            self,
            attributes: Union[BalanceAttributes, TotalRevenueAttributes, LoanManagementAttributes],
            intent: Union[BalanceIntent, TotalRevenueIntent, LoanManagementIntent]
    ) -> bool:
        """Check if có thể proceed với intent hiện tại"""
        is_valid, missing_attrs = self.validate_and_prepare_attributes(attributes, intent)
        return is_valid and len(missing_attrs) == 0

    def prepare_api_ready_attributes(
            self,
            attributes: Union[BalanceAttributes, TotalRevenueAttributes, LoanManagementAttributes],
            domain: str = None
    ) -> Union[BalanceAttributes, TotalRevenueAttributes, LoanManagementAttributes]:
        """UNIFIED preparation cho API call"""
        if domain is None:
            if isinstance(attributes, BalanceAttributes):
                domain = "balance"
            elif isinstance(attributes, TotalRevenueAttributes):
                domain = "total_revenue"
            elif isinstance(attributes, LoanManagementAttributes):
                domain = "loan_management"
            else:
                raise ValueError(f"Cannot determine domain from attributes type: {type(attributes)}")

        return self._route_to_domain_handler("prepare_api_ready_attributes", domain, attributes)

    def create_response_metadata(
            self,
            intent: Union[BalanceIntent, TotalRevenueIntent, LoanManagementIntent],
            attributes: Union[BalanceAttributes, TotalRevenueAttributes, LoanManagementAttributes]
    ) -> Dict[str, Any]:
        """Create metadata for response generation"""
        domain = self._get_domain_from_intent(intent)
        return self._route_to_domain_handler("create_response_metadata", domain, intent, attributes)

    def _balance_validate_and_prepare_attributes(
            self,
            attributes: BalanceAttributes,
            intent: BalanceIntent
    ) -> Tuple[bool, List[str]]:
        """Balance domain validation logic"""
        if not attributes:
            attributes = create_empty_balance_attributes()

        self._balance_apply_smart_defaults(attributes, intent)
        missing_attrs = BalanceValidationUtils.get_missing_attributes(attributes, intent)

        LOGGER.info(f"Balance attributes validated: intent={intent.value}, missing={len(missing_attrs)}")
        return len(missing_attrs) == 0, missing_attrs

    def _balance_apply_smart_defaults(self, attributes: BalanceAttributes, intent: BalanceIntent) -> None:
        """Apply smart defaults cho date attributes nếu cần"""
        date_required_intents = {
            BalanceIntent.QUERY_TRANSACTION_NORMAL,
            BalanceIntent.QUERY_TRANSACTION_DESCRIPTIVE,
            BalanceIntent.QUERY_TRANSACTION_BY_TYPE,
            BalanceIntent.QUERY_TRANSACTION_BY_AMOUNT,
            BalanceIntent.QUERY_TRANSACTION_BY_BENEFICIARY,
            BalanceIntent.QUERY_TRANSACTION_BY_CHANNEL,
            BalanceIntent.QUERY_TRANSACTION_MULTI_CONDITIONS,
        }

        if intent not in date_required_intents:
            return

        if not attributes.from_date:
            attributes.from_date = BalanceValidationUtils._get_default_from_date()
        if not attributes.to_date:
            attributes.to_date = BalanceValidationUtils._get_default_to_date()

    def _balance_prepare_api_ready_attributes(self, attributes: BalanceAttributes) -> BalanceAttributes:
        """UNIFIED preparation cho API call"""
        if not attributes:
            attributes = create_empty_balance_attributes()

        if attributes.from_date:
            attributes.from_date = self.normalize_date_to_api_format(attributes.from_date, False)
        if attributes.to_date:
            attributes.to_date = self.normalize_date_to_api_format(attributes.to_date, True)

        if not (attributes.from_date and attributes.to_date):
            default_from, default_to = self.get_default_date_range()
            attributes.from_date = attributes.from_date or default_from
            attributes.to_date = attributes.to_date or default_to

        return attributes

    def _balance_create_response_metadata(self, intent: BalanceIntent, attributes: BalanceAttributes) -> Dict[str, Any]:
        """Create metadata for balance response generation"""
        return {
            'intent': intent.value,
            'attributes': attributes.to_dict() if attributes else {},
            'processed_at': datetime.now().isoformat(),
            'domain': 'balance'
        }

    def _total_revenue_validate_and_prepare_attributes(
            self,
            attributes: TotalRevenueAttributes,
            intent: TotalRevenueIntent
    ) -> Tuple[bool, List[str]]:
        """Total revenue domain validation logic"""
        if not attributes:
            attributes = create_empty_total_revenue_attributes()

        is_valid = TotalRevenueValidationUtils.validate_attributes_for_intent(attributes, intent)
        missing_attrs = TotalRevenueValidationUtils.get_missing_attributes(attributes, intent)

        LOGGER.info(f"Total revenue attributes validated: intent={intent.value}, valid={is_valid}")
        return is_valid, missing_attrs

    def _total_revenue_prepare_api_ready_attributes(self, attributes: TotalRevenueAttributes) -> TotalRevenueAttributes:
        """UNIFIED preparation cho API call"""
        if not attributes:
            attributes = create_empty_total_revenue_attributes()
        return attributes

    def _total_revenue_create_response_metadata(
            self,
            intent: TotalRevenueIntent,
            attributes: TotalRevenueAttributes
    ) -> Dict[str, Any]:
        """Create metadata for total revenue response generation"""
        return {
            'intent': intent.value,
            'attributes': attributes.to_dict() if attributes else {},
            'processed_at': datetime.now().isoformat(),
            'domain': 'total_revenue'
        }

    def _loan_management_validate_and_prepare_attributes(
            self,
            attributes: LoanManagementAttributes,
            intent: LoanManagementIntent
    ) -> Tuple[bool, List[str]]:
        """Loan management domain validation logic"""
        if not attributes:
            attributes = create_empty_loan_management_attributes()

        is_valid = LoanManagementValidationUtils.validate_attributes_for_intent(attributes, intent)
        missing_attrs = LoanManagementValidationUtils.get_missing_attributes(attributes, intent)

        LOGGER.info(f"Loan management attributes validated: intent={intent.value}, valid={is_valid}")
        return is_valid, missing_attrs

    def _loan_management_prepare_api_ready_attributes(self, attributes: LoanManagementAttributes) -> LoanManagementAttributes:
        """UNIFIED preparation cho loan management API call"""
        if not attributes:
            attributes = create_empty_loan_management_attributes()
        return attributes

    def _loan_management_create_response_metadata(
            self,
            intent: LoanManagementIntent,
            attributes: LoanManagementAttributes
    ) -> Dict[str, Any]:
        """Create metadata for loan management response generation"""
        return {
            'intent': intent.value,
            'attributes': attributes.to_dict() if attributes else {},
            'processed_at': datetime.now().isoformat(),
            'domain': 'loan_management'
        }

    async def extract_account_from_enhanced_query_unified(
            self,
            enhanced_query: str,
            session_id: Optional[str] = None
    ) -> Optional[str]:
        """Extract account từ enhanced query sử dụng user_profile_service trực tiếp"""
        if not enhanced_query or "account_selection" in enhanced_query.lower():
            return None

        for pattern, pattern_type in self._ACCOUNT_PATTERNS:
            match = pattern.search(enhanced_query)
            if match:
                extracted_account = match.group(1)
                LOGGER.info(f"Extracted account '{extracted_account}' using pattern '{pattern_type}'")

                if session_id and self.user_profile_service:
                    available_accounts = self.get_available_accounts_for_session(session_id)
                    if available_accounts:
                        resolved = self.resolve_account_from_input(extracted_account, available_accounts)
                        if resolved:
                            return resolved
                        else:
                            LOGGER.warning(f"Extracted account '{extracted_account}' not in available accounts")
                            return None

                return extracted_account

        return None

    def get_available_accounts_for_session(self, session_id: str) -> List[str]:
        """Get available accounts cho session từ user_profile_service"""
        if not self.user_profile_service or not session_id:
            return []

        try:
            accounts = self.user_profile_service.get_sorted_user_accounts(session_id)
            return accounts or []
        except Exception as e:
            LOGGER.error(f"Error getting accounts for session {session_id}: {e}")
            return []

    def get_complete_account_context(self, session_id: str) -> Dict[str, Any]:
        """Get complete account context cho session"""
        accounts = self.get_available_accounts_for_session(session_id)

        return {
            'session_id': session_id,
            'has_accounts': len(accounts) > 0,
            'account_count': len(accounts),
            'accounts': accounts,
            'formatted_list': self.format_account_list_for_selection(accounts) if accounts else "Không có tài khoản khả dụ"
        }

    def format_account_list_for_selection(self, accounts: List[str]) -> str:
        """Format account list cho selection display"""
        if not accounts:
            return "Không có tài khoản khả dụ"

        sorted_accounts = sorted(accounts)
        formatted_lines = [f"{i}. **{account}** (TK{i})" for i, account in enumerate(sorted_accounts, 1)]
        return "\n".join(formatted_lines)

    def create_account_mapping(self, accounts: List[str]) -> Dict[str, str]:
        """Create account mapping for input resolution"""
        mapping = {}
        for i, account in enumerate(accounts, 1):
            mapping.update({
                str(i): account,
                f"tk{i}": account,
                f"TK{i}": account,
                f"tài khoản {i}": account
            })
            if len(account) >= 4:
                mapping[account[-4:]] = account

        return mapping

    def resolve_account_from_input(self, user_input: str, available_accounts: List[str]) -> Optional[str]:
        """UNIFIED account resolution từ user input với available accounts"""
        if not user_input or not available_accounts:
            return None

        user_input_clean = user_input.strip().lower()
        LOGGER.info(f"Resolving '{user_input}' against accounts: {available_accounts}")

        if user_input in available_accounts:
            LOGGER.info(f"Direct account match: {user_input}")
            return user_input

        mapping = self.create_account_mapping(available_accounts)
        resolved = mapping.get(user_input_clean)

        if resolved:
            LOGGER.info(f"Mapped '{user_input}' → {resolved}")
            return resolved

        LOGGER.info(f"Could not resolve '{user_input}'")
        return None

    def normalize_date_to_api_format(self, date_input: str, is_end_date: bool = False) -> Optional[str]:
        """Normalize date cho API format: yyyyMMdd HH:mm:ss"""
        if not date_input or date_input.lower() in ['null', 'none', '']:
            return None

        date_input = date_input.strip()

        try:
            from beechat_khcn.models.balance_retrieve_model import BalanceValidationUtils

            parsed_datetime = BalanceValidationUtils._parse_date_flexible(date_input)
            date_part = parsed_datetime.strftime("%Y%m%d")
            time_part = "23:59:59" if is_end_date else "00:00:00"
            api_format = f"{date_part} {time_part}"

            LOGGER.debug(f"Date API format: '{date_input}' → '{api_format}'")
            return api_format

        except Exception as e:
            LOGGER.error(f"Date normalization failed for '{date_input}': {e}")
            return None

    def get_default_date_range(self) -> Tuple[str, str]:
        """Get default date range cho API calls"""
        today = datetime.now()
        from_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        to_date = today.strftime("%Y-%m-%d")
        return from_date, to_date

    def validate_account_number(self, account_number: str, session_id: Optional[str] = None) -> bool:
        """UNIFIED account validation với membership check"""
        if not account_number:
            return False

        format_valid = bool(re.match(r'^\d[\d\s-]{5,}$', account_number) and
                            len(re.sub(r'[\s-]', '', account_number)) >= 6)

        if not format_valid:
            return False

        if session_id and self.user_profile_service:
            available_accounts = self.get_available_accounts_for_session(session_id)
            if available_accounts:
                normalized_input = re.sub(r'[\s-]', '', account_number)
                normalized_available = [re.sub(r'[\s-]', '', acc) for acc in available_accounts]
                return normalized_input in normalized_available

        return True

    def validate_date_format(self, date_str: str) -> bool:
        """UNIFIED date validation"""
        return bool(date_str and self.normalize_date_to_api_format(date_str))

    def get_balance_coordinator_interface(self):
        """Return a compatible interface for balance operations"""
        return BalanceCoordinatorInterface(self)

    def get_total_revenue_coordinator_interface(self):
        """Return a compatible interface for total revenue operations"""
        return TotalRevenueCoordinatorInterface(self)

    def get_loan_management_coordinator_interface(self):
        """Return a compatible interface for loan management operations"""
        return LoanManagementCoordinatorInterface(self)


class BalanceCoordinatorInterface:
    """Backward compatibility interface cho BalanceAttributeCoordinator"""

    def __init__(self, unified_coordinator: UnifiedAttributeCoordinator):
        self.unified_coordinator = unified_coordinator

    def validate_and_prepare_attributes(self, attributes: BalanceAttributes, intent: BalanceIntent):
        return self.unified_coordinator.validate_and_prepare_attributes(attributes, intent)

    def can_proceed_with_intent(self, attributes: BalanceAttributes, intent: BalanceIntent):
        return self.unified_coordinator.can_proceed_with_intent(attributes, intent)

    def prepare_api_ready_attributes(self, attributes: BalanceAttributes):
        return self.unified_coordinator.prepare_api_ready_attributes(attributes, "balance")

    def extract_account_from_enhanced_query_unified(self, enhanced_query: str, session_id: str = None):
        return self.unified_coordinator.extract_account_from_enhanced_query_unified(enhanced_query, session_id)

    def get_complete_account_context(self, session_id: str):
        return self.unified_coordinator.get_complete_account_context(session_id)

    def validate_account_number(self, account_number: str, session_id: str = None):
        return self.unified_coordinator.validate_account_number(account_number, session_id)

    def validate_date_format(self, date_str: str) -> bool:
        return self.unified_coordinator.validate_date_format(date_str)

    def get_default_date_range(self):
        return self.unified_coordinator.get_default_date_range()

    def get_current_time_context(self):
        """Get current time context for attribute extraction"""
        from datetime import datetime
        current_time = datetime.now()
        return {
            'current_time': current_time.strftime("%Y-%m-%d %H:%M:%S"),
            'current_date': current_time.strftime("%Y-%m-%d"),
            'timestamp': current_time.timestamp()
        }

    def normalize_date_to_api_format(self, date_input: str, is_end_date: bool = False):
        return self.unified_coordinator.normalize_date_to_api_format(date_input, is_end_date)

    def format_accounts_for_display(self, accounts: List[str], user_name: str = None) -> str:
        return self.unified_coordinator.format_account_list_for_selection(accounts)


class TotalRevenueCoordinatorInterface:
    """Backward compatibility interface cho TotalRevenueAttributeCoordinator"""

    def __init__(self, unified_coordinator: UnifiedAttributeCoordinator):
        self.unified_coordinator = unified_coordinator

    def validate_and_prepare_attributes(self, attributes: TotalRevenueAttributes, intent: TotalRevenueIntent):
        return self.unified_coordinator.validate_and_prepare_attributes(attributes, intent)

    def can_proceed_with_intent(self, attributes: TotalRevenueAttributes, intent: TotalRevenueIntent):
        return self.unified_coordinator.can_proceed_with_intent(attributes, intent)

    def prepare_api_ready_attributes(self, attributes: TotalRevenueAttributes):
        return self.unified_coordinator.prepare_api_ready_attributes(attributes, "total_revenue")

    def create_response_metadata(self, intent: TotalRevenueIntent, attributes: TotalRevenueAttributes):
        return self.unified_coordinator.create_response_metadata(intent, attributes)


class LoanManagementCoordinatorInterface:
    """Backward compatibility interface cho LoanManagementAttributeCoordinator"""

    def __init__(self, unified_coordinator: UnifiedAttributeCoordinator):
        self.unified_coordinator = unified_coordinator

    def validate_and_prepare_attributes(self, attributes: LoanManagementAttributes, intent: LoanManagementIntent):
        return self.unified_coordinator.validate_and_prepare_attributes(attributes, intent)

    def can_proceed_with_intent(self, attributes: LoanManagementAttributes, intent: LoanManagementIntent):
        return self.unified_coordinator.can_proceed_with_intent(attributes, intent)

    def prepare_api_ready_attributes(self, attributes: LoanManagementAttributes):
        return self.unified_coordinator.prepare_api_ready_attributes(attributes, "loan_management")

    def create_response_metadata(self, intent: LoanManagementIntent, attributes: LoanManagementAttributes):
        return self.unified_coordinator.create_response_metadata(intent, attributes)