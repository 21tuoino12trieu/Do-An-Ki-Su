from typing import List, Dict
from beegenerate.tools.function_tool import FunctionTool


def card_retrieval(
    query: str,
    topics: List[str]
) -> List:
    r"""
    Retrieves relevant card documents based on semantic search for RAG-based generation.

    This function performs semantic search against a collection of card-related documents,
    filtering by both the search query and specified topics.

    Args:
        query (str): The short search-optimized query in Vietnamese, refined from the user's question.
        topics (List[str]): all topics that are semantically related to the query.
            Topics MUST be from the predefined list below AND must have semantic relevance to the query intent. For example:
            [    
                "Dịch vụ trả góp qua thẻ tín dụng",
                "Dịch vụ thanh toán thẻ qua Ví Apple Pay",
                "Dịch vụ thanh toán giao dịch quảng cáo bằng thẻ",
                "Thẻ tín dụng quốc tế JCB Credit",
                "Thẻ tín dụng Visa Priority",
                "Thẻ tín dụng Visa Credit",
                "Thẻ tín dụng JCB Ultimate",
                "Thẻ đa năng Hi Slay-dy Mastercard",
                "Thẻ đa năng JCB Hi Collection",
                "Thẻ đa năng JCB Hi Sky",
                "Thẻ đa năng Mastercard Hi Green",
                "Thẻ đa năng Led-Visa Hi Collection",
                "Thẻ đa năng Master Hi League Of Legends (Hi LOL)",
                "Thẻ đa năng - Vòng tay thanh toán Stellar",
                "Thẻ đa năng Visa Hybrid",
                "Thẻ ghi nợ quốc tế Unionpay",
                "Thẻ ghi nợ nội địa Active Plus",
                "Thẻ ghi nợ Visa Debit",
                "Thẻ liên kết MB - Hi Shopee Food (JCB)"
            ]

    Returns:
        List: Retrieved card documents matching the query and selected topics.
    """
    pass


def common_retrieval(
   query: str
) -> List:
    r"""
    Performs semantic search over general banking documents and customer resources.

    Serves as a fallback retrieval method when card_retrieval() is not applicable.
    Searches across these categories:
        - Định danh (Identity Verification Guides)
        - Thẻ (Cards)
        - Ngân hàng điện tử (Digital Banking)
        - Top các nhu cầu của khách hàng (Top Customer Needs)
        - Vay online (Online Loans)

    Args:
        query (str): Search query (refined from user question, in Vietnamese) to match against the document collection.

    Returns:
        List: Retrieved documents matching the query.
    """
    pass


def general_chat(
    query: str
) -> Dict[str, str]:
    r"""
    Handles casual conversations and non-banking related queries.

    This function provides appropriate responses for:
        - Greetings and farewells
        - Small talk
        - Personal questions
        - Emotional expressions
        - General questions not related to banking services

    Args:
        query (str): The user's conversational input in Vietnamese.
    """
    pass


bee247_tools = [
    FunctionTool(card_retrieval),
    FunctionTool(common_retrieval),
    FunctionTool(general_chat)
]