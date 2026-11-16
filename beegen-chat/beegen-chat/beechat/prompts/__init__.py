"""
Package prompts chứa các template prompt được sử dụng trong ứng dụng BeeChat.
Các prompt được tổ chức theo chức năng để dễ quản lý và cập nhật.
"""

# Import các prompt từ các module con để có thể truy cập trực tiếp từ package
from .analysis_prompts import (
    ANALIZE_TOPIC_AND_SENTIMENT_PROMPT,
    CONVERSATION_ANALYSIS_PROMPT,
)

from .card_prompts import (
    CARD_KEYWORD_EXTRACT_PROMPT_V2
)

from .chat_prompts import (
    CHIT_CHAT,
    DESCRIPTION_BEE_PROMPT,
    PROMPT_REFUSE,
    VERBATIM_PROMPT
)

from .content_filter_prompts import (
    CONTENT_FILTER_PROMPT,
    REFUSAL_MESSAGES
)

from .document_prompts import (
    QA_FILTER_PROMPT
)

from .location_prompts import (
    DOCUMENT_TEXT_KEYWORD_EXTRACT_PROMPT,
    DOCUMENT_TEXT_PROMPT,
    ATM_TEXT_PROMPT
)

from .rag_prompts import (
    NORMAL_RAG_ANSWER_PROMPT,
    EMB_RAG_ANSWER_PROMPT,
    EKYC_RAG_ANSWER_PROMPT,
    QA_RESPONSE_PROMPT,
    CARD_RAG_ANSWER_PROMPT
)

from .scenarios.atm_withdrawal_dispute import *
from .scenarios.card_swallowed import *
from .scenarios.check_card_delivery_status import *
from .scenarios.check_credit_card_statement_payment import *
from .scenarios.check_failed_card_transaction import *
from .scenarios.check_failed_refund_to_account import *
from .scenarios.early_installment_settlement import *
from .scenarios.online_payment_dispute import *
from .scenarios.pos_transaction_dispute import *
from .scenarios.unknown_transaction_dispute import *

from .query_expansion_prompts import (
    QUERY_EXPANSION_PROMPT
)

from .fact_verification_prompts import (
    FACT_GROUNDING_VERIFICATION_PROMPT
)