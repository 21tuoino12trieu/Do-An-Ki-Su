import asyncio
from typing import Dict, List, Any, Optional

from pymilvus import DataType

from beeflow.nodes.base_node import BaseNode, START, END, INPUT, OUTPUT
from beeflow.nodes.graph.graph_node import GraphNode
from beeflow.configs.node_config import NodeType
from beeflow.configs.graph_config import GraphNodeConfig
from beegen.tools.schema.param import ParamSet
from beegen.configs import MilvusOperation
from beeflow.nodes.primitives.data.sql_node import SQLNode
from beegen.configs.storage.sql_config import SQLOperation
from beegen.loggings import LOGGER

def format_sql(sql_result: List[Dict]) -> Dict[str, List[str]]:
    """
    Extract distinct values from an SQL query result.

    Args:
        sql_result: A list of row dictionaries returned by an SQL query. Each row
            is expected to have at least one column key.

    Returns:
        distinct_values: A dict containing a single key "distinct_values" whose
            value is a list of extracted values from the first column found in
            the first row. Returns an empty list if input is invalid or empty.
    """
    if not sql_result or not isinstance(sql_result, list):
        return {"distinct_values": []}
    if not sql_result[0]:
        return {"distinct_values": []}
    column_name = list(sql_result[0].keys())[0]
    return {"distinct_values": [row[column_name] for row in sql_result if column_name in row]}

def format_rerank_results(reranks: List[Dict], top_k: int) -> Dict[str, List[Dict]]:
    """
    Format the reranked results to the top K candidates.

    Args:
        reranks: A list of candidate dicts already sorted by score in descending order.
        top_k: The maximum number of top candidates to keep.

    Returns:
        top_candidates: A dict with key "top_candidates" containing the first
            `top_k` items from `reranks`.
    """
    return {"top_candidates": reranks[:top_k]}

def generate_collection_name(table: str) -> Dict[str, str]:
    """
    Generate a consistent Milvus collection name for a table/column pair.

    Args:
        table: The SQL table name (may include schema prefix like "schema.table").
        column: The SQL column name.

    Returns:
        collection_name: A dict with key "collection_name" using the pattern
            "fuzzy_{table}_{column}", lowercased and with dots replaced by "_".
    """
    collection_name = f"fuzzy_{table}".lower().replace(".", "_").replace(" ", "_")
    return {"collection_name": collection_name}

def generate_partition_name(column: str) -> Dict[str, str]:
    """
    Generate partition name from column name.
    Partition naming: column name, lowercase, replace special chars with underscores.
    """
    partition_name = column.lower().replace(".", "_").replace(" ", "_")
    return {"partition_name": partition_name, "partition_names": [partition_name]}

def prepare_milvus_insertion(distinct_values: List[str], embeddings: List[List[float]]) -> Dict[str, List[Dict]]:
    """
    Prepare entity payloads for Milvus insertion.

    Args:
        distinct_values: The list of string values to store (one per embedding).
        embeddings: The list of vector embeddings aligned by index with values.

    Returns:
        data: A dict with key "entities", where each entity is a dict of
            {"value": <str>, "embedding": <List[float]>} ready for Milvus insert.

    Raises:
        ValueError: If the lengths of `distinct_values` and `embeddings` differ.
    """
    if len(distinct_values) != len(embeddings):
        raise ValueError("Mismatch between number of values and embeddings.")
    data = [
        {"value": val, "embedding": emb}
        for val, emb in zip(distinct_values, embeddings)
    ]
    return {"data": data}

def define_milvus_schema(embedding_dim: int) -> Dict[str, Any]:
    """
    Define a Milvus collection schema for value + embedding storage.

    Args:
        embedding_dim: The dimensionality of the embedding vectors.

    Returns:
        fields: A dict with key "fields", where each field is a dict of name, dtype,...
    """
    return {
        "fields": [
            {"name": "value", "type": "varchar", "is_primary": True, "max_length": 65535},
            {"name": "embedding", "type": "float_vector", "params": {"dim": embedding_dim}}
        ],
    }

