"""
Loan Management Model - Quản lý khoản vay LD và AC
Implements unified attribute structure for loan management intents
"""

from dataclasses import dataclass
from typing import Optional, Dict, List, Union, Any
from datetime import datetime
from enum import Enum


class LoanManagementIntent(Enum):
    """Loan Management intent definitions"""
    # LD (Loan Deposit) Management
    GET_ALL_LD = "get_all_ld"
    GET_LD_INFO = "get_ld_info"
    GET_LD_PAYMENT_SCHEDULE = "get_ld_payment_schedule"
    GET_LD_PAYMENT_HISTORY = "get_ld_payment_history"
    GET_LD_ADDITIONAL_LOAN_AMOUNT = "get_ld_additional_loan_amount"

    # AC (Account Credit) Management
    GET_AC_OVERDRAFT_LIST = "get_ac_overdraft_list"
    GET_AC_LIMIT_INCREASE = "get_ac_limit_increase"

    # Combined Analytics
    GET_TOTAL_OVERDUE_DEBT = "get_total_overdue_debt"
    GET_TOTAL_ADDITIONAL_LOAN_CAPACITY = "get_total_additional_loan_capacity"
    GET_COMBINED_PAYMENT_SCHEDULE = "get_combined_payment_schedule"
    GET_COMBINED_LOAN_LIST = "get_combined_loan_list"

    OUT_OF_SCOPE = "out_of_scope"

    @classmethod
    def is_implemented(cls, intent: 'LoanManagementIntent') -> bool:
        """Check if intent is implemented"""
        implemented = {
            cls.GET_ALL_LD,
            cls.GET_LD_INFO,
            cls.GET_LD_PAYMENT_SCHEDULE,
            cls.GET_TOTAL_OVERDUE_DEBT,
            cls.GET_AC_OVERDRAFT_LIST,
            cls.OUT_OF_SCOPE
        }
        return intent in implemented

    @classmethod
    def requires_attributes(cls, intent: 'LoanManagementIntent') -> bool:
        """Check if intent requires attribute collection"""
        intents_requiring_attributes = {
            cls.GET_ALL_LD,
            cls.GET_LD_INFO,
            cls.GET_LD_PAYMENT_SCHEDULE,
            cls.GET_LD_PAYMENT_HISTORY,
            cls.GET_LD_ADDITIONAL_LOAN_AMOUNT,
            cls.GET_AC_OVERDRAFT_LIST,
            cls.GET_AC_LIMIT_INCREASE,
            cls.GET_TOTAL_OVERDUE_DEBT,
            cls.GET_TOTAL_ADDITIONAL_LOAN_CAPACITY,
            cls.GET_COMBINED_PAYMENT_SCHEDULE,
            cls.GET_COMBINED_LOAN_LIST
        }
        return intent in intents_requiring_attributes


class LoanManagementValidationUtils:
    """Centralized validation utility class for Loan Management"""

    # Intent requirements
    INTENT_REQUIREMENTS = {
        LoanManagementIntent.GET_ALL_LD: ['customer_code'],
        LoanManagementIntent.GET_LD_INFO: ['customer_code'],
        LoanManagementIntent.GET_LD_PAYMENT_SCHEDULE: ['start_date', 'end_date'],
        LoanManagementIntent.GET_LD_ADDITIONAL_LOAN_AMOUNT: ['customer_code'],
        LoanManagementIntent.GET_AC_OVERDRAFT_LIST: ['customer_code'],
        # LoanManagementIntent.GET_AC_LIMIT_INCREASE: ['customer_code'],
        LoanManagementIntent.GET_TOTAL_OVERDUE_DEBT: ['customer_code'],
        # LoanManagementIntent.GET_TOTAL_ADDITIONAL_LOAN_CAPACITY: ['customer_code'],
        # LoanManagementIntent.GET_COMBINED_PAYMENT_SCHEDULE: ['customer_code'],
        # LoanManagementIntent.GET_COMBINED_LOAN_LIST: ['customer_code'],
        LoanManagementIntent.OUT_OF_SCOPE: [],
    }

    COLLECTION_QUESTIONS = {
        'customer_code': 'Vui lòng cung cấp mã khách hàng của bạn để truy xuất thông tin khoản vay.',
        'loan_id': 'Vui lòng cung cấp mã hợp đồng hoặc số hiệu khoản vay cụ thể.',
        'start_date': 'Vui lòng cung cấp ngày bắt đầu lịch thanh toán (định dạng: yyyymmdd).',
        'end_date': 'Vui lòng cung cấp ngày kết thúc lịch thanh toán (định dạng: yyyymmdd).'
    }

    ERROR_MESSAGES = {
        'customer_code': 'Mã khách hàng không hợp lệ',
        'loan_id': 'Mã hợp đồng vay không hợp lệ'
    }

    @classmethod
    def validate_attributes_for_intent(cls, attributes: 'LoanManagementAttributes',
                                       intent: Union[LoanManagementIntent, str]) -> bool:
        """Validate attributes for specific intent"""
        if isinstance(intent, str):
            intent = LoanManagementIntent(intent)

        required_attrs = cls.INTENT_REQUIREMENTS.get(intent, [])

        for attr_name in required_attrs:
            value = getattr(attributes, attr_name, None)
            if value is None or (isinstance(value, str) and not value.strip()):
                return False

        return True

    @classmethod
    def get_missing_attributes(cls, attributes: 'LoanManagementAttributes',
                               intent: Union[LoanManagementIntent, str]) -> List[str]:
        """Get list of missing required attributes với smart defaults cho dates"""
        if isinstance(intent, str):
            intent = LoanManagementIntent(intent)

        required_attrs = cls.INTENT_REQUIREMENTS.get(intent, [])
        missing = []

        for attr_name in required_attrs:
            value = getattr(attributes, attr_name, None)

            # Special handling cho GET_LD_PAYMENT_SCHEDULE dates
            if intent == LoanManagementIntent.GET_LD_PAYMENT_SCHEDULE:
                if attr_name in ['start_date', 'end_date']:
                    if not value:
                        continue

            # Standard validation cho các fields khác
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(attr_name)

        return missing

    @classmethod
    def get_required_attributes(cls, intent: Union[LoanManagementIntent, str]) -> List[str]:
        """Get required attributes for intent"""
        if isinstance(intent, str):
            intent = LoanManagementIntent(intent)
        return cls.INTENT_REQUIREMENTS.get(intent, [])

    @classmethod
    def get_validation_errors(cls, attributes: 'LoanManagementAttributes',
                              intent: Union[LoanManagementIntent, str]) -> List[str]:
        """Get validation error messages"""
        missing_attrs = cls.get_missing_attributes(attributes, intent)
        return [cls.ERROR_MESSAGES.get(attr, f"Thiếu thông tin: {attr}") for attr in missing_attrs]


