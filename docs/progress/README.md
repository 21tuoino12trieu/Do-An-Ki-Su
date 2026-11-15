# Báo cáo tiến độ thực hiện đồ án

## Bổ sung ngày 08/11/2026 — PostgreSQL nghiệp vụ ingestion

- Đã dựng container riêng `doan-ingestion-postgres`, PostgreSQL 16.11, local `127.0.0.1:5432`, database/user `ingestion`, volume `doan-ingestion_postgres-data`; tách PostgreSQL Airflow.
- Đã khởi tạo `knowledge_base.documents`, `knowledge_base.sync_jobs` và procedure tương thích caller AUTO/PARTIAL. DDL được viết theo SQL tham khảo vì không có DDL gốc trong repository.
- Đã kiểm tra health, cổng local và smoke SQL insert/update/hash/version/unique identity/job; dữ liệu thử đã rollback, hai bảng chưa có dữ liệu nghiệp vụ.
- Chưa cấu hình ResourceHub `anapp` hoặc chạy workflow ingestion end-to-end. Giữ PostgreSQL cho đối soát nội dung/metadata; không tạo thêm Mongo `sync_runs`.
- Cấu hình, cách kết nối và giới hạn kiểm chứng: [infra/postgres/README.md](../../infra/postgres/README.md).

- **Đề tài:** Nghiên cứu và xây dựng hệ thống kho tri thức doanh nghiệp thông minh từ Confluence.
- **Học viên:** Đặng Nam Cường.
- **Ngày cập nhật:** 03/11/2026.
- **Giai đoạn hiện tại:** đã dựng hạ tầng thử nghiệm, kiểm chứng một số workflow; chuẩn bị tích hợp dữ liệu Confluence.

**Đã hoàn thành nền hạ tầng local/cloud và các phép thử thành phần, bao gồm DAG Airflow gửi/đọc Kafka. Chưa hoàn thành pipeline Confluence → lập chỉ mục → hỏi đáp RAG.**

Báo cáo tổng hợp các lần kiểm thử đã thực hiện, không phải kết quả kiểm tra lại toàn bộ dịch vụ trong lần sửa tài liệu này. Không quy đổi số dịch vụ đã dựng thành phần trăm hoàn thành đồ án.

## 1. Bài toán và đầu ra hướng tới

- **Bài toán:** tài liệu Confluence thường xuyên được thêm, sửa, xóa; cần đồng bộ và quản lý phiên bản để nhân viên tra cứu, hỏi đáp có nguồn, tránh dùng nội dung hết hiệu lực.
- **Đầu vào:** hai Confluence Space thử nghiệm, dự kiến 100–300 trang; ưu tiên HTML đơn giản và nội dung tiếng Việt.
- **Đầu ra:** kho tri thức lưu được phiên bản, pipeline đồng bộ mỗi 60 phút, ứng dụng tìm kiếm/hỏi đáp RAG có liên kết và phiên bản nguồn, cùng báo cáo đánh giá.
- **Giới hạn cập nhật 05/11/2026:** dữ liệu giả lập hoặc công khai được phép sử dụng. Thiết kế mới tách nhân viên/Space chính sách và khách hàng/Space khuyến mãi; khách hàng phải đăng nhập. Chức năng xác thực/phân quyền này chưa có code.

## 2. Công việc đã hoàn thành

