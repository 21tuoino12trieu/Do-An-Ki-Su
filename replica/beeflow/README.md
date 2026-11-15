# Beeflow — mã nguồn được tách cho đồ án

- Kế thừa có chọn lọc từ [Beeflow gốc](../../beeflow/beeflow/beeflow/) theo [thiết kế 15 node và core workflow](../../docs/design/modules/beeflow.md).
- Giữ các lớp, cơ chế khai báo graph, cấu hình và state của mã nguồn gốc để đọc, đối chiếu và chỉnh sửa tiếp.
- Đã sao chép đầy đủ package `beegen` đi kèm: 139 tệp Python nguyên vẹn, gồm schema operation, engine, registry và các lớp hỗ trợ.
- Trạng thái hiện tại: **đã tách mã nguồn; chưa hoàn thành tách phụ thuộc và chưa kiểm chứng runtime**. Thư mục này chưa phải bản thư viện có thể thay thế Beeflow gốc ngay lập tức.

## Cấu trúc

```text
replica/beeflow/
├── README.md
├── SOURCE-MAP.md
├── MIGRATION.md
├── source-manifest.json
├── .gitignore
└── src/beeflow/
    ├── __init__.py
    ├── workflow.py
    ├── configs/
    │   ├── node_config.py
    │   ├── graph_config.py
    │   └── edge_config.py
    ├── states/
    │   ├── workflow_state.py
    │   ├── workflow_indexer.py
    │   ├── state_value.py
    │   └── state_manager.py
    ├── utils/
    │   ├── context.py
    │   ├── bimap.py
    │   └── streaming.py
    └── nodes/
        ├── __init__.py
        ├── base_node.py
        ├── node_factory.py
        ├── graph/graph_node.py
        ├── flow/
        │   ├── branch_node.py
        │   ├── for_loop_node.py
        │   └── while_loop_node.py
        ├── primitives/
        │   ├── data_node.py
        │   ├── data/
        │   │   ├── mongo_node.py
        │   │   ├── milvus_node.py
        │   │   ├── s3_node.py
        │   │   └── kafka_node.py
        │   ├── ai/
        │   │   ├── embedding_node.py
        │   │   └── llm_node.py
        │   └── transform/
        │       ├── code_node.py
        │       ├── prompt_node.py
        │       └── parser_node.py
        └── templates/
            ├── basic_chain_node.py
            └── retriever_node_v2.py
```

Song song với `src/beeflow/` là **`src/beegen/`**, giữ đầy đủ cấu trúc package gốc: `cache`, `configs`, `embeddings`, `event_streaming`, `interpreters`, `llms`, `loggings`, `mcp`, `memory`, `observations`, `parser`, `prompts`, `registry`, `reranks`, `storage`, `tools`, `utils`, `vectordb`, cùng `const.py` và `__init__.py`.

Tổng cộng có **179 tệp Python**: 40 tệp Beeflow được tách và 139 tệp Beegen được sao chép nguyên vẹn. [Bản đồ Beeflow](SOURCE-MAP.md) và [bản đồ Beegen](BEEGEN-SOURCE-MAP.md) liên kết từng tệp với nguồn gốc.

## Các tầng operation đã được bổ sung

| Node | Schema/operation trong Beegen | Engine thực thi trong Beegen |
| --- | --- | --- |
| MongoNode | [mongo_config.py](src/beegen/configs/storage/mongo_config.py) | [mongo_engine.py](src/beegen/storage/mongo/mongo_engine.py): CRUD, aggregate, index, transaction; engine đồng bộ/bất đồng bộ |
| MilvusNode | [milvus_config.py](src/beegen/configs/storage/vectordb/milvus_config.py) | [milvus_engine.py](src/beegen/vectordb/milvus_engine.py): search, insert/upsert, query/delete, quản lý collection/index/partition |
| S3Node | [s3_config.py](src/beegen/configs/storage/s3_config.py) | [s3_engine.py](src/beegen/storage/s3/s3_engine.py): read/write/delete/list_paths/upload_file/download_file |
| KafkaNode | [kafka_config.py](src/beegen/configs/event_streaming/kafka_config.py) | [kafka_engine.py](src/beegen/event_streaming/kafka_engine.py): produce/consume |

Các tầng embedding, LLM, parser, schema, logger và `ResourceHub` cũng đã được sao chép. Đây là toàn bộ cách thực thi hiện có trong Beegen gốc; việc có operation không xác nhận nó đã đáp ứng hợp đồng mới của đồ án, chẳng hạn session transaction, manual commit/ACK hay quota Cloudflare.

## Các lớp được giữ

| Nhóm | Thành phần |
| --- | --- |
| Core | `BaseNode`, `GraphNode`, `WorkflowEngine`, `WorkflowState` |
| Hỗ trợ core | `DummyNode`, các điểm `START`/`END`/`INPUT`/`OUTPUT`/`CONTINUE`, `NodeFactory`, `WorkflowIndexer`, `VariableCell`, `StateRegistry`, cấu hình node/graph/edge, context và `BiMap` |
| 6 node tích hợp | `MongoNode`, `MilvusNode`, `S3Node`, `KafkaNode`, `EmbeddingNode`, `LLMNode` |
| 9 node workflow/RAG | `CodeNode`, `DataNode`, `BranchNode`, `ForLoopNode`, `WhileLoopNode`, `PromptNode`, `ParserNode`, `RetrieverNode`, `BasicChainNode` |

