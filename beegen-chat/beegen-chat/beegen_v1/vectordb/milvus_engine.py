from beegen_v1.configs import MilvusConfig, MilvusOperation
from typing import (
    Any, 
    Dict, 
    List, 
    Optional, 
    Union
)
from pathlib import Path
from beegen_v1.vectordb.base_vectordb import (
    BaseVectorStore
)

from pymilvus import (
    connections,
    Collection,
    utility,
    DataType
)

from .milvus_collection_factory import MilvusCollectionFactory

import asyncio
from beegen_v1.configs import MILVUS_OPERATION_INPUTS, MILVUS_OPERATIONS_OUTPUTS
from beegen_v1.loggings import LOGGER


class MilvusEngine(BaseVectorStore):
    
    def __init__(self, config: MilvusConfig):
        self.config = config
        # Create the factory, passing only what it needs (the connection alias)
        self.collection_factory = MilvusCollectionFactory(self.config.alias)
        self.collections: Dict[str, Collection] = {}
        self._connect()
        
        # Define operation mappings
        self.operation_map = {
            # Collection operations
            MilvusOperation.SEARCH: self._search,
            MilvusOperation.INSERT: self._insert,
            MilvusOperation.DELETE: self._delete,
            MilvusOperation.QUERY: self._query,
            MilvusOperation.UPSERT: self._upsert,
            MilvusOperation.FLUSH: self._flush,
            MilvusOperation.COMPACT: self._compact,
            
            # Collection management
            MilvusOperation.CREATE_COLLECTION: self._create_collection,
            MilvusOperation.DROP_COLLECTION: self._drop_collection,
            MilvusOperation.LIST_COLLECTIONS: self._list_collections,
            MilvusOperation.HAS_COLLECTION: self._has_collection,
            MilvusOperation.LOAD_COLLECTION: self._load_collection,
            MilvusOperation.RELEASE_COLLECTION: self._release_collection,
            
            # Index operations
            MilvusOperation.CREATE_INDEX: self._create_index,
            MilvusOperation.DROP_INDEX: self._drop_index,
            
            # Partition operations
            MilvusOperation.CREATE_PARTITION: self._create_partition,
            MilvusOperation.DROP_PARTITION: self._drop_partition,
            MilvusOperation.HAS_PARTITION: self._has_partition,
            MilvusOperation.LIST_PARTITIONS: self._list_partitions,
            
            # Information operations
            MilvusOperation.GET_COLLECTION_STATS: self._status,
        }
        
    @classmethod
    def from_path(cls, path: Union[str, Path]) -> 'MilvusEngine':
        """Create a MongoStorage instance from a config file path.
        
        Args:
            path: Path to the mongo config YAML file
            
        Returns:
            MongoStorage: A new instance initialized with the config
        """
        config = MilvusConfig.from_yaml_file(Path(path))
        return cls(config=config)
    
    def _connect(self) -> None:
        """Establish connection to Milvus server."""
        try:
            # Check if connection already exists
            if not connections.has_connection(self.config.alias):
                LOGGER.info(f"Making connect...")
                connections.connect(
                    alias=self.config.alias,
                    uri=self.config.uri,
                    user=self.config.username,
                    password=self.config.password,
                    db_name=self.config.db_name
                )
                LOGGER.info(f"Successfully connected to Milvus at {self.config.uri}")
            else:
                LOGGER.info("Using existing Milvus connection")
        except Exception as e:
            LOGGER.error(f"Failed to connect to Milvus: {str(e)}")
            raise
        
    def _disconnect(self) -> None:
        """Close the connection to Milvus server."""
        try:
            if connections.has_connection(self.config.alias):
                connections.disconnect(self.config.alias)
                LOGGER.info("Disconnected from Milvus server")
        except Exception as e:
            LOGGER.error(f"Error disconnecting from Milvus: {str(e)}")
            raise
    
    ### BASIC USAGE FUNTIONS ###
    
    def _primary_field_of(self, collection_name: str) -> Optional[str]:
        """
        Get the name of the primary key field for a collection.
        
        :param collection_name: Name of the collection
        :return: Name of the primary key field or None if not found
        """
        collection = self._get(collection_name)
            
        schema = collection.schema
        for field in schema.fields:
            if field.is_primary:
                return field.name
                
        return None

    def _vector_field_of(self, collection_name: str) -> Optional[str]:
        """
        Get the name of the vector field for a collection.
        If multiple vector fields exist, returns the first one found.
        
        :param collection_name: Name of the collection
        :return: Name of the vector field or None if not found
        """
        collection = self._get(collection_name)
            
        schema = collection.schema
        vector_types = [DataType.FLOAT_VECTOR, DataType.BINARY_VECTOR, 
                    DataType.FLOAT16_VECTOR, DataType.BFLOAT16_VECTOR, 
                    DataType.SPARSE_FLOAT_VECTOR]
                    
        for field in schema.fields:
            if field.dtype in vector_types:
                return field.name
                
        return None
    
    def _status(self, collection_name) -> Dict[str, Any]:
        r"""Retrieves the current status of the Milvus collection. This method
        provides information about the collection, including its vector
        dimensionality and the total number of vectors stored.

        Returns:
            VectorDBStatus: An object containing information about the
                collection's status.
        """
        collection = self._get(collection_name)
        
        # Get number of entities in the collection
        vector_count = collection.num_entities
        
        # Get collection schema information
        collection_schema = collection.schema
        
        # Find vector field and its dimension
        dim_value = next(
            (
                field.params.get('dim')
                for field in collection_schema.fields
                if field.dtype == DataType.FLOAT_VECTOR
            ),
            None,
        )

        return {
            "status": "success",
            "vector_count": vector_count,
            "vector_dim": dim_value,
            "collection_name": collection_name
        }
    
    def _load(self, collection_name: str, **kwargs) -> Collection:
        """
        Get a collection by name and load it into memory.
        
        Args:
            collection_name (str): name of the collection
        
        Returns:
            Collection: Loaded collection object
        """
        # Verify that a collection exists, raise ValueError if not
        check_has_collection = self._has_collection(collection_name)
        if not check_has_collection['exists']:
            raise ValueError(f"Collection does not exist: {collection_name}")
        
        collection = Collection(collection_name, using=self.config.alias)
        collection.load(**kwargs)
        return collection
        
    def _get(self, collection_name) -> Collection:
        """get the collection, if they're not in cache, append it"""
        collection = None
        if collection_name not in self.collections:
            LOGGER.info(f"Collection {collection_name} loading...")
            self.collections[collection_name] = self._load(collection_name)
        
        collection = self.collections[collection_name]
        return collection
    
    def _reload(self, collection_name) -> Collection:
        self.collections[collection_name] = self._load(collection_name)
    
    ### COLLECTION MANAGEMENT OPERATIONS ###
    def _create_collection(
        self, 
        collection_name: str, 
        fields: List[Dict],
        **kwargs
    ) -> Dict[str, Any]:
        """Create a new collection with specified fields."""
        check_has_collection = self._has_collection(collection_name)
        if check_has_collection['exists']:
            return {"status": "success", "collection_name": collection_name,
                    "message": f"Collection {collection_name} already exists"}
        
        self.collection_factory.create(
            collection_name, 
            fields,
            **kwargs
        )
        
        return {"status": "success", "collection_name": collection_name}
    
    def _drop_collection(self, collection_name: str, **kwargs) -> Dict[str, Any]:
        r"""Deletes an existing collection from the database.
        
        Args:
            collection_name (str): Name of the collection to be deleted.
        """
        check_has_collection = self._has_collection(collection_name)
        
        if not check_has_collection['exists']:
            raise ValueError(f"Collection {collection_name} not exists")
            
        utility.drop_collection(collection_name, using=self.config.alias, **kwargs)
        LOGGER.info(f"Dropped collection: {collection_name}")
        
        return {"status": "success", "collection_name": collection_name}
    
    def _list_collections(self, **kwargs) ->  Dict[str, Any]:
        """List all collections."""
        collections = utility.list_collections(using=self.config.alias, **kwargs)
        return {
            "status": "success",
            "collections": collections
        }

    def _has_collection(self, collection_name: str, **kwargs) ->  Dict[str, Any]:
        """Check if a collection exists in Milvus"""
        result = utility.has_collection(collection_name, using=self.config.alias, **kwargs)
        return {
            "status": "success",
            "exists": result,
            "collection_name": collection_name
        }

    def _load_collection(self, collection_name: str, **kwargs) -> Dict[str, Any]:
        """
        Get a collection by name and load it into memory.
        
        Args:
            collection_name (str): name of the collection
        
        Returns:
            Collection: Loaded collection object
        """
        # Verify that a collection exists, raise ValueError if not
        check_has_collection = self._has_collection(collection_name)
        if not check_has_collection['exists']:
            raise ValueError(f"Collection does not exist: {collection_name}")
        
        collection = Collection(collection_name, using=self.config.alias)
        collection.load(**kwargs)
        return {"status": "success", "collection_name": collection_name}

    def _release_collection(self, collection_name: str, **kwargs) -> None:
        """Release collection from memory"""
        # Verify that a collection exists, raise ValueError if not
        check_has_collection = self._has_collection(collection_name)
        if not check_has_collection['exists']:
            raise ValueError(f"Collection does not exist: {collection_name}")
        
        collection = Collection(collection_name, using=self.config.alias)
        collection.release(**kwargs)
        LOGGER.info(f"Released collection: {collection_name}")
        return {"status": "success", "collection_name": collection_name}

    ### COLLECTION DATA OPERATIONS ###
    def _search(
        self,
        collection_name: str,
        query_vectors: List[List[float]],
        top_k: int = 10,
        threshold: float = None,
        output_fields: List[str] = [],
        metric_type: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Search for similar vectors in the collection."""
        vector_field = self._vector_field_of(collection_name)
        
        collection = self._get(collection_name)
        
        all_fields = {field.name for field in collection.schema.fields}
    
        # If no output fields specified, return all fields
        if not output_fields:
            raise ValueError("There is no output_fields indicated")
        
        # Find invalid fields
        invalid_fields = [field for field in output_fields if field not in all_fields]
        
        if invalid_fields:
            error_msg = f"Invalid output fields requested: {invalid_fields}. Valid fields are: {sorted(all_fields)}"
            LOGGER.error(error_msg)
            raise ValueError(error_msg)
        
        # Use provided metric_type or fall back to config
        if metric_type is None:
            metric_type = self.config.index_params.get('metric_type', 'COSINE')
        
        # Prepare search parameters
        search_params = {
            'metric_type': metric_type,
            'params': self.config.search_params
        }
        
        # Perform the search
        results = collection.search(
            data=query_vectors,
            anns_field=vector_field,
            param=search_params,
            limit=top_k,
            output_fields=output_fields,
            **kwargs
        )
        
        # Process results
        final_results = []
        total_hits = []
        for result in results:
            # Apply threshold filtering if needed
            if threshold:
                filtered_result = [hit for hit in result if hit.distance >= threshold]
            else:
                filtered_result = result
            
            # Format the results
            hits = [
                {
                    "id": hit.id,
                    "distance": hit.distance,
                    **{field: getattr(hit, field) for field in output_fields}
                }
                for hit in filtered_result
            ]
            final_results.append(hits)
            total_hits.append(len(hits))
        
        return {"status": "success", "results": final_results, "total_hits": total_hits}

    def _insert(
        self,
        collection_name: str,
        data: List[Dict],
        **kwargs
    ) -> Dict[str, Any]:
        """Insert data into the collection."""
        collection = self._get(collection_name)
        
        # Insert the data
        result = collection.insert(data, **kwargs)
        
        # Convert RepeatedScalarContainer to a regular Python list
        ids = list(result.primary_keys)
        insert_count = len(ids)
        LOGGER.info(f"Inserted {result.insert_count} entities into collection {collection_name}")
        
        # INSERT → FLUSH → LOAD
        collection.flush()
        self._reload(collection_name)
        return {
            "status": "success",
            "insert_count": insert_count,
            "ids": ids,  # Now this is a regular Python list
            "message": f"Successfully inserted {insert_count} entities"
        }
    
    def _delete(
        self,
        collection_name: str,
        expr: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Delete entities from collection by expression."""
        collection = self._get(collection_name)
        
        result = collection.delete(expr, **kwargs)
        LOGGER.info(f"Deleted entities from collection {collection_name} with expression: {expr}")
        
        # DELETE → FLUSH → COMPACT → LOAD
        collection.flush()
        
        compact = kwargs.get("compact", False)
        if compact:
            collection.compact()
        
        self._reload(collection_name)
        
        return {"status": "success", "delete_count": result.delete_count}
    
    def _query(
        self,
        collection_name: str,
        expr: str = "",
        output_fields: List[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Query data from collection by expression."""
        import json
        collection = self._get(collection_name)
        
        result = collection.query(expr=expr, output_fields=output_fields, **kwargs)
        
        serialize_result = []
        
        for item in result:
            if isinstance(item, dict):
                # Convert any non-serializable values to strings
                clean_item = {}
                for k, v in item.items():
                    try:
                        # Try to serialize the value to test if it's JSON compatible
                        json.dumps(v)
                        clean_item[k] = v
                    except (TypeError, OverflowError):
                        # If serialization fails, convert to string
                        clean_item[k] = str(v)
                serialize_result.append(clean_item)
            else:
                # If it's not a dict, convert the whole item to a string
                serialize_result.append(str(item))
        return {"status": "success", "results": serialize_result, "result_count": len(result)}
    
    def _upsert(
        self,
        collection_name: str,
        data: List,
        **kwargs
    ) -> Dict[str, Any]:
        """Upsert (insert or update) data in the collection."""
        if len(data) == 0:
            LOGGER.warning("No data provided for upsert operation")
            return
        
        collection = self._get(collection_name)
        
        # Find primary key field
        id_field = self._primary_field_of(collection_name)
        
        if not id_field:
            raise ValueError(f"No primary key field found for collection {collection_name}")
        
        # Check if primary key values exist in data
        if id_field not in data[0]:
            raise ValueError(f"ID field '{id_field}' not found in data")
        
        # Use Milvus's native upsert functionality
        result = collection.upsert(data=data,**kwargs)
        
        ids = list(result.primary_keys)
        upsert_count = len(ids)
        
        LOGGER.info(f"Upserted {result.upsert_count} entities into collection {collection_name}")
        
        # UPSERT → FLUSH → LOAD
        collection.flush()
        self._reload(collection_name)
        
        return {"status": "success", "upsert_count": upsert_count, "ids": ids}

    def _flush(self, collection_name: str, **kwargs) -> Dict[str, Any]:
        """Flush collection data to disk."""
        collection = self._load(collection_name)
        
        # FLUSH → LOAD
        collection.flush(**kwargs)
        self._reload(collection_name)
        LOGGER.info(f"Flushed collection {collection_name}")
        return {"status": "success", "collection_name": collection_name}
    
    def _compact(self, collection_name: str, **kwargs) -> Dict[str, Any]:
        """Compact the collection."""
        collection = self._load(collection_name)
        
        # COMPACT → FLUSH (before) → LOAD (after)
        collection.flush()
        collection.compact(**kwargs)
        self._reload(collection_name)
        
        LOGGER.info(f"Compacted collection {collection_name}")
        return {"status": "success", "collection_name": collection_name}
    
    ### INDEX OPERATIONS ###
    def _create_index(
        self,
        collection_name: str,
        field_name: str,
        index_params: Dict = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Create an index on the specified field."""
        collection = Collection(collection_name, using=self.config.alias)
        
        # Use default index parameters if not provided
        if index_params is None:
            index_params = self.config.index_params
        
        # CREATE_INDEX → FLUSH (before) → LOAD (after)
        collection.flush()
        
        # Create index
        collection.create_index(
            field_name=field_name,
            index_params=index_params,
            **kwargs
        )
        
        self._reload(collection_name)
        
        LOGGER.info(f"Created index on field {field_name} in collection {collection_name}")
        return {"status": "success", "collection_name": collection_name, "field_name": field_name}
    
    def _drop_index(
        self,
        collection_name: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Drop the index on the specified field.
        
        Args:
            collection_name (str): The name of the collection
            field_name (str): The name of the field whose index to drop
            **kwargs: Additional parameters for the operation
            
        Raises:
            ValueError: If the collection doesn't exist
        """
        self._release_collection(collection_name)
        collection = Collection(collection_name, using=self.config.alias)
        
        # DROP_INDEX → RELEASE (before)
        collection.drop_index(**kwargs)
                    
        LOGGER.info(f"Dropped index in collection {collection_name}")
        
        return {"status": "success", "collection_name": collection_name}

    ### PARTITION OPERATIONS ###
    def _create_partition(
        self,
        collection_name: str,
        partition_name: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Create a partition in the collection."""
        collection = self._get(collection_name)
        if collection.has_partition(partition_name):
            return {"status": "success", "collection_name": collection_name,
                    "partition_name": partition_name,
                    "message": f"Partition {partition_name} in collection {collection_name} already exists"}
            
        # CREATE_PARTITION → LOAD
        collection.create_partition(partition_name, **kwargs)
        self._reload(collection_name)
        LOGGER.info(f"Created partition {partition_name} in collection {collection_name}")
        return {"status": "success", "collection_name": collection_name, "partition_name": partition_name}
            
    def _drop_partition(
        self,
        collection_name: str,
        partition_name: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Drop a partition from the collection."""
        # DROP_PARTITION → RELEASE → LOAD
        
        # First release the collection from memory
        self._release_collection(collection_name)
        
        collection = Collection(collection_name, using=self.config.alias)
        
        if not collection.has_partition(partition_name):
            raise ValueError(f"partition {partition_name} in collection {collection_name} not existed.")
        
        collection.drop_partition(partition_name, **kwargs)
        self._reload(collection_name)
        LOGGER.info(f"Dropped partition {partition_name} from collection {collection_name}")
                
        return {"status": "success", "collection_name": collection_name, "partition_name": partition_name}
    
    def _has_partition(
        self,
        collection_name: str,
        partition_name: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Check if a partition exists in the collection."""
        check_has_collection = self._has_collection(collection_name)
        if not check_has_collection['exists']:
            raise ValueError(f"collection {collection_name} not existed.")

        collection = self._get(collection_name)

        return {
            "status": "success",
            "exists": collection.has_partition(partition_name),
            "collection_name": collection_name,
            "partition_name": partition_name
        }
    
    def _list_partitions(
        self,
        collection_name: str
    ) -> Dict[str, Any]:
        """List all partitions in the collection."""
        collection = self._load(collection_name)
        
        return {
            "status": "success",
            "partitions": [partition.name for partition in collection.partitions],
            "collection_name": collection_name
        }
    
    def validate_inputs(self, operation: MilvusOperation, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates and merges parameters with defaults for a given operation.
        
        Args:
            operation: The MilvusOperation to validate parameters for
            params: The parameters to validate and merge with defaults
            
        Returns:
            Dict containing validated parameters with defaults applied
            
        Raises:
            ValueError: If operation unknown or required parameters missing
            TypeError: If parameter types don't match specification
        """
        param_set = MILVUS_OPERATION_INPUTS.get(operation)
        if not param_set:
            raise ValueError(f"Unknown operation: {operation}")
            
        try:
            return param_set.validate(params)
        except (ValueError, TypeError) as e:
            raise type(e)(f"Invalid parameters for {operation.name}: {str(e)}")
    
    def validate_outputs(self, operation: MilvusOperation, results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates output results from a given operation and ensures they match expected format.
        
        Args:
            operation: The MilvusOperation that generated the results
            results: The operation results to validate
            
        Returns:
            Dict containing validated results
            
        Raises:
            ValueError: If operation unknown or required output fields missing
            TypeError: If output field types don't match specification
        """
        output_spec = MILVUS_OPERATIONS_OUTPUTS.get(operation)
        if not output_spec:
            raise ValueError(f"Unknown operation: {operation}")
            
        try:
            return output_spec.validate(results)
        except (ValueError, TypeError) as e:
            raise type(e)(f"Invalid results for {operation.name}: {str(e)}")
        

    async def run(
        self,
        operation: MilvusOperation,
        **params,
    ) -> Dict[str, Any]:
        """
        Run a Milvus operation asynchronously.
        
        Args:
            operation (MilvusOperation): The operation to perform
            params (Dict, optional): Parameters for the operation
            
        Returns:
            Dict[str, Any]: A dictionary containing operation results
        """
        try:
            if params is None:
                params = {}

            if operation not in self.operation_map:
                raise ValueError(f"Unsupported operation: {operation}")
            
            func = self.operation_map[operation]
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: func(**params)
            )
            
            # Generate appropriate success message
            if "message" not in result:
                if operation == MilvusOperation.SEARCH:
                    result["message"] = f"Search completed with {sum(result['total_hits'])} total hits"
                elif operation == MilvusOperation.INSERT:
                    result["message"] = f"Successfully inserted {result['insert_count']} entities"
                elif operation == MilvusOperation.DELETE:
                    result["message"] = f"Successfully deleted {result['delete_count']} entities"
                elif operation == MilvusOperation.QUERY:
                    result["message"] = f"Query returned {len(result['results'])} results"
                elif operation == MilvusOperation.LIST_COLLECTIONS:
                    result["message"] = f"Found {len(result['collections'])} collections"
                else:
                    result["message"] = f"Operation {operation} completed successfully"
                    
            return result
        except Exception as e:
            import traceback
            traceback_text = traceback.format_exc()
            LOGGER.error(f"Error during {operation}: {traceback_text}")
            return {
                "status": "error",
                "message": traceback_text
            }


async def test_all_operations():
    """Test all Milvus operations in sequence from collection creation to deletion."""
    import numpy as np
    from time import time
    import json
    
    # Create MilvusExecutor instance
    milvus_exec = MilvusEngine(MilvusConfig.default())
    
    # Test collection name (with timestamp to ensure uniqueness)
    test_collection = f"test_collection_v5"
    vector_dim = 128
    
    print("\n" + "="*80)
    print(f"STARTING MILVUS OPERATIONS TEST SUITE ON COLLECTION: {test_collection}")
    print("="*80)
    
    # STEP 1: LIST_COLLECTIONS - Check existing collections
    print("\n1. Listing existing collections...")
    response = await milvus_exec.run(operation=MilvusOperation.LIST_COLLECTIONS)
    print(json.dumps(response, indent=2))
    
    # STEP 2: CREATE_COLLECTION - Create a test collection
    print("\n2. Creating test collection...")
    create_response = await milvus_exec.run(
        operation=MilvusOperation.CREATE_COLLECTION,
        params={
            "collection_name": test_collection,
            "fields": [
                {"name": "id", "type": "int", "is_primary": True},
                {"name": "vector", "type": "vector", "params": {"dim": vector_dim}},
                {"name": "text", "type": "varchar", "params": {"max_length": 512}},
                {"name": "score", "type": "float"}
            ],
            "description": "Test collection for MilvusStorage operations"
        }
    )
    print(json.dumps(create_response, indent=2))
        
    # STEP 3: HAS_COLLECTION - Verify collection exists
    print("\n3. Verifying collection exists...")
    has_response = await milvus_exec.run(
        operation=MilvusOperation.HAS_COLLECTION,
        params={
            "collection_name": test_collection
        }
    )
    print(json.dumps(has_response, indent=2))
    
    # STEP 4: CREATE_INDEX - Create index on vector field
    print("\n4. Creating index on vector field...")
    index_response = await milvus_exec.run(
        operation=MilvusOperation.CREATE_INDEX,
        params={
            "collection_name": test_collection,
            "field_name": "vector",
            "index_params": {
                "metric_type": "L2",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 128}
            }
        }
    )
    print(json.dumps(index_response, indent=2))
    
    # STEP 5: LOAD_COLLECTION - Load collection into memory
    print("\n5. Loading collection into memory...")
    load_response = await milvus_exec.run(
        operation=MilvusOperation.LOAD_COLLECTION,
        params={
            "collection_name": test_collection
        }
    )
    print(json.dumps(load_response, indent=2))
    
    # STEP 6: CREATE_PARTITION - Create a partition
    print("\n6. Creating partition...")
    partition_name = "test_partition"
    partition_response = await milvus_exec.run(
        operation=MilvusOperation.CREATE_PARTITION,
        params={
            "collection_name": test_collection,
            "partition_name": partition_name
        }
    )
    print(json.dumps(partition_response, indent=2))
    
    # STEP 7: LIST_PARTITIONS - List partitions
    print("\n7. Listing partitions...")
    list_partitions_response = await milvus_exec.run(
        operation=MilvusOperation.LIST_PARTITIONS,
        params={
            "collection_name": test_collection
        }
    )
    print(json.dumps(list_partitions_response, indent=2))
    
    # STEP 8: HAS_PARTITION - Check if partition exists
    print("\n8. Checking if partition exists...")
    has_partition_response = await milvus_exec.run(
        operation=MilvusOperation.HAS_PARTITION,
        params={
            "collection_name": test_collection,
            "partition_name": partition_name
        }
    )
    print(json.dumps(has_partition_response, indent=2))
    
    # STEP 9: INSERT - Insert data    
    print("\n9. Inserting data...")
    num_entities = 10
    insert_data = [
        {
            "id": 100 + i,  # Assigning unique int64 IDs starting from 100
            "vector": np.random.rand(vector_dim).tolist(),  # Convert numpy array to list
            "text": f"Text document {i}",  # Text field
            "score": float(np.random.random())  # Convert numpy float to native float
        }
        for i in range(num_entities)
    ]
        
    insert_response = await milvus_exec.run(
        operation=MilvusOperation.INSERT,
        params={
            "collection_name" :test_collection,
            "data": insert_data,
            "partition_name": partition_name
        }
    )
    print(insert_response)
    print(json.dumps(insert_response, indent=2))

    # STEP 10: FLUSH - Flush data to make it searchable
    print("\n10. Flushing collection...")
    flush_response = await milvus_exec.run(
        operation=MilvusOperation.FLUSH,
        params={
            "collection_name" :test_collection
        }
    )
    print(json.dumps(flush_response, indent=2))
    
    # STEP 11: GET_COLLECTION_STATS - Get collection statistics
    print("\n11. Getting collection statistics...")
    stats_response = await milvus_exec.run(
        operation=MilvusOperation.GET_COLLECTION_STATS,
        params={
            "collection_name": test_collection
        }
    )
    print(json.dumps(stats_response, indent=2))
    
    # STEP 12: SEARCH - Search for vectors
    print("\n12. Searching for vectors...")
    query_vector = np.random.rand(vector_dim).tolist()
    search_response = await milvus_exec.run(
        operation=MilvusOperation.SEARCH,
        params={
            "collection_name" :test_collection,
            "query_vectors": [query_vector],
            "top_k": 3,
            "output_fields": ["id", "text", "score"],
            "partition_names": [partition_name],
            "metric_type": "L2"
        }
    )
    print(json.dumps(search_response, indent=2))
    
    # STEP 13: QUERY - Query data by expression
    print("\n13. Querying data...")
    query_response = await milvus_exec.run(
        operation=MilvusOperation.QUERY,
        params={
            "collection_name" :test_collection,
            "expr": "id in [100, 101, 102]",
            "output_fields": ["id", "text", "score"]
        }
    )
    print(json.dumps(query_response, indent=2))
        
    # STEP 14: UPSERT - Upsert (update and insert) data
    print("\n14. Upserting data...")
    # Update existing records and add new ones
    upsert_data = [
        {
            "id": _id,  # Assigning unique int64 IDs starting from 100
            "vector": np.random.rand(vector_dim).tolist(),  # Convert numpy array to list
            "text": f"Updated text {_id}",  # Text field
            "score": float(np.random.random())  # Convert numpy float to native float
        }
        for _id in [100, 101, 200, 201]
    ]
    
    upsert_response = await milvus_exec.run(
        operation=MilvusOperation.UPSERT,
        params={
            "collection_name" :test_collection,
            "data": upsert_data
        }
    )
    
    print(json.dumps(upsert_response, indent=2))
    
    # STEP 15: QUERY - Verify upsert results
    print("\n15. Verifying upsert results...")
    verify_response = await milvus_exec.run(
        operation=MilvusOperation.QUERY,
        params={
            "collection_name" :test_collection,
            "expr": "id in [100, 101, 200, 201]",
            "output_fields": ["id", "text", "score"]
        }
    )
    print(json.dumps(verify_response, indent=2))
        
    # STEP 16: DELETE - Delete some entities
    print("\n16. Deleting entities...")
    delete_response = await milvus_exec.run(
        operation=MilvusOperation.DELETE,
        params={
            "collection_name" :test_collection,
            "expr": "id in [100, 101]"
        }
    )
    print(json.dumps(delete_response, indent=2))
    
    # STEP 17: COMPACT - Compact collection after deletion
    print("\n17. Compacting collection...")
    compact_response = await milvus_exec.run(
        operation=MilvusOperation.COMPACT,
        params={
            "collection_name" :test_collection
        }
    )
    print(json.dumps(compact_response, indent=2))
    
    # STEP 18: DROP_PARTITION - Drop the test partition
    print("\n18. Dropping partition...")
    drop_partition_response = await milvus_exec.run(
        operation=MilvusOperation.DROP_PARTITION,
        params={
            "collection_name" :test_collection,
            "partition_name": partition_name
        }
    )
    print(json.dumps(drop_partition_response, indent=2))
    
    # STEP 19: DROP_INDEX - Drop the index
    print("\n19. Dropping index...")
    drop_index_response = await milvus_exec.run(
        operation=MilvusOperation.DROP_INDEX,
        params={
            "collection_name" :test_collection
        }
    )
    print(json.dumps(drop_index_response, indent=2))
    
    # STEP 20: RELEASE_COLLECTION - Release the collection from memory
    print("\n20. Releasing collection...")
    release_response = await milvus_exec.run(
        operation=MilvusOperation.RELEASE_COLLECTION,
        params={
            "collection_name" :test_collection
        }
    )
    print(json.dumps(release_response, indent=2))
    
    # STEP 21: DROP_COLLECTION - Drop the test collection
    print("\n21. Dropping test collection...")
    drop_response = await milvus_exec.run(
        operation=MilvusOperation.DROP_COLLECTION,
        params={
            "collection_name" :test_collection
        }
    )
    print(json.dumps(drop_response, indent=2))
    
    # Verify collection no longer exists
    verify_drop = await milvus_exec.run(
        operation=MilvusOperation.HAS_COLLECTION,
        params={
            "collection_name" :test_collection
        }
    )
    print(json.dumps(drop_response, indent=2))
    
    print("\n" + "="*80)
    print("MILVUS OPERATIONS TEST COMPLETED SUCCESSFULLY")
    print("="*80)
    

async def single_operation():
    import time
    
    query_vectors = [
        [-0.024514776, -0.021215761, -0.027467486, -0.06244433, 0.02289261, 0.024697043, -0.033828568, -0.060475856, 0.02289261, -0.001073091, -0.022418717, 0.015365023, -0.008329556, 0.050815757, -0.01447192, -0.033719208, 0.054278813, -0.0053950734, -0.045420684, -0.0015298952, 0.041629553, -0.008479926, 0.008958373, -0.012394087, 0.028178323, 0.0032215514, 0.003836699, -0.029144332, -0.009960837, 0.022181772, -0.014590393, 0.010152216, -0.02952709, -0.017406402, 0.0073544327, 0.0025631154, 0.03654433, -0.058871917, -0.06062167, -0.037729062, -0.006142364, 0.09302856, 0.02342118, -0.03184187, -0.0014695196, -0.0109086195, 0.011036206, -0.008315886, -0.019739408, -0.017461082, -0.004971305, -0.037164036, -0.015884481, 0.023658127, 0.012776846, 0.08005122, 0.0005382543, 0.0097421175, -0.026683742, -0.013688176, -0.024624135, -0.024915762, 0.063975364, 0.06368374, 0.01077192, 0.078301474, 0.030292608, -0.010790147, 0.014362561, -0.025225613, -0.06404827, 0.04432709, -0.06452216, -0.03269852, -0.032662068, -0.00538596, 0.06736551, -0.008420689, 0.008566502, 0.0022179494, 0.063647285, 0.015756896, -0.027595071, -0.0011972598, -0.020176845, 0.03638029, -0.01999458, 0.047389157, -0.0018841748, -0.010498521, 0.053622656, 0.00892192, 0.0050943345, -0.026902461, -0.06266305, -0.015911821, -0.03639852, 0.01607586, 0.023603447, -0.004235406, -0.009108743, -0.00999729, -0.0089766, -0.036799505, 0.022017732, 0.053513296, 0.03922364, 0.0097330045, -0.013888669, 0.004226293, -0.020176845, 0.0035108987, 0.026392115, 0.01817192, -0.04873793, -0.007664285, -0.0072541866, -0.017133003, 0.044946793, 0.02637389, 0.007851108, 0.0015093903, -0.015374136, -0.03907783, -0.014508373, -0.07152118, 0.031094579, -0.010061082, -0.036307387, 0.04228571, -0.027266992, 0.044618715, -0.021890147, -0.022236452, 0.031167485, -0.01157389, 0.0097421175, 0.019575369, 0.036690146, -0.03634384, 0.017552216, 0.051034477, 0.0022555417, 0.0065387925, -0.016786698, -0.018099014, 0.007846551, 0.03145911, -0.042103443, -0.0055363295, 0.0088672405, 0.029071426, -0.0046523395, 0.009851477, -0.023658127, -0.07604137, -0.022710342, -0.009459605, -0.055080783, 0.004347044, 0.015529063, 0.032607388, -0.011364285, 0.034794576, 0.00027382618, -0.028688667, -0.007855664, 0.017807387, -0.007869334, -0.009040393, -0.001921767, 0.008703201, 0.025790637, -0.0004881311, 0.02261921, 0.0213798, 0.07698916, 0.04910246, -0.0040440266, -0.008853571, -0.06590738, -0.0006037561, -0.035614774, -0.011418965, -0.044946793, 0.050961573, 0.023220688, -0.02303842, 0.025663052, 0.037109356, -0.0045452584, -0.009414039, 0.009341132, -0.02899852, 0.013241624, 0.03838522, 0.008694088, -0.03849458, -0.06084039, -0.018162806, -0.046988174, 0.01983054, 0.031823643, 0.016950738, -0.0035450736, 
-0.03269852, -0.019794088, -0.01941133, -0.040645316, -0.026610835, -0.006388423, -0.03350049, 0.07852019, 0.050998025, -0.04571231, -0.0060102213, 0.023913298, -0.006730172, 0.021197535, -0.03882266, -0.020869456, 0.020504924, -0.0038184726, -0.016741132, 0.012585467, 0.0034379924, 0.026665514, 0.021780787, -0.054205906, 0.005818842, 0.00542697, 0.02593645, -0.023111328, 0.013660836, 0.03278965, 0.026337435, -0.013369211, -0.027649751, 0.04571231, 0.0023045256, -0.08573792, 0.0027863914, 0.04902955, -0.034612313, -0.045748763, 0.03665369, -0.037619703, 0.04640492, 0.00980591, 0.05788768, 0.016859604, -0.00086462434, -0.001282697, -0.038348764, 0.06073103, 0.016066747, 0.010079309, -0.010006403, 0.019684728, 0.0069306646, 0.012503447, 0.027522165, 0.015100738, 0.043743838, -0.035468962, 0.022090638, -0.018190145, -0.015428816, -0.012193595, 0.030948766, -0.030055663, -0.0162399, 0.015966501, -0.01792586, 0.005786945, 0.02079655, 0.005773275, -0.018436205, -0.015620195, 0.032516252, 0.00049553567, 0.0065387925, 0.006105911, -0.0035997534, 0.02112463, 0.035560094, -0.08384236, -0.019648274, -0.029818717, 0.013141378, -0.01077192, 0.00032580047, 0.060402952, 0.019958127, 0.022236452, 0.024059111, -0.013970689, -0.12962757, 0.039150737, 0.008552832, 0.011510097, -0.010571428, -0.013715516, -0.0138066495, 0.007591379, -0.0143990135, -0.043598026, 0.04239507, -0.032024134, -0.0216532, 0.05274778, 0.03233399, -0.033646304, 0.016476845, 0.02739458, 0.024970442, -0.029891623, -0.026173396, -0.023220688, -0.012576354, -0.02888916, -0.006119581, -0.018828077, 0.053367484, 0.020942362, -0.03612512, 0.0015595134, 0.020286204, 0.06561576, -0.0041374383, 0.037309848, 0.043889653, 0.025407879, -0.009117857, -0.02256453, -0.025663052, -0.0023922413, -0.03504975, 0.009095073, 0.026793102, 0.002936761, 0.04892019, -0.01358793, 0.00899027, -0.016285466, -0.009281896, -0.021999506, -0.03907783, 0.029235465, -0.01961182, -0.010015517, -0.0011010005, -0.043488666, -0.0046523395, 0.016084975, 0.0048528323, -0.04512906, -0.017652461, 0.03237044, 0.023876846, 0.066271916, -0.0027795564, 0.0067073884, 0.018490884, -0.021634974, 0.024587683, 0.028743347, 0.0026451352, -0.06707389, 0.026136944, -0.031076351, 0.014891132, 0.032935467, 0.028816253, -0.026355663, 0.0180899, -0.09208078, -0.054315265, 0.009377586, -0.009906157, 0.07330738, 0.020122165, 0.012038669, -0.0026451352, 0.0077098515, 0.02433251, 0.20953299, -0.018773397, -0.0145266, 0.04491034, 0.0649596, -0.017369948, -0.01088128, -0.015401476, -0.025571918, -0.007910344, -0.037018225, -0.012084235, 0.020814776, 
0.017998766, -0.020650737, -0.032498028, -0.03585172, -0.01151921, 0.043999013, -0.031878322, 0.034120195, 0.026228076, -0.0028547412, -0.0052902703, 0.018718718, -0.062699504, 0.019848768, 0.05912709, -0.006716502, 0.06423054, -0.041520193, -0.048482753, -0.010234236, 0.0062016007, -0.012020443, -0.02593645, 0.012384974, -0.022199998, 0.016413053, 0.022491625, -0.029071426, -0.043926105, 0.027358126, 0.008917363, 0.03853103, 0.043379307, -0.001991256, 0.0057231523, -0.025189161, -0.00074501225, -0.023731032, 0.026246304, -0.039916255, 0.00900394, -0.0016415331, -0.021926599, 0.005048768, 0.00013185806, 0.008484482, -0.0074820193, 0.028451722, 0.0322064, -0.00037222134, 0.040499505, -0.013469457, 0.0054360833, -0.019794088, 0.005572783, -0.008657635, -0.034393594, 0.049649257, 0.004157943, 0.020596057, 0.042212803, 0.06546994, 0.027102953, 0.029727584, 0.021562068, -0.0042513544, -0.005759605, -0.016495073, 0.014125614, -0.036781278, 0.00986059, -0.020650737, -0.028761573, -0.037164036, 0.050305415, -0.037801966, 0.0033468592, 0.045420684, -0.031058125, 0.027212312, 0.043452214, 0.05267487, -0.029034972, 0.0809261, -0.002804618, -0.02927192, 0.0111911325, 0.06696453, -0.024204925, -0.0005596136, -0.0029390391, -0.027795564, 0.08741477, 0.026884234, 0.039733987, 0.025280293, 0.0006675492, -0.010279802, 0.0005917949, -0.064813785, 0.03463054, 0.012220935, 0.03226108, -0.041738912, 0.0129499985, 0.026082264, 0.012439654, -0.024150245, -0.0149822645, -0.076333, -0.012685713, 0.016495073, 0.0138066495, -0.017561328, 0.0016859605, -0.0028980293, 0.029381279, -0.03656256, 
-0.00091189955, -0.019976353, -0.028433494, 0.024879308, -0.022218226, 0.0036726599, 0.018490884, -0.05278423, 0.03634384, 0.025262067, -0.06583448, -0.0043926104, 0.0015196428, -0.019958127, -0.02593645, 0.013733743, 0.008830788, 0.025772411, 0.009035837, -0.018882757, -0.02347586, -0.049867976, -0.014007142, -0.03206059, -0.0022600982, -0.008438916, -0.021671427, 0.08581083, -0.0387133, -0.034484725, -0.019283742, 0.0035792484, 0.031768963, 0.0019673335, 0.060366496, -0.0060330043, 0.06896945, 0.04454581, -0.028451722, 0.030073889, -0.040900487, -0.041301474, 0.009614531, 0.049539898, 0.042796057, -0.003807081, -0.01353325, -0.01897389, -0.016713792, 0.008388792, 0.012293842, -0.006775738, 0.062189158, 0.01643128, 0.05128965, 0.057632506, -0.021780787, 0.014070935, 0.014754432, 0.019393101, 0.047243346, 0.008671304, 0.0063656396, -0.0031349752, 0.008648521, -0.09208078, -0.036744826, 0.014854679, -0.022309357, 0.04935763, -0.054533985, 0.017242363, -0.032516252, 0.061678812, 0.015000491, -0.008334112, -0.013132265, 0.028779801, -0.005841625, -0.02159852, 0.022582756, 0.03322709, -0.04512906, -0.016331034, -0.012512561, -0.011883743, -0.005272044, 0.050268963, -0.004394889, 
-0.008621181, 0.02068719, 0.013259851, -0.067985214, -0.017451968, -0.008520936, -0.023494087, -0.03269852, 0.054205906, 0.012694826, 0.018718718, 0.013159605, -0.028287683, -0.034266006, -0.033299997, 0.008785221, -0.0066435956, 0.00824298, -0.007040024, -0.022418717, -0.00035769702, 0.018791623, 0.020814776, 0.039260097, -0.012202708, 0.03178719, -0.016804924, 0.030401967, 0.0085756155, 0.020559603, -0.009933497, 0.00076893467, 0.015137191, -0.03709113, -0.07163054, -0.044181276, -0.015866255, -0.008912807, -0.036854185, 0.002980049, -0.046988174, -0.015365023, -0.04684236, 0.0027499383, 
-0.0586532, -0.00041864222, 0.033682756, -0.0018260775, -0.021853693, -0.03634384, 0.01264926, -0.01460862, -0.032078814, -0.045530044, -0.041046303, 0.017524876, -0.01935665, -0.048154674, -0.043561574, 0.03639852, -0.016139654, -0.0056548025, 0.0021837745, 0.008502709, -0.01908325, -0.0006390701, 0.03911428, 0.015957387, -0.025079802, -0.0048254924, -0.03543251, 0.038676843, -0.025025122, 0.026392115, -9.3838506e-05, -0.020085713, -0.07283349, 0.012968225, -0.043598026, 0.0111911325, -0.028761573, 0.027832018, -0.07932216, 0.008028817, -0.005504433, 0.07024531, -0.034193102, -0.004171613, 0.054606892, 0.02723054, -0.009468718, -0.01720591, 0.004087315, -0.02803251, 0.0180899, 0.026793102, -0.013733743, 0.0047662556, 0.019429555, -0.010434728, -0.013214285, 0.005130788, -0.0009529094, -0.0003633928, 0.03227931, -0.03510443, -0.0024765392, -0.030438421, 0.010562315, 0.016312806, -0.03860394, -0.011355171, -0.0011733373, -0.021689653, -0.012822413, 0.0035610218, 0.024788175, -0.011892856, 0.045530044, -0.009769457, 0.011218472, 0.005504433, 0.016440393, -0.011592117, 0.031805415, -0.008616625, 0.020322658, 0.018153694, 0.052383248, -0.007586822, 0.012293842, 0.00723596, -0.0009341132, -0.043889653, -0.024533004, -0.0018807573, -0.011555664, 0.02927192, 0.012685713, -0.03333645, -0.025553692, -0.013341871, 0.016932512, 0.0029322042, 0.02941773, -0.023074875, -0.021233989, 
-0.037656154, -0.052237432, -0.050451227, 0.008083497, 0.006875985, -0.0649596, 0.0054497533, -0.018773397, 0.04228571, 0.004636391, -0.04206699, 0.010972413, -0.0026041253, -0.025553692, -0.03654433, -0.017096551, -0.051799994, 0.025371427, -0.006570689, -0.008762438, -0.037984233, 0.018664038, -0.015647536, 0.008452586, -0.013916009, -0.03827586, 0.012457881, -0.11307782, -0.023238914, 0.05263842, -0.02728522, -0.05344039, -0.029363051, 0.035359602, 0.03537783, 0.009304679, -0.011856403, -0.028743347, -0.006192487, -0.030310836, 0.008994827, -0.0120660085, -0.0144081265, 0.01551995, -0.020614283, -0.026136944, 0.007769088, -0.047899503, 0.004595381, -0.012494334, -0.009236329, 0.08311329, -0.031331524, 0.025717732, 0.06178817, -0.030237928, -0.02117931, -0.017934974, 0.030529555, 0.023566993, 0.026574383, 0.004128325, -0.020723643, -0.00018639545, 0.0140982745, -0.00039557417, -0.024314284, 0.060402952, 0.022528077, 0.004636391, -0.07257832, -0.013970689, 0.01819926, 0.011391625, -0.009568965, -0.055919208, -0.006834975, -0.018044334, 0.02921724, -0.029946303, -0.04888374, 0.013323644, -0.046915267, 0.016932512, 0.03783842, 0.030474875, 0.030584235, -0.013305417, 0.0055636694, 0.009623645, -0.010671674, -0.018190145, 0.019976353, -0.046915267, -0.033464037, -0.044728074, 0.0032716745, 0.036635466, -0.025262067, 0.031823643, -0.035778813, 0.024132017, 0.023275368, 0.04840985, -0.009505171, -0.0078100977, 0.002588177, -0.02267389, 0.017060097, -0.021981278, 0.038676843, -0.013542363, -0.011182019, 0.022965515, -0.060913295, 0.03537783, 0.0161032, -0.025553692, -0.033354677, 0.015255664, 0.021744333, -0.052128073, 0.021361575, -0.03977044, -0.032625612, -0.040754676, -0.026975367, -0.031058125, -0.024132017, -0.025571918, 0.003371921, -9.163138e-05, -0.004212623, -0.010498521, -0.03145911, 0.012995565, 0.034193102, 0.028870933, 0.0046249996, 0.01063522, 0.00025047336, 0.028050736, 0.023913298, -0.007732635, -0.011619457, -0.014845565, -0.0043584355, 0.0063519697, 0.024095565, -0.029873397, -0.027667979, -0.0015412868, 0.044800982, 0.0025767854, 0.028287683, 0.034685217, -0.056903444, 0.024478324, -0.053258125, -0.047462065, -0.00016574813, -0.0024309726, 0.0145266, 0.025043348, 0.033846796, -0.018044334, -0.030784726, 0.010097536, -0.009760344, -0.021744333, -0.011008866, -0.0025858989, 0.016030295, -0.055554677, -0.032133494, -0.038786203, 0.01549261, 0.020577831, 0.003752401, -0.017032757, -0.027740885, 0.08828965, -0.0031121918, -0.022983741, 0.024933988, 0.02593645, 0.034502953, 0.030511327, -0.041666005, -0.02888916, -0.047498517, 0.018736944, 0.009368472, -0.010872167, -0.026009357, -0.026537929, -0.016367486, 0.002882081, -0.033901475, -0.023822166, 0.052018713, -0.004593103, -0.011455418, 0.026902461, 0.012986452, 0.028962066, -0.008115393, 0.024113791, 0.015939161, 0.0040417486, 0.0054998766, 0.017998766, 0.015228324, -0.033427585, -0.0027772782, 0.0066800485, -0.0129499985, 0.0129408855, -0.0068942113, 0.07137536, 0.0054862066, 0.0100337425, 0.017142117, 0.009906157, 0.04352512, -0.06448571, 0.053804923, -0.03233399, -0.028469948, -0.01983054, -0.04421773, 0.030894086, 0.0006339439, 0.018408865, -0.03692709, -0.007231403, 0.044582263, -0.016440393, -0.011583004, -0.011245812, 0.0073954426, 0.001086761, 0.04192118, 0.016932512, 0.0062152706, 0.055882756, -0.029435959, -0.009117857, 0.016012067, -0.018600244, -0.02079655, 0.0069169947, 0.0062016007, 0.016166994, 0.027266992, -0.012922659, -0.024733495, -0.008411576, 0.041848272, -0.023986205, 0.05263842, 0.03548719, -0.023639899, 0.01366995, -0.011911083, -0.031714283, -0.053768467, -0.0040349136, 0.03300837, -0.009231772, -0.041155662],
    ]
    
    milvus_exec = MilvusEngine(MilvusConfig.default())
    
    start_time = time.time()
    result = await milvus_exec.run(
        operation=MilvusOperation.SEARCH,
        query_vectors = query_vectors,
        collection_name = "bot_da498399_56c2_479f_80c6_b79e605dcd66",
        output_fields = ["chunk_id", "role"],
        top_k = 20
    )
    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"search successfully in {elapsed_time:.2f} seconds")


if __name__ == "__main__":
    asyncio.run(single_operation())