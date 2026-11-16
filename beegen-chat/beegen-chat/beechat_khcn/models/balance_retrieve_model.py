"""
Balance Retrieve Model - Consolidated and Simplified
Merged all validation logic into single utility class
Eliminated redundancy while preserving all functionality
"""

from dataclasses import dataclass
from typing import Optional, Dict, List, Union, Any
from datetime import datetime
from enum import Enum


class BalanceIntent(Enum):
    """Balance retrieve intent definitions"""
    QUERY_TRANSACTION_NORMAL = "query_transaction_normal"
    QUERY_TRANSACTION_DESCRIPTIVE = "query_transaction_descriptive"
    QUERY_TRANSACTION_BY_TYPE = "query_transaction_by_type"
    QUERY_TRANSACTION_BY_AMOUNT = "query_transaction_by_amount"
    QUERY_TRANSACTION_BY_BENEFICIARY = "query_transaction_by_beneficiary"
    QUERY_TRANSACTION_BY_CHANNEL = "query_transaction_by_channel"
    QUERY_TRANSACTION_EXPORT = "query_transaction_export"
    INITIATE_TRANSACTION_DISPUTE = "initiate_transaction_dispute"
    BALANCE_RETRIEVE_MENU = "balance_retrieve_menu"
    ACCOUNT_SELECTION = "account_selection"
    UNRECOGNIZED_TRANSACTION_QUERY = "unrecognized_transaction_query"
    QUERY_TRANSACTION_MULTI_CONDITIONS = "query_transaction_multi_conditions"

    @classmethod
    def is_implemented(cls, intent: 'BalanceIntent') -> bool:
        """Check if intent is implemented"""
        implemented = {
            cls.QUERY_TRANSACTION_NORMAL,

            cls.QUERY_TRANSACTION_DESCRIPTIVE,
            cls.QUERY_TRANSACTION_BY_TYPE,
            cls.QUERY_TRANSACTION_BY_AMOUNT,
            cls.QUERY_TRANSACTION_BY_BENEFICIARY,
            cls.QUERY_TRANSACTION_BY_CHANNEL,
            cls.BALANCE_RETRIEVE_MENU,
            cls.QUERY_TRANSACTION_EXPORT,
            cls.INITIATE_TRANSACTION_DISPUTE,
            cls.ACCOUNT_SELECTION,
            cls.UNRECOGNIZED_TRANSACTION_QUERY,
            cls.QUERY_TRANSACTION_MULTI_CONDITIONS,
        }
        return intent in implemented

    @classmethod
    def get_implemented_intents(cls) -> List['BalanceIntent']:
        """Get list of implemented intents"""
        return [
            cls.QUERY_TRANSACTION_NORMAL,
            cls.QUERY_TRANSACTION_DESCRIPTIVE,
            cls.QUERY_TRANSACTION_BY_TYPE,
            cls.QUERY_TRANSACTION_BY_AMOUNT,
            cls.QUERY_TRANSACTION_BY_BENEFICIARY,
            cls.QUERY_TRANSACTION_BY_CHANNEL,
            cls.QUERY_TRANSACTION_MULTI_CONDITIONS,
            cls.BALANCE_RETRIEVE_MENU,
            cls.QUERY_TRANSACTION_EXPORT,
            cls.INITIATE_TRANSACTION_DISPUTE,
            cls.ACCOUNT_SELECTION,
            cls.UNRECOGNIZED_TRANSACTION_QUERY
        ]

    @classmethod
    def requires_attributes(cls, intent: 'BalanceIntent') -> bool:
        """Check if intent requires attribute collection"""
        intents_requiring_attributes = {
            cls.QUERY_TRANSACTION_NORMAL,
            cls.QUERY_TRANSACTION_DESCRIPTIVE,
            cls.QUERY_TRANSACTION_BY_TYPE,
            cls.QUERY_TRANSACTION_BY_AMOUNT,
            cls.QUERY_TRANSACTION_BY_BENEFICIARY,
            cls.QUERY_TRANSACTION_BY_CHANNEL,
            cls.QUERY_TRANSACTION_MULTI_CONDITIONS
            # cls.QUERY_TRANSACTION_EXPORT,
            # cls.INITIATE_TRANSACTION_DISPUTE,
            # cls.BALANCE_RETRIEVE_MENU không cần thu thập attributes
        }
        return intent in intents_requiring_attributes


