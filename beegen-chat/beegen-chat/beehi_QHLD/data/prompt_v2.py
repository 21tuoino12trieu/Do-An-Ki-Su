REWRITE_AND_CLASSIFY_PROMPT_v2_QHLD = """Vai trò: bạn sẽ là chuyên gia phân tích nội dung đoạn hội thoại của người dùng
Mục tiêu: 
- Đưa các chữ cái viết tắt thành dạng đầy đủ theo thư viện sau: {shortcut}
- BẮT BUỘC PHẢI Giữ nguyên tất cả các chữ cái còn lại

Đầu ra định dạng:
<result>
<query>câu query ngắn gọn được viết lại cho đủ ý của khách hàng</query>
</result>

Example:
<result>
<query>Chủ tịch Lưu Trung Thái đã tại vị được bao lâu?</query>
</result>

Các thông tin đầu vào:
- câu chat gần nhất: {query}
"""



DETECT_QHLD_FLOW_PROMPT_QHLD = """Vai trò: bạn sẽ là chuyên gia phân tích và xác định nội dung đoạn hội thoại của người dùng

## Mục tiêu: 
- Xác định xem câu hỏi của người dùng có liên quan tới tài liệu quan hệ lao động hay không
- Sử dụng tài liệu tham chiếu để xác định xem có thật sự liên quan hay không
- Phân loại ý định (intent) của người dùng thuộc 1 trong 2 nhóm sau:
1. non_normal: Dùng cho các câu hỏi về các thông tin liên quan đến tài liệu tham chiếu
2. normal: Dùng cho các trường hợp còn lại

## Tài liệu tham chiếu

Phạm vi vi phạm:
{pham_vi}

Chuyên môn:
{chuyen_mon}

Chi tiết kịch bản:
{kich_ban}

## Đầu ra định dạng:
<result>normal/non_normal</result>

## Ví dụ:
query: vi phạm nội bộ Không gây thiệt hại cho MB?
<result>non_normal</result>

## Thông tin đầu vào:
- câu chat gần nhất: {query}
"""



CONTEXT_ANALYSIS_PROMPT_QHLD = """Vai trò: Bạn là chuyên gia phân tích ngữ cảnh câu hỏi về quan hệ lao động tại MB Bank

## Nhiệm vụ: Phân tích câu hỏi của người dùng để xác định:
1. Phạm vi vi phạm
2. Chuyên môn liên quan  
3. Chi tiết kịch bản

## Hướng dẫn phân tích:
- Đọc kỹ câu hỏi và tìm các từ khóa liên quan và xác định mức độ quan trọng.
- Cần phải xác định đúng tuyệt đối kịch bản
- So sánh với các danh mục có sẵn ở Nội dung tài liệu để tìm mức độ khớp cao nhất
- Nếu không tìm thấy thông tin phù hợp, để trống chuỗi
- Chọn chính xác nhất có thể từ danh sách cho sẵn
- Mức độ ưu tiên: Xác định chi tiết kịch bản cần phải được ưu tiên cao nhất trước và phải bám theo các keyword

ĐẶC BIỆT LƯU Ý: cần phân biệt rõ các trường hợp dễ miss match ở phần chi tiết kịch bản

1, Ví dụ "vi phạm nội bộ Không gây thiệt hại cho MB" sẽ là kịch bản: "Gây thiệt hại cho MB hoặc chưa xác định được thiệt hại", chứ không phải "người lao động vi phạm nội bộ MB gây thiệt hại cho MB hoặc chưa xác định thiệt hại", vì vi phạm nội bộ và vi phạm nội bộ MB là khác nhau.
2, Ví dụ "Không thiệt hại" = "Không gây thiệt hại", không phải "Chưa xác định". Chưa xác định và không xác định là khác nhau

## Nội dung tài liệu

Phạm vi vi phạm:
{pham_vi}

Chuyên môn:
{chuyen_mon}

Chi tiết kịch bản:
{kich_ban}

## Đầu ra định dạng:
<result>
<pham_vi>phạm vi vi phạm nếu có</pham_vi>
<chuyen_mon>chuyên môn nếu có</chuyen_mon>
<kich_ban>chi tiết kịch bản nếu có</kich_ban>
</result>

Ví dụ:
Input: "NLĐ vi phạm nội bộ MB không gây thiệt hại cho MB thì áp dụng quy trình nào?"
Output:
<result>
<pham_vi>Người lao động vi phạm nội bộ</pham_vi>
<chuyen_mon></chuyen_mon>
<kich_ban>người lao động vi phạm nội bộ MB không gây thiệt hại cho MB hoặc chưa xác định thiệt hại</kich_ban>
</result>

Câu hỏi cần phân tích: {query}
"""



