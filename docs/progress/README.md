# Báo cáo tiến độ thực hiện đồ án

| Thông tin | Nội dung |
| --- | --- |
| Đề tài | Nghiên cứu và xây dựng hệ thống kho tri thức doanh nghiệp thông minh từ Confluence |
| Học viên | Đặng Nam Cường |
| Ngày cập nhật | 17/11/2026 |
| Giai đoạn | Hoàn thiện tài liệu thiết kế và chuẩn bị tích hợp luồng nghiệp vụ |

- Phần chuẩn bị đã gần hoàn tất: hạ tầng được dựng, có các phép thử thành phần, đặc tả và thiết kế chung đã được review về nội dung.
- Phần sản phẩm còn cần hoàn thiện: đồng bộ thiết kế chi tiết, tích hợp nguồn Confluence thật, embedding/LLM và hỏi đáp theo role.
- Các kết quả hạ tầng bên dưới là kết quả đã được ghi nhận trong các lần thử trước; lần cập nhật báo cáo này không chạy lại dịch vụ hoặc kiểm thử end-to-end.
- Chưa quy đổi tiến độ thành phần trăm vì chưa có kết quả nghiệm thu toàn hệ thống.

## 1. Phạm vi hiện tại

- Một chatbot dùng chung cho hai Space: chính sách nội bộ và chương trình khuyến mãi.
- Tổng 100–300 trang tiếng Việt, HTML đơn giản; chuyển sang Markdown và giữ tham chiếu ảnh.
- Tài khoản ứng dụng được lưu trong database, kèm role để lọc nội dung khi retrieve; không bổ sung chức năng đăng nhập/quản lý phiên chatbot.
- Nhân viên đọc cả hai Space; khách hàng chỉ đọc khuyến mãi; quản trị được cấu hình nguồn và xem trạng thái.
- Thu thập lần đầu và cập nhật tự động mỗi 60 phút.
- Chạy lại task/DAG khi cần là thao tác vận hành trên Airflow, không phải chức năng của giao diện chatbot.

**Luồng cập nhật:** PostgreSQL đối soát → HTML/Markdown và chia đoạn → API train trực tiếp → embedding và ghi MongoDB/Milvus thành công → Kafka → backend → giao diện quản trị.

**Luồng hỏi đáp:** lấy tài khoản/role từ database → retrieve → lọc đúng quyền và trạng thái → LLM → câu trả lời kèm trích dẫn.

## 2. Tiến độ tài liệu

| Tài liệu | Kết quả hiện tại | Việc còn lại |
| --- | --- | --- |
| [Đặc tả yêu cầu](../requirements.md) | Đã review và thống nhất 5 Use Case; dùng bảng điều kiện/đầu vào/đầu ra và luồng chính; đã bỏ đăng nhập, tìm kiếm riêng, đồng bộ/xử lý lại thủ công trên ứng dụng | Tiếp tục điều chỉnh khi có thay đổi nghiệp vụ được thống nhất |
| [Thiết kế chung](../architecture.md) | Đã chỉnh theo 5 Use Case, role trong database, cập nhật tự động và API train; sơ đồ có số thứ tự, mô tả rõ các kho dữ liệu và triển khai | Đối chiếu khi tích hợp code thực tế |
| [Thiết kế chi tiết](../detailed-design.md) | Có bản thiết kế schema, API, Kafka, module, trạng thái và RAG dựa trên code tham khảo | Rà soát theo đặc tả/thiết kế chung hiện tại; bỏ contract đăng nhập, tìm kiếm, đồng bộ và retry thủ công không còn thuộc ứng dụng |
| [Sơ đồ Use Case](../use-cases/README.md) | Ba sơ đồ theo nhân viên, khách hàng, quản trị; đã xuất SVG và đồng bộ tên/mã UC01–UC05 | Giữ đồng nhất khi sửa chức năng |

### Bộ Use Case hiện hành

| Mã | Chức năng |
| --- | --- |
| UC01 | Hỏi đáp chính sách công ty |
| UC02 | Hỏi đáp chương trình khuyến mãi |
| UC03 | Xem và kiểm chứng nguồn |
| UC04 | Cấu hình nguồn và phạm vi |
| UC05 | Theo dõi trạng thái xử lý |

