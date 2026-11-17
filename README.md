# Hệ thống kho tri thức doanh nghiệp thông minh từ Confluence

- **Tên đề tài:** Nghiên cứu và xây dựng hệ thống kho tri thức doanh nghiệp thông minh từ Confluence.
- **Học viên:** Đặng Nam Cường.
- **Định hướng:** Data Engineering và AI; thử nghiệm với tổ chức ngân hàng giả lập.

## Bài toán và đầu ra

Tài liệu chính sách và khuyến mãi trên Confluence thường xuyên thay đổi. Hệ thống tự động đối soát, thu thập và lập chỉ mục để nhân viên/khách hàng hỏi đáp bằng tiếng Việt, nhận câu trả lời có căn cứ trong đúng phạm vi được cấp.

- Đầu vào: 100–300 trang tiếng Việt thuộc hai Space, HTML đơn giản.
- Đầu ra dữ liệu: bản gốc theo phiên bản đã thu thập, metadata/quyền, nội dung chuẩn hóa và chỉ mục vector.
- Đầu ra người dùng: câu trả lời RAG kèm nguồn; thông báo thiếu căn cứ khi dữ liệu không đủ.
- Đầu ra quản trị: trạng thái xử lý và thông báo sau khi cập nhật hoàn tất.

Giá trị hướng tới: kiểm soát chính sách khai thác tài liệu; giảm công sức tra cứu/hỗ trợ lặp lại; giúp giải thích chính sách ngân hàng nhất quán theo nguồn. Không thực hiện giao dịch hoặc quyết định nghiệp vụ ngân hàng thật.

## Phạm vi và luồng đã chốt

- Một bot chung; Space chính sách cấp quyền INTERNAL, Space khuyến mãi cấp INTERNAL và CUSTOMER.
- Nhân viên đọc cả hai Space; khách hàng có tài khoản chỉ hỏi đáp/xem nguồn khuyến mãi; quản trị có chức năng vận hành.
- Tài liệu kế thừa quyền Space; backend kiểm tra quyền trước đưa nội dung vào LLM và trả nguồn.
- Bootstrap lần đầu, sau đó AUTO mỗi 60 phút. Giữ các phiên bản thực tế thu thập được, không toàn bộ lịch sử Confluence.
- Chỉ HTML → Markdown và tham chiếu ảnh; không OCR/AI ảnh, attachment phức tạp hoặc lịch sử hội thoại nhiều lượt.

**Cập nhật kho:** Airflow → Confluence → PostgreSQL đối soát → bản gốc/metadata/quyền → chunk → API train trực tiếp → embedding và ghi MongoDB/Milvus → Kafka thông báo → backend → FE quản trị.

**Hỏi đáp:** lấy tài khoản/role từ database → vector retrieval → đọc nội dung MongoDB → lọc quyền/trạng thái → LLM → trả lời và trích dẫn.

HTTP tiếp nhận train khác hoàn tất job. Kafka chỉ thông báo kết quả, không điều phối train. Việc chạy lại task/DAG khi cần được thực hiện trên Airflow, không có nút đồng bộ hoặc xử lý lại trong chatbot.

## Bộ tài liệu hiện hành

| Tài liệu | Nội dung |
| --- | --- |
| [Đặc tả yêu cầu v2.0](docs/requirements.md) | Bài toán, phạm vi, role, 5 Use Case và luồng chính. |
| [Thiết kế chung v2.0](docs/architecture.md) | Thành phần, dữ liệu, luồng cập nhật/hỏi đáp và triển khai. |
| [Thiết kế chi tiết v2.0](docs/detailed-design.md) | Schema, API, Kafka notification, trạng thái, ACL/RAG và kế hoạch kiểm chứng. |

Các tài liệu đang ở trạng thái dự thảo để review. Contract có nhãn mới/đề xuất chưa đồng nghĩa đã được triển khai. [Báo cáo tiến độ](docs/progress/README.md) ghi riêng các phần đã kiểm chứng. Xem [mục lục docs](docs/README.md) để điều hướng.

## Công nghệ

| Nhóm | Thành phần |
| --- | --- |
| Nguồn | Confluence Cloud Free |
| Điều phối | Airflow; API trực tiếp kích hoạt train |
| Đối soát | PostgreSQL nghiệp vụ; tách PostgreSQL metadata Airflow |
| Lưu trữ | MongoDB, MinIO local, Milvus Standalone local và Attu |
| AI | Cloudflare Workers AI cho embedding/LLM; quota miễn phí |
| Ứng dụng | FastAPI, Streamlit, chunking tùy chỉnh |
| Thông báo/quan sát | Kafka, Redis theo dependency runtime và Langfuse |
| Triển khai | Docker Compose, máy 32 GB RAM, không GPU; chưa dùng Kubernetes |

MongoDB thử nghiệm dùng Atlas theo cấu hình hiện tại. Schema PostgreSQL local được dựng theo SQL caller tham khảo, không phải bản sao DDL production. Model/profile AI, schema tài khoản/role và cách truyền định danh tài khoản còn cần cụ thể hóa khi triển khai.

## Tiến độ hiện tại — 17/11/2026

- Phần chuẩn bị đã gần hoàn tất: hạ tầng được dựng, có thử nghiệm thành phần và bộ code tham khảo trong repository.
- Đặc tả và thiết kế chung đã review theo 5 Use Case; các sơ đồ đã được đồng bộ.
- Tiếp theo: chỉnh thiết kế chi tiết, tích hợp Confluence/PostgreSQL, embedding thật, thông báo và hỏi đáp đúng role.
- Chưa có bằng chứng nghiệm thu luồng Confluence → lập chỉ mục → hỏi đáp xuyên suốt. Chi tiết tại [báo cáo tiến độ](docs/progress/README.md).

## Hướng dẫn và tiến độ

- [Báo cáo tiến độ](docs/progress/README.md).
- [PostgreSQL nghiệp vụ](infra/postgres/README.md).
- [Airflow local](infra/airflow/README.md).
- [Kafka và Offset Explorer](infra/kafka/README.md).
- [MinIO nghiệp vụ](infra/minio/README.md).
- [Milvus và Attu](infra/milvus/README.md).
- [Resource keys](docs/resource-keys.md), [Langfuse](docs/setup-langfuse.md).
- [Sơ đồ Use Case và cách chỉnh sửa](docs/use-cases/README.md).

Mã nguồn tham khảo nằm trong `beegen-ingestion/`, `beegen-portal-api/`, `beegen-chat/`, `beedoc/` và `beeflow/`. Điểm kế thừa/thay đổi được dẫn trực tiếp trong thiết kế; các nhánh nghiệp vụ khác không tự thuộc phạm vi đồ án.

## Cấu hình sau khi clone

- Các module được lưu trực tiếp trong repository; không cần khởi tạo Git submodule.
- Sao chép `config/beeflow.example.yaml` thành `config/beeflow.yaml`, rồi điền kết nối MongoDB của môi trường.
- File `.env`, khóa riêng và cấu hình resource chứa thông tin đăng nhập được giữ ở local, không đưa lên Git.
- Các giá trị `REPLACE_WITH_LOCAL_SECRET`, `REPLACE_WITH_LOCAL_TOKEN` và `LOCAL_PASSWORD` trong code tham khảo là chỗ trống cần cấu hình trước khi chạy nhánh tương ứng.
