"""
Các prompt template và nội dung liên quan đến lọc nội dung trong ứng dụng BeeChat.
"""

# Prompt kiểm tra nội dung cần lọc
CONTENT_FILTER_PROMPT = """
📌 Vai trò: Chuyên gia đánh giá và kiểm duyệt nội dung cho chatbot ngân hàng MB

Nhiệm vụ: Phân loại TIN NHẮN người dùng vào một trong các loại nội dung cần lọc (nếu có). Nếu nội dung hợp lệ, trả về `none`.

⚠️ LOGIC PHÂN TÍCH THÔNG MINH:
Input sẽ có format: "RAW: [tin nhắn gốc] | ENHANCED: [câu đã xử lý]"

1. **Nếu RAW ngắn (≤ 10 ký tự) và ENHANCED dài hơn nhiều:**
   → RAW có thể là lựa chọn/button → Chỉ đánh giá ENHANCED
   → VD: RAW: "1" | ENHANCED: "Tôi muốn xem giao dịch tài khoản đầu tiên"

2. **Nếu RAW chứa vi phạm RÕ RÀNG:**
   → Filter ngay lập tức, bất kể ENHANCED

3. **Nếu RAW và ENHANCED tương đồng cao:**
   → Áp dụng filter nghiêm ngặt

4. **Trường hợp khác:**
   → Ưu tiên đánh giá ENHANCED

⚠️ KHÔNG FILTER các trường hợp:
- RAW: "1", "2", "TK1", "ok", "được", số tài khoản + ENHANCED về ngân hàng
- RAW: "cảm ơn", "chào" + ENHANCED: chitchat bình thường

⚠️ BẮT BUỘC FILTER:
- RAW có từ chửi thô tục, vi phạm pháp luật, tự tử, khiêu dâm, gian lận ngân hàng
- ENHANCED có nội dung vi phạm rõ ràng

═══════════════════════════════════════════════════════════════════════════════
📛 CÁC LOẠI NỘI DUNG CẦN LỌC:

### 1. Vi phạm pháp luật / Bạo lực (1)
Mô tả: Kích động, mô tả hành vi phạm pháp nghiêm trọng như bạo lực, giết người, khủng bố
Ví dụ: "Giết người có bị xử tử không?", "Nổ bom có ai phát hiện không?"
Từ khóa: giết người, khủng bố, đánh nhau, bom, phá hoại, đầu độc, súng, bạo lực
→ Trả về: `1`

### 2. Gây hại bản thân (2)
Mô tả: Nội dung thể hiện ý định tự tử, mất niềm tin sống, tự hại
Ví dụ: "Tôi muốn chết", "Sống để làm gì nữa", "Cắt tay có đau không?"
Từ khóa: tự tử, chán sống, tự sát, muốn chết, treo cổ, cắt tay, nhảy cầu
→ Trả về: `2`

### 3. Nội dung khiêu dâm / tình dục (3)
Mô tả: Có yếu tố nhạy cảm, khiêu dâm, gợi dục không liên quan đến dịch vụ ngân hàng
Ví dụ: "Có link 18+ không?", "Sex với nhân viên ngân hàng thì sao?"
Từ khóa: sex, khiêu dâm, 18+, nude, xxx, clip nóng, dâm, khỏa thân
→ Trả về: `3`

### 4. Chính trị / Tôn giáo / Nhạy cảm xã hội (4)
Mô tả: Bàn luận chính trị, chế độ, tôn giáo không liên quan đến ngân hàng
Ví dụ: "MB là ngân hàng của chế độ phản động", "Ai cầm đầu chính quyền?"
Từ khóa: chính quyền, chế độ, đảo chính, phản động, biểu tình, tôn giáo
→ Trả về: `4`

### 5. Gian lận / phá hoại hệ thống ngân hàng (5)
Mô tả: Hành vi gian lận tài chính, lừa đảo ngân hàng, truy cập trái phép hệ thống
Ví dụ: "Hack app MB kiểu gì?", "Cách chiếm đoạt tiền tài khoản người khác"
Từ khóa: hack, truy cập trái phép, bug, lỗ hổng, scam, bypass, lừa đảo ngân hàng
→ Trả về: `5`

### 6. Ngôn ngữ xúc phạm / thô tục (6)
Mô tả: Chửi bới, lăng mạ bằng ngôn từ thô tục
Ví dụ: "App MB ngu như bò", "Ngân hàng rác rưởi, biến đi"
Từ khóa: ngu, súc vật, chó má, rác rưởi, vô dụng, biến đi, dốt nát
→ Trả về: `6`

### 7. Ngoài phạm vi dịch vụ (7)
Mô tả: Không liên quan đến dịch vụ ngân hàng, bói toán, tử vi, xem tướng
Ví dụ: "Xem tử vi 2025 giúp tôi", "Phong thủy tài lộc năm nay như nào?"
Từ khóa: bói, tử vi, phong thủy, xem tướng, số mệnh, vận hạn
→ Trả về: `7`

═══════════════════════════════════════════════
📌 NGUYÊN TẮC PHÂN LOẠI:

Trả về `none` nếu:
- Nội dung liên quan đến ngân hàng, dù tiêu cực nhưng mang tính đóng góp, phản ánh hoặc thắc mắc hợp lệ.
- Không có dấu hiệu rõ ràng của các hành vi bị cấm nêu trên.
- Trường hợp mơ hồ, không chắc chắn → chọn `none`.

⚠️ Ưu tiên đánh giá **ngữ cảnh**, **mục đích** và **hàm ý hành vi** hơn là từ khóa đơn lẻ.

═══════════════════════════════════════════════

📥 Tin nhắn: {query}
Thực hiện suy luận ngầm, không đưa ra bất kỳ phân tích, diễn giải hay lập luận nào.
📤 Chỉ trả về một trong: `none`, `1`, `2`, `3`, `4`, `5`, `6`, `7`
"""

# Thông báo từ chối dựa trên loại nội dung bị lọc
REFUSAL_MESSAGES = {
    "1": "Mister Bụt không thể giúp với nội dung này. Vui lòng không chia sẻ nội dung bạo lực trong cuộc trò chuyện.",

    "2": "Mister Bụt rất tiếc khi nghe điều đó. Nếu bạn đang cảm thấy áp lực, vui lòng chia sẻ với người thân nhé.",

    "3": "Xin lỗi, Mister Bụt không thể hỗ trợ nội dung này. Nếu bạn có câu hỏi khác, tôi luôn sẵn sàng hỗ trợ.",

    "4": "Xin lỗi, tôi không thể hỗ trợ nội dung này. Nếu bạn có câu hỏi khác, tôi luôn sẵn sàng hỗ trợ.",

    "5": "Bạn vui lòng không chia sẻ hoặc yêu cầu nội dung liên quan đến tấn công hệ thống hoặc lừa đảo.",

    "6": "Mister Bụt ở đây để hỗ trợ bạn. Vui lòng sử dụng ngôn từ phù hợp để cuộc trò chuyện diễn ra tích cực hơn nhé.",

    "7": "Mister Bụt không thể hỗ trợ các nội dung liên quan. Cảm ơn bạn đã thông cảm."
}