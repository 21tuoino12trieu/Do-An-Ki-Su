"""
Prompt cải tiến cho trích xuất node thẻ dựa trên cấu trúc cây.
"""

# Trích xuất node thẻ cải tiến
CARD_KEYWORD_EXTRACT_PROMPT_V2 = """
Vai trò: Chuyên gia phân tích ngữ nghĩa và xác định node thẻ ngân hàng

Nhiệm vụ: 
1. Phân tích câu hỏi người dùng để xác định có phải là câu hỏi về THẺ CỤ THỂ hay không
2. Xác định chính xác NODE trong cây phân cấp chứa thông tin về loại thẻ đó
3. Xác định loại của NODE (dòng/loại/thương hiệu/bộ sưu tập)
4. Trả về TÊN NODE và KEYWORD tìm thấy trong câu hỏi
5. Tạo câu mô tả phân loại
6. Nếu câu hỏi chỉ liên quan đến thẻ nói chung HOẶC không tìm thấy node thẻ cụ thể, trả về "unknown" và "generic"

HƯỚNG DẪN PHÂN TÍCH:

1. PHÂN LOẠI TRUY VẤN:
   a. TRUY VẤN THẺ CỤ THỂ:
      - Đề cập đến TÊN THẺ CỤ THỂ (ví dụ: "Visa Infinite", "Hi LED", "JCB Ultimate")
      - Hoặc kết hợp LOẠI THẺ + HÃNG THẺ (ví dụ: "Thẻ tín dụng Visa", "Thẻ ghi nợ JCB")
      - Hoặc đề cập đến DÒNG THẺ CỤ THỂ (ví dụ: "Hi Collection", "Bộ sưu tập Hi LED")
      - Hoặc đề cập đến THẺ TRONG BỘ SƯU TẬP (ví dụ: "thẻ Wukong", "thẻ Maneki Neko")

   b. TRUY VẤN THẺ CHUNG CHUNG (trả về "unknown"):
      - Chỉ đề cập đến loại thẻ chung (ví dụ: "thẻ tín dụng", "thẻ ghi nợ", "thẻ hybrid")
      - Thảo luận chung về thẻ (ví dụ: "các loại thẻ của MB Bank", "cách đăng ký thẻ")
      - So sánh các loại thẻ không cụ thể (ví dụ: "so sánh thẻ tín dụng và ghi nợ")
      - Câu hỏi về biểu phí, điều kiện chung (ví dụ: "phí thường niên thẻ tín dụng")

2. QUY TẮC XÁC ĐỊNH NODE VÀ KEYWORD:
   a. TÌM NODE CHỨA TỪ KHÓA:
      - Phân tích câu hỏi và tìm các từ khóa liên quan đến thẻ
      - So sánh từ khóa với danh sách "keywords" của các node trong cây
      - Xác định node nào chứa chính xác từ khóa đó trong mảng "keywords" của nó
      - LƯU LẠI cả node và keyword tìm thấy

   b. XÁC ĐỊNH KEYWORD:
      - Keyword chính là từ khóa trong câu hỏi đã khớp với keywords của node
      - Nếu có nhiều keyword khớp, chọn keyword cụ thể nhất hoặc phù hợp nhất
      - Đảm bảo keyword phản ánh chính xác thẻ hoặc dòng thẻ được đề cập
      
   c. QUY TẮC XÁC ĐỊNH LOẠI NODE:
   **DÒNG SẢN PHẨM**: Các node thuộc card_types (credit, debit, hybrid)
      - VD: visa_infinite, jcb_ultimate, hi_mastercard_collection
   
   **LOẠI THẺ**: Các node cha lớn như credit, debit, hybrid
      - VD: credit, debit, hybrid
   
   **THƯƠNG HIỆU**: Các node thuộc brands
      - VD: visa, mastercard, jcb, unionpay
   
   **BỘ SƯU TẬP**: Các node có "collection" trong tên
      - VD: hi_lol_collection, hi_led_collection, hi_jcb_collection

3. NGUYÊN TẮC ƯU TIÊN:
   a. NODE LÁ TRƯỚC:
      - Ưu tiên node có ID cụ thể (là node lá)
      - Ví dụ: Nếu query nhắc đến "visa infinite", trả về node "visa_infinite" và keyword "visa infinite"

   b. NODE CON TRƯỚC NODE CHA:
      - Nếu từ khóa khớp với nhiều node, ưu tiên node cụ thể hơn
      - Ví dụ: Nếu query nhắc đến "visa tín dụng", trả về node "visa_credit" và keyword "visa tín dụng"

   c. COLLECTIONS (BỘ SƯU TẬP):
      - Nếu query nhắc đến thẻ trong bộ sưu tập (wukong, ahri, zodiac, LED), TÌM NODE COLLECTION chứa từ khóa đó
      - Trả về node của collection và keyword cụ thể (vd: node "hi_lol_collection", keyword "wukong")

4. XỬ LÝ CÁC TRƯỜNG HỢP ĐẶC BIỆT - KHI TRẢ VỀ "unknown":
   a. Trường hợp xuất hiện nhiều hơn một keyword, trả về node cha của chúng nếu cùng cha, nếu không trả về unknown
   b. TRƯỜNG HỢP KHÔNG TÌM THẤY:
      - Khi query có chứa từ khóa thẻ nhưng không khớp với từ khóa trong bất kỳ node nào
      - Khi từ khóa quá chung chung hoặc mơ hồ

5. VÍ DỤ CỤ THỂ - PHÂN LOẠI VÀ KẾT QUẢ:
   a. TRƯỜNG HỢP CẦN TRẢ VỀ TÊN NODE VÀ KEYWORD:
      * "Thẻ wukong có tính năng gì?" -> <node>hi_lol_collection</node><keyword>wukong</keyword>
      * "Điều kiện mở thẻ maneki neko" -> <node>hi_jcb_collection</node><keyword>maneki neko</keyword>
      * "Phí thẻ LED" -> <node>hi_led_collection</node><keyword>led</keyword>
      * "Thẻ visa infinite có ưu đãi gì" -> <node>visa_infinite</node><keyword>visa infinite</keyword>
      * "Thẻ tín dụng Visa của MB Bank" -> <node>visa_credit</node><keyword>visa tín dụng</keyword>
      * "Thẻ Hi Collection Mastercard có cashback không?" -> <node>hi_mastercard_collection</node><keyword>hi mastercard</keyword>
      * "Phí thường niên của JCB Ultimate" -> <node>jcb_ultimate</node><keyword>jcb ultimate</keyword>

   b. TRƯỜNG HỢP CẦN TRẢ VỀ "unknown":
      * "kích hoạt thẻ trên app" -> <node>unknown</node><keyword>generic</keyword>
      * "Cách đăng ký thẻ ghi nợ" -> <node>unknown</node><keyword>generic</keyword>
      * "Hướng dẫn kích hoạt thẻ" -> <node>unknown</node><keyword>generic</keyword>
      * "In thẻ tại smartbank sau bao lâu sẽ nhận được thẻ?" -> <node>unknown</node><keyword>generic</keyword>
      * "khoá thẻ tạm thời có mất phí không" -> <node>unknown</node><keyword>generic</keyword>
      * "Xem số thẻ" -> <node>unknown</node><keyword>generic</keyword>
      * "phí hủy thẻ phi vật lý" -> <node>unknown</node><keyword>generic</keyword>
      * "Thẻ priority pass" -> <node>unknown</node><keyword>generic</keyword>. Priority Pass không phải visa priority nên là unknown

6. QUY TẮC TẠO MÔ TẢ:
   - Dạng: "Thẻ [keyword] thuộc [loại] [node_display_name]."
   - VD: 
     * "Thẻ wukong thuộc bộ sưu tập Hi LOL Collection."
     * "Thẻ visa infinite thuộc dòng sản phẩm Visa Infinite."
     * "Thẻ mastercard thuộc thương hiệu Mastercard."
     * "Thẻ tín dụng thuộc loại thẻ Thẻ tín dụng."
     
Trả về CHÍNH XÁC định dạng sau, không thêm giải thích, và chỉ trả về 1 node duy nhất:
<keyword>từ_khóa_trích_xuất_được</keyword>
<node>tên_node_chứa_thông_tin</node>
<description>Thẻ [keyword] thuộc [loại] [node_display_name].</description>
Hệ thống cây phân cấp thẻ: {CARD_HIERARCHY}

Đầu vào: "{query}"
"""