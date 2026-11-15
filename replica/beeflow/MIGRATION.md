# Các bước chuyển bản tách sang thư viện dùng cho đồ án

[Quay lại README](README.md) · [Thiết kế mục tiêu](../../docs/design/modules/beeflow.md)

Đây là danh sách phần còn phải làm, không phải mô tả chức năng đã hoàn thành.

Đã sao chép đầy đủ 139 tệp Beegen vào `src/beegen` theo yêu cầu. Các schema, operation và engine gốc hiện đã có mặt; các bước dưới đây tập trung vào điều chỉnh và kiểm chứng chúng theo thiết kế đồ án.

| Thứ tự | Phần cần xử lý | Điều kiện kiểm chứng |
| --- | --- | --- |
| 1 | Rà các kiểu dữ liệu/cấu hình dùng chung trong Beegen đã sao chép: `ParamSet`, `YamlModel`, schema exporter, logger, `ResourceHub` | Xác định phần được dùng trong đồ án và phần cần thay bằng interface/injection; không yêu cầu xóa các module nguồn vừa sao chép |
| 2 | Tách core khỏi streaming, Redis, Langfuse và kiểu chunk OpenAI; bỏ khởi tạo service ở lúc import | Import core/CodeNode không cần cấu hình hay kết nối dịch vụ ngoài |
| 3 | Sửa hợp đồng lỗi của `BaseNode.run` và engine | Lỗi không bị `return` trong `finally` che mất; bước phụ thuộc dừng và caller nhận lỗi |
| 4 | Kiểm chứng graph, binding, trạng thái riêng từng run, fan-in/nhánh skipped, timeout và cancellation | Chạy các graph mẫu thành công/lỗi có ý nghĩa; không rò state hoặc tiếp tục chạy bước sau lỗi |
| 5 | Kiểm chứng `HtmlReader`/`HtmlRenderer` trong Beedoc với core và `CodeNode` | Chạy tệp HTML thật qua engine; phân biệt rỗng hợp lệ với reader/node thất bại; giữ nguyên ảnh |
| 6 | Rà `ForLoopNode`, `WhileLoopNode`, `BranchNode`, `DataNode` | Giới hạn vòng lặp/concurrency, điều kiện dừng, mapping kết quả và default branch rõ ràng |
| 7 | Thay cách lấy client ở Mongo/Milvus/S3/Kafka bằng cấu hình/client được ứng dụng cung cấp | Cùng Mongo session khi transaction; MinIO key bất biến; Milvus filter/consistency; Kafka ACK và manual commit theo service |
| 8 | Bổ sung adapter Cloudflare cho `EmbeddingNode` và `LLMNode` | Tái sử dụng cổng quota chung; xác minh vector dimension/order; trả lỗi quota/timeout, không gọi provider thay thế |
| 9 | Thu gọn Prompt/Parser/BasicChain cho luồng non-streaming | Không tự sửa output bằng một lần gọi model ngầm; BasicChain gọi LLM đúng một lần trong lượt sinh đáp án |
| 10 | Đổi `RetrieverNode` sang schema Mongo/Milvus của đồ án và callback kiểm tra nguồn | Chỉ dùng build hợp lệ, giữ định danh nguồn, không tự quyết định policy; chat kiểm tra lại trước sinh/trả đáp án |
| 11 | Chốt metadata package và các nhóm phụ thuộc cần thiết | Cài/import độc lập, không kéo dịch vụ ngoài phạm vi; chạy kiểm thử tích hợp phù hợp từng node |

Các chi tiết còn từ mã gốc cần chú ý khi review:

- `WorkflowEngine` lấy Langfuse từ `ResourceHub` trong constructor.
- `BaseNode`, `GraphNode` và `LLMNode` còn tham chiếu `STREAM_SERVICE`.
- `TokenStreamingService` được khởi tạo ở cấp module với tài nguyên Redis của hệ thống cũ.
- `NodeFactory` vẫn có cơ chế đọc/tạo registry tùy chỉnh theo `CONFIG_ROOT`; cần thay bằng đăng ký tường minh hoặc cấu hình do ứng dụng cấp.
- `RetrieverNode` còn có các collection/khái niệm role, dialogue, bot của hệ thống cũ; tắt rerank chưa đủ để dùng với mô hình dữ liệu đồ án.
- Node và state trong RAM không thay thế job/lease/checkpoint/outbox bền vững của ứng dụng.
