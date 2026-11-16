from pymilvus import MilvusClient, DataType

import numpy as np
from typing import List
import traceback
from pymilvus import Collection, connections


class MilvusDB:
    def __init__(
        self,
    ):
        self.host = "10.215.254.90"
        self.port = "19530"
        self.db_name = "chatbot_memory"
        self.collection_name = "archived_memory"
        self.dim = 1024
        self.index_params = {
            "index_type": "IVF_FLAT",
            "metric_type": "COSINE",
            "params": {"nlist": 1024}
        }
        self.username = "chatbot_memory_user"
        self.password = "MBQAZWSXEDC"
        
        self.partition_actors = ['user', 'assistant']

        self.client = self._connect()
        self._create_collection()
        
        self.client.load_collection(collection_name=self.collection_name)

    def _connect(self) -> MilvusClient:
        """Establish connection to Milvus server."""
        try:
            # First connect to default database
            client = MilvusClient(
                uri=f'http://{self.host}:{self.port}',
                token=f"{self.username}:{self.password}",
                db_name="default"
            )
            
            # databases = client.list_databases()
            # if self.db_name not in databases:
            # try:
            #     client.create_database(self.db_name)
            #     print(f"Created database: {self.db_name}")
            # except:
            #     print(f"No create database {self.db_name}")
            
            client = MilvusClient(
                uri=f'http://{self.host}:{self.port}',
                token=f"{self.username}:{self.password}",
                db_name=self.db_name
            )
            
            print(f"Successfully connected to Milvus server at {self.host}:{self.port} and database {self.db_name}")
            return client
        except Exception as e:
            raise e

    def _create_collection(self):
        """Create collection if it doesn't exist."""
        try:
            if not self.client.has_collection(self.collection_name):

                schema = MilvusClient.create_schema(auto_id=True, enable_dynamic_field=True)

                # Add fields to schema
                schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
                schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=self.dim)
                schema.add_field(field_name="content", datatype=DataType.VARCHAR, max_length=65535)
                schema.add_field(field_name="metadata", datatype=DataType.JSON)

                # Create collection
                self.client.create_collection(
                    collection_name=self.collection_name,
                    schema=schema,
                    consistency_level="Strong"
                )

                # Create index
                index_params = self.client.prepare_index_params()

                index_params.add_index(
                    field_name="vector",
                    index_type=self.index_params['index_type'],
                    metric_type=self.index_params["metric_type"],
                    params={"nlist": self.index_params["params"]["nlist"]}
                )

                # Apply index to collection
                self.client.create_index(
                    collection_name=self.collection_name,
                    index_params=index_params
                )
                print(f"Created collection: {self.collection_name}")
            else:
                print(f"Collection {self.collection_name} already exists")
        except Exception as e:
            raise e
        
    def create_partition(self, partition_name: str):
        try:
            if not self.client.has_partition(
                collection_name=self.collection_name,
                partition_name=partition_name
            ):
                self.client.create_partition(
                    collection_name=self.collection_name,
                    partition_name=partition_name
                )
                print(f"Created partition: {partition_name}")
            else:
                print(f"Partition {partition_name} already exists")
        except Exception as e:
            raise e

    def insert_data(self, vectors: list, contents: list, metadata_list: list, partition_name: str = None):
        try:
            if not (len(vectors) == len(contents) == len(metadata_list)):
                raise ValueError("Length of vectors, contents, and metadata must match")
            
            data = [
                {
                    "vector": vector,
                    "content": content,
                    "metadata": metadata
                }
                for vector, content, metadata in zip(vectors, contents, metadata_list)
            ]
            
            if partition_name:
                self.create_partition(partition_name)
            
            result = self.client.insert(
                collection_name=self.collection_name,
                data=data,
                partition_name=partition_name
            )
            
            print(f"Successfully inserted {len(vectors)} records")
            if partition_name:
                print(f"Into partition: {partition_name}")
                
            return result
            
        except Exception as e:
            raise e
        
    def search_top_n(self, query_embeddings: List[List[float]], top_k: int = 5, partition_name: str = None) -> List[dict]:
        try:
            if not self.client.has_partition(
                    collection_name=self.collection_name,
                    partition_name=partition_name
                ):
                return []
            search_params = {
                "metric_type": self.index_params["metric_type"],
                "params": {"nprobe": self.index_params["params"]["nlist"] // 4}  # Common practice to set nprobe to nlist/4
            }

            # Prepare output fields
            output_fields = ["content", "metadata"]

            # Execute search
            search_results = self.client.search(
                collection_name=self.collection_name,
                data=query_embeddings,
                output_fields=output_fields,
                field_name="vector",
                search_params=search_params,
                limit=top_k,
                partition_names=[partition_name]
            )
            # Process and format results
            formatted_results = []
            for hits in search_results:
                matches = []
                for hit in hits:
                    match = {
                        "id": hit['id'],
                        "distance": hit['distance'],
                        "content": hit['entity'].get("content"),
                        "metadata": hit['entity'].get("metadata")
                    }
                    matches.append(match)
                formatted_results.append(matches)
                
            return formatted_results

        except Exception as e:
            print(f"Error during search: {str(e)}")
            print(traceback.format_exc())
            raise e
        
    def search_by_user_id(self, user_id: str, query_embeddings: List[float], top_n: int, suffix: str = "archived"):
        result = {}
        
        for actor in self.partition_actors:
            partition_name = f"{user_id}_{actor}_{suffix}"
            try:
                partition_data = self.search_top_n(
                    partition_name=partition_name, 
                    query_embeddings=[query_embeddings], 
                    top_k=top_n)[0]
                archived_mem = [t['content'] for t in partition_data]
                result[actor] = archived_mem
                
            except:
                # ChatbotLogger.get_logger().warn(f"Error while search {actor} - {suffix} for user {user_id}")
                pass
                
        return result
    
    def get_all_user_content(self, user_id: str, suffix: str = "archived") -> List[str]:
        try:
            final_result = {}
            
            for actor in self.partition_actors:
                partition_name = f"{user_id}_{actor}_{suffix}"
                if not self.client.has_partition(self.collection_name, partition_name):
                    continue
                
                # Query to retrieve all records in the partition
                query_results = self.client.query(
                    collection_name=self.collection_name,
                    partition_names=[partition_name],
                    output_fields=["content"],
                    limit=100
                )
                
                # Extract content from query results
                partition_content = [
                    result.get("content", "") for result in query_results
                ]
                final_result[actor] = partition_content
            
            return final_result
        except Exception as e:
            print(f"Error while fetching user content: {str(e)}")
            print(traceback.format_exc())
            raise e

                
        
    def delete_by_ids(self, ids: List[int], partition_name: str):
        print(f"Deleting id: {ids}")
        if ids:
            try:
                # Check if partition exists
                if not self.client.has_partition(
                    collection_name=self.collection_name,
                    partition_name=partition_name
                ):
                    raise ValueError(f"Partition {partition_name} does not exist")
                
                # Delete records by their IDs
                self.client.delete(
                    collection_name=self.collection_name,
                    partition_name=partition_name,
                    ids=ids
                )
                
                print(f"Successfully deleted {len(ids)} records from partition {partition_name}\nDeleted ids: {ids}")
                
            except Exception as e:
                print(f"Error deleting records: {str(e)}")
                raise e

    def close(self):
        """Close connection to Milvus server."""
        try:
            if hasattr(self, 'client'):
                self.client.close()
                print("Disconnected from Milvus server")
        except Exception as e:
            print(f"Error disconnecting from Milvus server: {str(e)}")
            
if __name__ == "__main__":
    # Initialize the database
    db = MilvusDB()
    
    # Create some sample data
    # Let's create 5 sample vectors of dimension 8 (matching your nlist dimension)
    dimension = 1024  # This should match your config.index_config.params.nlist
    num_vectors = 5
    
    # Generate random vectors for testing
    vectors = [
        np.random.rand(dimension).tolist() for _ in range(num_vectors)
    ]
    
    # Create sample contents
    contents = [
        f"This is test document {i}" for i in range(num_vectors)
    ]
    
    # Create sample metadata
    metadata_list = [
        {"timestamp": f"2024-01-{i+1}", "category": f"category_{i}"} 
        for i in range(num_vectors)
    ]
    
    # Test insert
    print("\nTesting insert...")
    try:
        result = db.insert_data(
            vectors=vectors,
            contents=contents,
            metadata_list=metadata_list,
            partition_name="test_partition"
        )
        print("Insert result:", result)
    except Exception as e:
        print(f"Error during insert: {str(e)}")
    
    # Load the collection
    db.client.load_collection(db.collection_name)
    
    # Test search
    print("\nTesting search...")
    try:
        # Use the first two vectors as test queries
        query_vectors = vectors[:2]
        search_results = db.search_top_n(
            query_embeddings=query_vectors,
            top_k=3,
            partition_name="test_partition"
        )
        
        # Print results
        for i, matches in enumerate(search_results):
            print(f"\nResults for query vector {i}:")
            for j, match in enumerate(matches, 1):
                print(f"==> result for matches{j}: {match}")
                
    except Exception as e:
        print(f"Error during search: {str(e)}")
    