- UC03 mở rộng UC01/UC02 khi người dùng chọn nguồn; UC04 và UC05 là chức năng quản trị độc lập.
- Mục 9–13 của đặc tả và mục 15–16 của thiết kế chung đang được comment theo phạm vi review.
- Bản Markdown là bản để đọc và chỉnh sửa. Các bản PDF đã xuất trước đó chưa mặc định đồng bộ với nội dung Markdown hiện tại.

## 3. Hạ tầng và thử nghiệm đã thực hiện

| Hạng mục | Kết quả đã ghi nhận | Phần chưa kiểm chứng |
| --- | --- | --- |
| Conda | Môi trường `namcuong`, Python 3.12.15; đã cài requirements và từng chạy `pip check` đạt | Mọi module/node đều chạy được trong runtime đích |
| WSL2/Docker Desktop | Đã chạy các stack local bằng Compose | Tổng tải khi toàn pipeline cùng hoạt động |
| MongoDB Atlas | ResourceHub truy cập database `cuong`; MongoNode FIND_ONE qua graph đạt | Tài khoản/role và dữ liệu Confluence nghiệp vụ xuyên suốt |
| Redis | Container `doan-redis`; ping qua engine đạt | Streaming câu trả lời LLM hoàn chỉnh |
| Langfuse Cloud | Đã gửi/đọc trace và chạy workflow có root/child observation | Toàn bộ luồng AI thật của đồ án |
| Beedoc | HTML → Markdown qua engine/workflow; 10 tiêu chí nội dung/metadata và 25 test sẵn có đã ghi nhận đạt | Nội dung Confluence thật và mọi định dạng HTML |
| Milvus/Attu | Ghi/query/search 3 vector demo, dữ liệu còn sau tạo lại container; MilvusNode QUERY/SEARCH qua graph đạt | Vector thật từ Cloudflare, collection và chất lượng retrieve nghiệp vụ |
| MinIO nghiệp vụ | Hai bucket có versioning; ghi/đọc HTML/Markdown, kiểm tra hash/metadata; giữ dữ liệu sau tạo lại container | Nối với ingestion thật và quy ước lưu bản gốc theo phiên bản |
| Kafka | Một broker KRaft; gửi/đọc JSON, commit offset và giữ dữ liệu qua tạo lại container | Sự kiện hoàn tất thật của tài liệu/toàn lượt và hiển thị trên giao diện |
| Airflow | LocalExecutor + PostgreSQL; DAG demo gửi/đọc Kafka có hai task success và lịch sử còn sau tạo lại container | DAG Confluence, job train và lịch nghiệp vụ tự động 60 phút |
| PostgreSQL nghiệp vụ | Container riêng `doan-ingestion-postgres`; đã tạo hai bảng và procedure, thử insert/update/hash/version/unique/job | Resource SQL `anapp`, dependency adapter và ingestion end-to-end |
| ResourceHub | Đã ghi nhận 7 resource; Kafka/S3 tải lại cấu hình và kiểm tra kết nối đạt | Cấu hình phù hợp cho cả Windows và container Airflow |

- PostgreSQL nghiệp vụ có `knowledge_base.documents`, `knowledge_base.sync_jobs` và procedure tương thích SQL caller; tách PostgreSQL metadata Airflow.
- DDL local được viết theo code tham khảo, không có căn cứ xác nhận là DDL production gốc.
- Dữ liệu thử SQL đã rollback tại lần smoke test; chưa có kết quả chạy dữ liệu Confluence nghiệp vụ được xác nhận trong báo cáo.
- Manifest thử Airflow/Kafka/MinIO và Markdown Beedoc nằm trong `tests/output`.

### Điểm truy cập theo cấu hình

| Thành phần | Vị trí/địa chỉ |
| --- | --- |
| MongoDB | Atlas, database `cuong`, quản trị bằng Compass |
| Langfuse | Cloud US, project theo cấu hình |
| Redis | `127.0.0.1:6379` |
| PostgreSQL nghiệp vụ | `127.0.0.1:5432`, database `ingestion` |
| Milvus / Attu | `127.0.0.1:19530` / `127.0.0.1:8000` |
| MinIO nghiệp vụ | API `127.0.0.1:9000`, console `127.0.0.1:9001` |
| Kafka | Windows `127.0.0.1:9092`; mạng Docker `kafka:29092` |
| Airflow | `127.0.0.1:8080`, LocalExecutor và PostgreSQL metadata riêng |