class BalanceValidationUtils:
    """Centralized validation utility class"""

    # Intent requirements mapping
    INTENT_REQUIREMENTS = {
        BalanceIntent.QUERY_TRANSACTION_NORMAL: ['account_number', 'from_date', 'to_date'],
        BalanceIntent.QUERY_TRANSACTION_DESCRIPTIVE: ['account_number', 'from_date', 'to_date'],
        BalanceIntent.QUERY_TRANSACTION_BY_TYPE: ['account_number', 'from_date', 'to_date', 'transaction_type'],
        BalanceIntent.QUERY_TRANSACTION_BY_AMOUNT: ['account_number', 'from_date', 'to_date'],
        BalanceIntent.QUERY_TRANSACTION_BY_BENEFICIARY: ['account_number', 'from_date', 'to_date'],
        BalanceIntent.QUERY_TRANSACTION_BY_CHANNEL: ['account_number', 'from_date', 'to_date'],
        BalanceIntent.BALANCE_RETRIEVE_MENU: [],
        BalanceIntent.QUERY_TRANSACTION_EXPORT: [],
        BalanceIntent.INITIATE_TRANSACTION_DISPUTE: [],
        BalanceIntent.QUERY_TRANSACTION_MULTI_CONDITIONS: ['account_number', 'from_date', 'to_date'],
        BalanceIntent.UNRECOGNIZED_TRANSACTION_QUERY: ['account_number', 'from_date', 'to_date']
    }
    OPTIONAL_REQUIREMENTS = {
        BalanceIntent.QUERY_TRANSACTION_BY_AMOUNT: ['min_amount', 'max_amount'],  # ít nhất 1 trong 2
    }
    # Error messages
    ERROR_MESSAGES = {
        'INVALID_ACCOUNT': "Số tài khoản không hợp lệ, không nằm trong danh sách tài khoản của bạn",
        'INVALID_FROM_DATE': "Định dạng ngày bắt đầu không hợp lệ",
        'INVALID_TO_DATE': "Định dạng ngày kết thúc không hợp lệ",
        'INVALID_DATE_RANGE': "Khoảng thời gian không hợp lệ",
        'INVALID_AMOUNT_RANGE': "Số tiền tối thiểu không thể lớn hơn số tiền tối đa",
        'UNKNOWN_INTENT': "Unknown intent: {intent}",
        'API_ERROR': "Xin lỗi, có lỗi xảy ra trong quá trình xử lý yêu cầu tra cứu giao dịch.",
        'CONTACT_HOTLINE': "Bạn vui lòng thử lại hoặc liên hệ hotline **1900 588 822** để được hỗ trợ."
    }

    # Collection questions
    COLLECTION_QUESTIONS = {
        'account_number': "Bạn vui lòng cho Bee biết số tài khoản cần tra cứu giao dịch (10-15 chữ số)?",
        'from_date': "Bạn muốn xem giao dịch từ ngày nào? Vui lòng nhập theo định dạng DD/MM/YYYY (ví dụ: 01/01/2024).",
        'to_date': "Bạn muốn xem giao dịch đến ngày nào? Vui lòng nhập theo định dạng DD/MM/YYYY (ví dụ: 31/01/2024).",
        'transaction_type': "Bạn muốn xem loại giao dịch nào? (ví dụ: Tiền vào, Tiền ra, Chuyển khoản)",
        'min_amount': "Số tiền giao dịch tối thiểu là bao nhiêu? (VND)",
        'max_amount': "Số tiền giao dịch tối đa là bao nhiêu? (VND)",
        'beneficiary_name': "Tên người nhận hoặc nội dung giao dịch mà bạn muốn tìm?",
        'channel': "Kênh giao dịch nào? (ví dụ: Internet Banking, Mobile Banking, ATM)",
        'export_format': "Định dạng file xuất? (PDF/Excel)"
    }

    # ==================== VALIDATION METHODS ====================

    @classmethod
    def validate_account_number(cls, account_number: str) -> bool:
        """Validate account number format"""
        if not account_number:
            return False

        # Remove spaces and special characters
        cleaned = account_number.replace(" ", "").replace("-", "")

        # Check if all digits and proper length
        return cleaned.isdigit() and 10 <= len(cleaned) <= 15

    @classmethod
    def validate_date_format(cls, date_str: str) -> bool:
        """Validate date string format"""
        if not date_str:
            return False

        # Accept various formats
        valid_formats = [
            "%Y-%m-%d %H:%M:%S",  # 2025-07-01 00:00:00
            "%Y-%m-%d",  # 2025-07-01
            "%d/%m/%Y",  # 01/07/2025
            "%d-%m-%Y",  # 01-07-2025
        ]

        for fmt in valid_formats:
            try:
                datetime.strptime(date_str, fmt)
                return True
            except ValueError:
                continue

        return False

    @classmethod
    def validate_date_range(cls, from_date: str, to_date: str) -> bool:
        """Validate date range logic"""
        # ✅ FIX: Apply defaults if None
        if not from_date:
            from_date = cls._get_default_from_date()
        if not to_date:
            to_date = cls._get_default_to_date()

        if not cls.validate_date_format(from_date) or not cls.validate_date_format(to_date):
            return False

        try:
            from_dt = cls._parse_date_flexible(from_date)
            to_dt = cls._parse_date_flexible(to_date)
            return from_dt <= to_dt
        except Exception:
            return False

    @classmethod
    def validate_amount_range(cls, min_amount: float, max_amount: float) -> bool:
        """Validate amount range"""
        if min_amount is None or max_amount is None:
            return True  # Optional fields

        return min_amount <= max_amount

    @classmethod
    def _parse_date_flexible(cls, date_str: str) -> datetime:
        """Parse date string with multiple format support"""
        valid_formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%d-%m-%Y",
        ]

        for fmt in valid_formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        raise ValueError(f"Unable to parse date: {date_str}")

    # ==================== INTENT-BASED VALIDATION ====================

    @classmethod
    def get_required_attributes(cls, intent: Union[BalanceIntent, str]) -> List[str]:
        """Get required attributes for specific intent"""
        if isinstance(intent, str):
            try:
                intent = BalanceIntent(intent.lower())
            except ValueError:
                return []

        return cls.INTENT_REQUIREMENTS.get(intent, [])

    @classmethod
    def get_missing_attributes(cls, attributes: 'BalanceAttributes', intent: Union[BalanceIntent, str]) -> List[str]:
        """Get missing required attributes với smart defaults cho date"""
        if isinstance(intent, str):
            try:
                intent = BalanceIntent(intent)
            except ValueError:
                return []

        requirements = cls.INTENT_REQUIREMENTS.get(intent, [])
        missing = []

        for attr in requirements:
            value = getattr(attributes, attr, None)

            if attr == 'from_date' and value is None:
                setattr(attributes, 'from_date', cls._get_default_from_date())
                continue

            if attr == 'to_date' and value is None:
                setattr(attributes, 'to_date', cls._get_default_to_date())
                continue

            if value is None:
                missing.append(attr)

        # Special handling cho QUERY_TRANSACTION_BY_AMOUNT
        if intent == BalanceIntent.QUERY_TRANSACTION_BY_AMOUNT:
            if attributes.min_amount is None and attributes.max_amount is None:
                missing.append('min_amount')  # Yêu cầu ít nhất 1 trong 2

        return missing

    @classmethod
    def _get_default_from_date(cls) -> str:
        """Tạo default from_date = 7 ngày trước"""
        from datetime import datetime, timedelta
        default_date = datetime.now() - timedelta(days=6)
        return default_date.strftime("%Y-%m-%d 00:00:00")

    @classmethod
    def _get_default_to_date(cls) -> str:
        """Tạo default to_date = hôm nay"""
        from datetime import datetime
        default_date = datetime.now()
        return default_date.strftime("%Y-%m-%d 23:59:59")

    @classmethod
    def validate_attributes_for_intent(cls, attributes: 'BalanceAttributes', intent: Union[BalanceIntent, str]) -> bool:
        """Complete validation for specific intent"""
        # Check missing attributes
        missing = cls.get_missing_attributes(attributes, intent)
        if missing:
            return False

        # Intent-specific validations
        if isinstance(intent, str):
            try:
                intent = BalanceIntent(intent.lower())
            except ValueError:
                return False

        # Core transaction validation với from_date và to_date
        if intent in [BalanceIntent.QUERY_TRANSACTION_NORMAL, BalanceIntent.QUERY_TRANSACTION_DESCRIPTIVE,
                      BalanceIntent.QUERY_TRANSACTION_EXPORT, BalanceIntent.QUERY_TRANSACTION_BY_TYPE,
                      BalanceIntent.QUERY_TRANSACTION_BY_BENEFICIARY, BalanceIntent.QUERY_TRANSACTION_BY_CHANNEL,
                      BalanceIntent.QUERY_TRANSACTION_BY_AMOUNT,
                      BalanceIntent.QUERY_TRANSACTION_MULTI_CONDITIONS]:  # THÊM MỚI
            if not cls.validate_account_number(attributes.account_number):
                return False
            if not cls.validate_date_range(attributes.from_date, attributes.to_date):
                return False

        return True

    @classmethod
    def get_validation_errors(cls, attributes: 'BalanceAttributes', intent: Union[BalanceIntent, str]) -> List[str]:
        """Get detailed validation errors"""
        errors = []

        # Check missing attributes first
        missing = cls.get_missing_attributes(attributes, intent)
        if missing:
            for attr in missing:
                question = cls.COLLECTION_QUESTIONS.get(attr, f"Thiếu thông tin: {attr}")
                errors.append(question)
            return errors

        # Detailed validation
        if attributes.account_number and not cls.validate_account_number(attributes.account_number):
            errors.append(cls.ERROR_MESSAGES['INVALID_ACCOUNT'])

        if attributes.from_date and not cls.validate_date_format(attributes.from_date):
            errors.append(cls.ERROR_MESSAGES['INVALID_FROM_DATE'])

        if attributes.to_date and not cls.validate_date_format(attributes.to_date):
            errors.append(cls.ERROR_MESSAGES['INVALID_TO_DATE'])

        if attributes.from_date and attributes.to_date and not cls.validate_date_range(attributes.from_date,
                                                                                       attributes.to_date):
            errors.append(cls.ERROR_MESSAGES['INVALID_DATE_RANGE'])

        if attributes.min_amount is not None and attributes.max_amount is not None:
            if not cls.validate_amount_range(attributes.min_amount, attributes.max_amount):
                errors.append(cls.ERROR_MESSAGES['INVALID_AMOUNT_RANGE'])

        return errors


