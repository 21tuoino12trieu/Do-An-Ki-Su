# Resource key cho hạ tầng local

Cấu hình được lưu trong MongoDB Atlas `cuong.beegen_resource_configs`. Các key sau dành cho Beeflow chạy trên Windows, không dùng trực tiếp địa chỉ loopback này từ container.

| Document `_id` | Config | Cách lấy qua ResourceHub | Mục đích |
|---|---|---|---|
| `mongo:knowledge` | MongoConfig | `hub.mongo("knowledge")` | Metadata và trạng thái |
| `redis:aicenter-chatbot` | RedisConfig | `hub.redis("aicenter-chatbot")` | Stream service hiện tại |
| `langfuse:beegen` | LangfuseConfig | `hub.langfuse("beegen")` | Trace workflow |
| `milvus:knowledge` | MilvusConfig | `hub.milvus("knowledge")` | Vector trên Milvus local |
| `kafka:knowledge` | KafkaConfig | `hub.kafka("knowledge")` | Kafka `127.0.0.1:9092` |
| `s3:knowledge-raw` | S3Config | `hub.s3("knowledge-raw")` | Bucket HTML gốc trên MinIO `127.0.0.1:9000` |
| `s3:knowledge-processed` | S3Config | `hub.s3("knowledge-processed")` | Bucket Markdown trên cùng MinIO |

Node dùng phần sau dấu `:` làm `resource_key`, ví dụ KafkaNode dùng `knowledge`, S3Node dùng `knowledge-raw` hoặc `knowledge-processed`. Hai resource S3 cố định bucket vì engine ưu tiên bucket trong config. Không tạo key `minio:*`: MinIO dùng giao thức S3 nên được đăng ký dưới `s3:*`.

Kafka config dùng PLAINTEXT, `acks=all`, `auto_offset_reset=earliest`, `enable_auto_commit=False`, group `doan-knowledge-ingestion`. Group dùng chung chỉ dành cho các consumer cùng vai trò xử lý; pipeline khác cần config/group riêng. Test đăng ký chỉ truy vấn metadata, không tiêu thụ sự kiện của group này.

S3 config hiện dùng tài khoản setup local đã có trong `infra/minio/.env`. Khi nối ingestion thực tế, nên thay bằng tài khoản chỉ được phép truy cập các bucket cần thiết. MongoDB config có chứa thông tin truy cập: không xuất toàn bộ document hoặc đưa vào Git/log.

Airflow được cấu hình bằng Compose, secret cục bộ và PostgreSQL riêng; hiện không có AirflowConfig/factory trong ResourceHub. Attu và Offset Explorer là giao diện quản trị. PostgreSQL/etcd/MinIO nội bộ của Milvus cũng không cần key cho các node của đồ án.

## Kiểm tra hoặc đăng ký lại

```powershell
python test_infra_resources.py
# Chỉ thêm config còn thiếu, không ghi đè config khác hiện có:
python test_infra_resources.py --register
```

Script kiểm tra ba key Kafka/S3, kết nối S3 và versioning hai bucket, mở producer Kafka và kiểm tra metadata topic `doan.infra.smoke.v1`. Không gửi sự kiện, ghi object hoặc commit offset. Nếu topic/bucket demo chưa có thì chạy các test hạ tầng tương ứng trước.

Đã đăng ký và kiểm tra ngày 03/11/2026. Khi chuyển chương trình sang Docker, tạo cấu hình riêng với endpoint nội bộ phù hợp; riêng Airflow demo đang dùng `kafka:29092` trực tiếp và chưa gọi ResourceHub.
