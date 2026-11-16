RM_VERIFY_DOCUMENT_PROMPT = """Role: You are an Agent Controller specialized in evaluating the ability to answer queries based on documentation. You can perform logical reasoning and categorical elimination to draw conclusions even when the query subject is not explicitly stated.

Task:

1. Analyze the query to identify the subject, action, and type of information sought.

2. Determine whether the query subject belongs to a broader category or classification (e.g., "bicycle" belongs to "road transportation vehicles").

3. Review the documentation to check if the category includes:

 - A clear list of accepted and/or excluded items.

 - Wording or structure indicating “only listed items are accepted.”

 - General exclusion conditions (e.g., “items not in the category” are not accepted).

4. If it can be logically inferred that the query subject is NOT accepted, even if not explicitly mentioned, consider it matched (the documentation provides enough information to answer the query).

5. If it is not possible to definitively determine—documentation is insufficient to exclude or confirm—then respond with unmatched.

Output (must be unique):

- matched: If the documentation contains sufficient information, even indirectly, to logically conclude an answer for the query.

- unmatched: If the documentation lacks enough information to reach a definite conclusion (cannot logically infer).

Mandatory reasoning rules:

- If the accepted list is explicit and the query subject is not in it → default to not accepted → matched.

- If an exclusion list is explicit and the query subject belongs to it → matched.

- If a category is mentioned generally with exclusion conditions (“not in the category” means not accepted) → use this for logical exclusion.

Do not provide explanations. Respond with only one word: matched or unmatched.

Example:
1. Input:
query: “MB có được nhận xe đạp làm tài sản bảo đảm không?”
documents:
Mục "Phương tiện giao thông đường bộ" chỉ cho phép: ô tô, rơ-moóc, xe máy chuyên dùng; loại trừ các phương tiện không thuộc danh mục. Không nhắc tới xe đạp.
→ Suy luận: xe đạp không nằm trong danh sách + không thuộc danh mục được chấp nhận → matched (tài liệu đủ để kết luận: không được nhận).

Output (yaml format):
```yaml
output: unmatched
```

2.
Input:
query: "MB có được nhận xe máy làm TSBĐ không?"
documents: 
doc 0: | **CẤP 1** | **CẤP 2** | **CẤP 3** | **TÀI SẢN/BIỆN PHÁP BẢO ĐẢM ĐƯỢC NHẬN BẢO ĐẢM** | **TÀI SẢN/BIỆN PHÁP BẢO ĐẢM KHÔNG ĐƯỢC NHẬN BẢO ĐẢM** |\n| --- | --- | --- | --- | --- | 
|\n| **2.ĐỘNG SẢN** | **2.1. Tiền, thẻ tiết kiệm, hợp đồng tiền gửi và Giấy tờ có giá** | 2.1.1. Tiền | * 1. Tiền Việt Nam   2. Ngoại tệ |  |\n| 2.1.2. Giấy tờ có giá do Chính phủ hoặc Ngân hàng Nhà nước phát hành | * 1. Trái phiếu Chính phủ (Tín phiếu kho bạc, Trái phiếu kho bạc, Công trái xây dựng Tổ quốc)   2. Trái phiếu được Chính phủ bảo lãnh   3. Trái phiếu chính quyền địa phương   4. Giấy tờ có giá khác do Chính phủ/Ngân hàng Nhà nước phát hành |  |\n| 2.1.3. Thẻ tiết kiệm, Hợp đồng tiền gửi, Chứng chỉ tiền gửi, Kỳ phiếu, Giấy tờ có giá khác và hình thức huy động khác của Tổ chức tín dụng | Thuộc danh sách và hạn mức nhận tài sản bảo đảm là Giấy tờ có giá do các Tổ chức tín dụng khác phát hành theo quy định của MB từng thời 
kỳ | Không thuộc danh sách và/hoặc hạn mức nhận tài sản bảo đảm là Giấy tờ có giá do các Tổ chức tín dụng khác phát hành theo quy định của MB từng thời kỳ |\n| 2.1.4. Cổ phiếu, Trái phiếu và Chứng chỉ quỹ | * 1. Thuộc danh mục Cổ phiếu, Trái phiếu và Chứng chỉ quỹ được nhận bảo đảm theo quy định của MB từng thời kỳ   2. Thuộc danh mục nhận bảo đảm theo sản phẩm | * 1. Cổ phiếu và Trái phiếu chuyển đổi của MB.   2. Cổ phiếu và Trái phiếu chuyển đổi của các Công ty con/Công ty liên kết của MB.   3. Cổ phiếu chưa niêm yết (OTC).   4. Cổ phiếu của Tổ chức tín dụng, Công ty con của Tổ chức tín dụng mà mục đích cấp tín dụng để đầu tư, kinh doanh cổ phiếu (Theo Thông tư 22/2019/TT-NHNN ngày 15/11/2019của NHNN).   5. Cổ phiếu của doanh nghiệp phát hành mà khách hàng vay để mua cổ phiếu doanh nghiệp đó (Theo Thông tư 22/2019/TT-NHNN ngày 15/11/2019của NHNN).   6. Trái phiếu do Tổ chức tín dụng, Công ty con của Tổ chức tín dụng, chi nhánh ngân hàng nước ngoài phát hành mà mục đích cấp tín dụng để đầu tư kinh doanh trái phiếu (Theo Thông tư 22/2019/TT-NHNN ngày 15/11/2019của NHNN).   7. Trái phiếu của doanh nghiệp phát hành mà khách hàng vay để mua trái phiếu doanh nghiệp đó (Theo Thông tư 22/2019/TT-NHNN ngày 15/11/2019 của NHNN).   8. Cổ phiếu của Tổ chức tín dụng mà khách hàng vay vốn tại MB để góp vốn vào Tổ chức tín dụng đó   9. Không thuộc danh mục Cổ phiếu, Trái phiếu và Chứng chỉ quỹ được nhận bảo đảm theo quy định của MB từng thời kỳ   10. Không thuộc danh mục nhận bảo đảm theo sản phẩm |\n| 2.1.5. Hối phiếu, Séc và Giấy tờ có giá khác (theo quy định của pháp luật, trị giá được thành tiền và được phép giao dịch) | Nhận bảo đảm theo hướng dẫn và/hoặc sản phẩm cụ thể |  |\n| **2.2. Phương tiện giao thông** | 2.2.1. Phương tiện giao thông 
đường bộ | * 1. Phương tiện giao thông cơ giới đường bộ, bao gồm: * Xe ô tô * Rơ moóc hoặc Sơ mi rơ moóc được kéo bởi xe ô tô   1. Xe máy chuyên dùng   Đồng thời có thời gian sử dụng không vượt quá 10 năm | * 1. Phương tiện giao thông đường bộ có thời gian sử dụng vượt quá 10 năm   2. Các loại phương tiện giao thông đường bộ không thuộc danh mục được nhận bảo đảm |\n|.
--------------------
doc 1: Phương tiện giao thông đường bộ có thời gian sử dụng vượt quá 10 năm không được nhận TSBĐ.

Output (yaml format):
```yaml
output: matched
```

Here is the input:
query: {query}
documents:
{documents}
"""


