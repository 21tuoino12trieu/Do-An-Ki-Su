# Bản đồ mã nguồn Beeflow

| Tệp trong bản tách | Các lớp | Nguồn gốc |
| --- | --- | --- |
| [configs/edge_config.py](src/beeflow/configs/edge_config.py) | EdgeConfig | [source](../../beeflow/beeflow/beeflow/configs/edge_config.py) |
| [configs/graph_config.py](src/beeflow/configs/graph_config.py) | GraphNodeConfig | [source](../../beeflow/beeflow/beeflow/configs/graph_config.py) |
| [configs/node_config.py](src/beeflow/configs/node_config.py) | Reference, NodeConfig | [source](../../beeflow/beeflow/beeflow/configs/node_config.py) |
| [nodes/base_node.py](src/beeflow/nodes/base_node.py) | BaseNode, DummyNode | [source](../../beeflow/beeflow/beeflow/nodes/base_node.py) |
| [nodes/flow/branch_node.py](src/beeflow/nodes/flow/branch_node.py) | BranchNodeConfig, BranchNode | [source](../../beeflow/beeflow/beeflow/nodes/flow/branch_node.py) |
| [nodes/flow/for_loop_node.py](src/beeflow/nodes/flow/for_loop_node.py) | ForLoopNode | [source](../../beeflow/beeflow/beeflow/nodes/flow/for_loop_node.py) |
| [nodes/flow/while_loop_node.py](src/beeflow/nodes/flow/while_loop_node.py) | WhileLoopNode | [source](../../beeflow/beeflow/beeflow/nodes/flow/while_loop_node.py) |
| [nodes/graph/graph_node.py](src/beeflow/nodes/graph/graph_node.py) | GraphNode | [source](../../beeflow/beeflow/beeflow/nodes/graph/graph_node.py) |
| [nodes/node_factory.py](src/beeflow/nodes/node_factory.py) | NodeFactory | [source](../../beeflow/beeflow/beeflow/nodes/node_factory.py) |
| [nodes/primitives/ai/embedding_node.py](src/beeflow/nodes/primitives/ai/embedding_node.py) | EmbeddingNodeConfig, EmbeddingNode | [source](../../beeflow/beeflow/beeflow/nodes/primitives/ai/embedding_node.py) |
| [nodes/primitives/ai/llm_node.py](src/beeflow/nodes/primitives/ai/llm_node.py) | LLMNodeConfig, LLMNode | [source](../../beeflow/beeflow/beeflow/nodes/primitives/ai/llm_node.py) |
| [nodes/primitives/data/kafka_node.py](src/beeflow/nodes/primitives/data/kafka_node.py) | KafkaNodeConfig, KafkaNode | [source](../../beeflow/beeflow/beeflow/nodes/primitives/data/kafka_node.py) |
| [nodes/primitives/data/milvus_node.py](src/beeflow/nodes/primitives/data/milvus_node.py) | MilvusNodeConfig, MilvusNode | [source](../../beeflow/beeflow/beeflow/nodes/primitives/data/milvus_node.py) |
| [nodes/primitives/data/mongo_node.py](src/beeflow/nodes/primitives/data/mongo_node.py) | MongoNodeConfig, MongoNode | [source](../../beeflow/beeflow/beeflow/nodes/primitives/data/mongo_node.py) |
| [nodes/primitives/data/s3_node.py](src/beeflow/nodes/primitives/data/s3_node.py) | S3NodeConfig, S3Node | [source](../../beeflow/beeflow/beeflow/nodes/primitives/data/s3_node.py) |
| [nodes/primitives/data_node.py](src/beeflow/nodes/primitives/data_node.py) | DataNode | [source](../../beeflow/beeflow/beeflow/nodes/primitives/data_node.py) |
| [nodes/primitives/transform/code_node.py](src/beeflow/nodes/primitives/transform/code_node.py) | CodeNodeConfig, CodeNode | [source](../../beeflow/beeflow/beeflow/nodes/primitives/transform/code_node.py) |
| [nodes/primitives/transform/parser_node.py](src/beeflow/nodes/primitives/transform/parser_node.py) | ParserNodeConfig, ExtractField, ParserNode | [source](../../beeflow/beeflow/beeflow/nodes/primitives/transform/parser_node.py) |
| [nodes/primitives/transform/prompt_node.py](src/beeflow/nodes/primitives/transform/prompt_node.py) | VariableExtractor, OptimizedMessageFormatter, PrecompiledMessageBuilder, PromptNodeConfig, PromptNode | [source](../../beeflow/beeflow/beeflow/nodes/primitives/transform/prompt_node.py) |
| [nodes/templates/basic_chain_node.py](src/beeflow/nodes/templates/basic_chain_node.py) | BasicChainNode | [source](../../beeflow/beeflow/beeflow/nodes/templates/basic_chain_node.py) |
| [nodes/templates/retriever_node_v2.py](src/beeflow/nodes/templates/retriever_node_v2.py) | RetrieverNodeConfig, RetrieverNode | [source](../../beeflow/beeflow/beeflow/nodes/templates/retriever_node_v2.py) |
| [states/state_manager.py](src/beeflow/states/state_manager.py) | StateRegistry | [source](../../beeflow/beeflow/beeflow/states/state_manager.py) |
| [states/state_value.py](src/beeflow/states/state_value.py) | VariableCell | [source](../../beeflow/beeflow/beeflow/states/state_value.py) |
| [states/workflow_indexer.py](src/beeflow/states/workflow_indexer.py) | WorkflowIndexer | [source](../../beeflow/beeflow/beeflow/states/workflow_indexer.py) |
| [states/workflow_state.py](src/beeflow/states/workflow_state.py) | WorkflowState | [source](../../beeflow/beeflow/beeflow/states/workflow_state.py) |
| [utils/bimap.py](src/beeflow/utils/bimap.py) | BiMapReverse, BiMap | [source](../../beeflow/beeflow/beeflow/utils/bimap.py) |
| [utils/context.py](src/beeflow/utils/context.py) | ? | [source](../../beeflow/beeflow/beeflow/utils/context.py) |
| [utils/streaming.py](src/beeflow/utils/streaming.py) | TokenStreamingService | [source](../../beeflow/beeflow/beeflow/utils/streaming.py) |
| [workflow.py](src/beeflow/workflow.py) | WorkflowEngine | [source](../../beeflow/beeflow/beeflow/workflow.py) |