def check_collection_exists_output(result: Any) -> Dict[str, bool]:
    """
    Normalize the output of a Milvus collection-existence check.

    Args:
        result: The raw output from MilvusNode (e.g., boolean or dict) indicating
            whether a collection exists.

    Returns:
        collection_exists: A dict with key "collection_exists" set to True if
            the collection exists, else False.
    """
    exists = False
    if isinstance(result, bool):
        exists = result
    elif isinstance(result, dict) and 'value' in result:
         exists = bool(result['value'])
    elif isinstance(result, dict) and 'exists' in result:
         exists = bool(result['exists'])

    return {"collection_exists": exists}

def check_partition_exists_output(result: Any) -> Dict[str, bool]:
    """Normalize the output of Milvus partition-existence check."""
    exists = False
    if isinstance(result, bool):
        exists = result
    elif isinstance(result, dict) and 'value' in result:
        exists = bool(result['value'])
    elif isinstance(result, dict) and 'exists' in result:
        exists = bool(result['exists'])

    return {"partition_exists": exists}

def build_partition_names(partition_name: str) -> Dict[str, List[str]]:
    """
    Convert a single partition name (str) into a list of partition names
    for Milvus SEARCH API.

    Args:
        partition_name: Single partition name as string.

    Returns:
        A dict with key 'partition_names' whose value is a list[str].
    """
    if partition_name is None:
        return {"partition_names": []}

    if isinstance(partition_name, list):
        return {"partition_names": partition_name}
    if not isinstance(partition_name, str):
        raise TypeError(f"partition_name must be str or list[str], got {type(partition_name)}")

    return {"partition_names": [partition_name]}