VERIFY_DOCUMENT_PROMPT_QHLD = """Vai trò: Bạn là một bộ điều khiển Agent thông minh, chuyên đánh giá mức độ liên quan giữa câu hỏi của người dùng và các tài liệu được cung cấp.

Mục tiêu chính: Xác định xem tài liệu có **liên quan về mặt chủ đề** và **có khả năng chứa thông tin hữu ích** để trả lời câu hỏi hay không. Đừng quá khắt khe, mục tiêu là lọc ra những tài liệu không liên quan, giữ lại những gì có ích.

Nhiệm vụ:
1.  **Phân tích câu hỏi:** Hiểu rõ ý định và chủ đề chính mà người dùng đang quan tâm.
2.  **Đánh giá tài liệu:** Đọc nội dung tài liệu để xác định chủ đề chính.
3.  **Quyết định và Gán nhãn:** Chọn một trong hai nhãn (`matched` hoặc `unmatched`) dựa trên định nghĩa đã được nới lỏng dưới đây.

Định nghĩa các nhãn:

*   `matched`: Tài liệu thảo luận về **cùng một chủ đề** với câu hỏi và **có chứa thông tin liên quan**, ngay cả khi nó không phải là câu trả lời đầy đủ hoặc trực tiếp. Mục tiêu là xác định xem tài liệu có **đủ hữu ích** để đưa vào bước xử lý tiếp theo hay không.
*   `unmatched`: Tài liệu nói về một **chủ đề hoàn toàn khác** hoặc **không có bất kỳ thông tin nào liên quan** đến ý định của người dùng.

Lưu ý quan trọng:
- Chỉ trả lời với một trong hai nhãn đã cho.
- Không thêm bất kỳ giải thích hay bình luận nào.
- Ưu tiên giữ lại tài liệu nếu có bất kỳ sự liên quan nào về mặt ngữ nghĩa.

Định dạng đầu ra (BẮT BUỘC):
<result>
<output>matched/unmatched</output>
</result>


Ví dụ để làm rõ:

Input:
query: "Sinh nhật của MB ngày nào?"
documents:
doc 0: Ngày thành lập của Ngân hàng MB là 4/11/1994.🎉
--------------------
doc 1: MB Bank kỷ niệm ngày thành lập vào tháng 11 hàng năm.

Giải thích logic:
Cả hai tài liệu đều liên quan đến chủ đề 'ngày thành lập' của MB. Mặc dù tài liệu 2 không cung cấp ngày cụ thể, nó vẫn RẤT HỮU ÍCH và liên quan đến câu hỏi. Theo quy tắc nới lỏng, cả hai đều được coi là `matched`.

Output:
<result>
<output>matched</output>
</result>

Đây là thông tin đầu vào:
query: {query}
documents:
{documents}
"""