Những cấu hình node được định nghĩa trong cùng tệp node cũng được giữ, không chỉ sao chép phần thân lớp chính.

## Điều chỉnh khi tách

- Bỏ các hàm ví dụ/thử nghiệm và khối chạy `__main__` trong các tệp được chọn; giữ phương thức lớp và các hàm hỗ trợ nghiệp vụ của node.
- Sửa import `BaseNode` của S3/Kafka về namespace `beeflow.nodes.base_node`.
- `nodes/__init__.py` chỉ xuất các thành phần được chọn và nạp lớp khi được truy cập; không import sẵn node ngoài phạm vi.
- `NodeFactory` chỉ giữ các ánh xạ cấu hình có tệp đích trong bản tách; `RetrieverNodeConfig` trỏ đến `retriever_node_v2`. Không phải cả 15 node đều có lớp cấu hình riêng hoặc được tạo bằng factory; một số giữ cách khởi tạo trực tiếp như bản gốc.
- `RetrieverNode` giữ nhánh dense retrieval, bỏ nhánh gọi `RerankNode`. Rerank mặc định tắt; yêu cầu rerank/hybrid/hierarchical bị từ chối rõ ràng. Các truy vấn Mongo và cấu trúc dữ liệu của retriever vẫn còn mang giả định của hệ thống cũ, cần thay ở bước tiếp theo.
- Không sửa mã nguồn trong thư mục Beeflow gốc.

[source-manifest.json](source-manifest.json) ghi đường dẫn nguồn, SHA-256 trước/sau và thay đổi của từng tệp. Khác biệt xuống dòng không được xem là thay đổi chức năng.

[beegen-source-manifest.json](beegen-source-manifest.json) ghi riêng 139 tệp Beegen với SHA-256. Các tệp Beegen được sao chép nguyên byte, kể cả các hàm ví dụ có sẵn; không áp dụng bước lược bỏ ví dụ như phần Beeflow đã tách trước đó.

## Phụ thuộc và giới hạn hiện tại

- `Beegen`, `ParamSet`, `YamlModel`, logger và `ResourceHub` đã có trong `src/beegen`. Chúng vẫn giữ các phụ thuộc bên ngoài và cách khởi tạo tài nguyên của mã gốc, chưa được tái cấu trúc theo thiết kế đồ án.
- Core còn dùng kiểu response OpenAI, Langfuse và tiện ích streaming. `utils/streaming.py` được giữ vì core đang import nó; việc giữ tệp này không bổ sung token streaming vào phạm vi đồ án.
- Streaming còn tạo service dùng Redis ở cấp module. Không coi việc import node hiện tại là đã độc lập khỏi Redis hoặc cấu hình dịch vụ.
- Các node AI chưa có adapter Cloudflare mới. Các node tích hợp chưa được xác nhận đáp ứng transaction, Kafka manual commit/ACK, quota và các điều kiện nhất quán của thiết kế.
- Hành vi xử lý lỗi, timeout, cancellation, nhánh và vòng lặp còn phải rà soát; việc đã sao chép lớp không có nghĩa đã đáp ứng tiêu chí nghiệm thu.
- Không sao chép tệp cấu hình kết nối, thông tin đăng nhập, môi trường ảo, mã build hoặc danh sách phụ thuộc tổng hợp của repo cũ.
- Chưa tạo lệnh cài đặt cho bản tách này, chưa cài dependency hoặc chạy các node với dịch vụ thật.
- Beegen được sao chép đầy đủ theo yêu cầu, nên có cả mã hỗ trợ SQL, MCP, memory, rerank và provider khác. Sự hiện diện của các module này không mở rộng danh sách 15 node hoặc phạm vi tính năng đồ án.

## Quan hệ với Beedoc

- Giữ namespace `beeflow` và các đường dẫn `workflow.py`, `nodes/base_node.py`, `nodes/primitives/transform/code_node.py` mà [Beedoc đã tách](../beedoc/README.md) sử dụng.
- Đây là cơ sở để kiểm chứng tương thích graph của `HtmlReader` và `HtmlRenderer` ở bước tiếp theo; chưa xác nhận chúng chạy thành công với bản Beeflow này.
- Xem [các bước chuyển đổi còn lại](MIGRATION.md) trước khi tích hợp runtime.

## Kiểm tra đã thực hiện

- Phân tích cú pháp cả 179 tệp Python bằng AST, không import hoặc thực thi mã nguồn. Một số chuỗi escape trong mã Beegen gốc phát cảnh báo nhưng không gây lỗi phân tích; bản sao giữ nguyên nguồn.
- Đối chiếu sự hiện diện của 15 lớp node và 4 lớp core với thiết kế.
- Kiểm tra các import module nội bộ và các tên node được import từ `beeflow.nodes`; kiểm tra đường dẫn trong bản đồ mã nguồn và hash của manifest.
- Đối chiếu 139 tệp Beegen với nguồn bằng SHA-256: trùng khớp. Không thiếu module trong các import tuyệt đối bắt đầu bằng `beeflow`/`beegen`; kiểm tra này chưa xác minh mọi symbol, import động hoặc nhánh chạy. [Báo cáo phụ thuộc](dependency-audit.json) liệt kê các import bên ngoài để rà tiếp.
- Chưa chạy kiểm thử runtime, graph, dịch vụ lưu trữ hoặc gọi Cloudflare. Các kết quả trên chỉ xác nhận tính đầy đủ của bản tách và cú pháp, không xác nhận hành vi thực thi.
