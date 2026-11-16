from aenum import StrEnum, extend_enum

class NodeType(StrEnum):
    # core nodes
    LLM = "llm"
    EMBEDDING = "embedding"
    RERANK = "rerank"
    # controller nodes
    BRANCH = "branch"
    FOR = "for"
    WHILE = "while"
    MAP_REDUCE = "map_reduce"
    HUMAN = "human"
    # processings
    CODE = "code"
    PARSER = "parser"
    PROMPT = "prompt"
    # storage
    MILVUS = "milvus"
    MONGO = "mongo"
    # others
    GRAPH = "graph"
    DEFAULT = "default"


def add_node_type(key: str):
    extend_enum(NodeType, key.upper(), key)


add_node_type("retriever")

print(NodeType.RETRIEVER)