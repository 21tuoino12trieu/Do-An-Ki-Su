"""
Package prompts chứa các template prompt được sử dụng trong ứng dụng BeeChat.
Các prompt được tổ chức theo chức năng để dễ quản lý và cập nhật.
"""

# Import các prompt từ các module con để có thể truy cập trực tiếp từ package
from .analysis_prompts import (
    ANALIZE_DEPOSIT_TOPIC_PROMPT,
    ANALIZE_BALANCE_TOPIC_PROMPT,
    ANALIZE_CARD_TOPIC_PROMPT

)


from .content_filter_prompts import (
    CONTENT_FILTER_PROMPT,
    REFUSAL_MESSAGES
)

from .document_prompts import (
    QA_FILTER_PROMPT
)

