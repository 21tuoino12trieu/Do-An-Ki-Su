# Milvus Standalone và Attu trên máy local

## Thành phần

- Milvus `3.0.3`: API vector tại `http://127.0.0.1:19530`.
- Attu `3.0.1`: giao diện tại <http://localhost:8000>.
- etcd `3.5.25`: metadata nội bộ Milvus.
- MinIO: object storage nội bộ Milvus, chưa phải nơi lưu HTML/Markdown của ingestion.
- Container khởi tạo quyền volume chạy một lần rồi kết thúc là bình thường.

Compose dựa trên [bản phát hành chính thức Milvus 3.0.3](https://github.com/milvus-io/milvus/releases/tag/v3.0.3), đổi bind mount thành named volume cho Docker Desktop/WSL2, thêm Attu và chỉ mở cổng trên loopback. Không cần GPU. Các cổng etcd/MinIO không mở ra Windows. Milvus local chưa bật xác thực; không dùng cấu hình này để triển khai công khai.

## Chạy từ thư mục gốc đồ án

```powershell
docker compose -f infra/milvus/compose.yaml up -d
docker compose -f infra/milvus/compose.yaml ps -a
```

Chờ `standalone` có trạng thái `healthy`. Attu khởi động sau Milvus.
Nếu `docker` chưa nằm trong PATH, dùng:

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" compose -f infra/milvus/compose.yaml ps -a
```

## Mở Attu

Truy cập <http://localhost:8000>. Kết nối `doan-local` được tạo sẵn bằng `MILVUS_ADDRESS=standalone:19530`, database `default`, không cần token. Attu chạy chế độ một người dùng (`ATTU_AUTH_MODE=none`) dành cho máy local, chỉ mở trên loopback. Python chạy trên Windows dùng `http://127.0.0.1:19530`.

## Kiểm thử

Trong Conda `namcuong` đã có PyMilvus 3.0.2:

```powershell
python test_milvus.py
```

Test tạo collection `doan_infra_smoke_v1`, schema cố định gồm `id`, `text`, vector 4 chiều; upsert 3 bản ghi giả lập, flush, query và kiểm tra top-1 bằng COSINE. Chạy lại dùng cùng ID nên không thêm trùng. Collection demo được giữ lại để xem trên Attu. Đây không phải collection RAG và không dùng embedding thực tế.

Kiểm tra dữ liệu tồn tại qua lần dừng/khởi động:

```powershell
docker compose -f infra/milvus/compose.yaml down
docker compose -f infra/milvus/compose.yaml up -d
# Chờ standalone healthy rồi chạy kiểm tra không ghi lại dữ liệu:
python test_milvus.py --read-only
```

## Lưu trữ và vận hành

- Named volumes: `doan-milvus_etcd-data`, `doan-milvus_minio-data`, `doan-milvus_milvus-data`.
- Volume `doan-milvus_attu-data` lưu kết nối và thiết lập Attu.
- `stop` hoặc `down` giữ volume; `down -v` xóa dữ liệu, không dùng trong thao tác thông thường.
- `restart: unless-stopped` giúp dịch vụ tự chạy lại khi Docker khởi động, trừ khi chủ động dừng.
- Kiểm tra sức khỏe: <http://127.0.0.1:9091/healthz>.
- Xem log: `docker compose -f infra/milvus/compose.yaml logs --tail 100 standalone`.
- Dừng để giải phóng RAM: `docker compose -f infra/milvus/compose.yaml stop`.
- Cần lưu cả ba volume nếu sao lưu; không chỉ lưu riêng volume Milvus.

## ResourceHub

Đã đăng ký resource `_id: milvus:knowledge`, `config_class: MilvusConfig` trong MongoDB Atlas `cuong.beegen_resource_configs`. Cấu hình trỏ đến `http://127.0.0.1:19530`, database Milvus `default`, không xác thực. ResourceHub trên Windows gọi `hub.milvus("knowledge")`; MilvusNode dùng `resource_key="knowledge"`.

```powershell
python test_milvus_resource.py
```

Script tải lại resource từ MongoDB và đọc ba bản ghi demo qua kết nối ResourceHub. Để tạo lại khi resource chưa có: thêm `--register`. Script không ghi đè cấu hình khác đã tồn tại. Các index/search params hiện dành cho kiểm thử FLAT/COSINE, chưa chốt collection RAG. Nếu ứng dụng chuyển vào Docker, cần resource riêng trỏ hostname Docker thay cho loopback Windows.

Bước tiếp theo: chọn model embedding và số chiều, thiết kế collection RAG và kiểm thử graph MilvusNode. Engine hiện dùng ORM API của PyMilvus 3.0.2 và phát cảnh báo deprecated; cần chuyển sang MilvusClient trước khi nâng PyMilvus lên 3.1.

### Test graph MilvusNode

```powershell
python test_milvusnode.py
```

Test hai graph thật `START → MilvusNode → END` với operation QUERY và SEARCH, resource `knowledge`. QUERY phải trả đủ id 1/2/3, SEARCH COSINE phải trả id 1 ở đầu với điểm gần 1. Không ghi dữ liệu vector. Cần MongoDB Atlas, Redis, Milvus và Langfuse đã cấu hình; workflow gửi dữ liệu giả lên Langfuse dưới tên `milvusnode-query-test` và `milvusnode-search-test`.

Đã chạy thành công ngày 03/11/2026. Test phát hiện và đã sửa lỗi `_search` bọc thừa `params` khi config chứa mapping đầy đủ; engine giờ chấp nhận cả config phẳng và config có `params`. Chưa kiểm thử các operation ghi hoặc retry của MilvusNode.

## Kết quả kiểm tra ngày 03/11/2026

- Docker Compose khởi động thành công, etcd/MinIO/Milvus healthy.
- PyMilvus 3.0.2 kết nối, upsert và đọc đủ 3 bản ghi; tìm kiếm COSINE trả đúng id 1 ở vị trí đầu.
- Đã thực hiện `down` rồi `up -d`; test `--read-only` vẫn đọc và tìm kiếm đúng, không nạp lại dữ liệu.
- Trang Attu trả HTTP 200. Chưa kiểm thử thao tác chỉnh sửa dữ liệu bằng giao diện Attu hoặc MilvusNode/ResourceHub.

Tham khảo: [cài Milvus bằng Compose](https://milvus.io/docs/install_standalone-docker-compose.md), [Attu](https://github.com/zilliztech/attu).