@dataclass
class BalanceAttributes:
    """Unified balance attributes with built-in validation"""

    # Core transaction attributes
    account_number: Optional[str] = None
    from_date: Optional[str] = None
    to_date: Optional[str] = None

    # Additional filtering attributes
    transaction_type: Optional[str] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    beneficiary_name: Optional[str] = None
    channel: Optional[str] = None
    export_format: Optional[str] = None

    # Metadata
    created_at: datetime = None
    updated_at: datetime = None

    def __post_init__(self):
        """Initialize timestamps"""
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()

    def get_missing_attributes(self, intent: Union[BalanceIntent, str]) -> List[str]:
        """Get missing attributes for specific intent"""
        return BalanceValidationUtils.get_missing_attributes(self, intent)

    def is_valid_for_intent(self, intent: Union[BalanceIntent, str]) -> bool:
        """Check if attributes are valid for intent"""
        return BalanceValidationUtils.validate_attributes_for_intent(self, intent)

    def to_dict(self) -> Dict:
        """Convert to dictionary for API calls"""
        return {
            'account_number': self.account_number,
            'from_date': self.from_date,
            'to_date': self.to_date,
            'transaction_type': self.transaction_type,
            'min_amount': self.min_amount,
            'max_amount': self.max_amount,
            'beneficiary_name': self.beneficiary_name,
            'channel': self.channel,
            'export_format': self.export_format
        }

    def __str__(self) -> str:
        """String representation for debugging"""
        return f"BalanceAttributes(account={self.account_number}, from={self.from_date}, to={self.to_date})"


