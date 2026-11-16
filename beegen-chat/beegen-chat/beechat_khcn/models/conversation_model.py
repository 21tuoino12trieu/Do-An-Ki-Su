"""
Simplified conversation models - chỉ giữ DepositIntent enum
Loại bỏ complex conversation state management
"""

from enum import Enum


class DepositIntent(Enum):
    """Intent definitions theo customer journey stages"""

    # PRE-OPENING STAGE
    INQUIRE_SAVING_ACCOUNT_TYPES = "inquire_saving_account_types"
    INQUIRE_INTEREST_RATES = "inquire_interest_rates"
    CALCULATE_INTEREST = "calculate_interest"
    OPEN_SAVING_ACCOUNT = "open_saving_account"
    ELIGIBILITY_CRITERIA = "eligibility_criteria"
    PROMOTION_INQUIRY = "promotion_inquiry"

    COMPARE_PRODUCTS = "compare_products"
    REQUEST_PERSONALIZED_RECOMMENDATION = "request_personalized_recommendation"

    # DURING HOLDING PERIOD
    INQUIRE_MATURITY_DATE = "inquire_maturity_date"
    CHECK_ACCOUNT_BALANCE = "check_account_balance"
    CHECK_INTEREST_EARNED = "check_interest_earned"
    WITHDRAW_PRINCIPAL = "withdraw_principal"
    CHANGE_INTEREST_PAYOUT_METHOD = "change_interest_payout_method"
    TERMINATE_EARLY = "terminate_early"
    MAKE_ADDITIONAL_DEPOSIT = "make_additional_deposit"

    # AT/AFTER MATURITY
    MATURITY_NOTIFICATION = "maturity_notification"
    WITHDRAW_PRINCIPAL_INTEREST = "withdraw_principal_interest"

    REQUEST_REINVESTMENT_OPTIONS = "request_reinvestment_options"

    SPECIFIC_CARD = "specific_card"
    GENERIC_CARD = "generic_card"

    # NON-BANKING
    CHITCHAT = "chitchat"

    @classmethod
    def get_stage(cls, intent) -> str:
        """Get customer journey stage"""
        pre_opening = {
            cls.INQUIRE_SAVING_ACCOUNT_TYPES, cls.INQUIRE_INTEREST_RATES,
            cls.CALCULATE_INTEREST, cls.OPEN_SAVING_ACCOUNT,
            cls.ELIGIBILITY_CRITERIA, cls.PROMOTION_INQUIRY,
            cls.COMPARE_PRODUCTS, cls.REQUEST_PERSONALIZED_RECOMMENDATION  # 🆕
        }

        during_holding = {
            cls.INQUIRE_MATURITY_DATE, cls.CHECK_ACCOUNT_BALANCE,
            cls.CHECK_INTEREST_EARNED, cls.WITHDRAW_PRINCIPAL,
            cls.CHANGE_INTEREST_PAYOUT_METHOD, cls.TERMINATE_EARLY,
            cls.MAKE_ADDITIONAL_DEPOSIT
        }

        maturity = {
            cls.MATURITY_NOTIFICATION, cls.WITHDRAW_PRINCIPAL_INTEREST,
            cls.REQUEST_REINVESTMENT_OPTIONS  # 🆕
        }
        card_intents = {cls.SPECIFIC_CARD, cls.GENERIC_CARD}

        if intent in pre_opening:
            return "pre_opening"
        elif intent in during_holding:
            return "during_holding"
        elif intent in maturity:
            return "maturity"
        elif intent in card_intents:
            return "card"
        else:
            return "general"

    @classmethod
    def requires_attributes(cls, intent) -> bool:
        """Check if intent requires attribute collection"""
        attribute_required_intents = {
            cls.CALCULATE_INTEREST,
            cls.OPEN_SAVING_ACCOUNT,
            cls.REQUEST_PERSONALIZED_RECOMMENDATION,  # 🆕 Cần preferences
            cls.INQUIRE_MATURITY_DATE,
            cls.CHECK_ACCOUNT_BALANCE,
            cls.CHECK_INTEREST_EARNED,
            cls.WITHDRAW_PRINCIPAL,
            cls.CHANGE_INTEREST_PAYOUT_METHOD,
            cls.TERMINATE_EARLY,
            cls.MAKE_ADDITIONAL_DEPOSIT,
            cls.MATURITY_NOTIFICATION,
            cls.WITHDRAW_PRINCIPAL_INTEREST,
            cls.REQUEST_REINVESTMENT_OPTIONS  # 🆕 Cần thông tin sổ cũ
        }
        card_intents = {cls.SPECIFIC_CARD, cls.GENERIC_CARD}
        if intent in card_intents:
            return False

        return intent in attribute_required_intents