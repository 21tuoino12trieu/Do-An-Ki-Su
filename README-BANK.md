# Giới thiệu đồ án — định hướng lĩnh vực ngân hàng

## 1. Tên đề tài

- **Nghiên cứu và xây dựng hệ thống kho tri thức doanh nghiệp thông minh từ Confluence.**
- **Lĩnh vực ứng dụng:** tri thức nội bộ ngân hàng, tập trung vào tài liệu chính sách, quy trình và hướng dẫn nghiệp vụ.
- **Đối tượng sử dụng:** nhân viên đăng nhập để khai thác chính sách và khuyến mãi ở cả hai Space; khách hàng dùng tài khoản khách hàng chỉ hỏi khuyến mãi; quản trị có toàn bộ chức năng. Nhân viên không cấu hình nguồn, chạy đồng bộ, xem trạng thái vận hành hoặc retry.

## 2. Học viên

- **Họ và tên:** Đặng Nam Cường.

## 3. Bài toán đặt ra

- Trong bối cảnh ngân hàng được đồ án mô phỏng, tri thức nghiệp vụ được lưu trên Confluence dưới dạng nhiều trang tài liệu, có thể liên quan đến nhiều bộ phận và quy trình khác nhau.
- Nhân viên cần tìm được thông tin phù hợp với tình huống công việc, nhưng việc tìm theo từ khóa và đọc nhiều trang có thể mất thời gian hoặc chưa cung cấp đủ ngữ cảnh để hiểu đúng hướng dẫn.
- Tài liệu được tạo mới, sửa đổi, xóa hoặc thay đổi phạm vi được phép khai thác. Hệ thống hỏi đáp phải nhận biết những thay đổi này, quản lý phiên bản và tránh sử dụng nội dung đã bị vô hiệu hóa trong kho tri thức.
- Việc đưa tài liệu vào chatbot cần tuân theo chính sách quản lý và khai thác tài liệu của tổ chức, bao gồm phạm vi dữ liệu được phép sử dụng và điều kiện gửi nội dung đến dịch vụ AI.
- Câu trả lời cần có nguồn dẫn để nhân viên đối chiếu tài liệu, biết phiên bản được sử dụng và nhận ra khi thông tin chưa đủ để trả lời.
- Bài toán của đồ án là xây dựng và kiểm chứng một kho tri thức đồng bộ từ Confluence, kết hợp chatbot hỏi đáp tiếng Việt có dẫn nguồn, quản lý vòng đời tài liệu và hỗ trợ xử lý lại sau lỗi.

## 4. Vì sao hệ thống chatbot nội bộ được hình thành?

- **Lý do 1 — Quản lý việc khai thác tài liệu theo policy của tổ chức:** chatbot cần sử dụng tài liệu trong phạm vi được phép, có nguồn gốc và trạng thái rõ ràng; khi tài liệu không còn được phép khai thác, nội dung đó phải được loại khỏi truy xuất sau khi hệ thống phát hiện và xác minh. Policy ở đây được hiểu là chính sách quản lý, sử dụng và vòng đời tài liệu; chi tiết phân quyền cần được đặc tả theo môi trường triển khai.
- **Lý do 2 — Giúp nhân viên tiếp cận và sử dụng tri thức hiệu quả hơn:** chatbot cho phép đặt câu hỏi bằng ngôn ngữ tự nhiên, tìm các đoạn liên quan và tổng hợp thông tin từ tài liệu; hướng đến giảm thời gian tìm kiếm và giảm việc phải hỏi đồng nghiệp những câu hỏi đã có câu trả lời trong kho tri thức.
- **Lý do 3 — Hỗ trợ áp dụng quy trình nghiệp vụ nhất quán:** trong lĩnh vực ngân hàng, tìm được tài liệu chưa đồng nghĩa với hiểu đúng cách áp dụng. Chatbot có thể hỗ trợ tra cứu các bước, điều kiện, ngoại lệ và đầu mối xử lý được ghi trong tài liệu, giúp nhân viên đối chiếu hướng dẫn trước khi thực hiện công việc; hướng đến giảm nguy cơ hiểu sai hoặc bỏ sót thông tin nghiệp vụ.
- **Cơ sở cho lý do thứ ba:** các nguyên tắc quản lý rủi ro vận hành của Basel nhấn mạnh vai trò của quy trình, con người và kiểm soát nội bộ. Việc dùng chatbot để hỗ trợ tra cứu là phương án của đồ án, không phải yêu cầu của Basel. [Tham khảo BIS](https://www.bis.org/publications/fsi-summary-principles-sound-management-operational-risk-psmor-executive-summary).
- **Vai trò của hệ thống:** hỗ trợ nhân viên tiếp cận tài liệu và kiểm tra căn cứ; quyết định, phê duyệt và xử lý nghiệp vụ vẫn thuộc người hoặc bộ phận có thẩm quyền.
- **Phạm vi kiểm chứng cập nhật 05/11/2026:** bản thử nghiệm sử dụng 100–300 trang tiếng Việt trong 2 Space riêng theo nhóm nhân viên/khách hàng. Đăng nhập và kiểm soát quyền theo nhóm là yêu cầu thiết kế mới, chưa có code; chưa yêu cầu phân quyền tùy biến từng trang.
- **Giá trị cần đo:** thời gian tìm thông tin, tỷ lệ trả lời đúng và có nguồn, khả năng sử dụng đúng phiên bản đang có hiệu lực và cách xử lý câu hỏi thiếu căn cứ. Giảm sai sót hay tổn thất thực tế của ngân hàng là kỳ vọng dài hạn, chưa phải kết quả được đồ án chứng minh.
