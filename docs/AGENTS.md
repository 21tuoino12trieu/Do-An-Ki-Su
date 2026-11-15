# Quy tắc biên tập tài liệu đồ án

Áp dụng cho tài liệu đặc tả và thiết kế trong thư mục `docs/`.

1. Viết như tài liệu hiện hành độc lập. Không nhắc bản cũ, lịch sử trao đổi hoặc giải thích việc thay thế tài liệu.
2. Trình bày ngắn gọn, rõ ý. Ưu tiên gạch đầu dòng, mỗi ý diễn đạt một nội dung.
3. Dùng bảng cho phân quyền, yêu cầu, trách nhiệm module, schema, API, trạng thái và nghiệm thu.
4. Đánh số bước cho luồng xử lý; dùng Mermaid cho kiến trúc và tương tác. Giữ tác nhân hình người trong sơ đồ Use Case.
5. Dùng thuật ngữ SE, AI và DE chính xác, thống nhất tên gọi.
6. Không rút gọn mất đầu vào, đầu ra, điều kiện, ràng buộc, ngoại lệ hoặc tiêu chí kiểm chứng.
7. Bám code tham khảo khi ghi tên trường, collection, API và contract. Không mô tả đề xuất như chức năng đã triển khai.
8. Phân biệt quyết định đã xác định, hợp đồng triển khai đề xuất và điểm còn mở. Trạng thái triển khai phải có bằng chứng.
9. Tránh trùng lặp: mỗi nội dung có nơi mô tả chính; tài liệu khác liên kết tới khi cần.
10. Giữ đúng mức: SRS mô tả hệ thống phải làm gì; HLD mô tả tổ chức hệ thống; LLD mô tả cách triển khai.
11. Giữ luồng nghiệp vụ: một bot, hai Space, quyền kế thừa xuống tài liệu; PostgreSQL đối soát → chuẩn bị/chunk → API train trực tiếp → embedding và ghi MongoDB/Milvus hoàn tất → Kafka thông báo qua backend tới FE quản trị. Phân biệt tiếp nhận API, hoàn tất tài liệu và hoàn tất toàn lượt.
12. Không tự mở rộng phạm vi: không thêm bảng, chức năng hoặc cơ chế phục hồi nâng cao khi chưa thống nhất.

Giữ mã định danh FR/NFR/UC/BR/AC khi nội dung tương ứng không đổi. Kiểm tra liên kết, cấu trúc bảng, sơ đồ và truy vết sau khi biên tập. Không sửa code ứng dụng hoặc dữ liệu khi nhiệm vụ chỉ yêu cầu tài liệu.
