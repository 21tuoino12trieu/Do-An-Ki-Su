"""Selected original node exports; imported on first access."""
from importlib import import_module

_EXPORTS = {'BaseNode': ('beeflow.nodes.base_node', 'BaseNode'), 'DummyNode': ('beeflow.nodes.base_node', 'DummyNode'), 'DataNode': ('beeflow.nodes.primitives.data_node', 'DataNode'), 'NodeConfig': ('beeflow.configs', 'NodeConfig'), 'GraphNodeConfig': ('beeflow.configs', 'GraphNodeConfig'), 'NodeType': ('beeflow.configs', 'NodeType'), 'BranchNode': ('beeflow.nodes.flow.branch_node', 'BranchNode'), 'BranchNodeConfig': ('beeflow.nodes.flow.branch_node', 'BranchNodeConfig'), 'ForLoopNode': ('beeflow.nodes.flow.for_loop_node', 'ForLoopNode'), 'WhileLoopNode': ('beeflow.nodes.flow.while_loop_node', 'WhileLoopNode'), 'GraphNode': ('beeflow.nodes.graph.graph_node', 'GraphNode'), 'EmbeddingNode': ('beeflow.nodes.primitives.ai.embedding_node', 'EmbeddingNode'), 'EmbeddingNodeConfig': ('beeflow.nodes.primitives.ai.embedding_node', 'EmbeddingNodeConfig'), 'LLMNode': ('beeflow.nodes.primitives.ai.llm_node', 'LLMNode'), 'LLMNodeConfig': ('beeflow.nodes.primitives.ai.llm_node', 'LLMNodeConfig'), 'MilvusNode': ('beeflow.nodes.primitives.data.milvus_node', 'MilvusNode'), 'MilvusNodeConfig': ('beeflow.nodes.primitives.data.milvus_node', 'MilvusNodeConfig'), 'MongoNode': ('beeflow.nodes.primitives.data.mongo_node', 'MongoNode'), 'MongoNodeConfig': ('beeflow.nodes.primitives.data.mongo_node', 'MongoNodeConfig'), 'S3Node': ('beeflow.nodes.primitives.data.s3_node', 'S3Node'), 'KafkaNode': ('beeflow.nodes.primitives.data.kafka_node', 'KafkaNode'), 'CodeNode': ('beeflow.nodes.primitives.transform.code_node', 'CodeNode'), 'CodeNodeConfig': ('beeflow.nodes.primitives.transform.code_node', 'CodeNodeConfig'), 'ParserNode': ('beeflow.nodes.primitives.transform.parser_node', 'ParserNode'), 'ParserNodeConfig': ('beeflow.nodes.primitives.transform.parser_node', 'ParserNodeConfig'), 'PromptNode': ('beeflow.nodes.primitives.transform.prompt_node', 'PromptNode'), 'PromptNodeConfig': ('beeflow.nodes.primitives.transform.prompt_node', 'PromptNodeConfig'), 'BasicChainNode': ('beeflow.nodes.templates.basic_chain_node', 'BasicChainNode'), 'RetrieverNode': ('beeflow.nodes.templates.retriever_node_v2', 'RetrieverNode'), 'RetrieverNodeConfig': ('beeflow.nodes.templates.retriever_node_v2', 'RetrieverNodeConfig'), 'START': ('beeflow.nodes.base_node', 'START'), 'END': ('beeflow.nodes.base_node', 'END'), 'CONTINUE': ('beeflow.nodes.base_node', 'CONTINUE'), 'INPUT': ('beeflow.nodes.base_node', 'INPUT'), 'OUTPUT': ('beeflow.nodes.base_node', 'OUTPUT')}

__all__ = list(_EXPORTS)

def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module, symbol = _EXPORTS[name]
    value = getattr(import_module(module), symbol)
    globals()[name] = value
    return value
