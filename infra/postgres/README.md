# PostgreSQL local cho ingestion

Container riêng với PostgreSQL của Airflow. Ngày dựng: 08/11/2026.

| Thuộc tính | Giá trị |
| --- | --- |
| Container | `doan-ingestion-postgres` |
| Image | `postgres:16.11-alpine` |
| Host từ Windows/Conda | `127.0.0.1` |
| Port | `5432` — chỉ bind loopback |
| Database | `ingestion` |
| Username | `ingestion` |
| Password | `POSTGRES_PASSWORD` trong `.env` tại thư mục này; đã gitignore |
| Volume | `doan-ingestion_postgres-data` |

Dùng các thông tin trên trong pgAdmin/DBeaver hoặc SQL adapter. Container khác cần cấu hình mạng Docker phù hợp; `localhost` trong container không trỏ tới server này. Các Compose project hiện không tự dùng chung network/DNS.

## Vận hành từ thư mục gốc workspace

```powershell
docker compose -f infra/postgres/compose.yaml up -d --wait
docker compose -f infra/postgres/compose.yaml ps
docker compose -f infra/postgres/compose.yaml logs --tail 50 postgres
docker compose -f infra/postgres/compose.yaml stop
```

Không dùng `down -v` nếu muốn giữ dữ liệu. Volume giữ dữ liệu khi restart/tạo lại container nhưng không thay thế backup. Biến password chỉ khởi tạo tài khoản trên volume mới; sửa `.env` không tự đổi mật khẩu trong database đã có. Tài khoản hiện tại là tài khoản khởi tạo local.

## Schema

- `knowledge_base.documents`: snapshot trang để đối soát content/hash/version và metadata; unique `(bot_id,page_id)`.
- `knowledge_base.sync_jobs`: theo dõi lần chạy ingestion hiện có, khác metadata Airflow; không thêm Mongo `sync_runs`.
- `knowledge_base.sp_sync_confluence_page`: procedure 11 tham số tương ứng caller AUTO/PARTIAL, upsert snapshot và tính MD5.

Repository không có DDL/procedure gốc. [001-knowledge-base.sql](init/001-knowledge-base.sql) được viết mới theo các câu SQL trong `confluence_workflow`; đây là bản tương thích local, không phải bản sao schema production. Chưa chứng minh logic tương đương procedure gốc, chưa giữ lịch sử mọi version hoặc chống phiên bản cũ ghi đè. SQL không tự ghi Mongo/Milvus hay tạo embedding.

Init chỉ chạy khi volume trống. Sửa file SQL không tự migration database hiện có; cần migration tường minh sau này.

## Kiểm tra

```powershell
docker cp infra/postgres/smoke.sql doan-ingestion-postgres:/tmp/ingestion-smoke.sql
docker exec doan-ingestion-postgres psql -U ingestion -d ingestion -v ON_ERROR_STOP=1 -f /tmp/ingestion-smoke.sql
```

Kiểm tra procedure insert/update, content/hash/version, giữ một record cho cùng bot/page và insert sync job; rollback dữ liệu thử (identity sequence vẫn có thể tăng). Chưa phải test Confluence/Mongo/Milvus hoặc toàn pipeline.

Chưa đăng ký/ghi đè resource SQL `anapp` trong MongoDB và chưa đổi workflow sang local. Môi trường Conda `namcuong` hiện chưa có `psycopg`/`psycopg2`; bước nối ứng dụng phải kiểm tra adapter/dependency và SQL resource, sau đó test SQLNode riêng. Không cài thêm thư viện trong đợt dựng hạ tầng này.