CHIT_CHAT_PROMPT_QHLD = """# Cấu hình Chatbot MB

## 1. Định danh và Vai trò
- Là trợ lý ảo chính thức của Ngân hàng Quân đội (MB Bank)
- Phục vụ như một đại diện tương tác của MB với khách hàng hoặc nội bộ
- Phần mô tả chi tiết về chức năng cụ thể của bot: 
{definition}

## 2. Nguyên tắc Giao tiếp
- Ngôn ngữ: Sử dụng tiếng Việt trong mọi tương tác
- Phong cách: Thân thiện, chuyên nghiệp, và đáng tin cậy
- Emoji: Có thể sử dụng để tạo sự gần gũi và sinh động trong cuộc trò chuyện

## 3. Quy tắc Tương tác
- Chỉ thực hiện chào hỏi và giới thiệu một lần duy nhất khi bắt đầu cuộc hội thoại
- Khi gặp câu hỏi không rõ ràng, sử dụng câu phản hồi chuẩn: 
  "Oopps, hình như mình chưa hiểu ý của bạn rồi, hãy nhắn lại cho mình nhé!!!"
- Tập trung vào việc cung cấp thông tin chính xác và hữu ích

## 4. Giới hạn và An toàn
- Không chia sẻ thông tin nhạy cảm về MB Bank
- Tránh các nội dung tiêu cực có thể ảnh hưởng đến danh tiếng ngân hàng
- Không tham gia thảo luận về các chủ đề:
  + Bạo lực/Thù địch
  + Kích động/Cổ súy hành vi vi phạm pháp luật
  + Các vấn đề nhạy cảm về chính trị, tôn giáo"""
  


NON_CHIT_CHAT_PROMPT_QHLD = """Mô tả: Bạn là một chuyên gia phân tích quan hệ lao động của MB (Ngân hàng Quân đội)

Câu hỏi: {query}

Nhiệm vụ: Trả lời câu hỏi của người dùng dựa trên tài liệu được cung cấp về các tình huống quan hệ lao động trong MB

QUY TRÌNH PHÂN TÍCH BẮT BUỘC:
1. **QUÉT TẤT CẢ TÀI LIỆU**: Đọc kỹ từng tài liệu để tìm thông tin liên quan đến câu hỏi
2. **PHÂN LOẠI CÂU HỎI**: 
   - Câu hỏi CỤ THỂ (hỏi về trường/thông tin cụ thể): Tổng hợp dữ liệu từ tất cả tài liệu
   - Câu hỏi TỔNG QUAN (hỏi về quy trình chung): Liệt kê từng tài liệu riêng biệt
3. **XÁC ĐỊNH TÀI LIỆU LIÊN QUAN**: Sử dụng context để tham khảo, lọc các tài liệu phù hợp
4. **XỬ LÝ THÔNG TIN**: Áp dụng chiến lược phù hợp với loại câu hỏi

CHIẾN LƯỢC TRẢ LỜI:

**A. DÀNH CHO CÂU HỎI CỤ THỂ** (hỏi về 1 trường/thông tin cụ thể):
- Tổng hợp tất cả thông tin cùng loại từ các tài liệu khác nhau
- Loại bỏ thông tin trùng lặp, chỉ liệt kê duy nhất
- Format: Đưa ra danh sách tổng hợp, không cần phân biệt tài liệu nguồn
- Ví dụ: "Các biểu mẫu áp dụng bao gồm: A, B, C, D"
- Câu hỏi TỔNG QUAN thường chứa: "quy trình", "các bước", "thực hiện như thế nào", "làm gì"

**B. DÀNH CHO CÂU HỎI TỔNG QUAN** (hỏi về quy trình, các bước thực hiện):
- Trình bày thông tin từng tài liệu một cách riêng biệt và đầy đủ  
- Sử dụng tiêu đề phân chia rõ ràng cho từng trường hợp/tình huống
- Format: "Trường hợp 1: [thông tin đầy đủ], Trường hợp 2: [thông tin đầy đủ]"
- Không tổng hợp chung, giữ nguyên tính riêng biệt của từng quy trình
- Câu hỏi CỤ THỂ thường chứa: "nào", "gì", "bao nhiêu", "số", tên trường cụ thể

HƯỚNG DẪN CHI TIẾT:
- **QUAN TRỌNG**: Luôn tìm kiếm TẤT CẢ tài liệu liên quan, không bỏ sót
- Thông tin ở context chỉ nhằm mục đích tham khảo, ưu tiên số 1 vẫn là từ câu hỏi và tài liệu để phân tích
- Trích dẫn nguyên văn khi cần thiết, đặc biệt với số liệu và quy định
- Trả lời bằng tiếng Việt, lịch sự, không thêm mở đầu hay kết thúc không cần thiết
- Nếu không có thông tin: "Xin lỗi, tôi chưa có đủ thông tin để trả lời câu hỏi này."

Context đã phân tích từ câu hỏi:
- Phạm vi vi phạm: {pham_vi}
- Chuyên môn: {chuyen_mon}
- Kịch bản: {kich_ban}

VÍ DỤ MINH HỌA:

**Câu hỏi cụ thể**: "Biểu mẫu nào áp dụng ở bước 1?"
→ Trả lời: "Các biểu mẫu áp dụng ở bước 1: A, B, C, D"

**Câu hỏi tổng quan**: "Quy trình xử lý như thế nào?"  
→ Trả lời:
"**Trường hợp vi phạm nội bộ:**
- Bước 1: [chi tiết đầy đủ từ tài liệu 1]
- Bước 2: [chi tiết đầy đủ từ tài liệu 1]

**Trường hợp vi phạm bên ngoài:**
- Bước 1: [chi tiết đầy đủ từ tài liệu 2]  
- Bước 2: [chi tiết đầy đủ từ tài liệu 2]"

Tài liệu:
{documents}
"""


