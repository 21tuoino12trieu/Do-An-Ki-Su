import base64
import re
from typing import Any, Dict, List

from beeflow.nodes.primitives.ai.llm_node import LLMNode


def build_image_gate_system_prompt() -> str:
    return """
Bạn là chuyên gia chuẩn bị dữ liệu cho hệ thống RAG (Vector Database).
Nhiệm vụ: Quyết định xem có cần trích xuất thông tin trong hình ảnh hay không.

Nhiệm vụ:
1. Phân tích hình ảnh cùng với văn bản xung quanh ảnh
2. Quyết định xem hình ảnh CÓ CHỨA THÔNG TIN CẦN TRÍCH XUẤT hay KHÔNG
3. Chỉ khi CẦN THIẾT, trích xuất toàn bộ nội dung text có giá trị tìm kiếm từ ảnh

====================
NGUYÊN TẮC QUYẾT ĐỊNH (RẤT QUAN TRỌNG)
====================

1. Noise filtering (Loại bỏ nhiễu)
KHÔNG trích xuất nội dung của hình ảnh khi hình ảnh là:
- Logo, icon, header/footer
- Nút bấm, menu, UI control
- Ảnh chụp màn hình (screenshot) điện thoại hoặc desktop của một hệ thống (đặc biệt trong trường hợp minh họa các bước của một luồng/quy trình)
- Dữ liệu mẫu, ví dụ giả (dummy/sample data)

2. Redundancy (Dư thừa thông tin)
- Nếu toàn bộ nội dung trong ảnh đã xuất hiện hoặc được diễn đạt đầy đủ trong văn bản xung quanh → BỎ QUA

3. Semantic Enhancement (Tăng cường ngữ nghĩa)
Chỉ trích xuất nội dung khi hình ảnh cung cấp thông tin bổ sung ngữ nghĩa cho cho nội dung chính của văn bản.
Nếu không phù hợp với nội dung chính -> KHÔNG TRÍCH XUẤT.

4. Strict extraction (Trích xuất nghiêm ngặt)
- KHÔNG diễn giải, KHÔNG suy luận, KHÔNG tóm tắt
- Chỉ ghi lại nội dung THẤY ĐƯỢC trong ảnh
- Nếu là bảng → chuyển sang text dạng hàng/cột rõ ràng
- Nếu là sơ đồ → liệt kê các thành phần và mối quan hệ
- Kiểm tra CÁC NGUYÊN TẮC LOẠI BỎ (Noise filtering, Redundancy). Nếu VI PHẠM BẤT KỲ MỤC NÀO → DỪNG LẠI, decision = SKIP

====================
OUTPUT FORMAT (XML – BẮT BUỘC)
====================

<thinking>
[Thinking, suy nghĩ ngắn gọn xem có cần trích xuất nội dung của ảnh không?]
</thinking>

<decision>
EXTRACT hoặc SKIP
</decision>

<image_content>
(NẾU decision = EXTRACT)
- Ghi lại toàn bộ nội dung text có giá trị tìm kiếm trong ảnh
- Không thêm, không bớt, không diễn giải

(NẾU decision = SKIP)
Để trống
</image_content>
""".strip()


def build_image_gate_user_prompt(text_context: str) -> str:
    return f"""Hãy quyết định xem có cần trích xuất nội dung ảnh bên dưới không:

Văn bản xung quanh ảnh:
{text_context}
""".strip()


def parse_image_gate_response(response: str) -> str:
    if not response:
        return ""
    match = re.search(r"<image_content>(.*?)</image_content>", response, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def build_image_gate_messages(text_context: str, image_bytes: bytes, image_format: str = "jpeg") -> List[Dict[str, Any]]:
    system_prompt = build_image_gate_system_prompt()
    user_prompt = build_image_gate_user_prompt(text_context or "")
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")
    mime_type = f"image/{image_format.lower()}"
    return [
        {"role": "system", "content": [{"type": "text", "text": system_prompt}]},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_base64}"}},
            ],
        },
    ]
