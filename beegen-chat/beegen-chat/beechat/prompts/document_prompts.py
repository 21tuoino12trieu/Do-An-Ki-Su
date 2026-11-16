"""
Các prompt template liên quan đến kiểm tra và xác minh tài liệu trong ứng dụng BeeChat.
"""

QA_FILTER_PROMPT = """
Vai trò: Chuyên gia phân tích mức độ khớp giữa câu hỏi và nội dung văn bản
Nhiệm vụ: 
1. So sánh câu hỏi người dùng với tài liệu QA
2. Đánh giá độ khớp theo 4 yếu tố cụ thể với nguyên tắc NGHIÊM NGẶT về phạm vi sản phẩm
3. Tính điểm tin cậy (confidence) từ 0.0 đến 1.0

THÔNG TIN ĐẦU VÀO:
- Câu hỏi gốc: Câu hỏi ban đầu từ người dùng
- Câu hỏi đã cải thiện: Câu hỏi sau khi được phân tích ngữ cảnh và làm rõ
- Ưu tiên sử dụng câu hỏi đã cải thiện để đánh giá, nhưng tham khảo câu hỏi gốc để hiểu ý định người dùng

CÔNG THỨC TÍNH ĐIỂM TIN CẬY:
- MỤC ĐÍCH câu hỏi: tối đa 0.4 điểm (40%)
- HÀNH ĐỘNG chính: tối đa 0.3 điểm (30%)
- ĐỐI TƯỢNG chính: tối đa 0.2 điểm (20%)
- PHƯƠNG THỨC thực hiện: tối đa 0.1 điểm (10%)
- Tổng điểm tối đa: 1.0 (100%)

YẾU TỐ 1: MỤC ĐÍCH CÂU HỎI (40%)
Phân loại chính xác:
- Quy trình/cách thức: "làm thế nào", "các bước", "hướng dẫn", "thao tác ra sao"
- Thời gian: "mất bao lâu", "khi nào", "bao nhiêu ngày", "thời hạn", "ngày sao kê"
- Chi phí: "phí là gì", "tốn bao nhiêu", "giá", "lãi suất"
- Điều kiện/Hạn mức: "cần những gì", "yêu cầu", "điều kiện", "có thể không", "được cấp hạn mức"
- Tình trạng: "đang ở trạng thái nào", "hoạt động không"

Nếu MỤC ĐÍCH giữa câu hỏi và tài liệu:
- Hoàn toàn giống nhau: 0.4 điểm
- Tương đối giống nhau: 0.2-0.3 điểm
- Hoàn toàn khác nhau: 0.0 điểm

YẾU TỐ 2: HÀNH ĐỘNG CHÍNH (30%)
Phân loại hành động rõ ràng:
- Đăng ký/mở: "mở thẻ", "đăng ký", "tạo tài khoản", "phát hành"
- Hủy/đóng/xóa: "hủy thẻ", "đóng tài khoản", "khóa", "ngừng"
- Kích hoạt: "kích hoạt", "mở khóa", "bắt đầu sử dụng"
- Sử dụng: "sử dụng", "thanh toán", "giao dịch"
- Cấp/Được cấp: "được cấp", "cấp phát", "tăng hạn mức"

Nếu HÀNH ĐỘNG giữa câu hỏi và tài liệu:
- Hoàn toàn giống nhau: 0.3 điểm
- Tương đối liên quan: 0.1-0.2 điểm
- Trái ngược hoàn toàn: 0.0 điểm

YẾU TỐ 3: ĐỐI TƯỢNG CHÍNH (20%) - NGUYÊN TẮC NGHIÊM NGẶT VỀ PHẠM VI SẢN PHẨM
3.1. PHÂN CẤP ĐỐI TƯỢNG:
Cấp 1 - Loại sản phẩm tổng quát:
- "thẻ", "thẻ ngân hàng", "tài khoản"

Cấp 2 - Loại sản phẩm theo chức năng:
- "thẻ tín dụng", "thẻ ghi nợ", "thẻ đa năng"

Cấp 3 - Loại sản phẩm theo thương hiệu:
- "thẻ visa", "thẻ jcb", "thẻ mastercard"

Cấp 4 - Sản phẩm cụ thể theo thương hiệu + chức năng:
- "thẻ visa credit", "thẻ visa debit", "thẻ jcb credit"

Cấp 5 - Sản phẩm cụ thể với đặc tính:
- "thẻ visa infinite", "thẻ tín dụng 0 đồng", "thẻ tín dụng có phí"

Cấp 6 - Dòng sản phẩm đặc biệt:
- "Hi Collection", "Hi LED", "thẻ platinum"

3.2. QUY TẮC NGHIÊM NGẶT TÍNH ĐIỂM ĐỐI TƯỢNG:

a) Hoàn toàn giống nhau (cùng cấp, cùng loại): 0.2 điểm
   Ví dụ: "thẻ visa credit" vs "thẻ visa credit"

b) **TRƯỜNG HỢP KHÁC PHẠM VI - ĐIỂM THẤP BẮT BUỘC:**

   b1) Câu hỏi CHUNG, tài liệu CỤ THỂ (khác phạm vi): TỐI ĐA 0.05 điểm
   Ví dụ: 
   - "phí thường niên thẻ visa" vs "phí thường niên thẻ visa credit" → 0.05 điểm
   - "cách mở thẻ tín dụng" vs "cách mở thẻ tín dụng 0 đồng" → 0.05 điểm
   - "thẻ visa" vs "thẻ visa infinite" → 0.05 điểm

   b2) Câu hỏi CỤ THỂ, tài liệu CHUNG (khác phạm vi): TỐI ĐA 0.03 điểm
   Ví dụ:
   - "phí thường niên thẻ visa credit" vs "phí thường niên thẻ visa" → 0.03 điểm
   - "cách mở thẻ tín dụng 0 đồng" vs "cách mở thẻ tín dụng" → 0.03 điểm

c) **TRƯỜNG HỢP KHÁC LOẠI SẢN PHẨM - ĐIỂM RẤT THẤP:**

   c1) Cùng cấp nhưng khác thương hiệu: TỐI ĐA 0.02 điểm
   Ví dụ: 
   - "thẻ visa credit" vs "thẻ jcb credit" → 0.02 điểm
   - "thẻ mastercard" vs "thẻ visa" → 0.02 điểm

   c2) Cùng cấp nhưng khác chức năng: TỐI ĐA 0.01 điểm
   Ví dụ:
   - "thẻ visa credit" vs "thẻ visa debit" → 0.01 điểm
   - "thẻ tín dụng" vs "thẻ ghi nợ" → 0.01 điểm

d) Hoàn toàn khác nhau (khác loại sản phẩm): 0.0 điểm
   Ví dụ: "thẻ tín dụng" vs "tài khoản tiết kiệm"

3.3. VÍ DỤ PHÂN TÍCH CỤ THỂ VỚI ĐIỂM THẤP:

Ví dụ 1: 
- Câu hỏi: "phí thường niên thẻ visa" (Cấp 3 - chung)
- Tài liệu: "phí thường niên thẻ visa credit" (Cấp 4 - cụ thể)
- Phân tích: Khác phạm vi (chung vs cụ thể) → 0.05 điểm

Ví dụ 2:
- Câu hỏi: "cách mở thẻ tín dụng" (Cấp 2 - chung)
- Tài liệu: "cách mở thẻ tín dụng 0 đồng" (Cấp 5 - cụ thể)
- Phân tích: Khác phạm vi (chung vs cụ thể) → 0.05 điểm

Ví dụ 3:
- Câu hỏi: "phí thường niên thẻ visa credit" (Cấp 4)
- Tài liệu: "phí thường niên thẻ jcb credit" (Cấp 4)
- Phân tích: Cùng cấp nhưng khác thương hiệu → 0.02 điểm

YẾU TỐ 4: PHƯƠNG THỨC THỰC HIỆN (10%)
Phân loại kênh/phương thức:
- Kênh số: "App MB Bank", "Internet Banking", "SMS Banking", "QR Code"
- Kênh vật lý: "tại quầy", "tại chi nhánh", "ATM", "SmartBank"
- Nền tảng: "trên Android", "trên iOS", "trên website"

Nếu PHƯƠNG THỨC giữa câu hỏi và tài liệu:
- Hoàn toàn giống nhau: 0.1 điểm
- Khác nhau: 0.0 điểm

CÁC ĐIỀU KIỆN ĐẶC BIỆT (ưu tiên cao nhất):

1. **ĐIỀU KIỆN PHẠM VI SẢN PHẨM NGHIÊM NGẶT:**
   - Nếu câu hỏi và tài liệu có sự KHÁC BIỆT VỀ PHẠM VI sản phẩm: ĐIỂM TỐI ĐA = 0.4
   - Ví dụ: "thẻ visa" vs "thẻ visa credit" → điểm tối đa = 0.4

2. Nếu MỤC ĐÍCH khác nhau hoàn toàn:
   - ĐIỂM TỐI ĐA = 0.4 (dù các yếu tố khác giống)
   - Ví dụ: "Phí thường niên thẻ là bao nhiêu?" vs "Hướng dẫn mở thẻ"

3. Nếu HÀNH ĐỘNG trái ngược nhau:
   - ĐIỂM TỐI ĐA = 0.5 (dù các yếu tố khác giống)
   - Ví dụ: "Cách hủy thẻ tín dụng" vs "Đăng ký thẻ tín dụng"

4. Nếu ĐỐI TƯỢNG là cùng cấp nhưng khác loại cụ thể:
   - ĐIỂM TỐI ĐA = 0.6 (trừ điểm đối tượng = 0)
   - Ví dụ: "thẻ visa credit" vs "thẻ jcb credit"

5. Nếu tài liệu QA KHÔNG CHỨA thông tin trả lời câu hỏi:
   - TRỪ 0.3 từ điểm tổng
   - Ví dụ: Hỏi về phí nhưng tài liệu chỉ nói về tính năng

**THANG ĐIỂM TIN CẬY VỚI NGƯỠNG NGHIÊM NGẶT:**
- 0.9-1.0: Khớp gần như hoàn hảo (chỉ khi hoàn toàn giống nhau)
- 0.7-0.8: Khớp tốt, đáp ứng được câu hỏi (cùng phạm vi, cùng mục đích)
- 0.5-0.6: Khớp một phần, có thể trả lời được phần nào
- 0.3-0.4: Khớp ít, khó đáp ứng câu hỏi (khác phạm vi sản phẩm)
- 0.0-0.2: Không khớp, không thể trả lời (khác loại sản phẩm hoặc mục đích)

NGƯỠNG QUYẾT ĐỊNH: 0.7 (thiết lập trong hệ thống)
- Nếu confidence ≥ 0.7: Hệ thống sẽ sử dụng câu trả lời
- Nếu confidence < 0.7: Hệ thống bỏ qua câu trả lời

Lưu ý đặc biệt:
- Hủy tài khoản/thẻ = đóng tài khoản/thẻ = xóa tài khoản/thẻ
- Lịch sử giao dịch == lịch sử chuyển tiền, thông báo chuyển khoản = thông báo số dư
- Mặc định các hành vi như mua vé xem phim, thanh toán hóa đơn, đặt vé máy bay, ... được thực hiện trên app MB
- **QUAN TRỌNG:** Khác phạm vi sản phẩm (chung vs cụ thể) luôn dẫn đến điểm thấp (<0.7)

Trả về chính xác điểm tin cậy dưới dạng XML sau khi tính toán cẩn thận, không đưa ra bất cứ suy luận/ phân tích nào khác:
<confidence>0.0 đến 1.0</confidence>

Câu hỏi gốc của người dùng: {question}
Câu hỏi đã được cải thiện: {enhanced_question}
Tài liệu QA: {document}
"""

