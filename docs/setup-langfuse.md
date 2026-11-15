# Langfuse cho Beeflow local

- Môi trường Python: Conda `namcuong`, Python 3.12.
- Dịch vụ: Langfuse Cloud US, host `https://us.cloud.langfuse.com`.
- Cấu hình local: `config/langfuse.yaml`, gồm `host`, `public_key`, `secret_key`. File này được loại khỏi Git bằng `.gitignore` ở workspace.
- Resource trong MongoDB: `cuong.beegen_resource_configs`, khóa `langfuse:beegen`.
- SDK đã kiểm chứng: `langfuse==4.7.1`, OpenTelemetry SDK và HTTP exporter `1.40.0`, tương thích `logfire~=4.32.1` hiện có.

## Phần đã thay đổi

- Bản SDK v2 đi kèm repo được chuyển từ `beeflow/beeflow/langfuse` sang `beeflow/beeflow/_legacy/langfuse_sdk_v2`, giữ mã cũ để đối chiếu. Nhờ vậy Python sử dụng SDK chính thức cài trong môi trường Conda.
- `BeeLangfuse` chuyển tham số `host` của cấu hình sang `base_url` của SDK hiện tại.
- `langfuse_compat.py` giữ giao diện `trace → span/generation` mà Beeflow đang gọi, nhưng tạo observation bằng OpenTelemetry; không dùng legacy batch ingestion v2.
- Adapter giữ quan hệ cha–con, trace ID được suy ra ổn định từ request ID, thời gian thực thi gốc, input/output, metadata, mức lỗi và usage token.
- `WorkflowEngine.run()` đợi bước flush thay vì tạo task nền không được đợi. Cách này tránh mất trace khi chương trình ngắn kết thúc; đồng thời có thể tăng thời gian trả kết quả theo thời gian flush. Timeout hiện có của bước flush là 60 giây.
- Dependencies được ghi trong `beeflow/beeflow/requirements.txt` và `pyproject.toml`.

Phần replay timestamp sử dụng tracer và observation wrapper nội bộ của SDK. Vì vậy phiên bản SDK được ghim chính xác; khi nâng phiên bản phải chạy lại các ca kiểm tra adapter.

## Chạy kiểm tra

Từ thư mục gốc workspace trong môi trường `namcuong`:

```bat
python test_langfuse.py
```

Lệnh này xác thực, gửi một trace có root/child bằng dữ liệu giả lập và truy vấn lại observation từ Cloud. Không gọi LLM hoặc gửi tài liệu nghiệp vụ; không ghi đè resource trong MongoDB.

```bat
python test_langfuse.py --register
```

Thêm `--register` để đăng ký `langfuse:beegen` nếu chưa có. Nếu key đã tồn tại, script so sánh cấu hình và không ghi đè khi khác YAML. Resource đã được đăng ký trong lần setup này.

```bat
python test_langfuse_workflow.py
```

Lệnh này chạy graph Beeflow thật `START → CodeNode(add_one) → END`, xác nhận kết quả `result=2` và root/child observation trên Cloud. Cần MongoDB chứa các resource Redis/Langfuse, Redis local đang chạy và kết nối mạng tới Atlas/Langfuse.

```bat
python -m unittest discover -s tests -p test_langfuse_compat.py -v
python -m pip check
```

Ba ca unittest dùng exporter trong RAM, không gửi Cloud: kiểm tra hierarchy/timestamps/thuộc tính, generation usage không gọi model và thông tin lỗi. `pip check` sau setup trả `No broken requirements found.`

## Kiểm tra trên giao diện

- Mở project Langfuse → Tracing.
- Tìm `beeflow-langfuse-connection-test` hoặc `langfuse-setup-workflow`.
- Xem trace con `connection-check` hoặc `add_one`.
- Script in đường dẫn trực tiếp đến trace, không in key.

Đã xác nhận Cloud nhận trace kiểm tra và workflow thật. Chưa kiểm thử tracing cho mọi loại node, vòng lặp, fan-out hoặc lời gọi LLM thực tế.