@dataclass
class LoanManagementAttributes:
    """Attributes for loan management intents"""
    customer_code: Optional[str] = None
    loan_id: Optional[str] = None
    loan_type: Optional[str] = None  # LD, AC
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status_filter: Optional[str] = None  # PAID, UNPAID
    business_domain: Optional[str] = None

    def validate_for_intent(self, intent: Union[LoanManagementIntent, str]) -> bool:
        """Validate attributes for specific intent"""
        return LoanManagementValidationUtils.validate_attributes_for_intent(self, intent)

    def get_missing_attributes_for_intent(self, intent: Union[LoanManagementIntent, str]) -> List[str]:
        """Get missing attributes for intent"""
        return LoanManagementValidationUtils.get_missing_attributes(self, intent)

    def get_validation_errors_for_intent(self, intent: Union[LoanManagementIntent, str]) -> List[str]:
        """Get validation error messages for intent"""
        return LoanManagementValidationUtils.get_validation_errors(self, intent)

    def to_dict(self) -> Dict:
        """Convert to dictionary for API calls"""
        return {
            'customer_code': self.customer_code,
            'loan_id': self.loan_id,
            'loan_type': self.loan_type,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'status_filter': self.status_filter,
            'business_domain': self.business_domain
        }

    @classmethod
    def _is_valid_date_format(cls, date_str: str) -> bool:
        """Kiểm tra format date YYYYMMDD"""
        if not date_str or len(date_str) != 8 or not date_str.isdigit():
            return False
        try:
            datetime.strptime(date_str, "%Y%m%d")
            return True
        except ValueError:
            return False


# ==================== MODULE UTILITY FUNCTIONS ====================

def create_empty_loan_management_attributes() -> LoanManagementAttributes:
    """Factory function to create empty loan management attributes"""
    return LoanManagementAttributes()


def validate_loan_management_request(attributes: LoanManagementAttributes,
                                     intent: Union[LoanManagementIntent, str]) -> Dict[str, Any]:
    """Complete validation check for loan management request"""
    return {
        'is_valid': LoanManagementValidationUtils.validate_attributes_for_intent(attributes, intent),
        'missing_attributes': LoanManagementValidationUtils.get_missing_attributes(attributes, intent),
        'required_attributes': LoanManagementValidationUtils.get_required_attributes(intent),
        'validation_errors': LoanManagementValidationUtils.get_validation_errors(attributes, intent)
    }


def get_loan_management_intent_requirements(intent: Union[LoanManagementIntent, str]) -> List[str]:
    """Get required attributes for intent - public function"""
    return LoanManagementValidationUtils.get_required_attributes(intent)


# ==================== CONSTANTS FOR EXTERNAL USE ====================

# Intent requirements - exposed for external usage
INTENT_REQUIREMENTS = LoanManagementValidationUtils.INTENT_REQUIREMENTS

# Error messages - exposed for external usage
ERROR_MESSAGES = LoanManagementValidationUtils.ERROR_MESSAGES
