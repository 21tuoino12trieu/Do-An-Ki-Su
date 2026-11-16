from dataclasses import dataclass
from typing import Any


VECTOR_DIM = 1024


@dataclass(frozen=True)
class CollectionPair:
    chunk: str
    node: str


def build_bot_collection_names(bot_id: str) -> CollectionPair:
    if not bot_id.startswith("bot"):
        bot_id = f"bot_{bot_id}"
    base = bot_id.replace("-", "_")
    return CollectionPair(chunk=f"{base}_chunk", node=f"{base}_node")


def build_hybrid_schema(is_chunk: bool) -> dict[str, Any]:
    from pymilvus import DataType, Function, FunctionType, MilvusClient

    primary_key = "chunk_id" if is_chunk else "node_id"
    analyzer_params = {"tokenizer": "standard", "filter": ["lowercase"]}

    schema = MilvusClient.create_schema()
    schema.add_field(
        field_name=primary_key,
        datatype=DataType.VARCHAR,
        is_primary=True,
        auto_id=False,
        max_length=65535,
    )
    schema.add_field(
        field_name="content",
        datatype=DataType.VARCHAR,
        max_length=65535,
        analyzer_params=analyzer_params,
        enable_match=True,
        enable_analyzer=True,
    )
    schema.add_field(
        field_name="sparse_vector",
        datatype=DataType.SPARSE_FLOAT_VECTOR,
    )
    schema.add_field(
        field_name="vector",
        datatype=DataType.FLOAT_VECTOR,
        dim=VECTOR_DIM,
    )
    schema.add_field(
        field_name="topic",
        datatype=DataType.VARCHAR,
        is_partition_key=True,
        max_length=65535,
    )
    schema.add_field(
        field_name="type",
        datatype=DataType.VARCHAR,
        max_length=65535,
    )
    schema.add_function(
        Function(
            name="bm25",
            function_type=FunctionType.BM25,
            input_field_names=["content"],
            output_field_names="sparse_vector",
        )
    )

    index_params = MilvusClient.prepare_index_params()
    index_params.add_index(
        field_name="vector",
        index_type="IVF_FLAT",
        metric_type="COSINE",
    )
    index_params.add_index(
        field_name="sparse_vector",
        index_type="SPARSE_INVERTED_INDEX",
        metric_type="BM25",
    )
    return {"schema": schema, "index_params": index_params}


def create_hybrid_collection(
    client: Any,
    collection_name: str,
    *,
    is_chunk: bool,
) -> None:
    config = build_hybrid_schema(is_chunk=is_chunk)
    client.create_collection(
        collection_name=collection_name,
        schema=config["schema"],
        index_params=config["index_params"],
        consistency_level="Bounded",
        num_shards=1,
    )


def create_bot_collections(bot_id: str) -> dict[str, str]:
    from beegen.registry.resource_hub import ResourceHub
    from pymilvus import MilvusClient

    config = ResourceHub.self().milvus("chatbot-libra").config
    client = MilvusClient(
        uri=config.uri,
        user=config.username,
        password=config.password,
        db_name=config.db_name,
    )
    names = build_bot_collection_names(bot_id)

    try:
        create_hybrid_collection(client, names.chunk, is_chunk=True)
        create_hybrid_collection(client, names.node, is_chunk=False)
    finally:
        client.close()

    return {
        "chunk_collection_name": names.chunk,
        "node_collection_name": names.node,
    }
