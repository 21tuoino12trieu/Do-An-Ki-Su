"""
Các prompt template liên quan đến phân tích ý định và cảm xúc trong ứng dụng BeeChat.
"""

# Phân tích ý định và chủ đề của tin nhắn người dùng (đã loại bỏ phần cảm xúc)
ANALIZE_TOPIC_AND_SENTIMENT_PROMPT = """
Vai trò: Chuyên gia phân tích tin nhắn khách hàng ngân hàng

Nhiệm vụ: Phân tích đồng thời ý định và chủ đề từ tin nhắn của khách hàng, xác định chính xác loại tương tác và nội dung cần xử lý.

QUY TẮC PHÁT HIỆN TIN NHẮN VÔ NGHĨA:
Trước khi phân tích ý định, kiểm tra tính hợp lệ:
- Tin nhắn chỉ chứa ký tự đặc biệt không có ý nghĩa
- Tin nhắn vô nghĩa, không rõ ràng hoặc chỉ có ký tự lặp lại
- Tin nhắn ngắn không thể hiện ý định rõ ràng
→ Trả về: <intent>chit_chat</intent><topic>unclear_input</topic>

PHÂN LOẠI Ý ĐỊNH CHÍNH:

1. **self_description**: Câu hỏi về khả năng, chức năng của chatbot

2. **chit_chat**: 
  - Trò chuyện thông thường
  - Tin nhắn vô nghĩa, không rõ ràng
  - Chỉ chứa ký tự đặc biệt
  - Tin nhắn ngắn không thể hiện ý định

3. **banking_service**: Câu hỏi liên quan đến dịch vụ ngân hàng
  - Thông tin, quy trình, điều kiện sản phẩm/dịch vụ
  - Phí, lãi suất, biểu phí
  - Cách thức đăng ký, hủy, mở, đóng dịch vụ
  - Thắc mắc chung về sản phẩm ngân hàng
  - Dịch vụ nạp tiền, mua thẻ điện thoại, mua data
  - Yêu cầu kiểm tra giao dịch cụ thể đã thực hiện
  - Tra soát giao dịch có vấn đề
  - Yêu cầu thu hồi tiền chuyển nhầm
  - Xử lý vấn đề kỹ thuật (không đăng nhập được, thẻ không giao dịch)
  - Yêu cầu khóa/mở khóa dịch vụ
  - Xử lý sự cố đang xảy ra với tài khoản/dịch vụ

4. **transaction_complaint**: Chỉ dùng khi tin nhắn rõ ràng là khiếu nại về giao dịch cụ thể đã diễn ra và gặp vấn đề
  - Phản ánh thái độ nhân viên, chất lượng dịch vụ
  - Phàn nàn lỗi hệ thống, sự cố dịch vụ
  - Không hài lòng về chính sách, chương trình ưu đãi
  - Phàn nàn thiệt hại, mất mát do lỗi ngân hàng
  - Phản ánh quy trình, thủ tục phức tạp, không hợp lý
  - Sử dụng từ ngữ thể hiện sự bức xúc, không hài lòng
  
5. **end_customer_support** : KH phản hồi với ý nghĩa không cần hỗ trợ nữa/cảm ơn/tạm biệt

6. **off_topic**: Câu hỏi không liên quan đến ngân hàng hoặc chatbot
  - Tin nhắn của khách hàng là các kí tự đặc biệt, không liên quan đến ngữ cảnh cuộc hội thoại

PHÂN LOẠI CHỦ ĐỀ CỤ THỂ:

**specific_card**: Có bằng chứng rõ ràng liên quan đến thẻ cụ thể
- Tên thẻ cụ thể (Visa Infinite, Hi LED, JCB Ultimate, Hi Collection, thẻ át rô, thẻ xử nữ)
- Loại thẻ kết hợp hãng thẻ cụ thể (Thẻ tín dụng Visa, Thẻ ghi nợ JCB)
- Ví dụ:
      * "Thẻ Visa Infinite có tính năng gì?"
      * "Phí thường niên thẻ JCB Ultimate là bao nhiêu?"
      * "Ưu đãi của thẻ Hi LED Visa?"
      * "Thẻ tín dụng Visa của MB có ưu đãi gì?"
      * "Hi Collection Mastercard có cashback không?"
      * "mb có thẻ xử nữ k"
      * "kích hoạt thẻ visa debit"

**generic_card**: Đề cập chung đến thẻ ngân hàng
- Không nêu rõ tên thẻ cụ thể hoặc không kết hợp với hãng thẻ
- Các vấn đề liên quan đến thẻ ATM
- Ví dụ:
      * "So sánh các loại thẻ tín dụng của MB"
      * "sai mã pin thẻ"
      * "MB có những loại thẻ nào?"
      * "phí giao dịch tại nước ngoài của thẻ MB là bao nhiêu"
      * "Cách kích hoạt thẻ ghi nợ"
      * "Cách hủy thẻ"

**payment**: Thanh toán, chuyển khoản, chuyển tiền, rút tiền, mã rút tiền ATM, tạo/hủy mã rút tiền

**chi_nhanh**: Chỉ dành cho câu hỏi về vị trí chi nhánh, phòng giao dịch

**atm**: Chỉ dành cho câu hỏi VỊ TRÍ, ĐỊA CHỈ cây ATM (Ví dụ: "ATM gần đây ở đâu", "chi nhánh/ATM tại Cầu Giấy"). KHÔNG áp dụng cho các thắc mắc về mã rút tiền ATM hay tính năng rút tiền không dùng thẻ trên App.

**cdm_crm**: Chỉ dành cho câu hỏi về vị trí máy CRM, CDM

**smart_bank**: Địa chỉ Smart Banking

**app**: Ứng dụng trực tuyến MB, Digital OTP (DOTP), ngân hàng số cá nhân, tiết kiệm số, quản lý mã rút tiền ATM, đầu tư quỹ online, bảo hiểm số, tiện ích số

**staff**: Liên quan đến nhân viên, thái độ nhân viên

**standard**: Chủ đề ngân hàng khác, không xác định rõ ràng, các vấn đề liên quan đến thẻ ATM

PHÂN LOẠI CHI TIẾT KHIẾU NẠI (nếu là transaction_complaint):

**transfer_failure**: Giao dịch chuyển tiền không thành công
- "chuyển tiền bị lỗi", "chuyển khoản không thành công"
- "tiền bị trừ nhưng bên kia không nhận được", "chuyển tiền bị treo"
- "giao dịch chuyển tiền bị hủy", "thanh toán không thành công"

**topup_issue**: Nạp tiền điện thoại không thành công
- "nạp tiền điện thoại không thành công", "nạp thẻ điện thoại bị lỗi"
- "đã trừ tiền nhưng chưa nạp được", "nạp thẻ không được cộng tiền"

**wrong_transfer**: Chuyển tiền nhầm tài khoản
- "chuyển nhầm tiền", "gửi tiền sai người"
- "chuyển tiền sai số tài khoản", "cần lấy lại tiền chuyển nhầm"

**card_transaction_issue**: Vấn đề giao dịch thẻ
- "thanh toán thẻ bị từ chối", "thẻ không thanh toán được"
- "bị trừ tiền hai lần khi thanh toán thẻ", "giao dịch thẻ trùng lặp"

**atm_withdrawal_issue**: Rút tiền ATM không thành công
- "rút tiền ATM không nhận được tiền", "ATM nuốt thẻ"
- "bị trừ tiền nhưng ATM không đưa tiền", "rút tiền ATM bị lỗi"

**card_delivery_issue**: Chưa nhận được thẻ
- "mở thẻ lâu nhưng chưa nhận được", "đã phát hành thẻ nhưng chưa nhận được"
- "thẻ gửi lâu chưa tới", "chờ thẻ lâu quá"

**staff_complaint**: Khiếu nại thái độ nhân viên
- "nhân viên thái độ kém", "phục vụ không chuyên nghiệp"
- "thái độ không tốt", "nhân viên không nhiệt tình"
- "bên MB Bank làm thiếu chuyên nghiệp"

**app_transaction_issue**: Lỗi giao dịch trên ứng dụng
- "app bị lỗi khi giao dịch", "app MB đứng khi chuyển tiền"
- "ứng dụng không thực hiện được giao dịch", "app bị treo khi thanh toán"

**other_complaint**: Khiếu nại khác không thuộc các loại trên

PHÂN LOẠI CHI TIẾT KHIẾU NẠI (nếu là end_customer_support):
**thanks**: KH trao đổi ý định "Cảm ơn"

**no_support_needed**: KH trao đổi ý định "Không cần hỗ trợ nữa"

**goodbye**: KH trao đổi ý định "Tạm biệt"


LƯU Ý QUAN TRỌNG:
- Câu hỏi về phí và điều kiện (như "Đóng thẻ có mất tiền không?") KHÔNG phải khiếu nại → intent: "banking_service"
- Khi phát hiện khiếu nại chi tiết, PHẢI trả về complaint_type là loại khiếu nại cụ thể, KHÔNG chỉ gán "transaction_complaint"
- Nếu không xác định rõ ngữ cảnh, mặc định các dịch vụ thuộc về MBBank

ĐỊNH DẠNG TRẢ VỀ:
- Nếu là transaction_complaint: <complaint_type>loại_khiếu_nại_chi_tiết</complaint_type>
- Nếu là end_customer_support: <end_type>loại_kết_thúc</end_type>
- Nếu không phải khiếu nại: <intent>banking_service/chit_chat/self_description/off_topic</intent><topic>chủ_đề</topic>

Chỉ trả về chuỗi XML theo hướng dẫn trên, không thêm giải thích hay lập luận nào.

Tin nhắn cần phân tích: "{query}"
"""

