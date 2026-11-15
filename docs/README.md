# Tài liệu đồ án

## Bộ ba tài liệu chính

| Thứ tự | Tài liệu | Nội dung |
| --- | --- | --- |
| 1 | [Đặc tả yêu cầu](requirements/README.md) | Bài toán, phạm vi, quyền, Use Case, chức năng và nghiệm thu. |
| 2 | [Thiết kế chung](architecture/README.md) | Kiến trúc, trách nhiệm module, luồng tổng quan và triển khai. |
| 3 | [Thiết kế chi tiết](detailed-design/README.md) | Schema, API/Kafka, module/code, trạng thái, lỗi và kiểm thử. |

Các tài liệu đang ở trạng thái dự thảo để review; thiết kế không thay kết quả chạy thực tế.

**Cập nhật 10/11/2026:** cả ba tài liệu đã hiệu chỉnh lên v2.0 theo luồng PostgreSQL đối soát → chunk → API train trực tiếp → Kafka thông báo kết quả. Thiết kế chi tiết phân biệt schema/API đã có trong code với field/route/event mới đề xuất; cả bộ vẫn là thiết kế chờ review, không phải chứng nhận đã triển khai.

## Tài nguyên còn sử dụng

- [Sơ đồ Use Case và mã chỉnh sửa](requirements/use-cases/README.md).
- [Báo cáo tiến độ](progress/README.md).
- [Resource key và cấu hình kết nối](resource-keys.md).
- [Setup Langfuse](setup-langfuse.md).

Hướng dẫn chạy hạ tầng nằm tại `infra/` tương ứng. Bộ thiết kế cũ đã được thay bằng bộ ba trên để tránh nhiều bản quy định trùng nhau.
