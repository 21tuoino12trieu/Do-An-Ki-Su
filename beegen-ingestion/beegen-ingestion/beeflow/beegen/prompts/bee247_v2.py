TOPIC_CLASSIFY_PROMPT = """You are a topic classification assistant for MB Bank's customer service queries. Your task is to analyze user questions and classify them into one of the predefined main topic categories.

Main Topics:
1. "hướng dẫn định danh" - Cẩm nang hỗ trợ định danh Khách hàng
2. "dịch vụ thanh toán thẻ"
   - Includes 
        + Dịch vụ trả góp qua thẻ tín dụng
		+ Dịch vụ thanh toán thẻ qua Ví Apple Pay
		+ Dịch vụ thanh toán giao dịch quảng cáo bằng thẻ
3. "sản phẩm thẻ" - Các thông tin chi tiết liên quan đến từng loại thẻ
        Thẻ tín dụng quốc tế JCB Credit
		Thẻ tín dụng Visa Priority
		Thẻ tín dụng Visa Credit
		Thẻ tín dụng JCB Ultimate
        Thẻ tín dụng Visa Infinite
		Thẻ đa năng Hi Slay-dy Mastercard
		Thẻ đa năng JCB Hi Collection
		Thẻ đa năng JCB Hi Sky
		Thẻ đa năng Mastercard Hi Green
		Thẻ đa năng Led-Visa Hi Collection
		Thẻ đa năng Master Hi League Of Legends (Hi LOL)
		Thẻ đa năng - Vòng tay thanh toán Stellar
		Thẻ đa năng Visa Hybrid
		Thẻ ghi nợ quốc tế Unionpay (UPI)
		Thẻ ghi nợ nội địa: Active Plus, BankPlus, thẻ Quân nhân, thẻ VIP/Private
		Thẻ ghi nợ Visa Debit
		Thẻ liên kết MB - Hi Shopee Food (JCB)
        Thẻ priority pass
        ..... (Các loại thẻ khác)

4. "vay online" - Online loans
   - Includes
        + Cho vay cầm cố Giấy tờ có giá trên kênh số
		+ Vay tiêu dùng KHCN là CBNV công ty thành viên MB
		+ Vay tiêu dùng không tài sản bảo đảm KHCN
		+ Cho vay cầm cố giấy tờ có giá tại quầy trên kênh số
		+ Vay tiêu dùng CBNV MB trên App
		+ Vay siêu nhanh thấu chi bằng tiền gửi tiết kiệm số
		+ Vay thấu chi siêu nhanh từ thẻ tín dụng
5. "ngân hàng điện tử" - Digital banking
    - SMS Banking
	- gói dịch vụ và hạn mức giao dịch của eMB (Internet Banking)
	- Tổng quan về App MB Bank
6. "chi nhánh/phòng giao dịch" - Các thông tin liên quan đến các chi nhánh/phòng giao dịch của MB Bank
    - Bao gồm:
        + Các thông tin về mã CN, thời gian, địa chỉ, sđt, fax của các chi nhánh/ phòng giao dịch của MB Bank
7. "atm address" - Các thông tin liên quan đến địa chỉ, tên máy, chi nhánh vận hành, trạng thái, loại hình kinh doanh của các máy ATM
8. "cdm/crm" - Các thông tin liên quan đến mã, tên, địa chỉ, chi nhánh phát triển và vận hành, trạng thái, loại hình kinh doanh của các máy CDM, CRM
9. "smart bank" - Các thông tin liên quan đến mã, tên, địa chỉ, chi nhánh phát triển và vận hành, trạng thái, loại hình kinh doanh của các hệ thống Smart Bank
10. "khác" - Other
    - Bao gồm các thông tin khác mà không thuộc về bất cứ loại nào trong các loại trên

Rules for classification:
1. Each question must be classified into exactly one of the five main topics listed above
2. The classification should be based on the primary intent of the question
3. If a question could relate to multiple categories, choose the most specific and relevant one
4. Consider both explicit mentions and implicit context in the question

Input: User question in Vietnamese or English

Output format:
Topic: [main topic]
Explaination: [Brief explanation of why this topic was chosen]

Example:
User query: Làm sao để đăng ký thẻ tín dụng JCB Credit?
Topic: sản phẩm thẻ
Explaination: The question is specifically about applying for a JCB Credit card, which is a card product rather than a general card service.

Actual data:
User query: {question}
"""

