# MinIO dành cho tài liệu

Container `doan-documents-minio` chạy riêng với MinIO nội bộ của Milvus. Volume `doan-documents_documents-data` lưu bền dữ liệu; không cần chạy Milvus để sử dụng MinIO này.

## Mở giao diện

- Console: <http://localhost:9001>.
- S3 endpoint từ Python trên Windows: `http://127.0.0.1:9000`.
- Tài khoản `doanadmin`; mật khẩu ngẫu nhiên đã lưu trong [`.env`](.env). Mở file này trên máy để xem, không đưa vào Git. File mẫu [`.env.example`](.env.example) chỉ dùng làm hướng dẫn.
- Chỉ mở cổng loopback. Test hiện dùng tài khoản root cho setup local; khi nối ingestion cần tạo user/policy giới hạn theo bucket.

## Bật/tắt

Từ thư mục gốc đồ án:

```powershell
docker compose -f infra/minio/compose.yaml up -d
docker compose -f infra/minio/compose.yaml ps
docker compose -f infra/minio/compose.yaml stop
```

Nếu Docker chưa có trong PATH, thay `docker` bằng:

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" compose -f infra/minio/compose.yaml ps
```

Lần setup này dùng `milvusdb/minio:RELEASE.2024-12-18T13-15-44Z`, image mirror do Milvus cung cấp trong Compose chính thức, vì tải cùng tag từ Docker Hub/Quay của MinIO trả lỗi truy cập. Đây là bản MinIO cũ cho thử nghiệm local, không phải AIStor. Không tự đổi tag để tránh thay đổi hành vi. Tham khảo [Compose Milvus 3.0.3](https://github.com/milvus-io/milvus/releases/download/v3.0.3/milvus-standalone-docker-compose.yaml) và [MinIO Docker Quickstart của phiên bản này](https://github.com/minio/minio/blob/RELEASE.2024-12-18T13-15-44Z/docs/docker/README.md).

## Kiểm thử

Trong Conda `namcuong` đã có Boto3 và BeautifulSoup:

```powershell
python test_minio.py
```

Test thực hiện:

- Tạo bucket `knowledge-raw` và `knowledge-processed` nếu chưa có; bucket mới không có policy public.
- Bật versioning ở cả hai bucket.
- Dùng HTML giả lập trong `tests/fixtures/beedoc_bank_sample.html`, chuyển Markdown trực tiếp qua converter Beedoc (không chạy workflow ở test này).
- Ghi hai phiên bản HTML cùng key và một Markdown trong prefix `smoke/<UUID>/`.
- Đọc lại từng `VersionId`, kiểm tra SHA-256, Content-Type và metadata; xác nhận danh sách version HTML.
- Ghi manifest không chứa credential vào `tests/output/minio_smoke_manifest.json` để kiểm tra lại sau khi restart.

Kiểm tra lưu bền, không ghi lại dữ liệu:

```powershell
docker compose -f infra/minio/compose.yaml down
docker compose -f infra/minio/compose.yaml up -d
# Đợi healthy:
python test_minio.py --read-only
```

Mỗi lần chạy chế độ ghi tạo một prefix mới và giữ object để bạn xem. Manifest chỉ trỏ lần chạy gần nhất. `down` giữ volume; không dùng `down -v` vì sẽ xóa dữ liệu. Versioning chưa có lifecycle dọn dẹp nên dữ liệu các lần thử tích lũy.

## Ranh giới bước này

Đã kiểm tra ngày 03/11/2026: ghi/đọc từng version và checksum đều đạt; sau `down`/`up -d`, test `--read-only` vẫn đạt; Console trả HTTP 200.

- MinIO `VersionId` là phiên bản lưu trữ; không thay thế `page_id` và `version.number` của Confluence.
- Prefix `smoke/` chỉ dành cho kiểm thử, chưa phải hợp đồng object key của pipeline.
- Đã đăng ký S3 resource trong ResourceHub: s3:knowledge-raw và s3:knowledge-processed (xem ../../docs/resource-keys.md). Chưa ghi metadata tài liệu vào MongoDB, chưa nối Confluence thực tế.
- Chưa kiểm thử phân quyền user ingestion, mất kết nối hoặc phục hồi backup.