| Hạng mục | Kết quả đã xác nhận | Giới hạn hiện tại |
| --- | --- | --- |
| Thiết kế | Có tài liệu yêu cầu, kiến trúc, dữ liệu, đồng bộ, phiên bản, RAG và trách nhiệm module | Cần cập nhật theo triển khai và tiếp tục review |
| Conda | Môi trường `namcuong`, Python 3.12.15; đã cài requirements và từng chạy `pip check` đạt | Không khẳng định mọi node thư viện đều chạy được |
| WSL2/Docker Desktop | Đã chạy các stack local bằng Compose | Chưa đánh giá tải khi toàn bộ pipeline chạy đồng thời |
| MongoDB Atlas | ResourceHub truy cập database `cuong`; MongoNode FIND_ONE qua graph thật đạt | Chưa triển khai dữ liệu nghiệp vụ Confluence |
| Redis | Container `doan-redis`, ping qua engine đạt, phục vụ stream service | Chưa kiểm thử streaming câu trả lời LLM hoàn chỉnh |
| Langfuse Cloud | Xác thực, gửi/đọc lại trace, workflow thật có root/child observation | Chưa kiểm thử toàn bộ loại node hoặc model thật |
| Beedoc | HTML → Markdown qua BeedocEngine và workflow thật; 10 tiêu chí nội dung và metadata đạt; 25 test sẵn có đạt | Chưa thử trang Confluence thật hoặc mọi dạng HTML |
| Milvus + Attu | Thêm/query/search 3 vector giả lập, dữ liệu còn sau tạo lại container, giao diện trả HTTP 200 | Vector demo 4 chiều, chưa phải embedding/collection RAG |
| MilvusNode | QUERY và SEARCH qua hai graph Beeflow thật đạt | Chưa thử operation ghi, retry hoặc chuyển phiên bản chỉ mục |
| MinIO tài liệu | Hai bucket có versioning; ghi/đọc HTML và Markdown, kiểm tra SHA-256 và metadata; dữ liệu còn sau tạo lại container | Chưa nối ingestion hoặc chốt object key nghiệp vụ |
| Kafka | KRaft một broker; gửi/đọc JSON và commit offset; sự kiện/offset còn sau tạo lại container | Chưa thử KafkaNode, xử lý lỗi nghiệp vụ hoặc trực tiếp kết nối Offset Explorer |
| Airflow | LocalExecutor + PostgreSQL; đăng nhập API; DAG thật gửi/đọc Kafka, hai task success; lịch sử còn sau tạo lại container | DAG demo paused, chưa kiểm tra lần chạy tự động theo lịch hoặc DAG Confluence |
| ResourceHub | Có 7 key; Kafka/S3 tải lại trong tiến trình mới, kết nối và kiểm tra metadata/versioning đạt | Endpoint hiện dành cho chương trình trên Windows |

## 3. Hạ tầng hiện có

| Thành phần | Triển khai | Điểm truy cập |
| --- | --- | --- |
| MongoDB | Atlas cloud, quản trị bằng Compass | Database `cuong` |
| Langfuse | Cloud US | Project đã cấu hình |
| Redis | Docker local | `127.0.0.1:6379` |
| Milvus | Docker Standalone, có etcd/MinIO phụ thuộc | `127.0.0.1:19530`; Attu: http://localhost:8000 |
| MinIO tài liệu | Container/volume riêng với MinIO nội bộ Milvus | S3: `127.0.0.1:9000`; Console: http://localhost:9001 |
| Kafka | Broker kiêm controller KRaft | Windows: `127.0.0.1:9092`; network `doan-backend`: `kafka:29092` |
| Airflow | API server, scheduler/LocalExecutor, DAG processor và PostgreSQL | http://localhost:8080 |

- Máy phát triển 32 GB RAM, không GPU; Docker tại lần kiểm tra được cấp khoảng 15,5 GB RAM và 8 CPU.
- Các stack có volume lưu bền dữ liệu. Đã thử tạo lại container cho Milvus, MinIO, Kafka và Airflow; chưa thử backup/restore hoặc mất máy.
- PostgreSQL lưu vận hành Airflow, tách biệt MongoDB nghiệp vụ.
- DAG demo khai báo cron `0 * * * *` (đầu mỗi giờ), `catchup=False`; test trigger thủ công và khôi phục paused.
- Không ghi mật khẩu/token trong báo cáo; xem hướng dẫn stack để tìm file cấu hình cục bộ.

Hướng dẫn: [Milvus/Attu](../../infra/milvus/README.md), [MinIO](../../infra/minio/README.md), [Kafka/Offset Explorer](../../infra/kafka/README.md), [Airflow](../../infra/airflow/README.md), [Langfuse](../setup-langfuse.md).

## 4. Các resource đã đăng ký trong MongoDB

Collection **`cuong.beegen_resource_configs`** có:

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

## 5. Thư viện và các chỉnh sửa đã thực hiện

- [Beedoc replica](../../replica/beedoc/README.md) giữ engine, interface/model, reader, renderer, factory và tiện ích nhánh HTML. Phạm vi: **HTML → Markdown, giữ nguyên thẻ ảnh**, không tải ảnh/OCR hoặc gọi model phân tích ảnh.
- HTML mẫu kiểm tra tiếng Việt, heading, danh sách lồng, bảng đơn giản, liên kết, ảnh, code và blockquote; loại comment/script/style. Đã sửa HTML reader khai báo output của hashing node để trả metadata vào Document.
- [Beeflow replica](../../replica/beeflow/README.md) là bản tham khảo 40 tệp Beeflow và 139 tệp Beegen tại thời điểm sao chép. Runtime hiện dùng repo gốc `beeflow/beeflow`; hai cây mã không tự đồng bộ.
- Đã sửa RedisConfig/connection pool để kết nối Redis local.
- Langfuse dùng SDK chính thức 4.7.1, có adapter và đợi flush trong workflow; SDK cũ giữ tại `_legacy` để không che package pip. Adapter dùng API nội bộ nên cần kiểm tra khi nâng SDK.
- Đã sửa MilvusEngine SEARCH nhận cả config phẳng và mapping có `params`, tránh bọc thừa tham số.
- MilvusEngine dùng ORM API của PyMilvus 3.0.2, có cảnh báo deprecated; cần chuyển sang MilvusClient trước khi nâng lên 3.1.