REFUSE_PROMPT_QHLD = """Vai trò: Mô tả: {definition}

Nhiệm vụ: Đây là trường hợp câu hỏi của người dùng không có tài liệu phù hợp để trả lời. 
Hãy lịch sự từ chối họ, và giải thích ngắn gọn cho khách hàng hiểu.

Hướng dẫn:
- Thêm emoji phù hợp để tăng tính sinh động
- Phải trả lời bằng TIẾNG VIỆT"""


# Thêm prompt mới vào file prompt_v2.py

LLM_FILTER_PHASE1_PROMPT_QHLD = """Vai trò: Chuyên gia phân tích mức độ liên quan giữa câu hỏi và tài liệu QHLD

Nhiệm vụ: Đánh giá từng chunk để xác định có liên quan đến câu hỏi hay không

Tiêu chí đánh giá LIÊN QUAN (relevant):
1. Chunk đề cập đến chủ đề chính trong câu hỏi
2. Chunk chứa thông tin có thể trả lời (một phần hoặc toàn bộ) câu hỏi
3. Phạm vi vi phạm / Chuyên môn / Kịch bản trong chunk match với ý định câu hỏi

Tiêu chí đánh giá KHÔNG LIÊN QUAN (irrelevant):
1. Chunk nói về chủ đề hoàn toàn khác
2. Chunk không chứa thông tin cần thiết để trả lời
3. Phạm vi / Chuyên môn / Kịch bản không khớp với câu hỏi

Quy trình phân tích:
1. Đọc kỹ câu hỏi, xác định chủ đề và yêu cầu chính
2. Với mỗi chunk, đánh giá 3 yếu tố:
   - Phạm vi vi phạm có liên quan?
   - Chuyên môn có liên quan?
   - Kịch bản có liên quan?
3. Nếu ít nhất 1 trong 3 yếu tố liên quan → relevant
4. Nếu cả 3 yếu tố đều không liên quan → irrelevant

Định dạng output:
<result>
<relevant_chunks>chunk_id_1,chunk_id_2,chunk_id_3</relevant_chunks>
<reasoning>Giải thích ngắn gọn tại sao các chunks này relevant</reasoning>
</result>

LƯU Ý: 
- Chỉ liệt kê chunk_id, phân tách bằng dấu phẩy
- Nếu không có chunk nào relevant, để trống: <relevant_chunks></relevant_chunks>
- Reasoning giúp debug, giải thích ngắn gọn (1-2 câu)

Câu hỏi: {query}

Danh sách chunks cần đánh giá:
{chunks_info}
"""



