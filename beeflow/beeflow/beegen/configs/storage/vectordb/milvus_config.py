from typing import Dict, Optional, List
from xml.dom import HIERARCHY_REQUEST_ERR
from beegen.const import BEEGEN_ROOT
from .base import VectorDBConfig, VectorDBType
from enum import Enum
from beegen.tools.schema.param import ParamSet
    
    
class MilvusOperation(str, Enum):
    """Enumeration of supported Milvus operations."""
    # Collection operations
    SEARCH = "search"
    HYBRID_SEARCH = "hybrid_search"
    HIERARCHICAL_SEARCH = "hierarchical_search"
    INSERT = "insert"
    DELETE = "delete"
    QUERY = "query"
    FLUSH = "flush"
    COMPACT = "compact"
    UPSERT = "upsert"  # High-level operation (not direct Milvus API)
    
    # Collection management
    CREATE_COLLECTION = "create_collection"
    DROP_COLLECTION = "drop_collection"
    LIST_COLLECTIONS = "list_collections"
    HAS_COLLECTION = "has_collection"
    LOAD_COLLECTION = "load"
    RELEASE_COLLECTION = "release"
    
    # Index operations
    CREATE_INDEX = "create_index"
    DROP_INDEX = "drop_index"
    
    # Partition operations
    CREATE_PARTITION = "create_partition"
    DROP_PARTITION = "drop_partition"
    HAS_PARTITION = "has_partition"
    LIST_PARTITIONS = "partitions"
    
    # Information operations
    GET_COLLECTION_STATS = "get_statistics"
    

MILVUS_OPERATION_INPUTS = {
    # Collection Management
    MilvusOperation.CREATE_COLLECTION: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .var("fields: List", required=True)
            .var("description: str = ''", "Collection description")
            .var("shards_num: int = None", "Number of shards")
            .var("consistency_level: str = None", "Consistency level")
            .build()
    ),
    MilvusOperation.DROP_COLLECTION: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .build()
    ),
    MilvusOperation.LIST_COLLECTIONS: ParamSet.new().build(),
    MilvusOperation.HAS_COLLECTION: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .build()
    ),
    MilvusOperation.LOAD_COLLECTION: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .build()
    ),
    MilvusOperation.RELEASE_COLLECTION: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .build()
    ),
    
    # Search Operations
    MilvusOperation.SEARCH: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .var("query_vectors: List[List]", required=True)
            .var("top_k: int = 10", "Number of results to return")
            .var("threshold: float = 0.0", "Similarity threshold")
            .var("output_fields: List = ['chunk_id', 'role']", "Fields to return in results")
            .var("metric_type: str = None", "Distance metric type")
            .var("partition_names: List = None", "Partitions to search")
            .var("expr: str = None", "Filter expression")
            .build()
    ),

    MilvusOperation.HYBRID_SEARCH: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .var("query: str", required=True)
            .var("query_vectors: List[List]", required=True)
            .var("top_k: int = 10", "Number of results to return")
            .var("threshold: float = 0.0", "Similarity threshold")
            .var("output_fields: List = ['chunk_id', 'role']", "Fields to return in results")
            .var("metric_type: str = None", "Distance metric type")
            .var("partition_names: List = None", "Partitions to search")
            .var("expr: str = None", "Filter expression")
            .var("search_weighted_score: List = None", "weight values for Dense and Sparse search")
            .build()
    ),

    MilvusOperation.HIERARCHICAL_SEARCH: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .var("query: str", required=True)
            .var("query_vectors: List[List]", required=True)
            .var("top_k: int = 10", "Number of results to return")
            .var("top_k_topic: int = 3", "Number of topics to search")
            .var("top_k_score: int = 5", "number of samples to calculate score for each topic")
            .var("threshold: float = 0.0", "Similarity threshold")
            .var("output_fields: List = ['chunk_id', 'role']", "Fields to return in results")
            .var("metric_type: str = None", "Distance metric type")
            .var("expr: str = None", "Filter expression")
            .var("search_weighted_score: List = None", "weight values for Dense and Sparse search")
            .var("use_hybrid_search: bool = False", "use hybrid search")
            .build()
    ),

    # Document Operations
    MilvusOperation.INSERT: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .var("data: List", required=True)
            .var("partition_name: str = None", "Partition to insert into")
            .build()
    ),
    MilvusOperation.DELETE: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .var("expr: str", required=True)
            .build()
    ),
    MilvusOperation.QUERY: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .var("expr: str", required=True)
            .var("output_fields: List = None", "Fields to return in results")
            .build()
    ),
    MilvusOperation.UPSERT: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .var("data: List", required=True)
            .build()
    ),

    # Collection Operations
    MilvusOperation.FLUSH: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .build()
    ),
    MilvusOperation.COMPACT: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .build()
    ),

    # Index Operations
    MilvusOperation.CREATE_INDEX: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .var("field_name: str", required=True)
            .var("index_params: Dict = None", "Index parameters")
            .build()
    ),
    MilvusOperation.DROP_INDEX: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .build()
    ),

    # Partition Operations
    MilvusOperation.CREATE_PARTITION: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .var("partition_name: str", required=True)
            .build()
    ),
    MilvusOperation.DROP_PARTITION: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .var("partition_name: str", required=True)
            .build()
    ),
    MilvusOperation.HAS_PARTITION: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .var("partition_name: str", required=True)
            .build()
    ),
    MilvusOperation.LIST_PARTITIONS: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .build()
    ),
    MilvusOperation.GET_COLLECTION_STATS: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .build()
    )
}