- Các stack đã cấu hình volume; đã thử giữ dữ liệu demo qua tạo lại container cho Milvus, MinIO, Kafka và Airflow.
- Chưa có kết quả backup/restore toàn hệ thống hoặc tự tiếp tục pipeline đang dở.
- DAG demo đã thử trigger thủ công, không phải bằng chứng DAG nghiệp vụ chạy đúng lịch 60 phút.
- Danh sách địa chỉ không xác nhận các dịch vụ đang chạy ở thời điểm đọc báo cáo.

Hướng dẫn: [PostgreSQL](../../infra/postgres/README.md), [Milvus/Attu](../../infra/milvus/README.md), [MinIO](../../infra/minio/README.md), [Kafka](../../infra/kafka/README.md), [Airflow](../../infra/airflow/README.md), [Langfuse](../setup-langfuse.md).

## 4. Mã nguồn và quản lý Git

- Đã đưa các module Beedoc, Beeflow, Beegen Chat, Ingestion và Portal API vào repository đồ án dưới dạng code thông thường; không còn con trỏ submodule.
- Đã đẩy bộ mã nguồn lên nhánh `main`; lịch sử Git riêng của các module được sao lưu ngoài workspace.
- Đã bỏ theo dõi cấu hình MongoDB local, thêm file mẫu `config/beeflow.example.yaml` và quy tắc bỏ qua cấu hình bí mật.
- Đã loại các giá trị bí mật phát hiện trong phần mã chuẩn bị đẩy; snapshot được quét bằng Gitleaks tại lần nhập module không có phát hiện còn lại.
- Các thay đổi review tài liệu hiện tại đang ở working tree, chưa được coi là đã commit/push trong lần cập nhật báo cáo này.
- Cấu hình từng được commit vẫn có thể còn trong lịch sử cũ; cần đổi các thông tin đăng nhập đã lộ.

### Thư viện đã điều chỉnh trong các lần thử thành phần

- Beedoc: giữ nhánh HTML → Markdown và tham chiếu ảnh; sửa đầu ra hashing node để giữ metadata.
- Redis: điều chỉnh config/connection pool cho kết nối local.
- Langfuse: bổ sung adapter tương thích SDK đã dùng trong thử nghiệm và đợi flush trace.
- MilvusEngine: điều chỉnh cách nhận tham số SEARCH để graph QUERY/SEARCH chạy được.
- Các bản `replica/` là bản tham khảo; không tự đồng bộ với thư viện runtime trong `beeflow/beeflow`.

## 5. Resource và cấu hình kết nối

Các resource đã được ghi nhận tại **`cuong.beegen_resource_configs`**:

| Resource key | Config | Mục đích |
| --- | --- | --- |
| `mongo:knowledge` | MongoConfig | Kết nối MongoDB |
| `redis:aicenter-chatbot` | RedisConfig | Redis cho stream service |
| `langfuse:beegen` | LangfuseConfig | Trace workflow |
| `milvus:knowledge` | MilvusConfig | Milvus local |
| `kafka:knowledge` | KafkaConfig | Kafka local |
| `s3:knowledge-raw` | S3Config | Bucket HTML gốc |
| `s3:knowledge-processed` | S3Config | Bucket Markdown |

Đây là cấu hình kết nối, không phải tài liệu/chunk/hội thoại. Node dùng phần sau dấu `:` làm `resource_key`. Airflow, Attu và Offset Explorer được cấu hình riêng, không cần ResourceHub key trong thiết kế hiện tại.

`config/beeflow.yaml` khởi tạo ResourceHub; theo mã hiện tại, `authen_source` chọn database cấu hình, không đồng nghĩa tham số chuẩn MongoDB `authSource`. MongoDB thực tế dùng Atlas thay cho dự kiến local ban đầu.

Chi tiết địa chỉ Windows/Docker và cách kiểm tra: [danh sách resource key](../resource-keys.md).

## 6. Chạy lại các phép kiểm tra

Chạy từ thư mục gốc trong Conda `namcuong`. Cần các dịch vụ tương ứng đang hoạt động; workflow còn cần Atlas/Langfuse. Các kết quả là phép thử thành phần, chưa phải đánh giá chất lượng RAG.

