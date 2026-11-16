"""
Simplified deposit models with essential validation only
Tối ưu hóa data structures, loại bỏ complexity dư thừa
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any
from enum import Enum


class DepositProductType(Enum):
    """Enum cho loại sản phẩm tiền gửi"""
    TRADITIONAL = "traditional"
    ACCUMULATING = "accumulating"

    def get_display_name(self) -> str:
        """Get Vietnamese display name"""
        names = {
            self.TRADITIONAL: "Tiền gửi số truyền thống",
            self.ACCUMULATING: "Tiền gửi số tích lũy"
        }
        return names.get(self, "Không xác định")

    def get_min_amount(self) -> float:
        """Get minimum amount cho loại sản phẩm"""
        min_amounts = {
            self.TRADITIONAL: 1000000,  # 1 triệu VND
            self.ACCUMULATING: 50000    # 50 nghìn VND
        }
        return min_amounts.get(self, 0)


class CustomerPreference(Enum):
    """Customer preferences cho personalized recommendations"""
    MONTHLY_INTEREST = "monthly_interest"  # Trả lãi hàng tháng
    END_TERM_INTEREST = "end_term_interest"  # Trả lãi cuối kỳ
    FLEXIBLE_WITHDRAWAL = "flexible_withdrawal"  # Rút linh hoạt
    HIGH_RETURN = "high_return"  # Lãi suất cao
    LOW_RISK = "low_risk"  # Rủi ro thấp


@dataclass
class DepositAttributes:
    """
    Simplified attributes cho deposit intents
    Chỉ giữ essential data và basic validation
    """
    amount: Optional[float] = None
    product_type: Optional[DepositProductType] = None
    term: Optional[str] = None
    saving_account_name: Optional[str] = None

    customer_preference: Optional[CustomerPreference] = None
    preferred_term_range: Optional[str] = None  # "short", "medium", "long"
    minimum_amount: Optional[float] = None  # Tối thiểu muốn gửi

    def is_complete_for_intent(self, intent: str) -> bool:
        """Enhanced completion check với new intents"""
        intent_requirements = {
            # PRE-OPENING - existing + new
            "calculate_interest": ["amount", "product_type", "term"],
            "open_saving_account": ["amount", "product_type", "term"],
            "compare_products": [],  # 🆕 Không cần attributes cụ thể
            "request_personalized_recommendation": ["amount", "preferred_term_range"],  # 🆕

            # DURING HOLDING - existing
            "inquire_maturity_date": ["saving_account_name"],
            "check_account_balance": ["saving_account_name"],
            "check_interest_earned": ["saving_account_name"],
            "withdraw_principal": ["saving_account_name"],
            "change_interest_payout_method": ["saving_account_name"],
            "terminate_early": ["saving_account_name"],
            "make_additional_deposit": ["saving_account_name"],

            # MATURITY - existing + new
            "maturity_notification": ["saving_account_name"],
            "withdraw_principal_interest": ["saving_account_name"],
            "request_reinvestment_options": ["saving_account_name"],  # 🆕

            # INFO INQUIRY - existing + new
            "inquire_saving_account_types": [],
            "inquire_interest_rates": [],
            "eligibility_criteria": [],
            "promotion_inquiry": []
        }

        required_attrs = intent_requirements.get(intent, [])
        return all(getattr(self, attr) is not None for attr in required_attrs)

    def get_missing_attributes_for_intent(self, intent: str) -> list:
        """Get list missing attributes cho intent"""
        intent_requirements = {
            "calculate_interest": ["amount", "product_type", "term"],
            "open_saving_account": ["amount", "product_type", "term"],
            "inquire_maturity_date": ["saving_account_name"],
            "check_account_balance": ["saving_account_name"],
            "check_interest_earned": ["saving_account_name"],
            "withdraw_principal": ["saving_account_name"],
            "change_interest_payout_method": ["saving_account_name"],
            "terminate_early": ["saving_account_name"],
            "make_additional_deposit": ["saving_account_name"],
            "maturity_notification": ["saving_account_name"],
            "withdraw_principal_interest": ["saving_account_name"]
        }

        required_attrs = intent_requirements.get(intent, [])
        missing = []

        for attr in required_attrs:
            if getattr(self, attr) is None:
                missing.append(attr)

        return missing

    def get_completion_percentage(self, intent: str) -> float:
        """Get completion percentage cho intent"""
        intent_requirements = {
            "calculate_interest": ["amount", "product_type", "term"],
            "open_saving_account": ["amount", "product_type", "term"],
            "inquire_maturity_date": ["saving_account_name"],
            "check_account_balance": ["saving_account_name"],
            "check_interest_earned": ["saving_account_name"],
            "withdraw_principal": ["saving_account_name"],
            "change_interest_payout_method": ["saving_account_name"],
            "terminate_early": ["saving_account_name"],
            "make_additional_deposit": ["saving_account_name"],
            "maturity_notification": ["saving_account_name"],
            "withdraw_principal_interest": ["saving_account_name"]
        }

        required_attrs = intent_requirements.get(intent, [])
        if not required_attrs:
            return 1.0

        completed = sum(1 for attr in required_attrs if getattr(self, attr) is not None)
        return completed / len(required_attrs)

    def validate_amount(self) -> bool:
        """Basic amount validation"""
        if not self.amount or not self.product_type:
            return True  # Skip validation nếu incomplete

        min_amount = self.product_type.get_min_amount()
        return self.amount >= min_amount

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "amount": self.amount,
            "term": self.term,
            "product_type": self.product_type.value if self.product_type else None,
            "saving_account_name": self.saving_account_name
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DepositAttributes':
        """Create from dictionary"""
        attrs = cls()

        if data.get('amount'):
            attrs.amount = float(data['amount'])

        if data.get('term'):
            attrs.term = int(data['term'])

        if data.get('product_type'):
            attrs.product_type = DepositProductType(data['product_type'])

        if data.get('saving_account_name'):
            attrs.saving_account_name = data['saving_account_name']

        return attrs

    def __str__(self) -> str:
        """String representation for debugging"""
        parts = []
        if self.amount:
            parts.append(f"Amount: {self.amount:,.0f} VND")
        if self.product_type:
            parts.append(f"Type: {self.product_type.get_display_name()}")
        if self.term:
            parts.append(f"Term: {self.term}")
        if self.saving_account_name:
            parts.append(f"Account: {self.saving_account_name}")

        return f"DepositAttributes({', '.join(parts)})" if parts else "DepositAttributes(empty)"