Tài liệu hiện hành: [đặc tả yêu cầu](../requirements/README.md), [thiết kế chung](../architecture/README.md) và [thiết kế chi tiết](../detailed-design/README.md). Căn cứ code tham khảo được dẫn trực tiếp trong các tài liệu thiết kế.

Các đợt review 05–06/11/2026 đã bổ sung tài khoản khách hàng, ma trận quyền hai Space và sơ đồ UML tác nhân hình người. Ngày 07/11/2026, nội dung được tổng hợp vào bộ ba tài liệu mới; tài liệu thiết kế cũ cùng bản xuất Word/PDF/draw.io và ảnh QA đã được dọn khỏi `docs`. Bốn sơ đồ Use Case hiện hành cùng mã chỉnh sửa được giữ trong [tài nguyên đặc tả](../requirements/use-cases/README.md). Đây là tiến độ tài liệu, không chứng minh đăng nhập/phân quyền/pipeline nghiệp vụ đã được triển khai.

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

## 7. Công việc còn lại và thứ tự triển khai

| Thứ tự | Công việc | Tiêu chí hoàn thành |
| --- | --- | --- |
| 1 | Connector Confluence | Đọc một trang thật và metadata/version, xác nhận phạm vi hai Space |
| 2 | Lưu tài liệu và metadata nghiệp vụ | HTML/Markdown vào MinIO, định danh/trạng thái vào MongoDB; chạy lại cùng phiên bản không tạo trùng |
| 3 | Worker và vòng đời đồng bộ | Thêm/sửa/xóa/mất quyền, cơ chế gửi lại sự kiện, retry, idempotency và sự kiện sai thứ tự; tích hợp KafkaNode nếu dùng |
| 4 | Chunking, Cloudflare embedding và collection RAG | Chunk có nguồn/version; chốt model, quota, số chiều và metric; lập chỉ mục bộ dữ liệu nhỏ |
| 5 | Airflow đồng bộ thực tế mỗi 60 phút | DAG nghiệp vụ, cập nhật mốc đồng bộ đúng và theo dõi trạng thái sẵn sàng hỏi đáp |
| 6 | FastAPI, luồng chat và Streamlit | Hỏi đáp tiếng Việt có URL/phiên bản, chỉ dùng nội dung hiệu lực, báo thiếu căn cứ |
| 7 | Đánh giá và đóng gói | Recall@k, chất lượng trả lời/nguồn, độ mới, độ trễ, chi phí và các kịch bản phục hồi |

Cloudflare embedding/LLM chưa có kết quả tích hợp đầu cuối được xác nhận trong giai đoạn này. Việc từng gọi API embedding thành công không thay thế đánh giá truy xuất hoặc quota của pipeline.

## 8. Các điểm cần hoàn thiện trước bàn giao

- README tổng quan và thiết kế còn mô tả dự kiến cần đồng bộ với thực tế: MongoDB Atlas, lịch 60 phút, hai Space/100–300 trang và hạ tầng đã dựng.
- Git đang nhận năm thư mục nguồn dưới dạng repository lồng nhau; cần chốt submodule hoặc đưa code vào repo đồ án để bản clone có đủ nguồn và các sửa runtime.
- Theo lần kiểm tra Git gần nhất, `config/beeflow.yaml` đã vào vùng chờ commit trong khi có thông tin kết nối; cần bỏ theo dõi và thêm ignore trước commit/push. Lần cập nhật báo cáo này không thay đổi index hoặc cấu trúc repo.
- Chưa kiểm thử phân quyền ingestion trên MinIO, backup/restore, quota Cloudflare, sự kiện trùng/sai thứ tự, cập nhật/xóa tài liệu hoặc tải đồng thời toàn hệ thống.
- Restart thành công với dữ liệu demo chưa chứng minh phục hồi pipeline nghiệp vụ đang xử lý dở.

**Đánh giá tiến độ:** nền hạ tầng và các phép thử tích hợp nhỏ đã có bằng chứng hoạt động. Công việc trọng tâm tiếp theo là pipeline với tài liệu Confluence thật, lập chỉ mục và hỏi đáp có nguồn.
