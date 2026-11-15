# Airflow local trên Docker Desktop

Không cài Airflow vào Conda/Windows. Image mở rộng từ `apache/airflow:3.3.2-python3.12`, bổ sung `kafka-python==2.2.3` lúc build, không cài thư viện mỗi lần container khởi động.

## Thành phần

- PostgreSQL 16 lưu metadata, lịch sử DAG/task, trạng thái và cấu hình Airflow; không thay MongoDB của đồ án.
- API server cung cấp giao diện tại <http://localhost:8080>, chỉ bind loopback.
- Scheduler dùng LocalExecutor, parallelism 2; task chạy trong scheduler container, không cần Celery/Redis bổ sung.
- DAG processor đọc DAG từ `infra/airflow/dags` trên Windows.
- Service `init` migrate database rồi kết thúc `Exited (0)` là bình thường.
- DAG bind mount read-only; thư mục mật khẩu cho phép ghi vì SimpleAuthManager cần mở file ở chế độ cập nhật. Volume `doan-airflow_postgres-data` lưu database; `doan-airflow_airflow-logs` lưu log dùng chung.

## Tài khoản

- Username: `admin`.
- Mật khẩu: xem giá trị `admin` trong [secrets/passwords.json](secrets/passwords.json) trên máy.
- SimpleAuthManager dành cho phát triển/thử nghiệm. Mật khẩu và `.env` đã nằm trong `.gitignore`; không gửi các file này lên Git.
- `.env` chứa mật khẩu PostgreSQL, Fernet key và JWT secret. Giữ nguyên chúng khi tái sử dụng volume; sao lưu cùng database khi cần khôi phục. Không in toàn bộ `docker compose config` vì có secret; dùng `config --quiet` để kiểm tra cú pháp.

## Bật/tắt

Kafka phải chạy trước để network `doan-backend` tồn tại:

```powershell
docker compose -f infra/kafka/compose.yaml up -d
docker compose -f infra/airflow/compose.yaml up -d --build
docker compose -f infra/airflow/compose.yaml ps -a
```

Airflow nối network `doan-backend` và dùng `kafka:29092`, không dùng localhost:9092 trong container.

Nếu Docker chưa có trong PATH:

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" compose -f infra/airflow/compose.yaml ps -a
```

Dừng giải phóng RAM:

```powershell
docker compose -f infra/airflow/compose.yaml stop
```

`down` giữ volume, `down -v` xóa database/log. Bật lại bằng `up -d`, không cần build nếu chưa đổi Dockerfile. Không thay secret chỉ để restart. PostgreSQL không mở cổng ra Windows.

## DAG thử Kafka

DAG `infra_kafka_smoke` có hai task:

```text
send_event → verify_event
```

- `send_event` tạo topic demo `doan.airflow.smoke.v1` nếu chưa có, gửi JSON giả lập và trả topic/partition/offset qua XCom.
- `verify_event` đọc đúng offset, xác nhận key và nội dung.
- Không gọi Confluence, LLM hoặc embedding; chưa tích hợp ResourceHub/KafkaNode.
- Khai báo cron `0 * * * *`: chạy ở đầu mỗi giờ, không phải 60 phút tính từ lúc container bật. `catchup=False`, max active runs 1, retry 1 sau 15 giây.
- DAG mặc định paused để không tự tạo sự kiện. Khi nối đồng bộ thật sẽ dùng DAG nghiệp vụ riêng.
- Event ID hiện ngẫu nhiên mỗi attempt; DAG demo chưa có idempotency cấp nghiệp vụ, retry có thể gửi thêm sự kiện.

## Kiểm tra qua giao diện

1. Mở <http://localhost:8080> và đăng nhập.
2. Tìm DAG `infra_kafka_smoke`.
3. Bật DAG nếu muốn chạy lịch, hoặc dùng file test bên dưới để chạy một lần và khôi phục trạng thái paused.
4. Xem lần chạy mới, graph và log hai task. Có thể xem message tại Offset Explorer, topic `doan.airflow.smoke.v1`.

## File test trên Windows

Trong Conda `namcuong`:

```powershell
python test_airflow.py
```

Script kiểm tra health thật trong JSON (không chỉ HTTP 200), đăng nhập API, tạm unpause DAG nếu cần, trigger một run, đợi tối đa 180 giây và kiểm tra đủ hai task success. Cuối cùng khôi phục paused nếu DAG ban đầu paused. Không in mật khẩu/JWT. Manifest run gần nhất ở `tests/output/airflow_smoke_manifest.json`.

```powershell
python test_airflow.py --read-only
```

Chế độ này chỉ xác nhận run đã lưu, không trigger run mới. Có thể dùng sau `down`/`up -d` để kiểm tra metadata vẫn còn. Chờ tất cả dịch vụ healthy và DAG được parse trước khi chạy.

Chẩn đoán:

```powershell
docker compose -f infra/airflow/compose.yaml logs --tail 100 scheduler dag-processor
docker compose -f infra/airflow/compose.yaml exec scheduler airflow dags list-import-errors
```

## Kết quả kiểm tra ngày 03/11/2026

- API server, scheduler, DAG processor và PostgreSQL đều healthy.
- Đăng nhập qua API thành công; DAG chạy qua scheduler/LocalExecutor thật, cả `send_event` và `verify_event` success.
- Test đã trả DAG về paused.
- Sau `down`/`up -d`, test `--read-only` vẫn xác nhận được run và hai task success từ database cũ.
- Chưa kiểm tra một lần chạy tự động theo đồng hồ mỗi giờ hoặc luồng đồng bộ Confluence thực tế.

Tham khảo: [Docker Compose Airflow 3.3.2](https://airflow.apache.org/docs/apache-airflow/3.3.2/howto/docker-compose/index.html), [Simple auth manager](https://airflow.apache.org/docs/apache-airflow/3.3.2/core-concepts/auth-manager/simple/index.html), [API token](https://airflow.apache.org/docs/apache-airflow/3.3.2/core-concepts/auth-manager/simple/token.html).
