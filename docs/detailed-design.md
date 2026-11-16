# Tài liệu thiết kế chi tiết

| Thông tin | Nội dung |
| --- | --- |
| Đề tài | Nghiên cứu và xây dựng hệ thống kho tri thức doanh nghiệp thông minh từ Confluence |
| Học viên | Đặng Nam Cường |
| Loại tài liệu | Thiết kế chi tiết — Low-Level Design (LLD) |
| Phiên bản | 2.0 |
| Ngày cập nhật | 10/11/2026 |
| Trạng thái | Dự thảo để thẩm định |
| Căn cứ yêu cầu | [Đặc tả yêu cầu](requirements.md) |
| Căn cứ kiến trúc | [Thiết kế chung](architecture.md) |

- **Mục đích:** xác định schema, contract, interface, thuật toán, trạng thái và cách kiểm chứng để triển khai.
- **Nguồn kỹ thuật:** code ingestion/Portal/Chat/Beeflow và DDL PostgreSQL local.
- **Trạng thái thực hiện:** theo [báo cáo tiến độ](progress/README.md).

## 1. Phạm vi triển khai

- Một bot chung cho hai Space.
- Hai quyền đọc INTERNAL/CUSTOMER; tài liệu kế thừa quyền Space.
- PostgreSQL nghiệp vụ lưu snapshot đối soát và lượt ingestion, tách metadata Airflow.
- Chuẩn bị/chunk hoàn tất trước yêu cầu train.
- API trực tiếp kích hoạt train; Kafka thông báo kết quả qua backend tới FE quản trị.
- Hoàn tất tài liệu và hoàn tất toàn lượt được xác nhận riêng.
- Áp dụng AS01–AS03 của SRS; không thêm bảng theo dõi hoặc phục hồi phân tán nâng cao.

## 2. Phân loại nội dung

| Nhãn | Ý nghĩa |
| --- | --- |
| Có căn cứ mã nguồn | Quan sát từ writer, reader, model, router hoặc DDL local |
| Quyết định xác định | Yêu cầu/phương án thuộc phạm vi SRS và HLD |
| Đề xuất triển khai | Field, interface, route hoặc event chưa được xác nhận là đã triển khai |
| Còn mở | Tham số hoặc lựa chọn cần thẩm định/kiểm chứng |
| Ngoài phạm vi | Nhánh/thành phần không yêu cầu trong sản phẩm cốt lõi |

- Kiểu Mongo quan sát từ code không tự chứng minh validator/index trên database.

## 3. Cấu trúc tài liệu

| Tài liệu | Nội dung chính |
| --- | --- |
| [01 — Database và lưu trữ](detailed-design/01-data-storage.md) | Schema SQL/Mongo, key/index, raw/version và Milvus |
| [02 — API và Kafka](detailed-design/02-api-events.md) | Request/response, validation, status API và notification contract |
| [03 — Module và thuật toán](detailed-design/03-modules-code-mapping.md) | Interface, task graph, thứ tự I/O và điểm tích hợp |
| [04 — Trạng thái và completion](detailed-design/04-state-transitions.md) | Transition, predicate hoàn tất, lỗi và xử lý lại |
| [05 — Runtime và kiểm chứng](detailed-design/05-runtime-validation.md) | Profile, rollout, contract/integration/AI tests và nghiệm thu |
| [06 — ACL và RAG](detailed-design/06-space-access-control.md) | Quyền Space, policy, retrieval, evidence và trích dẫn |

## 4. Luồng xử lý

| Bước | Hoạt động | Nơi đặc tả chính |
| --- | --- | --- |
| 1 | Đọc Confluence, đối soát PostgreSQL, ghi nguồn/metadata/quyền | 01, 03 |
| 2 | HTML → Markdown → chunk | 03 |
| 3 | Gọi API train và theo dõi job | 02, 03 |
| 4 | Tạo embedding, ghi MongoDB/Milvus và xác nhận kết quả | 03, 04 |
| 5 | Kafka → notification backend → FE quản trị | 02, 04 |
| 6 | Truy xuất bằng chứng đúng quyền, sinh đáp án và nguồn | 06 |

## 5. Điểm còn mở

| Nội dung | Điều kiện xác định |
| --- | --- |
| Identity provider/session | Đáp ứng vai trò, service scope và yêu cầu xác thực SRS |
| Embedding/LLM profile | Model, dimension, context và quota được kiểm chứng |
| Giới hạn chunk/batch/timeout | Có số đo pilot và phù hợp tài nguyên |
