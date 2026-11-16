from beegenerate.configs.yaml_model import YamlModel
from beegenerate.const import BEEGEN_ROOT
from urllib.parse import quote_plus
from typing import List, Optional
from enum import Enum
from beegen_v1.tools.schema.param import ParamSet


class MongoOperation(str, Enum):
    # Existing operations
    FIND = "find"
    FIND_ONE = "find_one"
    INSERT_ONE = "insert_one"
    INSERT_MANY = "insert_many"
    UPDATE_ONE = "update_one"
    UPDATE_MANY = "update_many"
    DELETE_ONE = "delete_one"
    DELETE_MANY = "delete_many"
    COUNT = "count_documents"
    AGGREGATE = "aggregate"
    DISTINCT = "distinct"
    CREATE_INDEX = "create_index"
    
    # New collection operations
    LIST_COLLECTIONS = "list_collections"
    CREATE_COLLECTION = "create_collection"
    DROP_COLLECTION = "drop_collection"
    RENAME_COLLECTION = "rename_collection"
    
    # New index operations
    DROP_INDEX = "drop_index"
    LIST_INDEXES = "list_indexes"
    
    # New document operations with atomic guarantees
    FIND_ONE_AND_UPDATE = "find_one_and_update"
    FIND_ONE_AND_DELETE = "find_one_and_delete"
    FIND_ONE_AND_REPLACE = "find_one_and_replace"
    
    # Bulk operations
    BULK_WRITE = "bulk_write"
    
    # Transaction support
    BEGIN_TRANSACTION = "begin_transaction"
    COMMIT_TRANSACTION = "commit_transaction"
    ABORT_TRANSACTION = "abort_transaction"
    
    # Database operations
    LIST_DATABASES = "list_databases"
    

MONGO_OPERATION_INPUTS = {
    # Database Operations
    MongoOperation.LIST_DATABASES: ParamSet.new().build(),

    # Collection Operations
    MongoOperation.LIST_COLLECTIONS: (
        ParamSet.new()
            .var("filter: Dict = {}", "Filter criteria for collections")
            .build()
    ),
    MongoOperation.CREATE_COLLECTION: (
        ParamSet.new()
            .var("name: str", required=True)
            .var("options: Dict = {}", "Collection creation options")
            .build()
    ),
    MongoOperation.DROP_COLLECTION: (
        ParamSet.new()
            .var("name: str", required=True)
            .build()
    ),
    MongoOperation.RENAME_COLLECTION: (
        ParamSet.new()
            .var("old_name: str", required=True)
            .var("new_name: str", required=True)
            .build()
    ),

    # Transaction Operations
    MongoOperation.BEGIN_TRANSACTION: ParamSet.new().build(),
    MongoOperation.COMMIT_TRANSACTION: (
        ParamSet.new()
            .var("session_id: str", required=True)
            .build()
    ),
    MongoOperation.ABORT_TRANSACTION: (
        ParamSet.new()
            .var("session_id: str", required=True)
            .build()
    ),

    # Document Operations
    MongoOperation.FIND: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .var("query: Dict = {}", "MongoDB query filter")
            .var("projection: Dict = None", "Fields to include/exclude")
            .var("sort: Dict = None", "Sorting criteria")
            .var("skip: int = 0", "Number of documents to skip")
            .var("limit: int = 10", "Maximum number of documents to return")
            .build()
    ),
    MongoOperation.FIND_ONE: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .var("query: Dict = {}", "MongoDB query filter")
            .var("projection: Dict = None", "Fields to include/exclude")
            .build()
    ),
    MongoOperation.INSERT_ONE: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .var("document: Dict", required=True)
            .build()
    ),
    MongoOperation.INSERT_MANY: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .var("documents: List[Dict]", required=True)
            .var("ordered: bool = True", "Whether to insert documents in order")
            .build()
    ),
    MongoOperation.UPDATE_ONE: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .var("filter: Dict", required=True)
            .var("update: Dict", required=True)
            .var("upsert: bool = False", "Whether to insert if no documents match")
            .build()
    ),
    MongoOperation.UPDATE_MANY: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .var("filter: Dict", required=True)
            .var("update: Dict", required=True)
            .var("upsert: bool = False", "Whether to insert if no documents match")
            .build()
    ),
    MongoOperation.DELETE_ONE: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .var("filter: Dict", required=True)
            .build()
    ),
    MongoOperation.DELETE_MANY: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .var("filter: Dict", required=True)
            .build()
    ),
    MongoOperation.COUNT: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .var("query: Dict = {}", "MongoDB query filter")
            .build()
    ),
    MongoOperation.AGGREGATE: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .var("pipeline: List", required=True)
            .build()
    ),
    MongoOperation.DISTINCT: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .var("key: str", required=True)
            .var("query: Dict = {}", "MongoDB query filter")
            .build()
    ),

    # Index Operations
    MongoOperation.CREATE_INDEX: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .var("keys: Dict", required=True)
            .var("options: Dict = {}", "Index creation options")
            .build()
    ),
    MongoOperation.DROP_INDEX: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .var("index_name: str", required=True)
            .build()
    ),
    MongoOperation.LIST_INDEXES: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .build()
    ),

    # Atomic Operations
    MongoOperation.FIND_ONE_AND_UPDATE: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .var("filter: Dict", required=True)
            .var("update: Dict", required=True)
            .var("return_document: str = 'after'", "Whether to return document before or after update")
            .var("upsert: bool = False", "Whether to insert if no documents match")
            .build()
    ),
    MongoOperation.FIND_ONE_AND_DELETE: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .var("filter: Dict", required=True)
            .build()
    ),
    MongoOperation.FIND_ONE_AND_REPLACE: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .var("filter: Dict", required=True)
            .var("replacement: Dict", required=True)
            .var("return_document: str = 'after'", "Whether to return document before or after replacement")
            .var("upsert: bool = False", "Whether to insert if no documents match")
            .build()
    ),
    MongoOperation.BULK_WRITE: (
        ParamSet.new()
            .var("collection_name: str", required=True)
            .var("operations: List", required=True)
            .var("ordered: bool = True", "Whether to execute operations in order")
            .build()
    )
}