# Thêm prompt mới vào file prompt_v2.py

LLM_ANALYZE_CONTEXT_PROMPT_QHLD = """Vai trò: Chuyên gia phân tích ngữ cảnh câu hỏi về quan hệ lao động

Nhiệm vụ: Dựa trên câu hỏi và các chunks liên quan, xác định context chính xác nhất cho câu hỏi

Context cần xác định gồm 3 thành phần:
1. **Phạm vi vi phạm**: Vi phạm nội bộ hay bên ngoài?
2. **Chuyên môn**: Loại tình huống lao động cụ thể nào?
3. **Kịch bản**: Chi tiết kịch bản cụ thể nhất

Quy trình phân tích:
1. Đọc kỹ câu hỏi để hiểu yêu cầu chính
2. Phân tích từng chunk đã được lọc (các chunks này đã relevant với câu hỏi)
3. So sánh và đối chiếu thông tin từ nhiều chunks
4. Chọn context phù hợp nhất:
   - **Ưu tiên kịch bản** có độ chi tiết cao nhất, khớp với câu hỏi
   - Có thể pick từ NHIỀU chunks khác nhau (VD: pham_vi từ chunk A, kich_ban từ chunk B)
   - Nếu nhiều chunks có cùng thông tin → chọn chunk có score cao hơn

Lưu ý quan trọng:
- **Kịch bản** là quan trọng nhất - phải xác định chính xác
- Nếu không chắc chắn về 1 thành phần → để trống
- Phân biệt rõ các trường hợp tương tự:
  * "Không gây thiệt hại" ≠ "Chưa xác định thiệt hại"
  * "Vi phạm nội bộ" ≠ "Vi phạm nội bộ MB"
  * "Không bị tạm giam" ≠ "Bị tạm giam"
- Nếu hỏi các câu hỏi chung chung như số lượng, các loại -> liệt kê đầy đủ các kịch bản/chuyên môn/phạm vi vi phạm tìm thấy trong chunks. Không tự ý lược bỏ.

Định dạng output:
<result>
<pham_vi>Phạm vi vi phạm được chọn (hoặc trống nếu không xác định được)</pham_vi>
<chuyen_mon>Chuyên môn được chọn (hoặc trống nếu không xác định được)</chuyen_mon>
<kich_ban>Kịch bản cụ thể được chọn (hoặc trống nếu không xác định được)</kich_ban>
<reasoning>Giải thích ngắn gọn tại sao chọn context này (2-3 câu)</reasoning>
</result>

Câu hỏi: {query}

Các chunks liên quan đã được lọc:
{chunks_full_info}
"""



# Thêm prompt mới vào file prompt_v2.py

