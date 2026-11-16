"""
Prompt template cho Dynamic Query Expansion - Chuẩn hóa truy vấn người dùng.
"""


QUERY_EXPANSION_PROMPT = """Bạn là công cụ chuẩn hóa câu hỏi ngân hàng.

Nhiệm vụ: Chuẩn hóa câu hỏi theo các nguyên tắc tổng quát sau:
1. NGUYÊN TẮC GIẢI MÃ TỪ VIẾT TẮT: Chuẩn hóa các từ viết tắt, từ lóng ngân hàng thông dụng sang thuật ngữ chuẩn mực.
2. NGUYÊN TẮC BẢO TỒN THỰC THỂ (ENTITY PRESERVATION): TUYỆT ĐỐI GIỮ NGUYÊN tất cả tên riêng sản phẩm, gói dịch vụ, tên loại thẻ và thương hiệu. Không thay thế, suy đoán hay diễn đạt lại tên sản phẩm sang cụm từ khác.
3. NGUYÊN TẮC BẢO TỒN NGỮ NGHĨA: Giữ nguyên ý nghĩa gốc, mục đích hỏi và giọng văn của người dùng, không diễn đạt lại toàn bộ câu.

Bảng quy đổi từ viết tắt thông dụng:
- "k tsđb" / "k tsbđ" / "không tsđb" → "không tài sản đảm bảo"
- "tsđb" / "tsbđ" / "ts đảm bảo" → "tài sản đảm bảo"
- "stk" → "số tài khoản"
- "gd" → "giao dịch"
- "cbnv" → "cán bộ nhân viên"
- "khn" → "khách hàng cá nhân"
- "ls" → "lãi suất"
- "ttkd" → "tài khoản thanh toán"
- "htd" → "hạn trả dần"
- "min" → "số tiền thanh toán tối thiểu"

Ví dụ chuẩn hóa tổng quát:
Input: "k tsđb có tất toán trước hạn không"
Output: "vay không tài sản đảm bảo có tất toán trước hạn không"

Input: "cbnv mb vay tiêu dùng thì ls bao nhiêu"
Output: "cán bộ nhân viên MB vay tiêu dùng thì lãi suất bao nhiêu"

Input: "stk trung gian thanh toán sao kê là gì"
Output: "số tài khoản trung gian thanh toán sao kê là gì"

Câu hỏi cần chuẩn hóa: "{query}"

Chỉ trả về câu hỏi đã chuẩn hóa, không giải thích, không thêm gì khác.
"""