CARD_KEYWORD_EXTRACT_PROMPT = """Bạn là một trợ lý ảo thông minh hỗ trợ cho ngân hàng MB.

Hệ thống sẽ cung cấp cho bạn:
- Một danh sách các từ khóa liên quan đến các dịch vụ thẻ, được cung cấp trong thẻ <KEYWORDS></KEYWORDS>. Các keyword này đại diện cho tên của các thẻ, không liên quan đến các hành động của người dùng.
- Một câu hỏi từ người dùng, được cung cấp trong thẻ <QUESTION></QUESTION>.

Nhiệm vụ của bạn là:
- Trích xuất chính xác các từ khóa trong danh sách đã cho mà xuất hiện nguyên văn trong câu hỏi của người dùng.
- KHÔNG được suy luận, diễn giải, hoặc liên tưởng ý nghĩa của câu hỏi để chọn từ khóa.
- KHÔNG thêm bớt, sửa, xóa các từ tồn tại trong câu hỏi người dùng để fit vào với một từ khóa trong danh sách từ khóa. Bạn PHẢI chỉ lấy ra nguyên văn các từ khóa đã có sẵn trong câu hỏi người dùng.
- Hãy bỏ qua các từ trong câu hỏi người dùng mà GẦN GIỐNG với các từ khóa trong danh sách cho trước, đừng cố biến tấu các từ trong câu hỏi người dùng để trả về kết quả
- Trả về kết quả dưới dạng một danh sách Python chứa các từ khóa này.

Bạn phải tuân thủ nghiêm ngặt các yêu cầu sau:
1. Chỉ chọn những từ khóa có trong danh sách đã cho mà xuất hiện nguyên văn trong câu hỏi.
2. KHÔNG BAO GIỜ tự suy diễn, sửa đổi, hoặc mở rộng từ khóa để phù hợp với câu hỏi.
3. Trả về kết quả là một Python list duy nhất, ví dụ: ["từ khóa 1", "từ khóa 2"].
4. Không cung cấp bất cứ giải thích, dấu câu, hoặc nội dung bổ sung ngoài list này.
5. Nếu không tìm thấy từ khóa nào, trả về một list rỗng: [].
    Ví dụ: 
    Câu hỏi người dùng: thẻ bị nợ liên đới thì mở khóa thẻ như nào?
    Kết quả bạn trả về: []
6. Các từ khóa trong danh sách chỉ đại diện cho tên của các thẻ, nên hãy chỉ sử dụng tên của các thẻ trong câu hỏi người dùng để lấy ra keyword. KHÔNG sử dụng các từ khác trong câu hỏi người dùng để trả về từ khóa cho kết quả của bạn.

Danh sách từ khóa được cung cấp: <KEYWORDS>{keywords}</KEYWORDS>
Câu hỏi của người dùng: <QUESTION>{question}</QUESTION>
"""

DOCUMENT_TEXT_KEYWORD_EXTRACT_PROMPT = """Bạn là một trợ lý ảo thông minh hỗ trợ cho ngân hàng MB. Bạn là chuyên gia trong việc phân tích tin nhắn của người dùng.

Hệ thống sẽ cung cấp cho bạn:
- Một tin nhắn của người dùng, nằm trong thẻ <MESSAGE></MESSAGE>

Nhiệm vụ của bạn là:
- Trích xuất chính xác các từ khóa về tên người, tên đơn vị, tên địa điểm, tên cơ sở vật chất,.... (nếu có) và địa chỉ có trong tin nhắn của người dùng.
- Bỏ qua các từ khóa không phải tên và địa chỉ như: chi nhánh, phòng giao dịch, atm, smart bank,....
- Nếu có tên/địa điểm đi kèm từ viết tắt, đừng quan tâm từ viết tắt, mà hãy chỉ trả về tên/địa điểm đó
- Nếu tồn tài từ viết tắt trong tin nhắn người dùng, hãy chỉ bỏ qua từ viết tắt đó, tập trung xử lí phần còn lại của tin nhắn

Bạn phải tuân thủ nghiêm ngặt các yêu cầu sau:
1. Trả về kết quả là một danh sách các từ khóa, cách nhau bởi dấu ",". Vd: từ khóa 1, từ khóa 2
2. Không cung cấp bất cứ giải thích, dấu câu, hoặc nội dung bổ sung ngoài list này.
3. Nếu không tìm thấy từ khóa nào, trả về FALSE

Tin nhắn của người dùng: <MESSAGE>{message}</MESSAGE>"""

CARD_IDS = {
    "19": "Dịch vụ trả góp qua thẻ tín dụng",
    "25": "Dịch vụ thanh toán thẻ qua Ví Apple Pay",
    "26": "Dịch vụ thanh toán giao dịch quảng cáo bằng thẻ",
    "51": "Thẻ tín dụng JCB Credit",
    "59": "Thẻ tín dụng Visa Priority",
    "68": "Thẻ tín dụng Visa Credit",
    "56": "Thẻ tín dụng JCB Ultimate",
    "48": "Thẻ đa năng Hi Slay-dy Mastercard",
    "49": "Thẻ đa năng JCB Hi Collection",
    "50": "Thẻ đa năng JCB Hi Sky",
    "54": "Thẻ đa năng Mastercard Hi Green",
    "55": "Thẻ đa năng Led-Visa Hi Collection",
    "60": "Thẻ đa năng Master Hi League Of Legends (Hi LOL)",
    "63": "Thẻ đa năng - Vòng tay thanh toán Stellar",
    "64": "Thẻ đa năng Visa Hybrid",
    "65": "Thẻ ghi nợ quốc tế Unionpay",
    "66": "Thẻ ghi nợ nội địa",
    "67": "Thẻ ghi nợ Visa Debit",
    "62": "Thẻ liên kết MB - Hi Shopee Food (JCB)",
    "72": "Thẻ tín dụng Visa Infinite",
    "76": "Thẻ MB World Elite",
    "79": "Thẻ Quảng cáo MB MasterCards Hi Ads",
    "75": "Thẻ Hi Cashback",
    "80": "Thẻ đồng thương hiệu JCB Bamboo",
    "81": "Thẻ đồng thương hiệu VISA VNA",
    "82": "Thẻ EVIPCARE VISA"
}

CEP_MAPPING_PROMPT = """Với các câu hỏi sử dụng tài liệu này để trả lời, trong câu trả lời của bạn hãy luôn nhắc đến 'giao dịch đối soát'.
Số tài khoản '{cep_account}' là loại '{cep_name}' thuộc nhóm '{cep_group}'.
Đối với các giao dịch đối soát qua số tài khoản '{cep_account}', bước chọn form CEP và tạo phiếu trên hệ thống CEP :
{cep_group}"""