| Lệnh | Nội dung và tác động |
| --- | --- |
| `python test_resourcehub.py` | Kiểm tra YAML, MongoConfig, ping/read collection; chỉ đọc |
| `python test_redis.py` | RedisEngine ping |
| `python test_mongonode.py` | MongoNode FIND_ONE qua graph; đọc cấu hình đã chọn và tạo trace |
| `python test_langfuse.py` | Xác thực, gửi/đọc observation giả lập |
| `python test_langfuse_workflow.py` | CodeNode qua graph thật, dùng Redis và tạo trace |
| `python test_beedoc_html.py` | BeedocEngine qua workflow; lưu Markdown và tạo trace |
| `python test_beedoc_html.py --converter-only` | Converter trực tiếp, không cần dịch vụ; lưu Markdown |
| `python test_milvus.py` | Upsert 3 ID cố định, query/search vector demo |
| `python test_milvus_resource.py` | Tải Milvus config qua ResourceHub và đọc demo |
| `python test_milvusnode.py` | QUERY/SEARCH qua graph thật, không ghi vector; tạo trace |
| `python test_minio.py` | Bật versioning, ghi/đọc HTML/Markdown dưới prefix demo mới |
| `python test_kafka.py` | Tạo topic nếu thiếu, gửi message, đọc và commit offset bằng group demo mới |
| `python test_airflow.py` | Trigger DAG thật, xác nhận hai task success; khôi phục paused nếu ban đầu paused |
| `python test_infra_resources.py` | Kafka/S3 qua ResourceHub; chỉ kiểm tra metadata/bucket |
| `python test_infra_resources.py --register` | Thêm config Kafka/S3 còn thiếu; từ chối ghi đè config khác |

Các script `test_milvus.py`, `test_minio.py`, `test_kafka.py`, `test_airflow.py` có chế độ `--read-only` để kiểm tra dữ liệu/lịch sử cũ sau restart mà không ghi lại dữ liệu hoặc tạo run mới. Manifest gần nhất và Markdown đầu ra nằm trong `tests/output`. Một số test chế độ ghi thêm dữ liệu demo mỗi lần chạy.

## 7. Công việc cần hoàn thiện

| Thứ tự | Công việc | Kết quả cần có |
| --- | --- | --- |
| 1 | Đồng bộ thiết kế chi tiết | Dữ liệu, API, trạng thái và RAG phù hợp 5 Use Case; làm rõ schema tài khoản/role và cách truyền định danh tài khoản |
| 2 | Nối PostgreSQL nghiệp vụ và Confluence | Resource SQL/dependency đúng; đọc được tài liệu thật từ đủ hai Space và so sánh với dữ liệu đã lưu |
| 3 | Tích hợp thu thập và chuẩn bị nội dung | Bản gốc theo phiên bản vào MinIO; metadata/quyền và các đoạn vào MongoDB; xử lý thêm/sửa/xóa đúng phạm vi |
| 4 | Tích hợp embedding và train | Chốt model/kích thước vector theo quota; API train nhận đoạn đã chuẩn bị; ghi MongoDB/Milvus và xác nhận kết quả thật |
| 5 | Nối DAG và thông báo nghiệp vụ | Airflow chạy luồng cập nhật 60 phút; Kafka chỉ phát sau hoàn tất; backend/giao diện hiển thị đúng tài liệu và toàn lượt |
| 6 | Hoàn thiện hỏi đáp và giao diện | Lấy role từ database, retrieve đúng quyền; trả lời tiếng Việt, có trích dẫn và xem nguồn; cấu hình/theo dõi cho quản trị |
| 7 | Kiểm thử và bàn giao | Chạy xuyên suốt từ thay đổi Confluence đến câu trả lời; đo chất lượng, độ trễ và tài nguyên; có hướng dẫn, cấu hình mẫu và minh chứng |

- Ưu tiên một luồng nhỏ chạy hoàn chỉnh trước khi mở lên bộ 100–300 trang.
- Không bổ sung yêu cầu xác thực, tìm kiếm riêng, nút đồng bộ/retry hoặc phục hồi phân tán ngoài phạm vi đã thống nhất.
- Báo cáo chưa có bằng chứng xác nhận pipeline Confluence → embedding thật → RAG đúng role đã hoàn tất.
