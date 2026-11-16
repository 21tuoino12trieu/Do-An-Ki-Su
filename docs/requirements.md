# Tài liệu đặc tả yêu cầu

| Thông tin | Nội dung |
| --- | --- |
| Đề tài | Nghiên cứu và xây dựng hệ thống kho tri thức doanh nghiệp thông minh từ Confluence |
| Học viên | Đặng Nam Cường |
| Loại tài liệu | Đặc tả yêu cầu phần mềm |
| Phiên bản | 2.0 |
| Ngày cập nhật | 16/11/2026 |
| Trạng thái | Dự thảo để thẩm định |
| Tài liệu liên quan | [Thiết kế chung](architecture.md), [Thiết kế chi tiết](detailed-design.md) |

- **Mục đích:** xác định hệ thống phục vụ ai, giải quyết việc gì, có những chức năng nào và cần trả kết quả gì.
- **Đối tượng đọc:** giảng viên hướng dẫn, người thực hiện đồ án và người kiểm thử.
- Tài liệu mô tả yêu cầu của sản phẩm. Cách tổ chức hệ thống và triển khai nằm trong tài liệu thiết kế.
- Kết quả đã thực hiện và kiểm chứng được ghi tại [báo cáo tiến độ](progress/README.md).

## Mục lục

1. [Bài toán và lý do hình thành](#1-bài-toán-và-lý-do-hình-thành)
2. [Sản phẩm đầu ra](#2-sản-phẩm-đầu-ra)
3. [Phạm vi và ràng buộc](#3-phạm-vi-và-ràng-buộc)
4. [Người sử dụng và phân quyền](#4-người-sử-dụng-và-phân-quyền)
5. [Danh mục yêu cầu chức năng](#5-danh-mục-yêu-cầu-chức-năng)
6. [Sơ đồ Use Case](#6-sơ-đồ-use-case)
7. [Mô tả chi tiết các chức năng](#7-mô-tả-chi-tiết-các-chức-năng)
8. [Yêu cầu xử lý tự động](#8-yêu-cầu-xử-lý-tự-động)

<!--
9. [Quy tắc nghiệp vụ](#9-quy-tắc-nghiệp-vụ)
10. [Yêu cầu phi chức năng](#10-yêu-cầu-phi-chức-năng)
11. [Tiêu chí và kịch bản nghiệm thu](#11-tiêu-chí-và-kịch-bản-nghiệm-thu)
12. [Ma trận truy vết](#12-ma-trận-truy-vết)
13. [Quyết định còn mở](#13-quyết-định-còn-mở)
-->

14. [Thuật ngữ và tài liệu liên quan](#14-thuật-ngữ-và-tài-liệu-liên-quan)

## 1. Bài toán và lý do hình thành

### 1.1. Bối cảnh

- Doanh nghiệp lưu các chính sách, quy trình và hướng dẫn trên Confluence.
- Trong bối cảnh ngân hàng, nhân viên cần tra cứu chính sách công ty và thông tin chương trình khuyến mãi để làm việc, hỗ trợ khách hàng.
- Khách hàng cần tìm hiểu ưu đãi, đối tượng áp dụng, điều kiện và thời gian của từng chương trình.
- Tài liệu được cập nhật thường xuyên; không phải người dùng nào cũng được đọc toàn bộ tài liệu.
- Đồ án sử dụng dữ liệu của một tổ chức ngân hàng giả lập, do người thực hiện chuẩn bị và kiểm soát.

### 1.2. Vấn đề cần giải quyết

| Vấn đề | Khó khăn hiện tại | Kết quả mong muốn |
| --- | --- | --- |
| Quyền sử dụng tài liệu | Nhân viên được đọc chính sách nội bộ; khách hàng chỉ được đọc thông tin khuyến mãi dành cho họ | Mỗi người chỉ hỏi đáp và xem tài liệu trong phạm vi được phép |
| Thời gian tra cứu | Người dùng phải tìm, đọc và tổng hợp nhiều trang; bộ phận hỗ trợ phải trả lời các câu hỏi lặp lại | Người dùng hỏi bằng tiếng Việt, nhận câu trả lời từ tài liệu và có nguồn để kiểm tra |

### 1.3. Phát biểu bài toán

- Xây dựng một kho tri thức được cập nhật tự động từ hai không gian tài liệu trên Confluence.
- Cung cấp một chatbot chung, trả lời dựa trên nội dung tài liệu mà tài khoản được phép đọc.
- Cho nhân viên và quản trị tìm kiếm tài liệu khi cần tra cứu trực tiếp.
- Cho người dùng xem đoạn tài liệu làm căn cứ cho câu trả lời.
- Cho quản trị cấu hình nguồn, theo dõi cập nhật và nhận thông báo khi xử lý hoàn tất.

## 2. Sản phẩm đầu ra

| Sản phẩm | Nội dung cần có |
| --- | --- |
| Kho tri thức doanh nghiệp | Nội dung thu thập từ 100–300 trang thuộc hai Space, kèm nguồn, phiên bản và quyền đọc |
| Ứng dụng hỏi đáp và tra cứu | Hỏi đáp tiếng Việt theo quyền tài khoản; câu trả lời có trích dẫn; nhân viên và quản trị có chức năng tìm kiếm tài liệu |
| Chức năng cập nhật tự động | Kiểm tra nguồn mỗi 60 phút, xử lý trang thêm/sửa/xóa và đưa nội dung đã xử lý vào kho hỏi đáp |
| Giao diện quản trị | Cấu hình nguồn, yêu cầu đồng bộ, xem trạng thái, xử lý lại công việc và nhận thông báo kết quả |
| Mã nguồn và cấu hình chạy | Mã nguồn ứng dụng, cấu hình mẫu không chứa thông tin bí mật và hướng dẫn khởi động hệ thống |
| Tài liệu bàn giao | Đặc tả yêu cầu, thiết kế chung, thiết kế chi tiết và hướng dẫn sử dụng/vận hành |
| Bộ kiểm thử và báo cáo đánh giá | Dữ liệu thử, bộ câu hỏi, kết quả kiểm thử và đánh giá chất lượng câu trả lời, thời gian xử lý |

## 3. Phạm vi và ràng buộc

### 3.1. Phạm vi xác định

| Nội dung | Yêu cầu |
| --- | --- |
| Nguồn tài liệu | Một hệ thống Confluence Cloud Free |
| Không gian tài liệu | Hai Space: chính sách nội bộ và chương trình khuyến mãi |
| Chatbot | Một chatbot chung cho cả hai Space |
| Quy mô | Tổng 100–300 trang |
| Ngôn ngữ | Tài liệu, câu hỏi và giao diện bằng tiếng Việt |
| Định dạng tài liệu | Trang HTML đơn giản, gồm tiêu đề, đoạn văn, danh sách, bảng văn bản, liên kết và khối mã |
| Ảnh | Giữ tham chiếu ảnh trong nội dung; không đọc hoặc giải thích chữ/nội dung trong ảnh |
| Cập nhật | Thu thập lần đầu; tự kiểm tra thay đổi mỗi 60 phút; quản trị có thể yêu cầu đồng bộ thủ công |
| Phiên bản | Giữ các phiên bản mà hệ thống thực tế thu thập được |
| Khai thác | Hỏi đáp và xem nguồn theo quyền; tìm kiếm tài liệu dành cho nhân viên và quản trị |
| Vận hành | Cấu hình nguồn, theo dõi trạng thái, nhận thông báo và yêu cầu xử lý lại thủ công |

### 3.2. Ràng buộc sử dụng và triển khai

- Hệ thống được thử nghiệm trên máy phát triển có 32 GB RAM, không có GPU.
- Việc cập nhật định kỳ được thực hiện khi hệ thống đang hoạt động và kết nối được với nguồn tài liệu.
- Dịch vụ AI sử dụng hạn mức miễn phí; hệ thống không tự chuyển sang gói trả phí khi hết hạn mức.
- Tài liệu thử nghiệm phải được phép thu thập và sử dụng với dịch vụ AI.
- Công nghệ, cơ sở dữ liệu và cấu hình triển khai được mô tả tại [thiết kế chung](architecture.md) và [thiết kế chi tiết](detailed-design.md).

## 4. Người sử dụng và phân quyền

### 4.1. Tác nhân

| Mã | Người sử dụng | Nhu cầu |
| --- | --- | --- |
| A01 | Nhân viên nội bộ | Tra cứu chính sách công ty và chương trình khuyến mãi |
| A02 | Khách hàng có tài khoản | Hỏi về chương trình khuyến mãi và xem tài liệu giải thích |
| A03 | Quản trị kho tri thức | Sử dụng kho tri thức và quản lý việc cập nhật tài liệu |

### 4.2. Ma trận quyền chức năng

| Chức năng | Nhân viên | Khách hàng | Quản trị |
| --- | --- | --- | --- |
| UC10 — Đăng nhập/đăng xuất | Có | Có | Có |
| UC01 — Tìm kiếm tài liệu | Cả hai Space | Không | Cả hai Space |
| UC02 — Hỏi đáp chính sách | Có | Không | Có |
| UC11 — Hỏi đáp khuyến mãi | Có | Có | Có |
| UC03 — Xem nguồn | Cả hai Space | Chỉ khuyến mãi | Cả hai Space |
| UC04 — Cấu hình nguồn | Không | Không | Có |
| UC05 — Đồng bộ thủ công | Không | Không | Có |
| UC08 — Xem trạng thái và nhận thông báo vận hành | Không | Không | Có |
| UC09 — Xử lý lại thủ công | Không | Không | Có |

### 4.3. Quyền đọc theo Space

| Space | Người được phép đọc |
| --- | --- |
| Chính sách nội bộ | Nhân viên và quản trị |
| Chương trình khuyến mãi | Khách hàng, nhân viên và quản trị |

- Mỗi trang nhận quyền đọc từ Space chứa trang đó.
- Tài liệu chưa được xác định quyền đọc không được sử dụng để trả lời hoặc cung cấp nguồn.
- Khi trang chuyển Space hoặc quyền của Space thay đổi, quyền đọc tài liệu phải được cập nhật, kể cả khi nội dung không đổi.

### 4.4. Nguyên tắc kiểm soát truy cập

- Người dùng phải đăng nhập để sử dụng chức năng được cấp.
- Hệ thống xác định quyền từ tài khoản; nội dung câu hỏi không làm thay đổi quyền.
- Tài liệu ngoài quyền không được dùng để tạo câu trả lời, hiển thị kết quả tìm kiếm hoặc xem nguồn.
- Khách hàng không cần có tài khoản Confluence để xem nguồn khuyến mãi được phép trong ứng dụng.
- Thông tin đăng nhập nguồn và thông tin bí mật không được hiển thị cho người dùng.
- Chức năng và thông báo vận hành chỉ dành cho quản trị.

## 5. Danh mục yêu cầu chức năng

| Mã | Yêu cầu | Người sử dụng/đối tượng phục vụ | Kết quả cần có |
| --- | --- | --- | --- |
| FR01 | Cấu hình nguồn và quyền đọc | Quản trị | Lưu được nguồn Confluence, hai Space và nhóm người được đọc từng Space |
| FR02 | Thu thập tài liệu lần đầu | Quản trị; hệ thống thực hiện | Thu thập đủ các trang hợp lệ trong phạm vi đã chọn, kèm nguồn và phiên bản |
| FR03 | Đồng bộ định kỳ và thủ công | Quản trị; hệ thống thực hiện | Tự kiểm tra mỗi 60 phút hoặc chạy theo yêu cầu; không có hai lượt cùng nguồn chạy đồng thời |
| FR04 | Nhận biết thay đổi tài liệu | Hệ thống thực hiện | Phân biệt trang mới, sửa, xóa và thay đổi thông tin/quyền; không xử lý lại nội dung không đổi khi không cần thiết |
| FR05 | Ghi nhận phiên bản và nguồn | Người đọc tài liệu; quản trị | Xác định được tài liệu, phiên bản đã thu thập và nguồn dùng cho kết quả |
| FR06 | Bắt đầu xử lý tài liệu đã chuẩn bị | Hệ thống thực hiện | Chỉ bắt đầu khi nội dung đã chuẩn bị xong; phân biệt yêu cầu được tiếp nhận với xử lý hoàn tất |
| FR07 | Chuẩn bị tài liệu để hỏi đáp | Hệ thống thực hiện | Nội dung được chuyển đổi, chia thành các đoạn và lưu để tìm kiếm/hỏi đáp; chỉ sử dụng sau khi xử lý thành công |
| FR09 | Tìm kiếm và hỏi đáp từ tài liệu | Nhân viên, khách hàng, quản trị theo mục 4.2 | Kết quả đúng quyền, dựa trên tài liệu và có nguồn để kiểm tra |
| FR12 | Ghi nhận kết quả và số liệu xử lý | Quản trị; người đánh giá | Theo dõi được tài liệu/lượt cập nhật và có số liệu thời gian, kết quả phục vụ đánh giá |
| FR14 | Áp dụng quyền đọc tài liệu | Cả ba nhóm người dùng | Cùng một quyền đọc được áp dụng khi tìm kiếm, hỏi đáp và xem nguồn |
| FR15 | Thông báo xử lý hoàn tất | Quản trị | Nhận được kết quả đúng tài liệu/lượt cập nhật sau khi xử lý thành công |

## 6. Sơ đồ Use Case

- Sơ đồ thể hiện những chức năng mỗi nhóm người dùng được sử dụng.
- Hình người biểu diễn người sử dụng; hình elip biểu diễn chức năng.
- Mũi tên chỉ quan hệ sử dụng chức năng, không chỉ thứ tự thực hiện.

### 6.1. Tổng quan tác nhân và các chức năng

![Use Case tổng quan](use-cases/diagrams/01-usecase-tong-the.svg)

### 6.2. Nhân viên nội bộ

![Use Case nhân viên nội bộ](use-cases/diagrams/02-usecase-nhan-vien.svg)

### 6.3. Khách hàng có tài khoản

![Use Case khách hàng](use-cases/diagrams/03-usecase-khach-hang.svg)

### 6.4. Quản trị kho tri thức

![Use Case quản trị](use-cases/diagrams/04-usecase-quan-tri.svg)

- Mã nguồn và cách chỉnh sửa sơ đồ: [tài nguyên Use Case](use-cases/README.md).

## 7. Mô tả chi tiết các chức năng

### 7.1. UC10 — Đăng nhập và đăng xuất

| Nội dung | Mô tả |
| --- | --- |
| Mục tiêu | Cho người dùng truy cập đúng chức năng của tài khoản và kết thúc việc sử dụng |
| Người sử dụng | Nhân viên, khách hàng, quản trị |
| Điều kiện thực hiện | Có tài khoản được cấp; đăng xuất khi đang đăng nhập |
| Đầu vào | Thông tin đăng nhập; yêu cầu đăng xuất |
| Thao tác bắt đầu | Chọn Đăng nhập hoặc Đăng xuất |
| Kết quả | Đăng nhập thành công với đúng quyền, hoặc đã đăng xuất |

| Bước | Người dùng | Hệ thống |
| --- | --- | --- |
| 1 | Nhập thông tin và chọn Đăng nhập | Kiểm tra tài khoản |
| 2 | Sử dụng ứng dụng sau khi đăng nhập | Hiển thị các chức năng tài khoản được phép dùng |
| 3 | Chọn Đăng xuất khi muốn kết thúc | Kết thúc phiên đăng nhập và yêu cầu đăng nhập lại để tiếp tục sử dụng |

### 7.2. UC01 — Tìm kiếm tài liệu

| Nội dung | Mô tả |
| --- | --- |
| Mục tiêu | Tìm nhanh tài liệu hoặc đoạn nội dung liên quan |
| Người sử dụng | Nhân viên, quản trị |
| Điều kiện thực hiện | Đã đăng nhập và có quyền tìm kiếm |
| Đầu vào | Từ khóa hoặc nội dung cần tìm bằng tiếng Việt |
| Thao tác bắt đầu | Chọn Tìm kiếm |
| Kết quả | Danh sách tiêu đề, đoạn trích, phiên bản và nguồn tài liệu được phép đọc |

| Bước | Người dùng | Hệ thống |
| --- | --- | --- |
| 1 | Nhập nội dung cần tìm và gửi yêu cầu | Kiểm tra nội dung tìm kiếm và quyền tài khoản |
| 2 | Xem danh sách kết quả | Tìm và hiển thị những nội dung liên quan, đã xử lý xong và được phép đọc |
| 3 | Chọn một nguồn nếu muốn đọc thêm | Hiển thị nguồn theo chức năng UC03 |

### 7.3. UC02 — Hỏi đáp chính sách công ty

| Nội dung | Mô tả |
| --- | --- |
| Mục tiêu | Giúp người dùng hiểu chính sách, quy trình và hướng dẫn nội bộ |
| Người sử dụng | Nhân viên, quản trị |
| Điều kiện thực hiện | Đã đăng nhập và có quyền đọc chính sách nội bộ |
| Đầu vào | Câu hỏi tiếng Việt về chính sách công ty |
| Thao tác bắt đầu | Gửi câu hỏi cho chatbot |
| Kết quả | Câu trả lời dựa trên tài liệu, kèm trích dẫn; thông báo rõ khi chưa đủ thông tin hoặc chưa thể trả lời |

| Bước | Người dùng | Hệ thống |
| --- | --- | --- |
| 1 | Nhập và gửi câu hỏi | Kiểm tra câu hỏi và quyền tài khoản |
| 2 | Chờ câu trả lời | Tìm các đoạn tài liệu liên quan mà tài khoản được phép đọc |
| 3 | Đọc câu trả lời | Tổng hợp từ các đoạn đã tìm được và hiển thị trích dẫn nguồn |
| 4 | Chọn trích dẫn nếu muốn kiểm tra | Hiển thị nguồn theo UC03 |

- Người dùng có thể hỏi trực tiếp, không phải tìm kiếm tài liệu trước.
- Câu trả lời không được thêm điều kiện hoặc số liệu không có trong tài liệu.

### 7.4. UC11 — Hỏi đáp chương trình khuyến mãi

| Nội dung | Mô tả |
| --- | --- |
| Mục tiêu | Giải thích ưu đãi, đối tượng, điều kiện và thời gian áp dụng chương trình |
| Người sử dụng | Khách hàng, nhân viên, quản trị |
| Điều kiện thực hiện | Đã đăng nhập và có quyền đọc thông tin khuyến mãi |
| Đầu vào | Câu hỏi tiếng Việt về chương trình khuyến mãi |
| Thao tác bắt đầu | Gửi câu hỏi cho chatbot |
| Kết quả | Câu trả lời từ tài liệu khuyến mãi kèm nguồn; nêu rõ phần chưa có thông tin nếu tài liệu không đủ |

| Bước | Người dùng | Hệ thống |
| --- | --- | --- |
| 1 | Nhập và gửi câu hỏi | Kiểm tra câu hỏi và quyền tài khoản |
| 2 | Chờ câu trả lời | Tìm nội dung khuyến mãi liên quan, được phép sử dụng |
| 3 | Đọc câu trả lời | Trình bày ưu đãi, điều kiện và thời hạn nếu tài liệu có, kèm trích dẫn |
| 4 | Chọn nguồn để tìm hiểu thêm | Hiển thị nguồn khuyến mãi theo UC03 |

- Không xác nhận một khách hàng cụ thể được hưởng ưu đãi khi không có dữ liệu để kết luận.
- Tài liệu được lưu trong kho không có nghĩa chương trình vẫn còn thời hạn áp dụng.

### 7.5. UC03 — Xem và kiểm chứng nguồn

| Nội dung | Mô tả |
| --- | --- |
| Mục tiêu | Cho người dùng kiểm tra nội dung làm căn cứ cho kết quả tìm kiếm hoặc câu trả lời |
| Người sử dụng | Nhân viên, khách hàng, quản trị trong phạm vi được đọc |
| Điều kiện thực hiện | Đã đăng nhập; có nguồn từ kết quả tìm kiếm hoặc câu trả lời |
| Đầu vào | Nguồn người dùng lựa chọn |
| Thao tác bắt đầu | Chọn trích dẫn hoặc liên kết xem nguồn |
| Kết quả | Tiêu đề, đoạn tài liệu, vị trí nếu có, phiên bản và thời điểm thu thập được hiển thị |

| Bước | Người dùng | Hệ thống |
| --- | --- | --- |
| 1 | Chọn nguồn muốn xem | Kiểm tra lại quyền đọc và tài liệu tương ứng |
| 2 | Đọc nội dung nguồn | Hiển thị đoạn tài liệu đúng nguồn/phiên bản còn được phép sử dụng |
| 3 | Chọn liên kết Confluence nếu được cung cấp | Mở liên kết khi phù hợp quyền truy cập nguồn |

- Khách hàng xem được đoạn khuyến mãi trong ứng dụng mà không cần tài khoản Confluence.
- Nếu tài liệu đã thay đổi hoặc không còn được phép đọc, hệ thống thông báo nguồn chưa thể xem; không hiển thị nguồn sai hoặc ngoài quyền.
- Liên kết Confluence có thể mở nội dung mới hơn; giao diện phải phân biệt với phiên bản đã dùng cho câu trả lời.

### 7.6. UC04 — Cấu hình nguồn và phạm vi

| Nội dung | Mô tả |
| --- | --- |
| Mục tiêu | Xác định nguồn tài liệu và người được phép đọc từng Space |
| Người sử dụng | Quản trị |
| Điều kiện thực hiện | Đã đăng nhập bằng tài khoản quản trị; có thông tin kết nối nguồn |
| Đầu vào | Địa chỉ Confluence, thông tin kết nối, hai Space và quyền đọc tương ứng |
| Thao tác bắt đầu | Mở chức năng cấu hình và chọn lưu |
| Kết quả | Cấu hình hợp lệ được lưu; quyền đọc được áp dụng cho tài liệu liên quan |

| Bước | Người dùng | Hệ thống |
| --- | --- | --- |
| 1 | Nhập hoặc cập nhật nguồn Confluence và hai Space | Kiểm tra thông tin và khả năng đọc nguồn |
| 2 | Xác định quyền đọc từng Space | Kiểm tra đúng hai Space, không trùng nhau và đúng nhóm người dùng |
| 3 | Chọn Lưu | Lưu cấu hình hợp lệ và cập nhật quyền tài liệu bị ảnh hưởng |
| 4 | Xem kết quả | Hiển thị kết quả lưu và áp dụng quyền; chỉ báo hoàn tất khi đã áp dụng xong |

- Không hiển thị lại thông tin bí mật khi xem cấu hình.
- Chu kỳ đồng bộ của đồ án là 60 phút.

### 7.7. UC05 — Yêu cầu đồng bộ và cập nhật kho tri thức

| Nội dung | Mô tả |
| --- | --- |
| Mục tiêu | Cập nhật kho tri thức theo nội dung hiện có trên Confluence |
| Người sử dụng | Quản trị khi chạy thủ công |
| Điều kiện thực hiện | Đã đăng nhập bằng tài khoản quản trị; nguồn hợp lệ; các dịch vụ cần thiết sẵn sàng; không có lượt cùng nguồn đang chạy |
| Đầu vào | Phạm vi nguồn đã cấu hình |
| Thao tác bắt đầu | Chọn Đồng bộ |
| Kết quả | Có lượt xử lý được ghi nhận; quản trị theo dõi được kết quả và nhận thông báo khi hoàn tất |

| Bước | Người dùng | Hệ thống |
| --- | --- | --- |
| 1 | Chọn Đồng bộ | Kiểm tra điều kiện và tiếp nhận yêu cầu |
| 2 | Xem lượt xử lý được tạo | Đọc nguồn, so sánh với dữ liệu đã lưu và xác định thay đổi |
| 3 | Theo dõi tiến độ nếu cần | Cập nhật tài liệu theo luồng tại mục 8.2 |
| 4 | Xem kết quả | Tổng hợp kết quả của lượt và thông báo sau khi các bước cần thiết hoàn tất |

- Hệ thống tự thực hiện cùng luồng cập nhật mỗi 60 phút, không cần người dùng thao tác.
- Thu thập lần đầu phải được thực hiện trước khi cập nhật định kỳ.
- Việc tiếp nhận yêu cầu chưa có nghĩa tài liệu đã sẵn sàng để hỏi đáp.

### 7.8. UC08 — Theo dõi trạng thái và nhận thông báo

| Nội dung | Mô tả |
| --- | --- |
| Mục tiêu | Giúp quản trị biết tài liệu đang được xử lý đến đâu và kết quả ra sao |
| Người sử dụng | Quản trị |
| Điều kiện thực hiện | Đã đăng nhập bằng tài khoản quản trị; hệ thống đọc được trạng thái; chức năng thông báo hoạt động để nhận kết quả |
| Đầu vào | Lượt cập nhật hoặc tài liệu cần theo dõi |
| Thao tác bắt đầu | Mở màn hình trạng thái hoặc xem thông báo kết quả |
| Kết quả | Hiển thị tài liệu/lượt, bước xử lý, thời gian, số lượng và lỗi được ghi nhận nếu có |

| Bước | Người dùng | Hệ thống |
| --- | --- | --- |
| 1 | Mở màn hình trạng thái | Kiểm tra quyền quản trị và hiển thị các lượt xử lý |
| 2 | Chọn lượt hoặc tài liệu | Hiển thị tiến độ và kết quả tương ứng |
| 3 | Xem thông báo khi có kết quả | Cập nhật kết quả đã xác nhận trên giao diện quản trị |

- Phân biệt một tài liệu hoàn tất với toàn bộ lượt hoàn tất.
- Nhân viên và khách hàng không được xem thông báo vận hành.

### 7.9. UC09 — Yêu cầu xử lý lại thủ công

| Nội dung | Mô tả |
| --- | --- |
| Mục tiêu | Cho quản trị chủ động xử lý lại công việc chưa thành công, khi đủ điều kiện |
| Người sử dụng | Quản trị |
| Điều kiện thực hiện | Đã đăng nhập bằng tài khoản quản trị; công việc tồn tại; đầu vào và quyền hợp lệ; không có công việc trùng đang chạy |
| Đầu vào | Công việc hoặc tài liệu cần xử lý lại |
| Thao tác bắt đầu | Chọn Xử lý lại |
| Kết quả | Yêu cầu được tiếp nhận và có kết quả theo dõi, hoặc được từ chối kèm lý do |

| Bước | Người dùng | Hệ thống |
| --- | --- | --- |
| 1 | Chọn công việc hoặc tài liệu cần xử lý lại | Hiển thị kết quả hiện tại |
| 2 | Chọn Xử lý lại | Kiểm tra quyền và điều kiện xử lý |
| 3 | Theo dõi công việc | Tiếp nhận yêu cầu hợp lệ và thực hiện các bước cần thiết |
| 4 | Xem kết quả | Ghi nhận kết quả và thông báo khi hoàn tất |

- Nếu nội dung chưa được chuẩn bị xong, hệ thống phải chuẩn bị nội dung trước khi đưa vào kho hỏi đáp.
- Nếu chỉ việc gửi thông báo gặp lỗi, không xử lý lại nội dung tài liệu chỉ để gửi thông báo.

## 8. Yêu cầu xử lý tự động

### 8.1. Theo dõi thay đổi tài liệu

| Trường hợp | Yêu cầu |
| --- | --- |
| Trang mới | Thu thập nội dung, ghi nhận nguồn/phiên bản và chuẩn bị để sử dụng |
| Nội dung được sửa | So sánh với nội dung đã lưu và cập nhật phần phục vụ tìm kiếm/hỏi đáp |
| Chỉ thông tin hoặc quyền thay đổi | Cập nhật thông tin/quyền; không xử lý lại nội dung không đổi khi không cần thiết |
| Trang đã bị xóa | Xác minh việc xóa và ngừng sử dụng trang trong kho hỏi đáp |
| Không thay đổi | Ghi nhận đã kiểm tra; không tạo việc xử lý nội dung không cần thiết |

- Mỗi trang giữ nguyên định danh trong kho khi cập nhật, để liên hệ được nguồn và kết quả xử lý.
- Chỉ giữ các phiên bản thực tế đã thu thập; không coi kho lưu trữ là toàn bộ lịch sử chỉnh sửa trên Confluence.

### 8.2. Luồng cập nhật tổng thể

```mermaid
flowchart TD
    A["1. Đến kỳ 60 phút hoặc quản trị chọn Đồng bộ"] --> B["2. Đọc nguồn và so sánh với tài liệu đã lưu"]
    B --> C{"3. Xác định thay đổi"}
    C -->|"Trang mới hoặc sửa nội dung"| D["4. Lưu bản gốc và chuẩn bị nội dung"]
    D --> E["5. Xử lý nội dung để tìm kiếm và hỏi đáp"]
    E --> F["6. Xác nhận tài liệu đã xử lý thành công"]
    F --> K["Thông báo kết quả cho quản trị"]
    C -->|"Trang xóa đã xác minh"| G["Ngừng sử dụng và cập nhật kho"]
    C -->|"Không thay đổi"| H["Ghi nhận đã kiểm tra"]
    F --> I["7. Tổng hợp kết quả mọi công việc trong lượt"]
    G --> I
    H --> I
    I --> J["8. Xác nhận toàn lượt hoàn tất"]
    J --> K
```

- Sơ đồ thể hiện các nhánh cập nhật chính. Quyền đọc được áp dụng xuyên suốt theo mục 4.
- Cách kết nối các thành phần và lưu dữ liệu được mô tả trong tài liệu thiết kế.

### 8.3. Chuẩn bị tài liệu để hỏi đáp

| Nội dung | Yêu cầu |
| --- | --- |
| Đầu vào | Bản gốc hợp lệ, nguồn, phiên bản và quyền đọc của trang |
| Chuyển đổi | Chuyển HTML đơn giản thành Markdown, giữ nội dung và tham chiếu ảnh |
| Chia nội dung | Tách thành các đoạn có thứ tự, vẫn xác định được đoạn thuộc tài liệu nào |
| Đưa vào kho hỏi đáp | Xử lý và lưu nội dung cần thiết để tìm các đoạn liên quan đến câu hỏi |
| Kết quả | Tài liệu chỉ được sử dụng khi các bước xử lý và lưu dữ liệu cần thiết đã thành công |

- Nếu không đọc được nội dung hoặc xử lý thất bại, phải ghi nhận lỗi thay vì báo hoàn tất.
- Nội dung đang xử lý dở không được dùng để trả lời.

### 8.4. Trạng thái và mốc hoàn thành

| Mốc | Ý nghĩa đối với người sử dụng |
| --- | --- |
| Đã tiếp nhận | Hệ thống nhận yêu cầu; chưa có nghĩa xử lý xong |
| Đã thu thập và so sánh | Đã xác định được thay đổi nguồn; chưa có nghĩa nội dung mới đã dùng được |
| Đã chuẩn bị nội dung | Nội dung đã chuyển đổi và chia đoạn, sẵn sàng cho bước xử lý tiếp theo |
| Đang xử lý để hỏi đáp | Hệ thống đang đưa nội dung vào kho phục vụ tìm kiếm và câu trả lời |
| Tài liệu hoàn tất | Nội dung phục vụ tra cứu đã được xử lý và lưu thành công; chỉ được đọc nếu còn đúng quyền |
| Toàn lượt hoàn tất | Mọi công việc cập nhật, thay đổi quyền và xóa cần thiết của lượt đã xong |
| Đã thông báo | Kết quả được chuyển tới giao diện quản trị |
| Không thay đổi | Đã kiểm tra nguồn và không cần xử lý lại nội dung |
| Có lỗi | Bước xử lý chưa thành công, có thông tin để quản trị kiểm tra |

- Một tài liệu hoàn tất không có nghĩa toàn bộ lượt hoàn tất.
- Chỉ thông báo xử lý thành công sau khi kết quả đã được xác nhận.
- Việc hiển thị thông báo là bước riêng với việc xử lý xong tài liệu.

### 8.5. Xóa và thay đổi phạm vi đọc

- Trang đã xác minh bị xóa hoặc không còn thuộc phạm vi nguồn phải ngừng tham gia tìm kiếm, hỏi đáp và xem nguồn.
- Lỗi kết nối hoặc chưa đọc hết danh sách trang không được coi là tài liệu đã bị xóa.
- Trang chuyển Space hoặc đổi quyền phải áp dụng quyền đọc hiện hành, dù nội dung không đổi.
- Bản gốc đã lưu vẫn phải được bảo vệ theo quyền đọc; việc lưu bản gốc không tự cho phép mọi người xem.

### 8.6. Thông báo kết quả

| Nội dung | Yêu cầu |
| --- | --- |
| Người nhận | Quản trị đã đăng nhập và có quyền |
| Khi thông báo hoàn tất | Sau khi tài liệu hoặc toàn lượt đã xử lý thành công theo mục 8.4 |
| Thông tin hiển thị | Tài liệu/lượt cập nhật, kết quả, thời điểm và số lượng liên quan |
| Bảo mật | Không kèm toàn văn tài liệu hoặc thông tin đăng nhập nguồn |
| Không cần xử lý nội dung | Hiển thị kết quả kiểm tra tương ứng, không báo đã xử lý nội dung khi thực tế không chạy |

### 8.7. Luồng hỏi đáp từ tài liệu

1. Kiểm tra tài khoản và xác định những tài liệu người dùng được phép đọc.
2. Tìm các đoạn liên quan đến câu hỏi, thuộc tài liệu đã xử lý xong.
3. Chỉ dùng các đoạn đúng quyền để tạo câu trả lời.
4. Kiểm tra trích dẫn và trả câu trả lời kèm nguồn để người dùng đối chiếu.

- Không đủ thông tin từ tài liệu: nói rõ chưa có đủ căn cứ để trả lời.
- Dịch vụ hỏi đáp gặp lỗi: thông báo chưa thể xử lý; không kết luận là tài liệu không tồn tại.
- Các yêu cầu trong câu hỏi không được dùng để vượt quyền đọc hoặc thay đổi tài liệu.

<!--
## 9. Quy tắc nghiệp vụ

| Mã | Quy tắc |
| --- | --- |
| BR01 | Một bot, hai Space hợp lệ; thiếu ánh xạ quyền thì không phục vụ |
| BR02 | INTERNAL đọc cả hai Space; CUSTOMER chỉ khuyến mãi; quyền vận hành tách riêng |
| BR03 | Tài khoản nguồn tách danh tính người dùng; không tiết lộ secret |
| BR04 | Phiên bản gắn đúng nội dung thực tế thu thập |
| BR05 | Chỉ dữ liệu hoàn chỉnh và được phép đọc mới tham gia khai thác |
| BR06 | API trực tiếp kích hoạt train sau chunk; Kafka thông báo kết quả |
| BR07 | Xóa/thu hồi đã xác minh phải chặn retrieval và nguồn |
| BR08 | Lỗi đọc nguồn không tự biến thành xóa tài liệu hoặc thành công đồng bộ |
| BR09 | Thiếu bằng chứng không được bịa đáp án; lỗi dịch vụ khác thiếu dữ liệu |
| BR10 | Trích dẫn phải thực sự hỗ trợ câu trả lời và đúng phạm vi/phiên bản |
| BR11 | Prompt injection không thay đổi quyền, secret hoặc quy tắc hệ thống |
| BR12 | Tài liệu khuyến mãi có trong index không chứng minh ưu đãi còn hiệu lực |
| BR13 | ACL kế thừa Space áp dụng xuyên suốt API, context, nguồn và cache |
| BR14 | Không tự nâng gói hoặc chuyển dịch vụ trả phí khi hết quota |
| BR15 | Tiếp nhận HTTP, kết thúc ingestion, hoàn tất train và thông báo là các mốc riêng |
| BR16 | Chỉ phát thành công sau embedding và ghi dữ liệu bắt buộc thành công |
| BR17 | Dữ liệu đối soát/lượt ingestion dùng PostgreSQL; tách metadata Airflow |
| BR18 | Chỉ metadata/quyền đổi không bắt buộc embedding lại nội dung |
| BR19 | Kết quả một tài liệu không thay thế kết quả toàn lượt |

## 10. Yêu cầu phi chức năng

| Mã | Nhóm | Yêu cầu | Cách kiểm chứng |
| --- | --- | --- | --- |
| NFR01 | Nhất quán phục vụ | Không dùng nội dung đang xử lý dở hoặc ngoài quyền | Kiểm tra truy xuất trong chuỗi cập nhật tuần tự |
| NFR02 | Kiểm soát chạy chồng | Không có hai lượt cùng nguồn chạy đồng thời | Gửi yêu cầu khi một lượt đang chạy |
| NFR03 | Chẩn đoán | Lỗi có thông tin phù hợp; hỗ trợ thao tác thủ công UC09 | Kiểm tra lỗi và yêu cầu xử lý lại hợp lệ |
| NFR04 | Lưu bền vững | Dữ liệu đã ghi xác nhận còn sau restart có volume | Đối chiếu dữ liệu trước/sau restart |
| NFR05 | Minh bạch độ mới | Có phiên bản, thời điểm thu thập và trạng thái xử lý | Đối chiếu nguồn, dữ liệu và UI |
| NFR06 | Tài nguyên | Hoạt động trong môi trường 32 GB RAM, không GPU | Đo RAM/CPU toàn stack dưới tải thử |
| NFR07 | Quota | Giới hạn tải phù hợp gói miễn phí, không thành công giả hoặc tăng phí | Kiểm tra cấu hình và phản hồi quota |
| NFR08 | Bảo mật | Authorization phía server; không lộ secret; chỉ context hợp lệ gửi AI | Kiểm thử quyền và kiểm tra log/response |
| NFR09 | Quan sát | Truy vết ingestion, tài liệu, train và thông báo | Theo định danh qua các giai đoạn |
| NFR10 | Tái lập | Ghi phần mềm/model/cấu hình, snapshot và điều kiện thử | Thực hiện lại trên cấu hình đã ghi nhận |
| NFR11 | Dễ sử dụng | UI tiếng Việt; trạng thái rõ; không yêu cầu hiểu hạ tầng | Review chức năng và thử tác vụ người dùng |
| NFR12 | Hiệu năng | Đo độ trễ RAG, xử lý và thông báo; công bố tải/mạng/quota | Bộ đo theo mục 11.3 |
| NFR13 | Chất lượng AI | Đánh giá đúng/đủ, grounding, citation và thiếu dữ liệu | Bộ chuẩn và chấm thủ công |

- NFR04 không cam kết chống hỏng ổ đĩa hoặc tự tiếp tục công việc đang chạy.
- Ngưỡng hiệu năng và chất lượng cần chốt tại Q04 trước nghiệm thu định lượng.

## 11. Tiêu chí và kịch bản nghiệm thu

### 11.1. Nguyên tắc

- Dùng dữ liệu được phép sử dụng, đủ hai Space và tài khoản đại diện ba vai trò.
- Mỗi ca có đầu vào, điều kiện, kết quả mong đợi/thực tế, định danh và minh chứng.
- Phân biệt kiểm thử giả lập với kiểm thử Confluence/AI/Kafka thực.
- Hoàn thành setup hạ tầng không thay bằng chứng chạy chức năng.
- Phản hồi input sai/lỗi dịch vụ vẫn phải được kiểm tra.

### 11.2. Ma trận nghiệm thu

| Mã | Tình huống | Điều kiện đạt |
| --- | --- | --- |
| AC01 | Đăng nhập hợp lệ, sai và lỗi xác thực | Tài khoản hợp lệ có đúng quyền; sai/lỗi không được cấp quyền mặc định |
| AC02 | Chưa đăng nhập, hết hạn, đăng xuất, gọi API/nguồn trực tiếp | Không truy cập được chức năng/dữ liệu cần xác thực |
| AC03 | Nhân viên/khách hàng gọi vận hành hoặc đăng ký thông báo quản trị | Bị từ chối; quản trị được phép đúng điều kiện |
| AC04 | Nhân viên/quản trị tìm kiếm cả hai Space | Kết quả đúng quyền và có nguồn hợp lệ |
| AC05 | Hỏi chính sách có bằng chứng | Đáp án bám nguồn; không bắt buộc tìm kiếm trước |
| AC06 | Ba vai trò hỏi khuyến mãi | Đúng phạm vi; nêu điều kiện/thời hạn; không suy diễn ưu đãi cá nhân |
| AC07 | Xem nguồn; sửa ID sang nguồn ngoài quyền | Chỉ nguồn được phép được hiển thị; khách hàng không cần tài khoản Confluence |
| AC08 | Câu ngoài dữ liệu, mơ hồ hoặc prompt injection | Phản hồi giới hạn phù hợp; không bịa nguồn/vượt quyền |
| AC09 | Cấu hình bot/Space/quyền hợp lệ và không hợp lệ | Ánh xạ đúng; secret không lộ; quyền thiếu/rỗng/khác bot không cấp quyền |
| AC10 | Thu thập đầu, AUTO 60 phút, chạy thủ công khi đang xử lý | Đủ phạm vi; lịch đúng điều kiện; không chạy chồng |
| AC11 | Trang mới, body đổi, chỉ metadata/parent đổi, không đổi | Đối soát đúng; chỉ nội dung cần thiết được train |
| AC12 | Train trước chunk, input sai hoặc đang chạy | Phản hồi/từ chối đúng; không tạo xử lý chồng hoặc thành công giả |
| AC13 | Dịch vụ trả lỗi hoặc thiếu quota | Không công bố thành công; lỗi rõ; không tự chuyển trả phí |
| AC14 | API tiếp nhận, job còn chạy, sau đó train thành công | Không thông báo thành công sớm; chỉ hoàn tất sau các bước ghi bắt buộc |
| AC15 | Train thành công khi broker/backend hoạt động | Kafka có kết quả; backend/FE quản trị hiển thị đúng định danh và kết quả |
| AC16 | Xóa, chuyển Space, đổi quyền khi body không đổi | Tài liệu xóa bị chặn; quyền hiện hành có hiệu lực ở mọi đường đọc |
| AC17 | Khách hàng tự gửi role/Space hoặc đoán ID | Không có nội bộ trong context/đáp án/metadata/nguồn; nhân viên đọc được hai Space |
| AC18 | Xem trạng thái và xử lý lại thủ công | Đúng quyền; thấy kết quả/giai đoạn; yêu cầu đủ điều kiện được xử lý |
| AC19 | Restart kho sau công việc hoàn tất | Snapshot, nội dung, raw và vector đã xác nhận vẫn tồn tại |
| AC20 | Thu thập thiếu do lỗi phân trang/kết nối | Không xóa hàng loạt hoặc báo hoàn tất sai; có lỗi phù hợp |
| AC21 | Lượt nhiều tài liệu hoặc chỉ metadata/quyền/xóa/không đổi | Tổng hợp đúng mọi tác vụ; không nhầm một tài liệu xong với toàn lượt hoặc giả lập embedding |

### 11.3. Đánh giá chất lượng và hiệu quả — đề xuất

| Hạng mục | Kế hoạch đề xuất |
| --- | --- |
| Kho dữ liệu | 100–300 trang thuộc hai Space |
| Bộ câu hỏi | 80 câu: 40 trực tiếp, 15 tổng hợp nhiều đoạn/trang, 15 thiếu dữ liệu, 10 đổi đáp án theo phiên bản |
| Chia tập | 20 câu phát triển/pilot, 60 câu đánh giá độc lập; phân bổ đại diện các nhóm và vai trò |
| Dữ liệu chuẩn | Câu hỏi, quyền, phạm vi, đáp án/khả năng trả lời, tài liệu/phiên bản và đoạn bằng chứng |
| Thay đổi kiểm soát | 20 trang có lịch sửa tuần tự, xóa, khôi phục hợp lệ và chuyển phạm vi |
| Chấm thủ công | Đúng nội dung, đủ điều kiện, grounding và trích dẫn hỗ trợ khẳng định |
| Hiệu quả tác vụ | So thời gian/tỷ lệ hoàn thành với tra cứu thủ công; ghi người tham gia và kinh nghiệm |
| Tải pilot | 1–3 người truy vấn đồng thời; concurrency lập chỉ mục phù hợp quota/RAM |
| Ngân sách RAM container | Đề xuất 20 GiB; xác nhận bằng đo thực tế trên máy 32 GB RAM |
| Hiệu năng | Độ trễ truy xuất/đáp án, thời gian đồng bộ/lập chỉ mục/thông báo, RAM/CPU và điều kiện mạng/quota |

- Chỉ số báo cáo: truy xuất bằng chứng top-k, tỷ lệ trả lời đúng/đủ, độ chính xác trích dẫn, xử lý thiếu dữ liệu và độ trễ.
- Cố định snapshot, công thức, thang chấm và ngưỡng sau pilot, trước khi chạy tập đánh giá độc lập.
- Không điều chỉnh tham số dựa vào tập đánh giá độc lập.
- Không dùng điểm LLM tự chấm làm bằng chứng duy nhất.
- Hạn chế hiệu ứng người tham gia đã biết đáp án khi so sánh hai cách tra cứu.

### 11.4. Điều kiện bàn giao

- Các ca AC01–AC21 đạt trên bộ kiểm thử được thẩm định.
- Ngưỡng chất lượng/hiệu năng được duyệt trước đánh giá và có kết quả thực tế.
- Mã nguồn, cấu hình mẫu, hướng dẫn và bộ minh chứng đầy đủ.
- Giới hạn chưa được kiểm chứng được nêu trong báo cáo thực nghiệm.

## 12. Ma trận truy vết

| Yêu cầu | Chức năng/xử lý | Nghiệm thu |
| --- | --- | --- |
| FR01 | UC04 | AC09, AC16 |
| FR02 | UC05, thu thập ban đầu | AC10 |
| FR03 | UC05, lịch AUTO | AC03, AC10 |
| FR04 | Đối soát, mục 8.1 | AC11, AC20 |
| FR05 | UC03, UC05, UC08 | AC07, AC11, AC19 |
| FR06 | UC05, UC09 | AC12, AC14, AC18 |
| FR07 | Chuẩn hóa/lập chỉ mục, mục 8.3 | AC11, AC13, AC14 |
| FR09 | UC01, UC02, UC03, UC11 | AC04–AC08 |
| FR12 | Định danh và đo lường | AC14, AC15, AC18, AC21; mục 11.3 |
| FR14 | Ma trận quyền và RAG | AC03, AC07, AC09, AC16, AC17 |
| FR15 | UC08, thông báo mục 8.6 | AC03, AC14, AC15, AC21 |
| NFR01–NFR05 | Nhất quán/trạng thái/lưu bền vững | AC10–AC14, AC18–AC21 |
| NFR06, NFR12 | Tài nguyên/hiệu năng | Mục 11.3 |
| NFR07–NFR09 | Quota/bảo mật/quan sát | AC02, AC03, AC09, AC13–AC18 |
| NFR10, NFR13 | Tái lập/chất lượng | Mục 11.1, 11.3 |
| NFR11 | UI và thông báo | Review Use Case; AC14, AC15, AC21 |

## 13. Quyết định còn mở

| Mã | Nội dung cần quyết định | Phương án đề xuất | Tiêu chí lựa chọn |
| --- | --- | --- | --- |
| Q01 | Cơ chế xác thực/phiên | Cấp sẵn tài khoản demo; chọn auth local hoặc IdP | Đáp ứng UC10 và ba vai trò; không thêm tự đăng ký |
| Q02 | ID hai Space và dữ liệu cloud | Dùng dữ liệu giả lập được phép | Kiểm soát quyền nguồn và phạm vi dữ liệu gửi cloud |
| Q03 | Hình thức UI quản trị | Streamlit gọi API cấu hình/sync/status/retry | Đủ chức năng, kiểm tra quyền phía backend |
| Q04 | Ngưỡng chất lượng/hiệu năng | Chốt sau pilot, trước đánh giá độc lập | Có thang chấm, workload và ngưỡng nghiệm thu xác định |
| Q05 | Giới hạn query/đáp án/số nguồn | Chọn theo model, context và quota | Kiểm tra input, độ trễ và chi phí |
| Q06 | Thời hạn lưu raw/log/trace | Giữ raw thu thập trong kỳ đánh giá; chọn retention log/trace riêng | Dung lượng, truy vết và bảo mật |
| Q07 | Phạm vi trace Langfuse | Ưu tiên ID, thời gian, trạng thái và số đo | Chỉ gửi nội dung khi đã được cho phép |

- Các mục Q là đề xuất/chưa xác định, không tự thành cam kết nghiệm thu định lượng.
- Quyết định về schema, API, profile AI và kênh thông báo cụ thể được trình bày tại tài liệu thiết kế.
- Mọi lựa chọn phải tuân phạm vi, quyền và luồng tại mục 3–8.

-->

## 14. Thuật ngữ và tài liệu liên quan

### 14.1. Thuật ngữ

| Thuật ngữ | Giải thích |
| --- | --- |
| Kho tri thức | Tập tài liệu được thu thập, tổ chức và chuẩn bị để tra cứu, hỏi đáp |
| Chatbot | Ứng dụng nhận câu hỏi và trả lời người dùng qua giao diện trò chuyện |
| Confluence | Nền tảng lưu trữ và quản lý tài liệu được chọn làm nguồn cho đồ án |
| Space | Không gian nhóm các trang tài liệu trên Confluence |
| Use Case | Chức năng được mô tả theo mục tiêu của người sử dụng |
| Quyền truy cập tài liệu | Quy định nhóm người dùng nào được phép đọc và hỏi đáp từ tài liệu |
| Đồng bộ | Kiểm tra nguồn và cập nhật kho theo các thay đổi được phát hiện |
| Phiên bản thu thập | Phiên bản của trang tại thời điểm hệ thống lấy nội dung về |
| Trích dẫn nguồn | Tham chiếu đến tài liệu hoặc đoạn nội dung làm căn cứ cho câu trả lời |
| HTML / Markdown | Định dạng trang nguồn và định dạng văn bản dùng sau chuyển đổi |
| RAG | Cách tạo câu trả lời bằng việc tìm nội dung liên quan trong tài liệu rồi dùng nội dung đó làm căn cứ |

### 14.2. Tài liệu liên quan

- [Thiết kế chung](architecture.md): tổ chức hệ thống, thành phần và các luồng kết nối.
- [Thiết kế chi tiết](detailed-design.md): dữ liệu, API, xử lý nội dung và trạng thái triển khai.
- [Tài nguyên Use Case](use-cases/README.md): sơ đồ và mã chỉnh sửa.
- [Báo cáo tiến độ](progress/README.md): kết quả thực hiện và kiểm chứng.
