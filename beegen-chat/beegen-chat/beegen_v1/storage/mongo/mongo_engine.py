from beegen_v1.configs import MongoOperation, MongoConfig
from typing import Dict, Any
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument
from pymongo import MongoClient
from bson import json_util
import json


def serializable(obj):
    """Recursively convert MongoDB documents to JSON-serializable format."""
    if obj is None:
        return None
    return json.loads(json_util.dumps(obj))


class MongoEngine:
    """
    A modular MongoDB executor with individual methods for each operation type.
    
    This executor handles connection to a MongoDB instance and provides a unified
    interface to run various MongoDB operations synchronously with validation of both
    input parameters and output results.
    """
    
    def __init__(self, config: MongoConfig):
        """
        Initialize the MongoDB executor.
        
        Args:
            config: MongoDB connection configuration
        """
        self.client = MongoClient(config.uri)
        self.db = self.client[config.authen_source]
        self.operation_map = {
            # Operations that don't require a collection
            MongoOperation.LIST_DATABASES: self._list_databases,
            MongoOperation.LIST_COLLECTIONS: self._list_collections,
            MongoOperation.CREATE_COLLECTION: self._create_collection,
            MongoOperation.DROP_COLLECTION: self._drop_collection,
            MongoOperation.RENAME_COLLECTION: self._rename_collection,
            MongoOperation.BEGIN_TRANSACTION: self._begin_transaction,
            MongoOperation.COMMIT_TRANSACTION: self._commit_transaction,
            MongoOperation.ABORT_TRANSACTION: self._abort_transaction,
        
            # Operations that require a collection
            MongoOperation.FIND: self._find,
            MongoOperation.FIND_ONE: self._find_one,
            MongoOperation.INSERT_ONE: self._insert_one,
            MongoOperation.INSERT_MANY: self._insert_many,
            MongoOperation.UPDATE_ONE: self._update_one,
            MongoOperation.UPDATE_MANY: self._update_many,
            MongoOperation.DELETE_ONE: self._delete_one,
            MongoOperation.DELETE_MANY: self._delete_many,
            MongoOperation.COUNT: self._count,
            MongoOperation.AGGREGATE: self._aggregate,
            MongoOperation.DISTINCT: self._distinct,
            MongoOperation.CREATE_INDEX: self._create_index,
            MongoOperation.DROP_INDEX: self._drop_index,
            MongoOperation.LIST_INDEXES: self._list_indexes,
            MongoOperation.FIND_ONE_AND_UPDATE: self._find_one_and_update,
            MongoOperation.FIND_ONE_AND_DELETE: self._find_one_and_delete,
            MongoOperation.FIND_ONE_AND_REPLACE: self._find_one_and_replace,
            MongoOperation.BULK_WRITE: self._bulk_write
        }
        self._sessions = {}
                
    def close(self):
        """Close the MongoDB connection."""
        self.client.close()
        
    # ==== Database Operations ====
    
    def _list_databases(self, **params) -> Dict[str, Any]:
        """
        List all databases on the MongoDB server.
        
        Args:
            params: Operation parameters
            
        Returns:
            Dictionary with status and list of databases
        """
        databases = [serializable(db) for db in self.client.list_databases(**params)]
        return {
            "status": "success", 
            "databases": databases, 
            "count": len(databases)
        }
    
    # ==== Collection Operations ====
    
    def _list_collections(self, **params) -> Dict[str, Any]:
        """
        List collections in the current database.
        
        Args:
            params: Operation parameters
            
        Returns:
            Dictionary with status and list of collections
        """
        collections = [serializable(coll) for coll in self.db.list_collections(
            filter=params.get('filter', {})
        )]
                
        return {
            "status": "success", 
            "collections": collections, 
            "count": len(collections)
        }
    
    def _create_collection(self, **params) -> Dict[str, Any]:
        """
        Create a new collection in the database.
        
        Args:
            params: Operation parameters
            
        Returns:
            Dictionary with status and collection name
        """
        self.db.create_collection(
            params['name'],
            **params.get('options', {})
        )
        return {"status": "success", "collection": params['name']}
    
    def _drop_collection(self, **params) -> Dict[str, Any]:
        """
        Drop a collection from the database.
        
        Args:
            params: Operation parameters
            
        Returns:
            Dictionary with status and operation result
        """
        result = self.db.drop_collection(params['name'])
        serializable_result = json.loads(json_util.dumps(result))
        return {"status": "success", "result": serializable_result}
    
    def _rename_collection(self, **params) -> Dict[str, Any]:
        """
        Rename a collection in the database.
        
        Args:
            params: Operation parameters
            
        Returns:
            Dictionary with status and operation result
        """
        result = self.db.command(
            'renameCollection', 
            f"{self.db.name}.{params['old_name']}",
            to=f"{self.db.name}.{params['new_name']}"
        )
        
        serializable_result = serializable(result)
        return {"status": "success", "result": serializable_result}
    
    # ==== Transaction Operations ====
    
    def _begin_transaction(self, **params) -> Dict[str, Any]:
        """
        Begin a new MongoDB transaction.
        
        Args:
            params: Operation parameters
            
        Returns:
            Dictionary with status and session ID
        """
        session = self.client.start_session()
        session.start_transaction()
        session_id = str(id(session))
        self._sessions[session_id] = session
        return {"status": "success", "session_id": session_id}
    
    def _commit_transaction(self, **params) -> Dict[str, Any]:
        """
        Commit a MongoDB transaction.
        
        Args:
            params: Operation parameters
            
        Returns:
            Dictionary with status and commit result
            
        Raises:
            ValueError: If session_id is invalid
        """
        session = self._sessions.pop(params['session_id'], None)
        if not session:
            raise ValueError("Valid session_id must be provided")
        session.commit_transaction()
        session.end_session()
        return {"status": "success", "committed": True}
    
    def _abort_transaction(self, **params) -> Dict[str, Any]:
        """
        Abort a MongoDB transaction.
        
        Args:
            params: Operation parameters
            
        Returns:
            Dictionary with status and abort result
            
        Raises:
            ValueError: If session_id is invalid
        """
        session = self._sessions.pop(params['session_id'], None)
        if not session:
            raise ValueError("Valid session_id must be provided")
        session.abort_transaction()
        session.end_session()
        return {"status": "success", "aborted": True}
    
    # ==== Document Operations ====
    
    def _find(self, **params) -> Dict[str, Any]:
        """
        Find documents in a collection.
        
        Args:
            params: Operation parameters
            
        Returns:
            Dictionary with status and matching documents
        """
        collection = self.db[params['collection_name']]
        cursor = collection.find(
            params.get('query', {}),
            params.get('projection')
        )
        
        if params.get('sort'):
            cursor = cursor.sort(params['sort'])
        if params.get('skip'):
            cursor = cursor.skip(params['skip'])
        if params.get('limit'):
            cursor = cursor.limit(params['limit'])
            
        documents = [serializable(doc) for doc in cursor]
        return {
            "status": "success", 
            "data": documents, 
            "count": len(documents)
        }
    
    def _find_one(self, **params) -> Dict[str, Any]:
        """
        Find a single document in a collection.
        
        Args:
            params: Operation parameters
            
        Returns:
            Dictionary with status and matching document
        """
        collection = self.db[params['collection_name']]
        document = collection.find_one(
            params.get('query', {}),
            params.get('projection')
        )
        serializable_document = serializable(document)
        return {"status": "success", "data": serializable_document}
    
    def _insert_one(self, **params) -> Dict[str, Any]:
        """
        Insert a single document into a collection.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and inserted ID
        """
        collection = self.db[params['collection_name']]
        result = collection.insert_one(params['document'])
        return {"status": "success", "inserted_id": str(result.inserted_id)}
    
    def _insert_many(self, **params) -> Dict[str, Any]:
        """
        Insert multiple documents into a collection.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and inserted IDs
        """
        collection = self.db[params['collection_name']]
        result = collection.insert_many(
            params['documents'],
            ordered=params.get('ordered', True)
        )
        return {
            "status": "success",
            "inserted_ids": [str(id) for id in result.inserted_ids],
            "count": len(result.inserted_ids)
        }
    
    def _update_one(self, **params) -> Dict[str, Any]:
        """
        Update a single document in a collection.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and update counts
        """
        collection = self.db[params['collection_name']]
        result = collection.update_one(
            params['filter'],
            params['update'],
            upsert=params.get('upsert', False)
        )
        response = {
            "status": "success",
            "matched_count": result.matched_count,
            "modified_count": result.modified_count
        }
        if result.upserted_id:
            response["upserted_id"] = str(result.upserted_id)
        return response
    
    def _update_many(self, **params) -> Dict[str, Any]:
        """
        Update multiple documents in a collection.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and update counts
        """
        collection = self.db[params['collection_name']]
        result = collection.update_many(
            filter=params['filter'],
            update=params['update'],
            upsert=params.get('upsert', False)
        )
        response = {
            "status": "success",
            "matched_count": result.matched_count,
            "modified_count": result.modified_count
        }
        if result.upserted_id:
            response["upserted_id"] = str(result.upserted_id)
        return response
    
    def _delete_one(self, **params) -> Dict[str, Any]:
        """
        Delete a single document from a collection.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and delete count
        """
        collection = self.db[params['collection_name']]
        result = collection.delete_one(params['filter'])
        return {"status": "success", "deleted_count": result.deleted_count}
    
    def _delete_many(self, **params) -> Dict[str, Any]:
        """
        Delete multiple documents from a collection.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and delete count
        """
        collection = self.db[params['collection_name']]
        result = collection.delete_many(params['filter'])
        return {"status": "success", "deleted_count": result.deleted_count}
    
    def _count(self, **params) -> Dict[str, Any]:
        """
        Count documents in a collection.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and count
        """
        collection = self.db[params['collection_name']]
        count = collection.count_documents(params.get('query', {}))
        return {"status": "success", "count": count}
    
    def _aggregate(self, **params) -> Dict[str, Any]:
        """
        Run an aggregation pipeline on a collection.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and aggregation results
        """
        collection = self.db[params['collection_name']]
        documents = [serializable(doc) for doc in collection.aggregate(params['pipeline'])]
        
        return {"status": "success", "data": documents, "count": len(documents)}
    
    def _distinct(self, **params) -> Dict[str, Any]:
        """
        Get distinct values for a field in a collection.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and distinct values
        """
        collection = self.db[params['collection_name']]
        values = collection.distinct(
            params['key'],
            params.get('query', {})
        )
        return {"status": "success", "data": serializable(values), "count": len(values)}
    
    def _create_index(self, **params) -> Dict[str, Any]:
        """
        Create an index on a collection.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and index name
        """
        collection = self.db[params['collection_name']]
        index_name = collection.create_index(
            params['keys'],
            **params.get('options', {})
        )
        return {"status": "success", "index_name": index_name}
    
    def _drop_index(self, **params) -> Dict[str, Any]:
        """
        Drop an index from a collection.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and operation result
        """
        collection = self.db[params['collection_name']]
        result = collection.drop_index(params['index_name'])
        return {"status": "success", "result": serializable(result)}
    
    def _list_indexes(self, **params) -> Dict[str, Any]:
        """
        List indexes on a collection.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and list of indexes
        """
        collection = self.db[params['collection_name']]
        indexes = [serializable(idx) for idx in collection.list_indexes()]
        return {"status": "success", "indexes": indexes, "count": len(indexes)}
    
    def _find_one_and_update(self, **params) -> Dict[str, Any]:
        """
        Find a document and update it atomically.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and updated document
        """
        collection = self.db[params['collection_name']]
        return_option = (ReturnDocument.AFTER 
                       if params.get('return_document') == 'after'
                       else ReturnDocument.BEFORE)
        document = collection.find_one_and_update(
            params['filter'],
            params['update'],
            return_document=return_option,
            upsert=params.get('upsert', False)
        )
        return {"status": "success", "data": serializable(document)}
    
    def _find_one_and_delete(self, **params) -> Dict[str, Any]:
        """
        Find a document and delete it atomically.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and deleted document
        """
        collection = self.db[params['collection_name']]
        document = collection.find_one_and_delete(params['filter'])
        return {"status": "success", "data": serializable(document)}
    
    def _find_one_and_replace(self, **params) -> Dict[str, Any]:
        """
        Find a document and replace it atomically.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and replaced document
        """
        collection = self.db[params['collection_name']]
        return_option = (ReturnDocument.AFTER 
                       if params.get('return_document') == 'after'
                       else ReturnDocument.BEFORE)
        
        document = collection.find_one_and_replace(
            params['filter'],
            params['replacement'],
            return_document=return_option,
            upsert=params.get('upsert', False)
        )
        
        return {"status": "success", "data": serializable(document)}
    
    def _bulk_write(self, **params) -> Dict[str, Any]:
        """
        Perform multiple write operations in bulk.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and bulk write results
        """
        collection = self.db[params['collection_name']]
        result = collection.bulk_write(
            params['operations'],
            ordered=params.get('ordered', True)
        )
        return {
            "status": "success",
            "inserted_count": result.inserted_count,
            "matched_count": result.matched_count,
            "modified_count": result.modified_count,
            "deleted_count": result.deleted_count,
            "upserted_count": result.upserted_count,
            "upserted_ids": [str(id) for id in result.upserted_ids.values()] if result.upserted_ids else []
        }
        
    def run(self, operation: MongoOperation, params: Dict[str, Any]={}) -> Dict[str, Any]:
        """
        Execute a MongoDB operation synchronously with validation.
        
        This method routes the operation to the appropriate specialized method.
        
        Args:
            operation: The MongoDB operation to perform (from MongoOperation enum)
            params: Parameters for the operation
            
        Returns:
            A standardized response dictionary with operation results
        """
        # try:
            # Validate input parameters
            # validated_params = self._validate_input_params(operation, params)
        
        if operation not in self.operation_map:
            raise ValueError(f"Unsupported operation: {operation}")
        
        result = self.operation_map[operation](**params)
        
        # Add operation success message if not present
        if 'message' not in result:
            op_name = operation.name.lower().replace('_', ' ')
            result['message'] = f"Operation {op_name} completed successfully"
            
        # Validate output result
        # return self._validate_output_result(operation, result)
        return result
            
        # except Exception as e:
        #     import traceback
        #     error_traceback = traceback.format_exc()
        #     return {
        #         "status": "error", 
        #         "message": str(error_traceback)
        #     }


