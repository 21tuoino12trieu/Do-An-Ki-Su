"""
Total Revenue Model - Standardized according to Balance domain format
Implements unified attribute structure with validation utilities
"""

from dataclasses import dataclass
from typing import Optional, Dict, List, Union, Any
from datetime import datetime
from enum import Enum
from beegenerate.loggings import LOGGER


class TotalRevenueIntent(Enum):
    """Total revenue intent definitions"""
    GET_TOTAL_ASSETS = "get_total_assets"
    GET_NET_WORTH = "get_net_worth"
    GET_INCOME_PROJECTION = "get_income_projection"
    GET_TOTAL_DEBT = "get_total_debt"
    TRIGGER_ASSET_SUMMARY_NOTIFICATION = "trigger_asset_summary_notification"
    ASSET_HEALTH_CHECK = "asset_health_check"
    OUT_OF_SCOPE = "out_of_scope"

    @classmethod
    def is_implemented(cls, intent: 'TotalRevenueIntent') -> bool:
        """Check if intent is implemented"""
        implemented = {
            cls.GET_TOTAL_ASSETS,
            cls.GET_NET_WORTH,
            cls.GET_INCOME_PROJECTION,
            cls.GET_TOTAL_DEBT,
            cls.TRIGGER_ASSET_SUMMARY_NOTIFICATION,
            cls.ASSET_HEALTH_CHECK,
            cls.OUT_OF_SCOPE
        }
        return intent in implemented

    @classmethod
    def requires_attributes(cls, intent: 'TotalRevenueIntent') -> bool:
        """Check if intent requires attribute collection"""
        intents_requiring_attributes = {
            cls.GET_TOTAL_ASSETS,
            cls.GET_NET_WORTH,
            cls.GET_INCOME_PROJECTION,
            cls.GET_TOTAL_DEBT,
            cls.ASSET_HEALTH_CHECK
            # cls.TRIGGER_ASSET_SUMMARY_NOTIFICATION,
        }
        return intent in intents_requiring_attributes


class TotalRevenueValidationUtils:
    """Centralized validation utility class for Total Revenue"""

    # Intent requirements - Updated to include customer_code for all intents
    INTENT_REQUIREMENTS = {
        TotalRevenueIntent.GET_TOTAL_ASSETS: ['customer_code'],
        TotalRevenueIntent.GET_NET_WORTH: ['customer_code'],
        TotalRevenueIntent.GET_INCOME_PROJECTION: ['customer_code'],
        TotalRevenueIntent.GET_TOTAL_DEBT: ['customer_code'],
        TotalRevenueIntent.ASSET_HEALTH_CHECK: ['customer_code'],
        TotalRevenueIntent.TRIGGER_ASSET_SUMMARY_NOTIFICATION: [],
        TotalRevenueIntent.OUT_OF_SCOPE: [],
    }

    COLLECTION_QUESTIONS = {
        'customer_code': 'Vui lòng cung cấp mã khách hàng của bạn để truy xuất thông tin tài sản.'
    }

    # Error messages
    ERROR_MESSAGES = {
        'MISSING_CUSTOMER_CODE': 'Thiếu mã khách hàng',
        'INVALID_CUSTOMER_CODE': 'Mã khách hàng không hợp lệ',
        'INVALID_BUSINESS_DOMAIN': 'Domain kinh doanh không hợp lệ'
    }

    @classmethod
    def validate_customer_code(cls, customer_code: str) -> bool:
        """Validate customer code format"""
        if not customer_code or not isinstance(customer_code, str):
            return False
        # Basic validation - can be enhanced based on business rules
        return len(customer_code.strip()) > 0

    @classmethod
    def validate_business_domain(cls, business_domain: str) -> bool:
        """Validate business domain"""
        valid_domains = ['MBB']
        return business_domain in valid_domains

    @classmethod
    def get_attributes_with_customer_injection(
            cls,
            attributes: Optional['TotalRevenueAttributes'],
            session_id: str,
            user_profile_service
    ) -> 'TotalRevenueAttributes':
        """
        Initialize attributes if missing và inject customer_code từ profile nếu có

        Args:
            attributes: Current attributes (có thể None)
            session_id: Session identifier để lấy profile
            user_profile_service: Service để lấy customer info từ profile

        Returns:
            TotalRevenueAttributes với customer_code từ profile nếu có
        """
        if not attributes:
            attributes = create_empty_total_revenue_attributes()

        if not attributes.customer_code and user_profile_service:
            profile_customer_code = user_profile_service.get_customer_code(session_id)
            if profile_customer_code:
                attributes.customer_code = profile_customer_code
                LOGGER.info(f"Injected customer_code from profile: {profile_customer_code}")

        return attributes

    @classmethod
    def get_required_attributes(cls, intent: Union['TotalRevenueIntent', str]) -> List[str]:
        """Get required attributes for intent"""
        if isinstance(intent, str):
            try:
                intent = TotalRevenueIntent(intent)
            except ValueError:
                return []

        return cls.INTENT_REQUIREMENTS.get(intent, [])

    @classmethod
    def validate_attributes_for_intent(cls, attributes: 'TotalRevenueAttributes',
                                       intent: Union['TotalRevenueIntent', str]) -> bool:
        """Validate if attributes are sufficient for intent"""
        if isinstance(intent, str):
            try:
                intent = TotalRevenueIntent(intent)
            except ValueError:
                return False

        required_attrs = cls.get_required_attributes(intent)
        return all(getattr(attributes, attr) for attr in required_attrs)

    @classmethod
    def get_missing_attributes(cls, attributes: 'TotalRevenueAttributes', intent: Union['TotalRevenueIntent', str]) -> List[str]:
        """Get missing attributes for intent"""
        if isinstance(intent, str):
            try:
                intent = TotalRevenueIntent(intent)
            except ValueError:
                return []

        required = cls.get_required_attributes(intent)
        return [attr for attr in required if not getattr(attributes, attr, None)]

    @classmethod
    def get_validation_errors(cls, attributes: 'TotalRevenueAttributes', intent: Union[TotalRevenueIntent, str]) -> \
    List[str]:
        """Get detailed validation errors for intent"""
        missing = cls.get_missing_attributes(attributes, intent)  # Truyền đủ parameters
        errors = []

        for attr in missing:
            if attr == 'customer_code':
                errors.append(TotalRevenueValidationUtils.ERROR_MESSAGES['MISSING_CUSTOMER_CODE'])

        return errors

    @classmethod
    def get_collection_question(cls, attribute_name: str) -> str:
        """Get collection question for specific attribute"""
        return cls.COLLECTION_QUESTIONS.get(
            attribute_name,
            f"Vui lòng cung cấp thông tin: {attribute_name}"
        )