# ==================== MODULE UTILITY FUNCTIONS ====================

def create_empty_balance_attributes() -> BalanceAttributes:
    """Factory function to create empty balance attributes"""
    return BalanceAttributes()


def validate_balance_request(attributes: BalanceAttributes, intent: Union[BalanceIntent, str]) -> Dict[str, Any]:
    """Complete validation check for balance request"""
    return {
        'is_valid': BalanceValidationUtils.validate_attributes_for_intent(attributes, intent),
        'missing_attributes': BalanceValidationUtils.get_missing_attributes(attributes, intent),
        'validation_errors': BalanceValidationUtils.get_validation_errors(attributes, intent),
        'required_attributes': BalanceValidationUtils.get_required_attributes(intent)
    }


def get_collection_question(attribute_name: str) -> str:
    """Get collection question for specific attribute"""
    return BalanceValidationUtils.COLLECTION_QUESTIONS.get(
        attribute_name,
        f"Vui lòng cung cấp thông tin: {attribute_name}"
    )


def get_intent_requirements(intent: Union[BalanceIntent, str]) -> List[str]:
    """Get required attributes for intent - public function"""
    return BalanceValidationUtils.get_required_attributes(intent)


def validate_account_number(account_number: str) -> bool:
    """Validate account number - public function"""
    return BalanceValidationUtils.validate_account_number(account_number)


def validate_date_range(from_date: str, to_date: str) -> bool:
    """Validate date range - public function"""
    return BalanceValidationUtils.validate_date_range(from_date, to_date)


# ==================== CONSTANTS FOR EXTERNAL USE ====================

# Intent requirements - exposed for external usage
INTENT_REQUIREMENTS = BalanceValidationUtils.INTENT_REQUIREMENTS

# Error messages - exposed for external usage
ERROR_MESSAGES = BalanceValidationUtils.ERROR_MESSAGES

# Collection questions - exposed for external usage
COLLECTION_QUESTIONS = BalanceValidationUtils.COLLECTION_QUESTIONS
