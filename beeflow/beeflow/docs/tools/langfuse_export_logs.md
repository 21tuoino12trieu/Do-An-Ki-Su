# Langfuse Log Exporter

Công cụ CLI để fetch logs từ Langfuse và export ra JSON hoặc XLSX.

## Cấu hình

Tạo file `.env` trong thư mục `beeflow-tools/`:

```env
LANGFUSE_PUBLIC_KEY=your_public_key
LANGFUSE_SECRET_KEY=your_secret_key
LANGFUSE_BASE_URL=https://your-langfuse-instance.com
```

## Cách sử dụng

### Fetch logs theo khoảng thời gian

```bash
python beeflow_log_langfuse.py --start 2026-04-01T00:00:00 --end 2026-04-07T23:59:59
```

### Fetch logs theo tên trace

```bash
python beeflow_log_langfuse.py --name "chat-completion" --start 2026-04-01T00:00:00 --end 2026-04-07T23:59:59
```

### Fetch single trace

```bash
python beeflow_log_langfuse.py --trace-id trace_id_here
```

### Export ra XLSX

```bash
python beeflow_log_langfuse.py --start 2026-04-01T00:00:00 --end 2026-04-07T23:59:59 --format xlsx --output logs
```

### Giới hạn số trang

```bash
python beeflow_log_langfuse.py --start 2026-04-01T00:00:00 --end 2026-04-07T23:59:59 --max-pages 5
```

## Options

| Flag | Mô tả | Default |
|------|-------|---------|
| `--name` | Lọc theo trace name | - |
| `--start` | Thời gian bắt đầu (ISO format) | required |
| `--end` | Thời gian kết thúc (ISO format) | required |
| `--limit` | Số lượng traces mỗi page | 100 |
| `--max-pages` | Giới hạn số pages | all |
| `--trace-id` | Fetch một trace cụ thể | - |
| `--output` | Đường dẫn output (không có extension) | stdout |
| `--format` | Định dạng output: `json` hoặc `xlsx` | json |

## Output Fields

| Field | Mô tả |
|-------|-------|
| `Tên` | Trace name |
| `Thời gian` | Timestamp (dd/mm/YYYY HH:MM:SS, +7 hours) |
| `Người dùng` | Username từ input |
| `Câu hỏi` | Content của message cuối trong input.messages |
| `Phản hồi` | Content của output từ observation có startTime lớn nhất |