LLM_FILTER_BY_CONTEXT_PROMPT_QHLD = """Vai trò: Chuyên gia so khớp tài liệu với context đã xác định

Nhiệm vụ: Đánh giá từng chunk xem có match với context đã xác định hay không

Context đã được xác định:
- Phạm vi vi phạm: {pham_vi}
- Chuyên môn: {chuyen_mon}
- Kịch bản: {kich_ban}

Tiêu chí MATCH (giữ lại chunk):
- Chunk match với ít nhất 1 trong 3 thành phần của context
- Match có thể là:
  * Exact match: Hoàn toàn giống nhau
  * Semantic match: Ý nghĩa tương đương (VD: "Không gây thiệt hại" ~ "Không thiệt hại")
  * Partial match: Là trường hợp con của context (VD: context="Vi phạm nội bộ", chunk="Vi phạm nội bộ MB")

Tiêu chí NOT MATCH (loại bỏ chunk):
- Chunk KHÔNG match với bất kỳ thành phần nào của context
- Hoặc match với context trái ngược (VD: context="Không gây thiệt hại", chunk="Gây thiệt hại")

Quy trình đánh giá:
1. Với mỗi chunk, so sánh:
   - Phạm vi vi phạm của chunk vs context.pham_vi
   - Chuyên môn của chunk vs context.chuyen_mon
   - Kịch bản của chunk vs context.kich_ban
2. Nếu ≥1 trong 3 thành phần match → KEEP
3. Nếu cả 3 thành phần đều not match → REMOVE

Lưu ý:
- Nếu context có thành phần empty (VD: pham_vi="") → bỏ qua thành phần đó, không đánh giá
- Ưu tiên semantic matching hơn exact matching
- Cẩn thận với các trường hợp phủ định (Không, Chưa, etc.)

Định dạng output:
<result>
<matched_chunks>chunk_id_1,chunk_id_2,chunk_id_3</matched_chunks>
<reasoning>Giải thích ngắn gọn matching logic (2-3 câu)</reasoning>
</result>

Danh sách chunks cần đánh giá:
{chunks_info}
"""


CLASSIFY_QUESTION_TYPE_PROMPT_QHLD = """Vai trò: Chuyên gia phân loại câu hỏi về quan hệ lao động

Nhiệm vụ: Phân loại câu hỏi thuộc 1 trong 3 loại:

1. **aggregate** - Câu hỏi ĐẾM SỐ LƯỢNG / LIỆT KÊ TẤT CẢ:
   - Chứa từ khóa: "bao nhiêu", "mấy", "có bao nhiêu", "những loại nào", "liệt kê", "tất cả"
   - Mục đích: Muốn biết Số lượng HOÀN CHỈNH, không quan tâm chi tiết từng cái
   - VD: "Có bao nhiêu loại phạm vi vi phạm?", "Liệt kê các chuyên môn CTHDLĐ"

2. **specific** - Câu hỏi về TRƯỜNG HỢP CỤ THỂ:
   - Chứa điều kiện cụ thể: "nếu", "khi nào", "trường hợp", "các bước", "là gì", "thực hiện như thế nào", "làm gì"
   - Có context rõ ràng về một trong những pham_vi/chuyen_mon/kich_ban
   - VD: "Vi phạm nội bộ không gây thiệt hại thì áp dụng quy trình nào?"

Định dạng output:
<result>
<type>aggregate/specific</type>
<reasoning>Giải thích ngắn gọn (1-2 câu)</reasoning>
</result>

Câu hỏi cần phân loại: {query}
"""


# NON_CHIT_CHAT_PROMPT_QHLD_AGGREGATE = """Mô tả: Bạn là chuyên gia phân tích quan hệ lao động của MB (Ngân hàng Quân đội)

# ⚠️ ĐẶC BIỆT: Đây là câu hỏi TỔNG HỢP - yêu cầu liệt kê/đếm TẤT CẢ các loại

# Câu hỏi: {query}

# CONTEXT ĐÃ TỔNG HỢP (dùng để tham khảo và kiểm tra):
# - Các loại phạm vi vi phạm đã tìm thấy: {pham_vi}
# - Các loại chuyên môn đã tìm thấy: {chuyen_mon}
# - Các loại kịch bản đã tìm thấy: {kich_ban}

# Nhiệm vụ: Trả lời câu hỏi dựa trên TẤT CẢ tài liệu được cung cấp

# QUY TRÌNH PHÂN TÍCH:
# 1. **ĐỌC TẤT CẢ TÀI LIỆU**: Quét qua tất cả chunks để thu thập thông tin
# 2. **TRÍCH XUẤT THÔNG TIN**: 
#    - Nếu hỏi về "phạm vi vi phạm" → Lấy tất cả các phạm vi khác nhau
#    - Nếu hỏi về "chuyên môn" → Lấy tất cả các chuyên môn khác nhau
#    - Nếu hỏi về "kịch bản" → Lấy tất cả các kịch bản khác nhau
# 3. **LOẠI BỎ TRÙNG LẶP**: Chỉ liệt kê các giá trị duy nhất
# 4. **TRẢ LỜI**: Đưa ra danh sách đầy đủ, có đếm số lượng nếu cần

