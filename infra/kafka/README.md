# Kafka local và Offset Explorer

## Cấu hình

- Image chính thức `apache/kafka:4.1.2`, một broker kiêm controller chạy KRaft, không cần ZooKeeper.
- Container `doan-kafka`; heap tối đa 1 GB, giới hạn RAM container 2 GB.
- Named volume `doan-kafka_kafka-data` lưu log sự kiện, metadata KRaft và consumer offsets.
- Retention mặc định 7 ngày, không bật tự tạo topic. Replication factor 1 phù hợp đồ án local, chưa có dự phòng khi mất volume/máy.
- Chỉ mở cổng Windows trên loopback; PLAINTEXT, không có SASL/TLS cho cấu hình local.

| Nơi chạy client | Bootstrap servers |
|---|---|
| Windows, Python, Offset Explorer | `127.0.0.1:9092` |
| Container cùng network `doan-backend` | `kafka:29092` |

Airflow sẽ tham gia network `doan-backend` với cấu hình network external khi tích hợp. Khi dừng Kafka để bảo trì, nên dùng `stop` để giữ network dùng chung. Không đổi `CLUSTER_ID` khi tái sử dụng volume đã format.

## Bật/tắt từ thư mục gốc đồ án

```powershell
docker compose -f infra/kafka/compose.yaml up -d
docker compose -f infra/kafka/compose.yaml ps -a
docker compose -f infra/kafka/compose.yaml logs --tail 100 kafka
docker compose -f infra/kafka/compose.yaml stop
```

Chờ `kafka` healthy. Service `volume-init` kết thúc `Exited (0)` là bình thường.
Nếu `docker` chưa có trong PATH, dùng đường dẫn Docker Desktop:

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" compose -f infra/kafka/compose.yaml ps -a
```

`stop` và `down` giữ volume. Không dùng `down -v` trong vận hành thông thường vì sẽ xóa cả sự kiện và offsets.

## Kết nối Offset Explorer trên Windows

1. Mở Offset Explorer, chọn **Add Cluster** (thêm kết nối).
2. Đặt tên `doan-local-kafka`.
3. Điền **Bootstrap Servers**: `127.0.0.1:9092` (thường nằm trong tab Advanced, tùy phiên bản giao diện).
4. Chọn Security **PLAINTEXT**, không SASL, không SSL; nếu phải chọn Kafka version, chọn 4.1 hoặc phiên bản 4.x tương ứng được ứng dụng hỗ trợ.
5. Không điền ZooKeeper: cluster này dùng KRaft. Nếu ứng dụng bắt buộc ZooKeeper, cần bản Offset Explorer hỗ trợ kết nối qua bootstrap servers.
6. Nhấn **Test**, rồi **Add/Connect**.
7. Xem topic `doan.infra.smoke.v1`, mở partition và đọc message; chọn hiển thị Key/Value dạng UTF-8/String để thấy JSON tiếng Việt. Nếu chưa có message mới, đọc từ đầu partition thay vì chỉ đọc từ cuối.

Offset Explorer là GUI client; đóng nó không dừng Kafka. Bước setup này chưa cài hoặc thao tác trực tiếp ứng dụng Offset Explorer.

## Kiểm thử Python

Trong môi trường Conda `namcuong` đã có `kafka-python==2.2.3`:

Script dùng protocol baseline `(2, 6, 0)` của client hiện có và kết nối IPv4 rõ ràng để tránh `localhost` được phân giải thành `::1` trong khi cổng chỉ bind IPv4. Kafka server vẫn chạy phiên bản 4.1.2.

```powershell
python test_kafka.py
```

Test tạo topic demo với 3 partition, replication factor 1; gửi JSON giả lập với key `DEMO-0001`, đợi broker xác nhận (`acks=all`), rồi đọc đúng partition/offset và so sánh toàn bộ key/nội dung. Sau khi kiểm tra thành công mới commit offset kế tiếp; test xác nhận group lưu đúng offset đó. Topic mới có retention 7 ngày; test không sửa cấu hình topic đã tồn tại.

Mỗi lần chạy gửi thêm một message và tạo group kiểm thử mới; dữ liệu giữ lại để xem trên Offset Explorer. Manifest lần gần nhất lưu tại `tests/output/kafka_smoke_manifest.json`, không chứa credential.

Kiểm tra dữ liệu và committed offset còn sau khi tạo lại container:

```powershell
docker compose -f infra/kafka/compose.yaml down
docker compose -f infra/kafka/compose.yaml up -d
# Chờ Kafka healthy:
python test_kafka.py --read-only
```

Chế độ `--read-only` không gửi message hoặc commit offset, chỉ đọc chính xác message cũ và kiểm tra committed offset đã lưu. Sau thời gian retention, message có thể bị xóa và cần chạy lại test chế độ ghi.

Topic demo không phải hợp đồng sự kiện nghiệp vụ Confluence. Đã đăng ký resource kafka:knowledge trong ResourceHub (xem ../../docs/resource-keys.md), chưa kiểm thử KafkaNode, chưa dựng Airflow hoặc xử lý retry/DLQ/idempotency ở cấp ứng dụng. `acks=all` trên một broker không tạo thêm bản sao dữ liệu.

## Kết quả kiểm tra ngày 03/11/2026

- Kafka đã khởi động thành công, healthcheck dùng listener nội bộ.
- Test Python từ Windows gửi và đọc đúng JSON/key/partition/offset, commit đúng offset kế tiếp.
- Sau `down`/`up -d`, `--read-only` vẫn đọc được message cũ và committed offset cũ, không gửi lại message.
- CLI qua `kafka:29092` xác nhận topic có đủ 3 partition với leader/ISR hợp lệ.
- Chưa kiểm tra kết nối trực tiếp từ ứng dụng Offset Explorer.

Tham khảo: [Apache Kafka Docker](https://kafka.apache.org/41/getting-started/docker/), [ví dụ listeners chính thức](https://github.com/apache/kafka/blob/trunk/docker/examples/docker-compose-files/cluster/combined/plaintext/docker-compose.yml), [Offset Explorer — kết nối](https://www.kafkatool.com/documentation/connecting.html).