class FuzzyMatchNode(GraphNode):
    """
    Node for performing fuzzy matching against values in a database column.

    It embeds the input text and searches for similar embeddings in Milvus.
    If the embeddings for the specified table/column are not in Milvus,
    it fetches distinct values from the SQL database, embeds them,
    stores them in Milvus, and then performs the search.
    Finally, it reranks the results.
    """
    type: NodeType = "fuzzy_match"

    input_schema: ParamSet = (
        ParamSet.new()
            .var("text: str", required=True, description="Input text to fuzzy match.")
            .var("column: str", required=True, description="Database column name.")
            .var("table: str", required=True, description="Database table name.")
            .var("top_k: int = 5", description="Number of top candidates to return.")
            .var("milvus_search_top_k: int = 20", description="Initial K for Milvus search before reranking.")
            .var("threshold: float = 0.0", description="Similarity threshold for Milvus search.")
            .var("rerank_threshold: float = 0.0", description="Score threshold for reranking.")
            .var("metric_type: str = 'COSINE'", description="Similarity metric type for Milvus search.")
            .build()
    )

    output_schema: ParamSet = (
        ParamSet.new()
            .var("top_candidates: List[Dict]", description="List of top matching candidates with scores.")
            .build()
    )

    def __init__(
        self,
        embedding: Optional[str] = "bge-m3",
        rerank: Optional[str] = "bge-m3",
        milvus: Optional[str] = "chatbot-libra",
        sql: Optional[str] = "tckt",
        embedding_dim: Optional[int] = 1024,
        **kwargs
    ):
        super().__init__(**kwargs)

        self.embedding = embedding
        self.rerank = rerank
        self.milvus = milvus
        self.sql = sql
        self.embedding_dim = embedding_dim

        self._build_graph()

    def _build_graph(self):
        from beeflow.nodes import (
            CodeNode, EmbeddingNode, MilvusNode, RerankNode, BranchNode,
            START, END, INPUT, OUTPUT
        )

        def sub(suffix: str):
            return suffix

        with self:
            embed_input = EmbeddingNode(
                name=sub("embed_input"),
                resource_key=self.embedding,
                inputs={"texts": INPUT["text"]},
            )
            code_gen_collection_name = CodeNode(
                name=sub("code_gen_collection_name"),
                code_fn=generate_collection_name,
                inputs={"table": INPUT},
                return_keys=["collection_name: str"]
            )

            code_gen_partition_name = CodeNode(
                name=sub("code_gen_partition_name"),
                code_fn=generate_partition_name,
                inputs={"column": INPUT["column"]},
                return_keys=["partition_name: str", "partition_names: list"]
            )

            milvus_check_collection = MilvusNode(
                name=sub("milvus_check_collection"),
                resource_key=self.milvus,
                operation=MilvusOperation.HAS_COLLECTION, # Or DESCRIBE_COLLECTION
                inputs={"collection_name": code_gen_collection_name}
                # Output needs processing to determine existence
            )
            
            milvus_check_partition = MilvusNode(
                name=sub("milvus_check_partition"),
                resource_key=self.milvus,
                operation=MilvusOperation.HAS_PARTITION,
                inputs={
                    "collection_name": code_gen_collection_name["collection_name"],
                    "partition_name": code_gen_partition_name
                }
            )

            branch_check_milvus = BranchNode(
                name=sub("branch_check_milvus"),
                cases={"(partition_exists == True) and (collection_exists == True)": sub("search_milvus_existing")}, 
                default=sub("code_gen_sql_fetch"),
                inputs={"partition_exists": milvus_check_partition["exists"], "collection_exists": milvus_check_collection["exists"]}
            )

            # --- Path A: Partition Exists ---
            search_milvus_existing = MilvusNode(
                name=sub("search_milvus_existing"),
                resource_key=self.milvus,
                operation=MilvusOperation.SEARCH,
                inputs={
                    "collection_name": code_gen_collection_name,
                    "partition_names": code_gen_partition_name,
                    "query_vectors": embed_input["embeddings"],
                    "top_k": INPUT["milvus_search_top_k"],
                    "threshold": INPUT["threshold"],
                    "output_fields": ["value"],
                    "metric_type": INPUT["metric_type"]
                }
                # Output: {"results": [[{'id': ..., 'distance': ..., 'entity': {'value': ...}}]]}
            )

            # --- Path B: Partition Not Exists - Create
            code_gen_sql_fetch = CodeNode(
                name=sub("code_gen_sql_fetch"),
                code_fn=lambda column, table: {"query": f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL"},
                inputs={"column": INPUT, "table": INPUT},
                return_keys=["query: str"]
            )

            sql_fetch = SQLNode(
                name=sub("sql_fetch"),
                resource_key=self.sql,
                operation=SQLOperation.QUERY,
                inputs={"query": code_gen_sql_fetch, "limit": 1000000}
                # Output format depends on SqlNode implementation, e.g., {"results": [...]}
            )

            code_format_sql = CodeNode(
                name=sub("code_format_sql"),
                code_fn=format_sql,
                inputs={"sql_result": sql_fetch["data"]}, 
                return_keys=["distinct_values: List[str]"]
            )

            embed_sql_values = EmbeddingNode(
                name=sub("embed_sql_values"),
                resource_key=self.embedding,
                inputs={"texts": code_format_sql["distinct_values"]}
            )

            milvus_create_partition = MilvusNode(
                name=sub("milvus_create_partition"),
                resource_key=self.milvus,
                operation=MilvusOperation.CREATE_PARTITION,
                inputs={
                    "collection_name": code_gen_collection_name["collection_name"],
                    "partition_name": code_gen_partition_name
                }
            )

            code_prepare_milvus_insertion = CodeNode(
                name=sub("code_prepare_milvus_insertion"),
                code_fn=prepare_milvus_insertion,
                inputs={
                    "distinct_values": code_format_sql["distinct_values"],
                    "embeddings": embed_sql_values["embeddings"]
                },
                return_keys=["data: List[Dict]"]
            )
            milvus_insert = MilvusNode(
                name=sub("milvus_insert"),
                resource_key=self.milvus,
                operation=MilvusOperation.INSERT,
                inputs={
                    "collection_name": code_gen_collection_name,
                    "data": code_prepare_milvus_insertion,
                    "partition_name": code_gen_partition_name
                }
            )

            load_new_collection = MilvusNode(
                 name=sub("load_new_collection"),
                 resource_key=self.milvus,
                 operation=MilvusOperation.LOAD_COLLECTION, # Assumed operation
                 inputs={"collection_name": code_gen_collection_name}
            )

            search_milvus_new = MilvusNode(
                name=sub("search_milvus_new"),
                resource_key=self.milvus,
                operation=MilvusOperation.SEARCH,
                inputs={
                    "collection_name": code_gen_collection_name,
                    "partition_names": code_gen_partition_name,
                    "query_vectors": embed_input["embeddings"],
                    "top_k": INPUT["milvus_search_top_k"],
                    "threshold": INPUT["threshold"],
                    "output_fields": ['embedding', 'value'],
                    "metric_type": INPUT["metric_type"]
                }
                 # Output: {"results": [[{'id': ..., 'distance': ..., 'entity': {'value': ...}}]]}
            )

            # --- Merge Paths and Rerank ---
            code_merge_results = CodeNode(
                name=sub("code_merge_results"),
                code_fn=lambda existing=None, new=None: {
                    "merged_results": (
                        (existing if isinstance(existing, list) else ([existing] if existing is not None else []))
                        +
                        (new if isinstance(new, list) else ([new] if new is not None else []))
                    )
                },
                inputs={
                    "existing": search_milvus_existing["results"],        
                    "new": search_milvus_new["results"]          
                },
                return_keys=["merged_results: List"]
            )

            code_format_rerank = CodeNode(
                name=sub("code_format_rerank"),
                code_fn=lambda merged_results: {"documents": [{"id": res.get('id'), "content": res.get('value'), "milvus_score": 1-res.get('distance',1)} for sublist in merged_results for res in sublist]},
                inputs={"merged_results": code_merge_results},
                return_keys=["documents: List[Dict]"]
            )

            rerank_results = RerankNode(
                name=sub("rerank"),
                resource_key=self.rerank,
                inputs={
                    "query": INPUT["text"],
                    "documents": code_format_rerank["documents"],
                    "top_k": INPUT["top_k"],
                    "threshold": INPUT["rerank_threshold"]
                }
                # Output format: {"reranks": [...]}
            )

            code_format_output = CodeNode(
                name=sub("code_format_output"),
                code_fn=format_rerank_results,
                inputs={"reranks": rerank_results, "top_k": INPUT["top_k"]},
                return_keys=["top_candidates: List[Dict]"],
                outputs={"top_candidates": OUTPUT}
            )

            # milvus_drop_partition = MilvusNode(
            #     name=sub("milvus_drop_partition"),
            #     resource_key=self.milvus,
            #     operation=MilvusOperation.DROP_PARTITION,
            #     inputs={
            #         "collection_name": code_gen_collection_name["collection_name"],
            #         "partition_name": code_gen_partition_name
            #     }
            # )

            START >> embed_input >> code_gen_collection_name >> code_gen_partition_name >> [milvus_check_collection, milvus_check_partition] >> branch_check_milvus
            branch_check_milvus >> [search_milvus_existing, code_gen_sql_fetch]

            search_milvus_existing >> code_merge_results

            code_gen_sql_fetch >> sql_fetch >> code_format_sql >> embed_sql_values >> milvus_create_partition >> code_prepare_milvus_insertion
            code_prepare_milvus_insertion >> milvus_insert >> load_new_collection >> search_milvus_new
            search_milvus_new >> code_merge_results

            code_merge_results >> code_format_rerank >> rerank_results >> code_format_output >> END
            # code_merge_results >> code_format_rerank >> rerank_results >> code_format_output >> milvus_drop_partition >> END

        self.build()

async def main():
    from beeflow.states import WorkflowState, WorkflowIndexer

    fuzzy_match = FuzzyMatchNode(
        name="fuzzy_match",
        sql="tckt",
        inputs=INPUT,
        outputs=OUTPUT
    )

    indexer = WorkflowIndexer(name="fuzzy_match").add_node(fuzzy_match).build()
        
    state = WorkflowState(
        indexer=indexer, 
        inputs={
            "text": "Nợ quá hạn",
            "table": "APPS.FIN_RPT_CEO_DAILY_POC",
            "column": "IND_NAME",
            "top_k": 3,
        }
    )

    try:
        result = await fuzzy_match.run(state=state)
        print("Fuzzy Match Result:")
        print(result)
    except Exception as e:
        LOGGER.error(f"Workflow execution failed: {e}", exc_info=True)
        print(f"Error during execution: {e}")

if __name__ == "__main__": 
    asyncio.run(main())