MILVUS_OPERATIONS_OUTPUTS = {

    # Collection Management
    MilvusOperation.CREATE_COLLECTION: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'failed')", required=True)
            .var("message: str", "message if status is not 'success'")
            .build()
    ),
    MilvusOperation.DROP_COLLECTION: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("collection_name: str", "Name of the dropped collection")
            .var("message: Optional[str] = None", "message if status is not 'success'")
            .build()
    ),
    MilvusOperation.LIST_COLLECTIONS: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("collections: List[str]", "List of collection names")
            .var("message: str", "message if status is not 'success'")
            .build()
    ),
    MilvusOperation.HAS_COLLECTION: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("exists: bool", "Whether the collection exists")
            .var("message: str", "message if status is not 'success'")
            .build()
    ),
    
    # Basic Usage Functions
    MilvusOperation.LOAD_COLLECTION: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("message: str", "message if status is not 'success'")
            .build()
    ),
    MilvusOperation.RELEASE_COLLECTION: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("collection_name: str", "Name of the released collection")
            .var("message: Optional[str] = None", "message if status is not 'success'")
            .build()
    ),
    
    # Search Operations
    MilvusOperation.SEARCH: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("results: List[List[Dict[str, Any]]]", "List of search results for each query vector")
            .var("total_hits: List[int]", "Total number of hits across all query vectors")
            .var("message: Optional[str] = None", "message if status is not 'success'")
            .build()
    ),

    MilvusOperation.HYBRID_SEARCH: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("results: List[List[Dict[str, Any]]]", "List of search results for each query vector")
            .var("total_hits: List[int]", "Total number of hits across all query vectors")
            .var("message: Optional[str] = None", "message if status is not 'success'")
            .build()
    ),

    MilvusOperation.HIERARCHICAL_SEARCH: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("results: List[List[Dict[str, Any]]]", "List of search results for each query vector")
            .var("total_hits: List[int]", "Total number of hits across all query vectors")
            .var("message: Optional[str] = None", "message if status is not 'success'")
            .build()
    ),

    # Document Operations
    MilvusOperation.INSERT: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("insert_count: int", "Number of entities inserted")
            .var("ids: List", "IDs of inserted entities")
            .var("message: Optional[str] = None", "message if status is not 'success'")
            .build()
    ),
    MilvusOperation.DELETE: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("delete_count: int", "Number of entities deleted")
            .var("message: Optional[str] = None", "message if status is not 'success'")
            .build()
    ),
    MilvusOperation.QUERY: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("results: List[Dict[str, Any]]", "List of query results")
            .var("result_count: int", "Number of results returned")
            .var("message: Optional[str] = None", "message if status is not 'success'")
            .build()
    ),
    MilvusOperation.UPSERT: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("upsert_count: int", "Number of entities upserted")
            .var("ids: List", "IDs of upserted entities")
            .var("message: Optional[str] = None", "message if status is not 'success'")
            .build()
    ),

    # Collection Operations
    MilvusOperation.FLUSH: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("collection_name: str", "Name of the flushed collection")
            .var("message: Optional[str] = None", "message if status is not 'success'")
            .build()
    ),
    MilvusOperation.COMPACT: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("collection_name: str", "Name of the compacted collection")
            .var("message: Optional[str] = None", "message if status is not 'success'")
            .build()
    ),
    
    # Index Operations
    MilvusOperation.CREATE_INDEX: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("message: Optional[str] = None", "message if status is not 'success'")
            .build()
    ),
    MilvusOperation.DROP_INDEX: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("collection_name: str", "Name of the collection")
            .var("message: Optional[str] = None", "message if status is not 'success'")
            .build()
    ),

    # Partition Operations
    MilvusOperation.CREATE_PARTITION: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            # .var("collection_name: str", "Name of the collection")
            # .var("partition_name: str", "Name of the created partition")
            .var("message: Optional[str] = None", "message if status is not 'success'")
            .build()
    ),
    MilvusOperation.DROP_PARTITION: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("message: Optional[str] = None", "message if status is not 'success'")
            .build()
    ),
    MilvusOperation.HAS_PARTITION: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("exists: bool", "Whether the partition exists")
            # .var("collection_name: str", "Name of the collection")
            # .var("partition_name: str", "Name of the partition checked")
            .var("message: Optional[str] = None", "message if status is not 'success'")
            .build()
    ),
    MilvusOperation.LIST_PARTITIONS: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("partitions: List[str]", "List of partition names")
            .var("collection_name: str", "Name of the collection")
            .var("message: Optional[str] = None", "message if status is not 'success'")
            .build()
    ),
    MilvusOperation.GET_COLLECTION_STATS: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("vector_count: int", "Number of vectors in the collection")
            .var("vector_dim: int", "Dimension of vectors in the collection")
            .var("collection_name: str", "Name of the collection")
            .var("message: Optional[str] = None", "message if status is not 'success'")
            .build()
    )
}