class AsyncMongoEngine:
    """
    A modular MongoDB executor with individual methods for each operation type.
    
    This executor handles connection to a MongoDB instance and provides a unified
    interface to run various MongoDB operations asynchronously with validation of both
    input parameters and output results.
    """
    
    def __init__(self, config: MongoConfig):
        """
        Initialize the MongoDB executor.
        
        Args:
            config: MongoDB connection configuration
        """
        self.client = AsyncIOMotorClient(config.uri)
        self.db = self.client[config.authen_source]
        self.operation_map = {
            # Operations that don't require a collection
            MongoOperation.LIST_DATABASES: self._list_databases,
            MongoOperation.LIST_COLLECTIONS: self._list_collections,
            MongoOperation.CREATE_COLLECTION: self._create_collection,
            MongoOperation.DROP_COLLECTION: self._drop_collection,
            MongoOperation.RENAME_COLLECTION: self._rename_collection,
            MongoOperation.BEGIN_TRANSACTION: self._begin_transaction,
            MongoOperation.COMMIT_TRANSACTION: self._commit_transaction,
            MongoOperation.ABORT_TRANSACTION: self._abort_transaction,
        
            # Operations that require a collection
            MongoOperation.FIND: self._find,
            MongoOperation.FIND_ONE: self._find_one,
            MongoOperation.INSERT_ONE: self._insert_one,
            MongoOperation.INSERT_MANY: self._insert_many,
            MongoOperation.UPDATE_ONE: self._update_one,
            MongoOperation.UPDATE_MANY: self._update_many,
            MongoOperation.DELETE_ONE: self._delete_one,
            MongoOperation.DELETE_MANY: self._delete_many,
            MongoOperation.COUNT: self._count,
            MongoOperation.AGGREGATE: self._aggregate,
            MongoOperation.DISTINCT: self._distinct,
            MongoOperation.CREATE_INDEX: self._create_index,
            MongoOperation.DROP_INDEX: self._drop_index,
            MongoOperation.LIST_INDEXES: self._list_indexes,
            MongoOperation.FIND_ONE_AND_UPDATE: self._find_one_and_update,
            MongoOperation.FIND_ONE_AND_DELETE: self._find_one_and_delete,
            MongoOperation.FIND_ONE_AND_REPLACE: self._find_one_and_replace,
            MongoOperation.BULK_WRITE: self._bulk_write
        }
        self._sessions = {}
                
    async def close(self):
        """Close the MongoDB connection."""
        self.client.close()
        
    # ==== Database Operations ====
    
    async def _list_databases(self, **params) -> Dict[str, Any]:
        """
        List all databases on the MongoDB server.
        
        Args:
            params: Operation parameters
            
        Returns:
            Dictionary with status and list of databases
        """
        databases = [serializable(db) async for db in await self.client.list_databases(**params)]
        return {
            "status": "success", 
            "databases": databases, 
            "count": len(databases)
        }
    
    # ==== Collection Operations ====
    
    async def _list_collections(self, **params) -> Dict[str, Any]:
        """
        List collections in the current database.
        
        Args:
            params: Operation parameters
            
        Returns:
            Dictionary with status and list of collections
        """
        collections = [serializable(coll) async for coll in await self.db.list_collections(
            filter=params.get('filter', {})
        )]
                
        return {
            "status": "success", 
            "collections": collections, 
            "count": len(collections)
        }
    
    async def _create_collection(self, **params) -> Dict[str, Any]:
        """
        Create a new collection in the database.
        
        Args:
            params: Operation parameters
            
        Returns:
            Dictionary with status and collection name
        """
        await self.db.create_collection(
            params['name'],
            **params.get('options', {})
        )
        return {"status": "success", "collection": params['name']}
    
    async def _drop_collection(self, **params) -> Dict[str, Any]:
        """
        Drop a collection from the database.
        
        Args:
            params: Operation parameters
            
        Returns:
            Dictionary with status and operation result
        """
        result = await self.db.drop_collection(params['name'])
        serializable_result = json.loads(json_util.dumps(result))
        return {"status": "success", "result": serializable_result}
    
    async def _rename_collection(self, **params) -> Dict[str, Any]:
        """
        Rename a collection in the database.
        
        Args:
            params: Operation parameters
            
        Returns:
            Dictionary with status and operation result
        """
        result = await self.db.command(
            'renameCollection', 
            f"{self.db.name}.{params['old_name']}",
            to=f"{self.db.name}.{params['new_name']}"
        )
        
        serializable_result = serializable(result)
        return {"status": "success", "result": serializable_result}
    
    # ==== Transaction Operations ====
    
    async def _begin_transaction(self, **params) -> Dict[str, Any]:
        """
        Begin a new MongoDB transaction.
        
        Args:
            params: Operation parameters
            
        Returns:
            Dictionary with status and session ID
        """
        session = await self.client.start_session()
        session.start_transaction()
        session_id = str(id(session))
        self._sessions[session_id] = session
        return {"status": "success", "session_id": session_id}
    
    async def _commit_transaction(self, **params) -> Dict[str, Any]:
        """
        Commit a MongoDB transaction.
        
        Args:
            params: Operation parameters
            
        Returns:
            Dictionary with status and commit result
            
        Raises:
            ValueError: If session_id is invalid
        """
        session = self._sessions.pop(params['session_id'], None)
        if not session:
            raise ValueError("Valid session_id must be provided")
        await session.commit_transaction()
        await session.end_session()
        return {"status": "success", "committed": True}
    
    async def _abort_transaction(self, **params) -> Dict[str, Any]:
        """
        Abort a MongoDB transaction.
        
        Args:
            params: Operation parameters
            
        Returns:
            Dictionary with status and abort result
            
        Raises:
            ValueError: If session_id is invalid
        """
        session = self._sessions.pop(params['session_id'], None)
        if not session:
            raise ValueError("Valid session_id must be provided")
        await session.abort_transaction()
        await session.end_session()
        return {"status": "success", "aborted": True}
    
    # ==== Document Operations ====
    
    async def _find(self, **params) -> Dict[str, Any]:
        """
        Find documents in a collection.
        
        Args:
            params: Operation parameters
            
        Returns:
            Dictionary with status and matching documents
        """
        collection = self.db[params['collection_name']]
        cursor = collection.find(
            params.get('query', {}),
            params.get('projection')
        )
        
        if params.get('sort'):
            cursor = cursor.sort(params['sort'])
        if params.get('skip'):
            cursor = cursor.skip(params['skip'])
        if params.get('limit'):
            cursor = cursor.limit(params['limit'])
            
        documents = [serializable(doc) async for doc in cursor]
        return {
            "status": "success", 
            "data": documents, 
            "count": len(documents)
        }
    
    async def _find_one(self, **params) -> Dict[str, Any]:
        """
        Find a single document in a collection.
        
        Args:
            params: Operation parameters
            
        Returns:
            Dictionary with status and matching document
        """
        collection = self.db[params['collection_name']]
        document = await collection.find_one(
            params.get('query', {}),
            params.get('projection')
        )
        serializable_document = serializable(document)
        return {"status": "success", "data": serializable_document}
    
    async def _insert_one(self, **params) -> Dict[str, Any]:
        """
        Insert a single document into a collection.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and inserted ID
        """
        collection = self.db[params['collection_name']]
        result = await collection.insert_one(params['document'])
        return {"status": "success", "inserted_id": str(result.inserted_id)}
    
    async def _insert_many(self, **params) -> Dict[str, Any]:
        """
        Insert multiple documents into a collection.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and inserted IDs
        """
        collection = self.db[params['collection_name']]
        result = await collection.insert_many(
            params['documents'],
            ordered=params.get('ordered', True)
        )
        return {
            "status": "success",
            "inserted_ids": [str(id) for id in result.inserted_ids],
            "count": len(result.inserted_ids)
        }
    
    async def _update_one(self, **params) -> Dict[str, Any]:
        """
        Update a single document in a collection.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and update counts
        """
        collection = self.db[params['collection_name']]
        result = await collection.update_one(
            params['filter'],
            params['update'],
            upsert=params.get('upsert', False)
        )
        response = {
            "status": "success",
            "matched_count": result.matched_count,
            "modified_count": result.modified_count
        }
        if result.upserted_id:
            response["upserted_id"] = str(result.upserted_id)
        return response
    
    async def _update_many(self, **params) -> Dict[str, Any]:
        """
        Update multiple documents in a collection.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and update counts
        """
        collection = self.db[params['collection_name']]
        result = await collection.update_many(
            filter=params['filter'],
            update=params['update'],
            upsert=params.get('upsert', False)
        )
        response = {
            "status": "success",
            "matched_count": result.matched_count,
            "modified_count": result.modified_count
        }
        if result.upserted_id:
            response["upserted_id"] = str(result.upserted_id)
        return response
    
    async def _delete_one(self, **params) -> Dict[str, Any]:
        """
        Delete a single document from a collection.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and delete count
        """
        collection = self.db[params['collection_name']]
        result = await collection.delete_one(params['filter'])
        return {"status": "success", "deleted_count": result.deleted_count}
    
    async def _delete_many(self, **params) -> Dict[str, Any]:
        """
        Delete multiple documents from a collection.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and delete count
        """
        collection = self.db[params['collection_name']]
        result = await collection.delete_many(params['filter'])
        return {"status": "success", "deleted_count": result.deleted_count}
    
    async def _count(self, **params) -> Dict[str, Any]:
        """
        Count documents in a collection.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and count
        """
        collection = self.db[params['collection_name']]
        count = await collection.count_documents(params.get('query', {}))
        return {"status": "success", "count": count}
    
    async def _aggregate(self, **params) -> Dict[str, Any]:
        """
        Run an aggregation pipeline on a collection.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and aggregation results
        """
        collection = self.db[params['collection_name']]
        documents = [serializable(doc) async for doc in collection.aggregate(params['pipeline'])]
        
        return {"status": "success", "data": documents, "count": len(documents)}
    
    async def _distinct(self, **params) -> Dict[str, Any]:
        """
        Get distinct values for a field in a collection.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and distinct values
        """
        collection = self.db[params['collection_name']]
        values = await collection.distinct(
            params['key'],
            params.get('query', {})
        )
        return {"status": "success", "data": serializable(values), "count": len(values)}
    
    async def _create_index(self, **params) -> Dict[str, Any]:
        """
        Create an index on a collection.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and index name
        """
        collection = self.db[params['collection_name']]
        index_name = await collection.create_index(
            params['keys'],
            **params.get('options', {})
        )
        return {"status": "success", "index_name": index_name}
    
    async def _drop_index(self, **params) -> Dict[str, Any]:
        """
        Drop an index from a collection.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and operation result
        """
        collection = self.db[params['collection_name']]
        result = await collection.drop_index(params['index_name'])
        return {"status": "success", "result": serializable(result)}
    
    async def _list_indexes(self, **params) -> Dict[str, Any]:
        """
        List indexes on a collection.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and list of indexes
        """
        collection = self.db[params['collection_name']]
        indexes = [serializable(idx) async for idx in collection.list_indexes()]
        return {"status": "success", "indexes": indexes, "count": len(indexes)}
    
    async def _find_one_and_update(self, **params) -> Dict[str, Any]:
        """
        Find a document and update it atomically.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and updated document
        """
        collection = self.db[params['collection_name']]
        return_option = (ReturnDocument.AFTER 
                       if params.get('return_document') == 'after'
                       else ReturnDocument.BEFORE)
        document = await collection.find_one_and_update(
            params['filter'],
            params['update'],
            return_document=return_option,
            upsert=params.get('upsert', False)
        )
        return {"status": "success", "data": serializable(document)}
    
    async def _find_one_and_delete(self, **params) -> Dict[str, Any]:
        """
        Find a document and delete it atomically.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and deleted document
        """
        collection = self.db[params['collection_name']]
        document = await collection.find_one_and_delete(params['filter'])
        return {"status": "success", "data": serializable(document)}
    
    async def _find_one_and_replace(self, **params) -> Dict[str, Any]:
        """
        Find a document and replace it atomically.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and replaced document
        """
        collection = self.db[params['collection_name']]
        return_option = (ReturnDocument.AFTER 
                       if params.get('return_document') == 'after'
                       else ReturnDocument.BEFORE)
        
        document = await collection.find_one_and_replace(
            params['filter'],
            params['replacement'],
            return_document=return_option,
            upsert=params.get('upsert', False)
        )
        
        return {"status": "success", "data": serializable(document)}
    
    async def _bulk_write(self, **params) -> Dict[str, Any]:
        """
        Perform multiple write operations in bulk.
        
        Args:
            params: Operation parameters
            
            
        Returns:
            Dictionary with status and bulk write results
        """
        collection = self.db[params['collection_name']]
        result = await collection.bulk_write(
            params['operations'],
            ordered=params.get('ordered', True)
        )
        return {
            "status": "success",
            "inserted_count": result.inserted_count,
            "matched_count": result.matched_count,
            "modified_count": result.modified_count,
            "deleted_count": result.deleted_count,
            "upserted_count": result.upserted_count,
            "upserted_ids": [str(id) for id in result.upserted_ids.values()] if result.upserted_ids else []
        }
        
    async def run(self, operation: MongoOperation, params: Dict[str, Any]={}) -> Dict[str, Any]:
        """
        Execute a MongoDB operation asynchronously with validation.
        
        This method routes the operation to the appropriate specialized method.
        
        Args:
            operation: The MongoDB operation to perform (from MongoOperation enum)
            params: Parameters for the operation
            
        Returns:
            A standardized response dictionary with operation results
        """
        # try:
            # Validate input parameters
            # validated_params = self._validate_input_params(operation, params)
        
        if operation not in self.operation_map:
            raise ValueError(f"Unsupported operation: {operation}")
        
        result = await self.operation_map[operation](**params)
        
        # Add operation success message if not present
        if 'message' not in result:
            op_name = operation.name.lower().replace('_', ' ')
            result['message'] = f"Operation {op_name} completed successfully"
            
        # Validate output result
        # return self._validate_output_result(operation, result)
        return result
            
        # except Exception as e:
        #     import traceback
        #     error_traceback = traceback.format_exc()
        #     return {
        #         "status": "error", 
        #         "message": str(error_traceback)
        #     }
            

