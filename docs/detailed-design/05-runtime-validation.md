# 05. Runtime, rollout và kiểm chứng

[← Mục lục](../detailed-design.md) · LLD v2.0 — 10/11/2026.

## 1. Deployment profiles

| Runtime | Profile kết nối | Trách nhiệm |
| --- | --- | --- |
| Windows Conda | Endpoint host loopback cho dịch vụ local; Atlas/cloud theo config | API/Chat/Streamlit và notification consumer pilot. |
| Airflow Linux container | DNS/network alias container hoặc host endpoint đã kiểm chứng | Ingestion, preparation, train tasks; không dùng đường dẫn Python/Conda Windows. |
| PostgreSQL nghiệp vụ | Container riêng `doan-ingestion-postgres`, database/user ingestion, host port 5432 | SQL snapshot và sync_jobs. |
| Airflow metadata | PostgreSQL riêng của Compose Airflow | DAG/task/runtime; không dùng credentials này cho knowledge_base. |

- Không dùng localhost của container để trỏ host khác.
- Airflow đang có network `doan-backend`, nhưng từng Compose phải được nối và kiểm tra alias thực.
- Kafka bootstrap và advertised listener phải phù hợp profile.
- Không chỉ sửa bootstrap address.
- FastAPI host muốn nhận request từ container phải bind interface được truy cập và giữ auth.

- **Port ứng dụng đề xuất:** FastAPI 8001, Streamlit 8501 để tránh Attu hiện dùng 8000.
- Milvus 19530, MinIO nghiệp vụ 9000/9001, Kafka host 9092, Airflow 8080 và PostgreSQL ingestion 5432 theo file setup.

## 2. Configuration contract

| Nhóm | Cấu hình cần có | Validation |
| --- | --- | --- |
| Bootstrap | BEEGEN_ROOT và Mongo registry config | File đúng loader, không in URI/secret. |
| SQL | Resource caller `anapp` hoặc alias được thay có kiểm soát | Dùng đúng trường uri/user/password/pool/connect options của `SQLConfig`; không truyền field ngoài model. |
| Mongo | Bot/metadata resource | Đúng database/collection; chọn profile host/container. |
| S3 | Raw và processed resources | Bucket allowlist, raw version key, không xóa raw sau train. |
| Milvus | Resource/schema/model profile | D khớp index/query, cùng namespace/metric/type. |
| Airflow API | Base URL, auth, allowed DAG IDs và timeout | Khớp bản local; bỏ Basic token/path hardcode/verify=False của môi trường gốc. |
| Notification | Topic/group/schema version theo 02 | Producer/consumer đúng topic, không group CHUNKING. |
| Cloudflare AI | Embedding/LLM profile, credentials, quota/concurrency | Chọn model và D trước tạo index; chưa chọn thì fail validation, không tự đoán model. |
| Domain | Một bot, hai Space/roles, no-overlap | Đúng mapping và không chứa credential user cuối. |
| Redis/Langfuse | Resource theo đường thực thi đã chọn | Stream dependency có thể cần init; trace không mặc định gửi toàn văn. |

- Resource registry hiện tại xem [resource-keys.md](../resource-keys.md).
- Key kỹ thuật không cấp quyền người dùng.
- SQL container đã dựng không đồng nghĩa resource anapp đã trỏ local hoặc dependency psycopg đã có trong mọi runtime.
- Giảm pool/concurrency phải qua model validation và test.

- Không in `docker compose config` chứa secret hoặc dump resource document để debug.

## 3. Thứ tự rollout đề xuất

