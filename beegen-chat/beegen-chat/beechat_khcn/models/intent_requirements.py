"""
Central configuration cho intent requirements
Thay thế tất cả duplicated definitions
"""

from beechat_khcn.models.balance_retrieve_model import BalanceIntent
from beechat_khcn.models.conversation_model import DepositIntent


class IntentRequirements:
    """Single source of truth cho intent requirements"""

    BALANCE_REQUIREMENTS = {
        BalanceIntent.QUERY_TRANSACTION_NORMAL: ["account_number", "from_date", "to_date"],
        BalanceIntent.QUERY_TRANSACTION_DESCRIPTIVE: ["account_number", "from_date", "to_date"],
        BalanceIntent.QUERY_TRANSACTION_BY_TYPE: ["account_number", "transaction_type"],
        BalanceIntent.QUERY_TRANSACTION_BY_AMOUNT: ["account_number", "min_amount", "max_amount"],
        BalanceIntent.QUERY_TRANSACTION_BY_BENEFICIARY: ["account_number", "beneficiary_name"],
        BalanceIntent.QUERY_TRANSACTION_BY_CHANNEL: ["account_number", "channel"],
        BalanceIntent.QUERY_TRANSACTION_EXPORT: ["account_number", "from_date", "to_date", "export_format"],
        BalanceIntent.INITIATE_TRANSACTION_DISPUTE: ["account_number", "transaction_type"]
    }

    DEPOSIT_REQUIREMENTS = {
        DepositIntent.CALCULATE_INTEREST: ['amount', 'term', 'product_type'],
        DepositIntent.OPEN_SAVING_ACCOUNT: ['amount', 'term', 'product_type'],
        DepositIntent.INQUIRE_INTEREST_RATES: [],
        DepositIntent.INQUIRE_SAVING_ACCOUNT_TYPES: [],
    }

    @classmethod
    def get_balance_requirements(cls, intent: BalanceIntent) -> list:
        """Get required attributes for balance intent"""
        return cls.BALANCE_REQUIREMENTS.get(intent, [])

    @classmethod
    def get_deposit_requirements(cls, intent: DepositIntent) -> list:
        """Get required attributes for deposit intent"""
        return cls.DEPOSIT_REQUIREMENTS.get(intent, [])