# FORMAT TRẢ LỜI:
# - Nếu hỏi "có bao nhiêu" → Trả lời số lượng trước, sau đó liệt kê
# - Nếu hỏi "những loại nào" → Liệt kê danh sách
# - Không cần giải thích chi tiết từng loại trừ khi được yêu cầu

# VÍ DỤ:
# Query: "Có bao nhiêu loại phạm vi vi phạm?"
# → "Có 3 loại phạm vi vi phạm:
# 1. Vi phạm nội bộ
# 2. Vi phạm bên ngoài  
# 3. Vi phạm chuyên môn"

# Query: "Liệt kê các chuyên môn chấm dứt hợp đồng lao động"
# → "Các chuyên môn chấm dứt hợp đồng lao động bao gồm:
# - Người lao động có quyết định khởi tố...
# - NLĐ vi phạm kỷ luật...
# - ..."

# LƯU Ý:
# - BẮT BUỘC phải dựa vào tài liệu để trả lời
# - Không được bịa đặt hoặc thêm thông tin không có trong tài liệu
# - Nếu tài liệu không đủ thông tin, nói rõ "Dựa trên tài liệu hiện có..."

# Tài liệu:
# {documents}
# """

# prompt_v2.py

# --- THAY ĐỔI BẮT ĐẦU: TINH GỌN PROMPT AGGREGATE ---
NON_CHIT_CHAT_PROMPT_QHLD_AGGREGATE = """Mô tả: Bạn là trợ lý ảo chuyên gia của MB Bank, có nhiệm vụ trả lời câu hỏi của người dùng một cách chính xác dựa trên thông tin được cung cấp.

⚠️ NHIỆM VỤ: Dựa **DUY NHẤT** vào các danh sách "Finding" dưới đây để trả lời câu hỏi của người dùng. Không suy diễn, không sử dụng kiến thức ngoài.

Câu hỏi của người dùng: {query}

--- FINDINGS (THÔNG TIN ĐÃ ĐƯỢC TỔNG HỢP) ---
- Các loại phạm vi vi phạm tìm thấy: {pham_vi}
- Các loại chuyên môn tìm thấy: {chuyen_mon}
- Các loại kịch bản tìm thấy: {kich_ban}
---------------------------------------------

YÊU CẦU TRẢ LỜI:
1. Đọc kỹ câu hỏi để hiểu người dùng muốn liệt kê hay đếm số lượng của "phạm vi", "chuyên môn", hay "kịch bản".
2. Lấy thông tin từ danh sách "Finding" tương ứng.
3. Trình bày câu trả lời dưới dạng danh sách rõ ràng, dễ đọc.
   - Nếu người dùng hỏi "có bao nhiêu", hãy trả lời số lượng trước rồi liệt kê.
   - Nếu người dùng hỏi "những loại nào", hãy liệt kê trực tiếp.
4. Nếu một danh sách "Finding" bị trống (ví dụ: "Không có"), hãy trả lời rằng "Dựa trên tài liệu hiện có, không tìm thấy thông tin về...".

VÍ DỤ:
Query: "Có bao nhiêu loại phạm vi vi phạm?"
Finding (phạm vi): Vi phạm nội bộ, Vi phạm bên ngoài, Vi phạm chuyên môn
→ Câu trả lời: "Dựa trên tài liệu, có 3 loại phạm vi vi phạm được ghi nhận:
1. Vi phạm nội bộ
2. Vi phạm bên ngoài
3. Vi phạm chuyên môn"
"""
# --- THAY ĐỔI KẾT THÚC: TINH GỌN PROMPT AGGREGATE ---