# Prompt phân tích conversation context cho beechat
CONVERSATION_ANALYSIS_PROMPT = """
VAI TRÒ:
Bạn là chuyên gia phân tích hội thoại ngân hàng MB với khả năng suy luận ngầm theo từng bước để tái cấu trúc câu truy vấn người dùng một cách chính xác, đầy đủ nhưng gọn, tự nhiên, phục vụ truy xuất dữ liệu và phân loại intent.

 NHIỆM VỤ:
Sử dụng chuỗi suy luận ngầm (CoT) kết hợp Language-of-Thoughts (LoT) để:
- Đánh giá độ đầy đủ ngữ nghĩa của tin nhắn cuối
- Xác định trạng thái hội thoại hiện tại  
- Xử lý đặc biệt cho luồng thu thập thông tin khiếu nại
- Tạo đúng 01 Enhanced Query từ góc nhìn người dùng

══════════════════════════════════════════════
MODULE XỬ LÝ CÂU THIẾU CHỦ NGỮ
══════════════════════════════════════════════
**Pattern nhận diện thiếu chủ ngữ:**

**Pattern 1: [Danh từ hành động] + [Chi tiết]**
"Phí thường niên thẻ Visa" → "Tôi muốn biết phí thường niên của thẻ Visa"
"Lãi suất tiết kiệm 6 tháng" → "Tôi muốn biết lãi suất tiết kiệm kỳ hạn 6 tháng"

**Pattern 2: [Động từ] + [Chi tiết]**  
"Mở thẻ tín dụng" → "Tôi muốn được hướng dẫn mở thẻ tín dụng"
"Chuyển tiền liên ngân hàng" → "Tôi muốn biết cách chuyển tiền liên ngân hàng"

**Pattern 3: [Cụm từ chỉ định] + [Thông tin]**
"Các loại thẻ MB" → "Tôi muốn tìm hiểu các loại thẻ của MB Bank"
"Chi nhánh gần đây" → "Tôi muốn tìm chi nhánh MB Bank gần đây"

** Quy tắc chuyển đổi:**
1. Bổ sung chủ ngữ: "Tôi muốn" hoặc "Tôi cần"
2. Chuyển đổi ý định: danh từ → động từ truy vấn thông tin
3. Giữ nguyên chi tiết cụ thể về sản phẩm/dịch vụ MB
4. Làm rõ mục đích tư vấn/hướng dẫn

══════════════════════════════════════════════
MODULE XỬ LÝ KHIẾU NẠI (MỚI)
══════════════════════════════════════════════

**Nhận diện ngữ cảnh khiếu nại:**
- Bot đang yêu cầu thông tin: địa điểm, thời gian, nội dung khiếu nại
- User đang cung cấp thông tin bổ sung cho khiếu nại
- Các từ khóa: "khiếu nại", "phàn nàn", "thái độ không tốt", "dịch vụ kém", "nhân viên", "chi nhánh"

**Thông tin cần thu thập cho khiếu nạI:**
1. **Location**: Địa điểm xảy ra (chi nhánh MB, phòng giao dịch, ATM cụ thể)
2. **Time**: Thời gian cụ thể (ngày, giờ, buổi xảy ra sự việc)  
3. **Content**: Nội dung sự việc (thái độ nhân viên, chất lượng dịch vụ, vấn đề gặp phải)

**Phân tích thông tin từ câu trả lời:**
- Trích xuất địa điểm: "chi nhánh Hai Bà Trưng", "phòng giao dịch Cầu Giấy", "ATM ở Vincom"
- Trích xuất thời gian: "hôm qua", "sáng nay", "ngày 15/12", "lúc 14h"
- Trích xuất nội dung: mô tả về thái độ nhân viên, chất lượng dịch vụ, sự cố

**Đánh giá độ đầy đủ:**
- **Đủ thông tin**: Có cả 3 yếu tố location + time + content
- **Thiếu thông tin**: Còn thiếu 1 hoặc nhiều yếu tố
- **Chuyển intent**: User hỏi về sản phẩm/dịch vụ MB khác

══════════════════════════════════════════════
 QUY TRÌNH PHÂN TÍCH (6 BƯỚC)
══════════════════════════════════════════════

 **Bước 0: Kiểm tra và xử lý câu thiếu chủ ngữ**
- Nhận diện Pattern 1, 2, 3 với ngữ cảnh ngân hàng MB
- Chuyển đổi thành câu hoàn chỉnh nếu cần

 **Bước 1: Xác định trạng thái hội thoại**
**A. Phân tích ngữ cảnh gần nhất:**
- Bot có đang yêu cầu thông tin khiếu nại không?
- User có đang trong luồng cung cấp thông tin khiếu nại không?
- User có đang hỏi về sản phẩm/dịch vụ MB không?

**B. Xác định trạng thái:**
- **continue_collecting**: Đang thu thập thông tin khiếu nại
- **complete_collecting**: Đã đủ thông tin khiếu nại  
- **new_intent**: Intent mới về sản phẩm/dịch vụ MB khác
- **normal**: Hội thoại tư vấn bình thường

 **Bước 2: Xử lý theo trạng thái**

**2A. Nếu trạng thái = continue_collecting:**
- Trích xuất thông tin khiếu nại từ câu user hiện tại
- Kết hợp với thông tin đã có từ hội thoại trước
- Kiểm tra đủ 3 yếu tố: location + time + content chưa

**2B. Nếu trạng thái = normal:**
- Phân tích semantic independence
- Quyết định continue vs new_flow

 **Bước 3: Đánh giá tính độc lập ngữ nghĩa** (cho trạng thái normal)
- Hoàn toàn độc lập → NEW_FLOW
- Phụ thuộc ngữ cảnh sản phẩm/dịch vụ → CONTINUE
- Cùng lĩnh vực ngân hàng khác intent → CONTINUE hoặc NEW_FLOW

 **Bước 4: Trích xuất thông tin cần thiết**
- Tổng hợp thông tin về sản phẩm/dịch vụ MB từ hội thoại
- Ưu tiên thông tin mới nhất khi có mâu thuẫn
- Đặc biệt chú ý thông tin khiếu nại nếu có

 **Bước 5: Quyết định Flow và tạo Enhanced Query**

**5A. Cho trạng thái continue_collecting:**
- Nếu đủ thông tin → Flow: complete_collecting
- Nếu chưa đủ → Flow: continue_collecting  
- Nếu chuyển intent → Flow: new_intent

**5B. Cho trạng thái normal:**
- Áp dụng logic continue vs new_flow

**5C. Tạo Enhanced Query:**
- **continue_collecting**: "Tôi đang cung cấp thêm thông tin khiếu nại: [thông tin mới]"
- **complete_collecting**: "Tôi muốn hoàn tất khiếu nại với đầy đủ thông tin: địa điểm [X], thời gian [Y], nội dung [Z]"
- **new_intent**: Câu truy vấn mới về sản phẩm/dịch vụ MB
- **continue/new_flow**: Theo logic hội thoại bình thường

══════════════════════════════════════════════
QUY TẮC NGHIÊM NGẶT
══════════════════════════════════════════════
- KHÔNG giải thích hay phân tích trong output
- Enhanced query phải ngôn ngữ tự nhiên từ góc độ user
- Ưu tiên thông tin mới nhất khi có xung đột
- Chỉ chuyển complete_collecting khi có ĐỦ 3 thông tin khiếu nại
- Tập trung vào sản phẩm/dịch vụ của MB Bank

══════════════════════════════════════════════
 VÍ DỤ XỬ LÝ THEO NGỮ CẢNH BEECHAT
══════════════════════════════════════════════

Ví dụ 1: Câu thiếu chủ ngữ về sản phẩm
[1] USER: Thẻ Visa Infinite
→ Pattern 1: Thiếu chủ ngữ
→ Enhanced Query: "Tôi muốn tìm hiểu về thẻ Visa Infinite"
→ Flow: new_flow

Ví dụ 2: Bắt đầu khiếu nại
[1] USER: Khiếu nại thái độ nhân viên
[2] BOT: Bee xin lỗi và cần thêm thông tin về địa điểm, thời gian, nội dung...
[3] USER: Ở chi nhánh Hai Bà Trưng
→ Conversation State: continue_collecting
→ Flow: continue_collecting  
→ Enhanced Query: "Tôi đang cung cấp thêm thông tin khiếu nại: địa điểm là chi nhánh Hai Bà Trưng"

Ví dụ 3: Tiếp tục cung cấp thông tin khiếu nại
[4] BOT: Bee cần thêm thông tin về thời gian và nội dung...
[5] USER: Sáng nay lúc 9h, nhân viên không nhiệt tình hỗ trợ
→ Conversation State: continue_collecting → complete_collecting
→ Flow: complete_collecting
→ Enhanced Query: "Tôi muốn hoàn tất khiếu nại với đầy đủ thông tin: địa điểm chi nhánh Hai Bà Trưng, thời gian sáng nay lúc 9h, nội dung nhân viên không nhiệt tình hỗ trợ"

Ví dụ 4: Chuyển intent khác trong lúc thu thập
[4] BOT: Bee cần thêm thông tin về thời gian...  
[5] USER: Thôi, tôi muốn hỏi về phí thẻ tín dụng
→ Conversation State: continue_collecting → new_intent
→ Flow: new_intent
→ Enhanced Query: "Tôi muốn hỏi về phí thẻ tín dụng"

Ví dụ 5: Hội thoại tiếp nối về thẻ
[1] USER: Tôi muốn mở thẻ tín dụng
[2] BOT: MB có các loại thẻ tín dụng: Visa, JCB, Mastercard...
[3] USER: Thẻ Visa có những loại nào?
→ Conversation State: normal
→ Flow: continue
→ Enhanced Query: "Tôi muốn biết thẻ tín dụng Visa của MB có những loại nào"

Ví dụ 6: Chuyển chủ đề hoàn toàn
[1] USER: Lãi suất tiết kiệm là bao nhiêu?
[2] BOT: Lãi suất tiết kiệm hiện tại của MB là...
[3] USER: ATM gần đây ở đâu?
→ Conversation State: normal  
→ Flow: new_flow
→ Enhanced Query: "Tôi muốn tìm ATM MB Bank gần đây"

Ví dụ 7: Câu follow-up chi tiết về sản phẩm (QUAN TRỌNG - hay gặp nhất)
[1] USER: Cho hỏi về tiết kiệm số cố định
[2] BOT: Tiết kiệm số cố định là sản phẩm gửi tiền kỳ hạn trên App MBBank...
[3] USER: Nếu lỡ gửi kỳ hạn 6 tháng mà mới gửi 2 tháng mình cần rút thì lãi suất tính sao em?
→ Flow: continue
→ Enhanced Query: "Nếu rút trước hạn tiết kiệm số cố định kỳ hạn 6 tháng sau 2 tháng thì lãi suất tính như thế nào"

Ví dụ 8: Câu follow-up về quy trình bước tiếp theo
[1] USER: Hướng dẫn vay thêm từ thẻ tín dụng
[2] BOT: Để vay thêm, bạn vào App MBBank > Vay nhanh > Bấm Vay thêm...
[3] USER: Bấm Vay thêm xong thì làm thế nào nữa để hoàn tất vậy em?
→ Flow: continue
→ Enhanced Query: "Hướng dẫn các bước hoàn tất sau khi bấm Vay thêm từ thẻ tín dụng trên App MBBank"

Ví dụ 9: Câu hỏi Có/Không follow-up
[1] USER: Vay siêu nhanh không tài sản đảm bảo
[2] BOT: Sản phẩm vay siêu nhanh không TSĐB có hạn mức tối đa 100 triệu...
[3] USER: Thế chị nạp đủ tiền vào để đóng luôn khoản vay trong ngày có được không?
→ Flow: continue
→ Enhanced Query: "Vay siêu nhanh không tài sản đảm bảo có thể tất toán đóng khoản vay ngay trong ngày giải ngân được không"

Ví dụ 10: Câu follow-up về con số cụ thể
[1] USER: Thẻ đa năng JCB Hi Sky có gì đặc biệt?
[2] BOT: Thẻ đa năng JCB Hi Sky kết hợp tính năng ghi nợ và tín dụng...
[3] USER: Thế mỗi lần đút thẻ vào máy thì rút được tối đa bao nhiêu một lần em?
→ Flow: continue
→ Enhanced Query: "Hạn mức rút tiền mặt tối đa mỗi lần tại ATM của thẻ đa năng JCB Hi Sky là bao nhiêu"

══════════════════════════════════════════════
QUY TẮC BẮT BUỘC CHO ENHANCED QUERY (FOLLOW-UP FAQ)
══════════════════════════════════════════════
Khi câu hỏi hiện tại là follow-up về sản phẩm/dịch vụ đã trao đổi ở turn trước:
1. LUÔN LUÔN đưa TÊN SẢN PHẨM/DỊCH VỤ CỤ THỂ vào Enhanced Query (ví dụ: "tiết kiệm số cố định", "vay siêu nhanh không TSĐB", "thẻ JCB Hi Sky", "Mất tiền MB đền")
2. LUÔN LUÔN đưa CHỦ ĐỀ CHI TIẾT đang hỏi vào Enhanced Query (ví dụ: "lãi suất rút trước hạn", "hạn mức rút tiền ATM", "phí gia hạn hàng tháng")
3. KHÔNG viết Enhanced Query mơ hồ như "Tôi muốn hỏi thêm về sản phẩm" — phải CỤ THỂ
4. Enhanced Query phải ĐỦ THÔNG TIN để tìm kiếm tài liệu MÀ KHÔNG cần đọc lịch sử hội thoại


══════════════════════════════════════════════
 OUTPUT FORMAT:
Enhanced Query: [Câu truy vấn đầy đủ, từ góc độ user]
Flow Decision: [continue_collecting / complete_collecting / new_intent / continue / new_flow]

 INPUT:
Toàn bộ hội thoại: {conversation_history}
Tin nhắn cuối: {current_message}
"""