@dataclass
class TotalRevenueAttributes:
    """Unified total revenue attributes with built-in validation"""

    # Core attributes - cần thiết cho API transaction-integration
    customer_code: Optional[str] = None
    business_domain: Optional[str] = "MBB"

    # Metadata
    created_at: datetime = None
    updated_at: datetime = None

    def __post_init__(self):
        """Initialize timestamps"""
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()

    def get_missing_attributes(self, intent: Union[TotalRevenueIntent, str]) -> List[str]:
        """Get missing attributes for specific intent"""
        return TotalRevenueValidationUtils.get_missing_attributes(self, intent)

    def is_valid_for_intent(self, intent: Union[TotalRevenueIntent, str]) -> bool:
        """Check if attributes are valid for intent"""
        return TotalRevenueValidationUtils.validate_attributes_for_intent(self, intent)

    def get_validation_errors(self, intent: Union[TotalRevenueIntent, str]) -> List[str]:
        """Get validation error messages for intent"""
        return TotalRevenueValidationUtils.get_validation_errors(self, intent)

    def to_dict(self) -> Dict:
        """Convert to dictionary for API calls"""
        return {
            'customer_code': self.customer_code,
            'business_domain': self.business_domain
        }


# ==================== MODULE UTILITY FUNCTIONS ====================

def create_empty_total_revenue_attributes() -> TotalRevenueAttributes:
    """Factory function to create empty total revenue attributes"""
    return TotalRevenueAttributes()


def validate_total_revenue_request(attributes: TotalRevenueAttributes,
                                   intent: Union[TotalRevenueIntent, str]) -> Dict[str, Any]:
    """Complete validation check for total revenue request"""
    return {
        'is_valid': TotalRevenueValidationUtils.validate_attributes_for_intent(attributes, intent),
        'missing_attributes': TotalRevenueValidationUtils.get_missing_attributes(attributes, intent),
        'required_attributes': TotalRevenueValidationUtils.get_required_attributes(intent),
        'validation_errors': TotalRevenueValidationUtils.get_validation_errors(attributes, intent)
    }


def get_total_revenue_intent_requirements(intent: Union[TotalRevenueIntent, str]) -> List[str]:
    """Get required attributes for intent - public function"""
    return TotalRevenueValidationUtils.get_required_attributes(intent)


# ==================== CONSTANTS FOR EXTERNAL USE ====================

# Intent requirements - exposed for external usage
INTENT_REQUIREMENTS = TotalRevenueValidationUtils.INTENT_REQUIREMENTS

# Error messages - exposed for external usage
ERROR_MESSAGES = TotalRevenueValidationUtils.ERROR_MESSAGES