1. Kiểm tra local PostgreSQL schema/procedure và resource SQL bằng SQLNode; giữ phân biệt DDL local với upstream chưa có.
2. Seed/validate một bot, hai roles, mapping Space; audit ID/type/index trước migration Mongo.
3. Nối connector Cloud với inventory hai Space, raw version key và ACL; xác minh hash so cùng content representation.
4. Tách và test preparation entrypoint từ graph consumer; giữ raw/quyền, bỏ image AI/empty success giả.
5. Sửa train API accepted semantics/correlation/local Airflow, cài package đúng image Linux; triển khai parent graph và reschedule wait.
6. Test một document embedding/index đúng profile trên Milvus local; sau đó kiểm thử batch và metadata-only/xóa.
7. Thêm publisher tài liệu/toàn lượt sau compute completion; chạy notification backend và UI poll có auth.
8. Chọn RAG entrypoint có đủ dependency, áp policy cho chunk/node/tool/source; đo chất lượng bằng bộ chuẩn.
9. Chạy AC end-to-end trong điều kiện AS01–AS03; ghi expected/actual, IDs và minh chứng. Không gọi mọi test là pass từ việc thiết kế xong.

- Pipeline API và consumer CHUNKING không được cùng điều phối một tài liệu.

## 4. Contract/unit tests phải có khi triển khai

| Mã test | Đối tượng/input | Expected behavior |
| --- | --- | --- |
| T01 | SQL snapshot insert/update qua caller/procedure | Cùng bot/page một row, MD5 đúng, version/metadata đúng tên SQL. |
| T02 | Hash fragment và wrapper HTML | Hash tính nhất quán trên fragment, không đổi giả do wrapper. |
| T03 | Body đổi, title-only, parent-only, không đổi | Phân loại đúng, không train metadata-only; ID Mongo giữ nguyên. |
| T04 | Fetch phân trang chưa đủ | Không sinh tập xóa hàng loạt. |
| T05 | Logs legacy/plain và JSON v1 | Parse tương thích; finalize giữ correlation, không lộ secret. |
| T06 | Bot/role/Space invalid hoặc trùng | Từ chối; không default L1/công khai. |
| T07 | Raw URI sai bucket/bot/version | Preparation từ chối, không tải URL tùy ý. |
| T08 | Beedoc result model/lỗi/text rỗng | Adapter lấy Markdown đúng, lỗi không biến empty success. |
| T09 | Chunk HTML có heading/list/table/code/ref ảnh | Thứ tự/nội dung đúng profile; không OCR/AI ảnh. |
| T10 | Preparation ghi lại | Không eligible trong lúc replace; ACL/raw không bị unset; trạng thái chunk đúng. |
| T11 | TrainRequest body/case/empty IDs | Giữ tên bot_id/type/ids, document/QA case đúng; phạm vi cốt lõi không mở QA ngoài scope. |
| T12 | Train chưa chunk/đã trained/đang chạy/bot khác | 409/404/authorization phù hợp; không trigger job chồng. |
| T13 | Header SQL job sai bot/ID | Bị từ chối; correlation từ client phải được xác minh phía server. |
| T14 | Train API HTTP 200 queued | Accepted data đúng; không publish success từ router. |
| T15 | Vector count/D/NaN/Inf/zero sai | Không DONE hoặc publish success. |
| T16 | Node profile disabled so với node generation lỗi | Optional rỗng hợp lệ khác required node thất bại. |
| T17 | Operation Mongo/Milvus failure | training ERROR, không success; không claim rollback nhiều kho. |
| T18 | Compute thành công, Kafka publish thất bại | Data DONE không reset; delivery/task lỗi tách biệt. |
| T19 | Manifest nhiều loại item | Tổng hợp đúng, không dùng SQL count hoặc event count thay manifest. |
| T20 | Event v1 hợp lệ/schema lạ/key bot lệch | Consumer xử lý đúng hoặc sanitized log/skip; không gọi train. |
| T21 | Event lặp cùng document/run | Projection set theo ID; không tăng counter theo số lần nhận; không cam kết exactly-once. |
| T22 | Config policy thu hồi khi body giống | Quyền bị chặn ngay bằng policy, propagation hoàn tất trước xác nhận. |
| T23 | CUSTOMER query, node/tool/source và role giả | Nội bộ không có trong context/rerank/answer/citation. |
| T24 | Source version/ID đoạn không khớp | 409 source changed hoặc lỗi không tiết lộ, không trả raw URL. |
| T25 | LLM evidence ID giả/thiếu bằng chứng | Không dựng citation giả; INSUFFICIENT_EVIDENCE khi phù hợp. |
| T26 | Quota/network/auth query fail | Lỗi khác no-evidence, không provider fallback trả phí. |