class MilvusConfig(VectorDBConfig):
    """Configuration settings for Milvus database connection and collections.

    A configuration model that handles connection parameters, authentication, and collection settings
    for interacting with a Milvus vector database.

    Attributes:
        alias (str): Unique identifier for this configuration instance.
        uri (str): Connection URI for the Milvus server.
        username (str): Authentication username.
        password (str): Authentication password.
        db_name (str): Target database name.
        timeout (float, optional): Operation timeout in seconds. Defaults to 10.0.
        connection_pool_size (int, optional): Maximum number of connections in the pool. Defaults to 5.
        enable_ssl (bool, optional): Flag to enable SSL/TLS encryption. Defaults to False.
        ca_path (str, optional): Path to SSL CA certificate file. Required if enable_ssl is True.
        index_params (Dict): Vector index configuration parameters.
        search_params (Dict): Vector search configuration parameters.

    Example:
        ```yaml
        milvus_config:
          alias: "prod_db"
          uri: "localhost:19530"
          username: "default"
          password: "password123"
          db_name: "vector_db"
          timeout: 15.0
          index_params:
            metric_type: "L2"
            index_type: "IVF_FLAT"
          search_params:
            nprobe: 10
        ```
    """
    db_type: VectorDBType = VectorDBType.MILVUS
    alias: str
    uri: str
    username: str
    password: str
    db_name: str
    timeout: float = 10.0
    connection_pool_size: int = 5
    enable_ssl: bool = False
    ca_path: Optional[str] = None
    index_params: Dict
    search_params: Dict
    
    
    @classmethod
    def default(cls) -> 'MilvusConfig':
        """Load default config"""
        dict = MilvusConfig.read_yaml(BEEGEN_ROOT / "config/milvus.yaml")
        return MilvusConfig(**dict)


if __name__ == "__main__":
    # log_config.to_yaml_file(Path('log_config.yaml'))
    log_config = MilvusConfig.default()
    print(log_config)