# Define the output parameter sets for each MongoDB operation
MONGO_OPERATION_OUTPUTS = {
    # Database Operations
    MongoOperation.LIST_DATABASES: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("databases: List[Dict]", "List of database information dictionaries")
            .var("count: int", "Number of databases returned")
            .var("message: str", "message if status is not 'success'")
            .build()
    ),

    # Collection Operations
    MongoOperation.LIST_COLLECTIONS: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("collections: List[Dict]", "List of collection information dictionaries")
            .var("count: int", "Number of collections returned")
            .var("message: str", "message if status is not 'success'")
            .build()
    ),
    MongoOperation.CREATE_COLLECTION: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("collection: str", "Name of the created collection")
            .var("message: str", "message if status is not 'success'")
            .build()
    ),
    MongoOperation.DROP_COLLECTION: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("result: Any", "Result of the drop operation")
            .var("message: str", "message if status is not 'success'")
            .build()
    ),
    MongoOperation.RENAME_COLLECTION: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("result: Dict", "Result of the rename operation")
            .var("message: str", "message if status is not 'success'")
            .build()
    ),

    # Transaction Operations
    MongoOperation.BEGIN_TRANSACTION: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("session_id: str", "Unique identifier for the created session")
            .var("message: str", "message if status is not 'success'")
            .build()
    ),
    MongoOperation.COMMIT_TRANSACTION: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("committed: bool", "Whether the transaction was committed successfully")
            .var("message: str", "message if status is not 'success'")
            .build()
    ),
    MongoOperation.ABORT_TRANSACTION: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("aborted: bool", "Whether the transaction was aborted successfully")
            .var("message: str", "message if status is not 'success'")
            .build()
    ),

    # Document Operations
    MongoOperation.FIND: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("data: List[Dict]", "List of documents matching the query")
            .var("count: int", "Number of documents returned")
            .var("message: str", "message if status is not 'success'")
            .build()
    ),
    MongoOperation.FIND_ONE: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("data: Dict", "The document matching the query, or None if not found")
            .var("message: str", "message if status is not 'success'")
            .build()
    ),
    MongoOperation.INSERT_ONE: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("inserted_id: str", "String representation of the inserted document's ID")
            .var("message: str", "message if status is not 'success'")
            .build()
    ),
    MongoOperation.INSERT_MANY: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("inserted_ids: List[str]", "List of string representations of the inserted document IDs")
            .var("count: int", "Number of documents inserted")
            .var("message: str", "message if status is not 'success'")
            .build()
    ),
    MongoOperation.UPDATE_ONE: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("matched_count: int", "Number of documents that matched the filter")
            .var("modified_count: int", "Number of documents that were modified")
            .var("upserted_id: str", "ID of the upserted document if an upsert occurred", required=False)
            .var("message: str", "message if status is not 'success'")
            .build()
    ),
    MongoOperation.UPDATE_MANY: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("matched_count: int", "Number of documents that matched the filter")
            .var("modified_count: int", "Number of documents that were modified")
            .var("upserted_id: str", "ID of the upserted document if an upsert occurred", required=False)
            .var("message: str", "message if status is not 'success'")            
            .build()
    ),
    MongoOperation.DELETE_ONE: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("deleted_count: int", "Number of documents deleted (0 or 1)")
            .var("message: str", "message if status is not 'success'")
            .build()
    ),
    MongoOperation.DELETE_MANY: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("deleted_count: int", "Number of documents deleted")
            .var("message: str", "message if status is not 'success'")
            .build()
    ),
    MongoOperation.COUNT: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("count: int", "Number of documents that matched the query")
            .var("message: str", "message if status is not 'success'")
            .build()
    ),
    MongoOperation.AGGREGATE: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("data: List[Dict]", "List of documents produced by the aggregation pipeline")
            .var("count: int", "Number of documents returned")
            .var("message: str", "message if status is not 'success'")
            .build()
    ),
    MongoOperation.DISTINCT: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("data: List", "List of distinct values for the specified key")
            .var("count: int", "Number of distinct values returned")
            .var("message: str", "message if status is not 'success'")
            .build()
    ),

    # Index Operations
    MongoOperation.CREATE_INDEX: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("index_name: str", "Name of the created index")
            .var("message: str", "message if status is not 'success'")
            .build()
    ),
    MongoOperation.DROP_INDEX: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("result: Dict", "Result of the drop index operation")
            .var("message: str", "message if status is not 'success'")
            .build()
    ),
    MongoOperation.LIST_INDEXES: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("indexes: List[Dict]", "List of index information dictionaries")
            .var("count: int", "Number of indexes returned")
            .var("message: str", "message if status is not 'success'")
            .build()
    ),

    # Atomic Operations
    MongoOperation.FIND_ONE_AND_UPDATE: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("data: Dict", "The document before or after the update, as specified by return_document")
            .var("message: str", "message if status is not 'success'")
            .build()
    ),
    MongoOperation.FIND_ONE_AND_DELETE: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("data: Dict", "The deleted document, or None if no document matched")
            .var("message: str", "message if status is not 'success'")
            .build()
    ),
    MongoOperation.FIND_ONE_AND_REPLACE: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("data: Dict", "The document before or after the replacement, as specified by return_document")
            .var("message: str", "message if status is not 'success'")
            .build()
    ),
    MongoOperation.BULK_WRITE: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')")
            .var("inserted_count: int", "Number of documents inserted")
            .var("matched_count: int", "Number of documents matched for update")
            .var("modified_count: int", "Number of documents modified")
            .var("deleted_count: int", "Number of documents deleted")
            .var("upserted_count: int", "Number of documents upserted")
            .var("upserted_ids: List[str]", "List of IDs of upserted documents")
            .var("message: str", "message if status is not 'success'")
            .build()
    ),
}
    
    
class MongoConfig(YamlModel):
    """
    MongoDB connection configuration class.
    
    Supports both instance creation and default singleton pattern through get_instance().
    Reads configuration from BEEGEN_ROOT/config/mongo.yaml for default settings.

    Attributes:
        authen_source (str): Authentication database name
        uri (str): MongoDB connection URI string
    """
    authen_source: str
    uri: str 
    
    @classmethod
    def default(cls) -> 'MongoConfig':
        """Load default config"""
        dict = MongoConfig.read_yaml(BEEGEN_ROOT / "config/mongo.yaml")
        return MongoConfig(**dict)


if __name__ == "__main__":
    # log_config.to_yaml_file(Path('log_config.yaml'))
    # log_config = MongoConfig.default()
    # print(log_config)
    print(MONGO_OPERATION_OUTPUTS[MongoOperation.DELETE_MANY])