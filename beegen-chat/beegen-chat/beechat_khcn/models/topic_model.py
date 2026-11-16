from enum import Enum


class TopicCategory(Enum):
    """Topic classification - bước đầu tiên"""
    DEPOSIT = "deposit"
    CARD = "card"
    BALANCE_RETRIEVE = "balance_retrieve"
    TOTAL_REVENUE = "total_revenue"
    CHITCHAT = "chitchat"
    LOAN_MANAGEMENT = "loan_management"

    @classmethod
    def get_display_name(cls, topic) -> str:
        """Get Vietnamese display name"""
        names = {
            cls.LOAN_MANAGEMENT: "Quản lý khoản vay",
            cls.DEPOSIT: "Tiền gửi số",
            cls.CARD: "Thẻ ngân hàng",
            cls.BALANCE_RETRIEVE: "Tra cứu giao dịch",
            cls.TOTAL_REVENUE: "Tổng tài sản",
            cls.CHITCHAT: "Trò chuyện"
        }
        return names.get(topic, topic.value if hasattr(topic, 'value') else str(topic))