DOCUMENT_RELEVANCE_CHECK_PROMPT = """
Vai trò: Chuyên gia đánh giá tính liên quan giữa tài liệu và câu hỏi

Nhiệm vụ: Phân tích KỸ LƯỠNG xem tài liệu có CHỨA BẤT KỲ THÔNG TIN HỮU ÍCH nào để trả lời câu hỏi không

Quy trình phân tích nội bộ:
1. Đọc và hiểu rõ yêu cầu từ câu hỏi của người dùng
2. Xác định các thông tin có thể hữu ích để trả lời câu hỏi
3. Kiểm tra xem tài liệu CÓ CHỨA bất kỳ thông tin hữu ích nào không
4. Đánh giá xem tài liệu có thể đóng góp gì cho câu trả lời

QUAN TRỌNG: Áp dụng tiêu chí RỘNG RÃI - nếu tài liệu có BẤT KỲ thông tin nào liên quan đến chủ đề của câu hỏi, coi là CÓ LIÊN QUAN.

Tiêu chí đánh giá:
- Tài liệu chỉ cần chứa TỪNG PHẦN thông tin hữu ích, không cần đầy đủ
- Tài liệu có thể chỉ liên quan GIÁN TIẾP và vẫn được coi là có liên quan
- Tài liệu có thể chứa thuật ngữ, khái niệm, hoặc ngữ cảnh tương tự và vẫn được coi là có liên quan
- CHỈ loại bỏ tài liệu nếu HOÀN TOÀN không liên quan đến câu hỏi
- Các trường hợp sau được coi là KHÔNG CÓ TÀI LIỆU LIÊN QUAN:
  * Tài liệu chỉ chứa "không tìm thấy tài liệu phù hợp"
  * Tài liệu hoàn toàn về một chủ đề khác, không có liên hệ nào với câu hỏi

QUY TẮC XỬ LÝ CÁC TRƯỜNG HỢP ĐẶC BIỆT:
1. Đối với câu hỏi về ĐIỀU KIỆN NGƯỜI DÙNG (độ tuổi, tình trạng, v.v.) mà tài liệu có hướng dẫn quy trình:
   - Coi tài liệu LÀ LIÊN QUAN nếu nó chứa quy trình cơ bản, ngay cả khi không đề cập điều kiện cụ thể
   - Ví dụ: Câu hỏi về "chuyển tiền khi dưới 18 tuổi" và tài liệu có hướng dẫn chuyển tiền → CÓ liên quan

2. Đối với câu hỏi về QUY TRÌNH mà tài liệu chỉ đề cập một phần:
   - Coi tài liệu LÀ LIÊN QUAN nếu nó chứa thông tin về quy trình tổng thể, ngay cả khi không có chi tiết đầy đủ
   - Ví dụ: Câu hỏi về "cách mở thẻ tín dụng online" và tài liệu đề cập quy trình mở thẻ → CÓ liên quan

3. Đối với câu hỏi về MỘT SẢN PHẨM CỤ THỂ mà tài liệu đề cập tổng quát:
   - Coi tài liệu LÀ LIÊN QUAN nếu nó chứa thông tin về nhóm sản phẩm đó, ngay cả khi không đề cập chính xác sản phẩm
   - Ví dụ: Câu hỏi về "thẻ Visa Infinite" và tài liệu nói về thẻ Visa nói chung → CÓ liên quan

Lưu ý: Nếu câu hỏi không nhắc đến cụ thể sản phẩm dịch vụ nào, mặc định nó của MBBank
QUAN TRỌNG: Chỉ trả về 1 từ "có" hoặc "không" theo định dạng sau:
có/không

Câu hỏi: {question}

Tài liệu:
{documents}
"""