async def main():
    """
    Comprehensive test of all MongoDB operations.
    Starts with creating a collection and ends with dropping it.
    """
    import datetime
    import json
    from pymongo import ASCENDING, DESCENDING, InsertOne, UpdateOne, DeleteOne, ReplaceOne
    from beegen_v1.configs import MongoOperation, MongoConfig
    
    # Initialize the executor with a MongoDB URI and database name
    executor = AsyncMongoEngine(
        config=MongoConfig.default()
    )
    
    # Create a unique collection name using timestamp to avoid conflicts
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    test_collection = f"test_collection_{timestamp}"
    

    print("\n" + "="*80)
    print(f"STARTING MONGO OPERATIONS TEST SUITE ON COLLECTION: {test_collection}")
    print("="*80)
    
    # 1. Database Operations
    print("\n1. --- Database Operations ---")
    
    # List databases
    print(f"Listing existing databases...")
    db_result = await executor.run(MongoOperation.LIST_DATABASES, {})
    print(json.dumps(db_result, indent=2))
    
    # 2. Collection Operations
    print("\n2. --- Collection Operations ---")
    
    print("Creating test collection...")
    # Create collection
    create_result = await executor.run(
        MongoOperation.CREATE_COLLECTION,
        {"name": test_collection, "options": {"capped": False}}
    )
    print(json.dumps(create_result, indent=2))
    
    # List collections - first just list all collections to verify the operation works
    print("Listing all collections...")
    list_all_collections_result = await executor.run(
        MongoOperation.LIST_COLLECTIONS,
        {}  # No filter to get all collections
    )
    print(f"Found {list_all_collections_result['count']} collections.")        

    # Then try to filter for our specific collection
    print(f"Listing collections with filter {test_collection}")
    list_specific_collection_result = await executor.run(
        MongoOperation.LIST_COLLECTIONS,
        {"filter": {"name": test_collection}}
    )
    print(f"Found {list_specific_collection_result['count']} collections.")        
    
    # 3. Document Operations
    print("\n3. --- DOCUMENT OPERATIONS ---")
    
    # Insert one document
    print("insert one document...")
    insert_one_result = await executor.run(
        MongoOperation.INSERT_ONE,
        {
            "document": {
                "name": "John Doe",
                "email": "john.doe@example.com",
                "age": 30,
                "created_at": datetime.datetime.now()
            },
            "collection_name": test_collection
        }
    )
    print(json.dumps(insert_one_result, indent=2))
    
    # Insert many documents
    print("insert many documents...")
    insert_many_result = await executor.run(
        MongoOperation.INSERT_MANY,
        {
            "documents": [
                {
                    "name": "Alice Smith",
                    "email": "alice.smith@example.com",
                    "age": 28,
                    "created_at": datetime.datetime.now(),
                    "tags": ["sales", "marketing"]
                },
                {
                    "name": "Bob Johnson",
                    "email": "bob.johnson@example.com",
                    "age": 35,
                    "created_at": datetime.datetime.now(),
                    "tags": ["engineering", "product"]
                }
            ],
            "collection_name": test_collection
        }
    )
    print(json.dumps(insert_many_result, indent=2))
    
    # Find one document
    print("find one document...")
    find_one_result = await executor.run(
        MongoOperation.FIND_ONE,
        {
            "query": {"name": "John Doe"},
            "collection_name": test_collection
        }
    )
    print(json.dumps(find_one_result, indent=2))
    
    # Find multiple documents
    print("find multiple documents...")
    find_result = await executor.run(
        MongoOperation.FIND,
        {
            "query": {},
            "sort": {"name": 1},
            "collection_name": test_collection
        }
    )
    print(json.dumps(find_result, indent=2))
    
    # Update one document
    print("update one document...")
    update_one_result = await executor.run(
        MongoOperation.UPDATE_ONE,
        {
            "filter": {"name": "John Doe"},
            "update": {"$set": {"status": "active", "last_login": datetime.datetime.now()}},
            "collection_name": test_collection
        }
    )
    print(json.dumps(update_one_result, indent=2))
    
    # Update many documents
    print("update many documents...")
    update_many_result = await executor.run(
        MongoOperation.UPDATE_MANY,
        {
            "filter": {},
            "update": {"$set": {"updated_at": datetime.datetime.now()}},
            "collection_name": test_collection
        }
    )
    print(json.dumps(update_many_result, indent=2))
    
    # Count documents
    print(f"count documents in collection {test_collection}...")
    count_result = await executor.run(
        MongoOperation.COUNT,
        {
            "query": {},
            "collection_name": test_collection
        }
    )
    print(json.dumps(count_result, indent=2))
    
    # 4. Index Operations
    print("\n4. --- INDEX OPERATIONS ---")
    
    print(f"Creating index 'email' in collection {test_collection}")
    # Create index
    create_index_result = await executor.run(
        MongoOperation.CREATE_INDEX,
        {
            "keys": {"email": ASCENDING},
            "options": {"unique": True},
            "collection_name": test_collection
        }
    )
    print(json.dumps(create_index_result, indent=2))
    
    # List indexes
    print(f"Listing indexes in collection {test_collection}")
    list_indexes_result = await executor.run(
        MongoOperation.LIST_INDEXES,
        {"collection_name": test_collection}
    )
    print(json.dumps(list_indexes_result, indent=2))
    
    # 5. Aggregation Operations
    print("\n5. --- AGGREGATION OPERATIONS ---")
    
    # Aggregate
    print("Aggregate ops testing...")
    aggregate_result = await executor.run(
        MongoOperation.AGGREGATE,
        {
            "pipeline": [
                {"$group": {"_id": None, "avg_age": {"$avg": "$age"}}},
                {"$project": {"_id": 0, "avg_age": 1}}
            ],
            "collection_name": test_collection
        }
    )
    print(json.dumps(aggregate_result, indent=2))
    
    # Distinct
    print("Distinct ops testing...")
    distinct_result = await executor.run(
        MongoOperation.DISTINCT,
        {
            "key": "age",
            "collection_name": test_collection
        }
    )
    print(json.dumps(distinct_result, indent=2))
    
    # 6. Atomic Operations
    print("\n6. --- ATOMIC OPERATIONS ---")
    
    # Find one and update
    print("Find one and update testing...")
    find_one_update_result = await executor.run(
        MongoOperation.FIND_ONE_AND_UPDATE,
        {
            "filter": {"name": "Alice Smith"},
            "update": {"$set": {"department": "Marketing"}},
            "return_document": "after",
            "collection_name": test_collection
        }
    )
    print(json.dumps(find_one_update_result, indent=2))
        
    # Find one and replace
    print("Find one and replace testing...")
    find_one_replace_result = await executor.run(
        MongoOperation.FIND_ONE_AND_REPLACE,
        {
            "filter": {"name": "Bob Johnson"},
            "replacement": {
                "name": "Bob Johnson",
                "email": "bob.johnson@example.com",
                "age": 36,  # Changed age
                "department": "Engineering",
                "updated_at": datetime.datetime.now()
            },
            "return_document": "after",
            "collection_name": test_collection
        }
    )
    print(json.dumps(find_one_replace_result, indent=2))
        
    # Find one and delete
    print("Find one and delete testing...")
    find_one_delete_result = await executor.run(
        MongoOperation.FIND_ONE_AND_DELETE,
        {
            "filter": {"name": "John Doe"},
            "collection_name": test_collection
        }
    )
    print(json.dumps(find_one_delete_result, indent=2))
    
    # 7. Bulk Operations
    print("\n7. --- BULK OPERATIONS ---")
    
    # Bulk write
    print("bulk write testing...")
    bulk_write_result = await executor.run(
        MongoOperation.BULK_WRITE,
        {
            "operations": [
                InsertOne({
                    "name": "Charlie Brown",
                    "email": "charlie.brown@example.com",
                    "age": 42,
                    "created_at": datetime.datetime.now()
                }),
                UpdateOne(
                    {"name": "Alice Smith"},
                    {"$set": {"role": "Team Lead"}}
                ),
                ReplaceOne(
                    {"name": "Non-existent User"},
                    {
                        "name": "David Wilson",
                        "email": "david.wilson@example.com",
                        "age": 45,
                        "created_at": datetime.datetime.now()
                    },
                    upsert=True
                ),
                DeleteOne({"name": "Non-existent User"})
            ],
            "ordered": True,
            "collection_name": test_collection
        }
    )
    print(json.dumps(bulk_write_result, indent=2))
    
    # 8. Delete Operations
    print("\n8. --- DELETE OPERATIONS ---")
    
    # Delete one
    print("Delete operation testing...")
    delete_one_result = await executor.run(
        MongoOperation.DELETE_ONE,
        {
            "filter": {"name": "Charlie Brown"},
            "collection_name": test_collection
        }
    )
    print(json.dumps(delete_one_result, indent=2))
    
    # Recount documents
    print("Recount the documents in collection to verify")
    recount_result = await executor.run(
        MongoOperation.COUNT,
        {
            "query": {},
            "collection_name": test_collection
        }
    )
    print(json.dumps(recount_result, indent=2))
    
    # 9. Transaction Operations (if supported by MongoDB deployment)
    print("\n9. --- TRANSACTION OPERATIONS ---")
    # Begin transaction
    print("begin transaction...")
    tx_begin_result = await executor.run(MongoOperation.BEGIN_TRANSACTION, {})
    print(json.dumps(tx_begin_result, indent=2))
    
    # Insert document within transaction
    print("insert document with transaction...")
    session_id = tx_begin_result['session_id']
    tx_insert_result = await executor.run(
        MongoOperation.INSERT_ONE,
        {
            "document": {
                "name": "Transaction Test",
                "email": "tx.test@example.com",
                "age": 50,
                "created_in_transaction": True,
                "created_at": datetime.datetime.now()
            },
            "collection_name": test_collection,
            "session_id": session_id
        }
    )
    print(json.dumps(tx_insert_result, indent=2))
    
    # Update document within transaction
    print("Update document within transaction")
    tx_update_result = await executor.run(
        MongoOperation.UPDATE_ONE,
        {
            "filter": {"name": "Alice Smith"},
            "update": {"$set": {"updated_in_transaction": True}},
            "collection_name": test_collection,
            "session_id": session_id
        }
    )
    print(json.dumps(tx_update_result, indent=2))
    
    # Commit transaction
    print("Commit transaction...")
    tx_commit_result = await executor.run(
        MongoOperation.COMMIT_TRANSACTION,
        {"session_id": session_id}
    )
    print(json.dumps(tx_commit_result, indent=2))
    
    # 10. Collection operations (continued)
    print("\n10. --- COLLECTION OPERATIONS ---")
    # Drop index by name
    print("Drop index by name...")
    if create_index_result['status'] == 'success':
        drop_index_result = await executor.run(
            MongoOperation.DROP_INDEX,
            {
                "index_name": create_index_result['index_name'],
                "collection_name": test_collection
            }
        )
        print(json.dumps(drop_index_result, indent=2))
    
    # Rename collection - commented out for now as it may not be supported in all environments
    # new_collection_name = f"{test_collection}_renamed"
    # rename_result = await executor.run(
    #     MongoOperation.RENAME_COLLECTION,
    #     {
    #         "old_name": test_collection,
    #         "new_name": new_collection_name
    #     }
    # )
    # print(f"RENAME_COLLECTION: {'SUCCESS' if rename_result['status'] == 'success' else 'FAILED'}")
    # if rename_result['status'] == 'success':
    #     print(f"Collection renamed from {test_collection} to {new_collection_name}")
    #     # Update collection name for drop operation
    #     test_collection = new_collection_name
    
    # Finally, drop the collection
    print("Finally, drop the collection...")
    drop_result = await executor.run(
        MongoOperation.DROP_COLLECTION,
        {"name": test_collection}
    )
    print(json.dumps(drop_result, indent=2))
    
    # Summary
    print("\n" + "="*50)
    print("TEST SUMMARY")
    print("="*50)
    print("All MongoDB operations tested.")


async def single_ops():
    _mongo = AsyncMongoEngine(MongoConfig.default())
    result = await _mongo.run(
        MongoOperation.FIND,
        {
            "filter": {},  # Get all documents
            "collection_name": "beegen_registry_configs"
        }
    )
    
    print(result)


if __name__ == "__main__":
    import asyncio
    asyncio.run(single_ops())