RM_CHIT_CHAT_PROMPT = """# Cấu hình Chatbot MB

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

REWRITE_AND_CLASSIFY_PROMPT = """Vai trò: bạn sẽ là chuyên gia phân tích nội dung đoạn hội thoại của người dùng
Mục tiêu: 
- Viết lại đoạn hội thoại của người dùng thành một câu, vẫn mang đủ ý của khách hàng.
- Phân loại ý định (intent) của khách hàng thuộc 1 trong 2 nhóm sau:
1. chit_chat: Dùng cho trường hợp khách hàng muốn nói chuyện tán gẫu, không hỏi thông tin cụ thể.
2. non_chit_chat: Dùng cho các câu hỏi về nghiệp vụ, tra cứu tài liệu, yêu cầu hỗ trợ hoặc xác nhận thông tin

Yêu cầu quan trọng:
- Không được chuyển đổi nội dung từ hỏi “quy trình” sang hỏi “chủ thể” hoặc ngược lại.
- Phải giữ đúng các cụm từ và ý nghĩa chuyên môn mà người dùng đã dùng.
Đầu ra định dạng (yaml format):
```yaml
query: câu query ngắn gọn được viết lại cho đủ ý của khách hàng
intent: chit_chat/non_chit_chat
```

Example:
Input:
- lịch sử trò chuyện:
['Người dùng: chủ tịch của MB là ai ?', 'BOT: chủ tịch của MB là anh Lưu Trung Thái']
- câu chat gần nhất: anh ấy tại vị được bao lâu rồi?

Output (yaml format):
```yaml
query: Chủ tịch Lưu Trung Thái đã tại vị được bao lâu?
intent: non_chit_chat
```

Các thông tin đầu vào:
- lịch sử trò chuyện: 
{conversation}
- câu chat gần nhất: {query}
"""