- Unit tests dùng adapter giả lập và call-order assertions có ý nghĩa.
- Test vector visibility/dimension cần kiểm chứng client/backend thật ở integration, không kết luận từ mock insert success.

## 5. Integration và end-to-end

| Luồng | Fixture/thao tác | Minh chứng |
| --- | --- | --- |
| Một trang mới | Capture → SQL/Mongo/MinIO → prep → train API → Airflow → Milvus | Row/record/object/IDs và state theo từng bước, event chỉ sau completion. |
| Version tuần tự | v1 hoàn tất rồi v2 đổi body | Hash đổi, UUID giữ, raw hai version còn, derived hiện hành dùng body v2. |
| Metadata-only | Title/link/parent hoặc ACL đổi, body giữ | Không gọi embedding, metadata/quyền hiển thị đúng, không reset trạng thái tốt thành giả. |
| Xóa | Xác minh page rời nguồn/phạm vi | Chặn Mongo trước, vector cũ không bypass quyền, raw lịch sử giữ. |
| Batch | Nhiều document + metadata/xóa/unchanged | Từng document success khác whole-run success, manifest đúng và không zero-train event giả. |
| API/correlation | Source caller → Portal → child DAG | Conf/header/run ID đúng bot/job, logs JSON vẫn giữ lỗi gốc. |
| UI notification | Broker/backend hoạt động | Producer event → consumer → poll API admin → UI có kết quả đúng; nhân viên/khách hàng bị chặn. |
| Parent/child capacity | Airflow parallelism local nhỏ | Sensor nhường slot, child chạy được, không deadlock do parent giữ tài nguyên. |
| RAG quyền | Hai Space + ba principal | Policy applies trước context; citation/source đúng. |
| Persistence | Restart sau toàn bộ job đã xong | Dữ liệu đã ghi còn; không kiểm tra auto-resume job đang dở ngoài scope. |

- Sự kiện hoàn tất là bằng chứng phụ của data complete, không thay query trực tiếp xác minh record/vector.

## 6. Truy vết SRS

| SRS AC | Test/kiểm chứng thiết kế |
| --- | --- |
| AC01–AC03 | Identity/session adapter, API operation guards và notification auth; provider cụ thể còn chờ chọn. |
| AC04–AC08 | T23–T26, tìm kiếm và bộ chất lượng/citation/thiếu căn cứ. |
| AC09–AC11 | T01–T10, config bootstrap/AUTO, no-overlap và snapshot. |
| AC12 | T11–T14, chunk-ready và validation. |
| AC13 | T15–T18, T26, error/quota. |
| AC14–AC15 | T14–T21, completion → Kafka → backend/UI. |
| AC16–AC17 | T22–T24, metadata/ACL/xóa/node/tool/source. |
| AC18 | Manual retry/state API theo 02/04, không crash recovery. |
| AC19 | Persistence sau job đã hoàn tất, volume đúng kho. |
| AC20 | T04, không xóa khi fetch thiếu. |
| AC21 | T19, batch/no-change/metadata/xóa và whole-run completion. |

## 7. AI evaluation và số đo

- Theo SRS: bộ câu hỏi có vai trò/phạm vi, snapshot và đáp án/đoạn chuẩn.
- Chia pilot/held-out trước đánh giá.
- Đo retrieval hit/recall theo evidence, độ đúng/đủ, grounding/citation support và thiếu dữ liệu.
- Không dùng LLM tự chấm duy nhất hoặc điều chỉnh tham số theo held-out.

- Đo latency capture/preparation/embedding/write/notification và online RAG.
- Model/profile/token counts khi provider trả, RAM của cả stack và concurrency.
- Không tự coi 32 GB là đủ cho mọi batch, không tuyên bố hạn mức hiện tại của Cloudflare chưa kiểm tra.
- Ngưỡng chất lượng/tải/timeout/chunk budget còn cần chốt theo pilot, không có số đo giả trong LLD.

- Minh chứng kiểm thử ghi expected/actual, định danh job/document và kết quả; tổng hợp tại [báo cáo tiến độ](../progress/README.md).
