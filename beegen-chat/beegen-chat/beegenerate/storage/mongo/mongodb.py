from beegenerate.const import BEEGEN_ROOT
from typing import List, Dict
import time
from concurrent.futures import ThreadPoolExecutor
from beegenerate.configs.db.mongo_config import MongoConfig
from typing import Dict, List, Optional, Any, Union
from pymongo import MongoClient
from pymongo.database import Database
from pathlib import Path
from beegenerate.loggings import LOGGER
from typing_extensions import Annotated
from fastapi import Depends


class MongoStorage:

    def __init__(
        self,
        config: Optional[MongoConfig] = None
    ):
        if not config:
            config = MongoConfig.default()

        self.uri = config.uri
        self.db_name = config.authen_source
        self._client: Optional[MongoClient] = None
        self._db: Optional[Database] = None
        self.connect()
        self._initialized = True

    @classmethod
    def default(cls) -> 'MongoStorage':
        """Create a default MongoStorage instance from a given config file."""
        config = MongoConfig.default()
        return cls(config=config)

    @classmethod
    def from_path(cls, path: Union[str, Path]) -> 'MongoStorage':
        """Create a MongoStorage instance from a config file path.

        Args:
            path: Path to the mongo config YAML file

        Returns:
            MongoStorage: A new instance initialized with the config
        """
        config = MongoConfig.from_yaml_file(Path(path))
        return cls(config=config)

    def connect(self):
        try:
            LOGGER.info(f"Making connect to {self.uri}...")
            self._client = MongoClient(self.uri)
            self._db = self._client[self.db_name]
        except Exception as e:
            LOGGER.error(f"Failed to connect to MongoDB: {str(e)}")
            raise ConnectionError(f"Failed to connect to MongoDB: {str(e)}")

    def disconnect(self):
        try:
            if self._client:
                self._client.close()
        except Exception as e:
            LOGGER.error(f"Failed to disconnect from MongoDB: {str(e)}")
            raise ConnectionError(
                f"Failed to disconnect from MongoDB: {str(e)}")

    @property
    def db(self) -> Database:
        if self._db is None:
            raise ConnectionError("Database not connected")
        return self._db

    def aggregate(
            self,
            collection_name: str,
            pipeline: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        r"""
        Run a MongoDB aggregation pipeline and return the results.

        Args:
            collection_name (str): The name of the MongoDB collection to query.
            pipeline (List[Dict[str, Any]]): A list of aggregation pipeline stages.

        Returns:
            List[Dict[str, Any]]: A list of documents returned by the aggregation.

        Raises:
            ConnectionError: If the database connection is not available.
            ValueError: If the pipeline is invalid.
            Exception: For any other unexpected errors.
        """
        try:
            if self._db is None:
                raise ConnectionError("Database not connected")

            collection = self._db[collection_name]
            cursor = collection.aggregate(pipeline)
            return list(cursor)

        except ConnectionError as e:
            LOGGER.error(f"Connection error while aggregating from {collection_name}: {e}")
            raise
        except ValueError as e:
            LOGGER.error(f"Invalid aggregation pipeline for {collection_name}: {e}")
            raise
        except Exception as e:
            LOGGER.error(f"Unexpected error during aggregation on {collection_name}: {e}")
            raise

    def find(
        self,
        collection_name: str,
        query: Dict
    ) -> List[Dict]:
        r"""
        Excute a MongoDB query and return results as dictionary/dictionaries

        Args:
            collection_name (str): name of the collection to query
            query (dict): MongoDB query to execute

        Returns:
            List[Dict]: query results
        """

        try:
            if self._db is None:
                raise ConnectionError("Database not connected")

            collection = self._db[collection_name]

            cursor = collection.find(query)

            result = list(cursor)

            return result

        except ConnectionError as e:
            LOGGER.error(f"Connection error during query: {str(e)}")
            raise
        except ValueError as e:
            LOGGER.error(f"Invalid limit parameter: {str(e)}")
            raise
        except Exception as e:
            LOGGER.error(
                f"Error executing query on collection {collection_name}: {str(e)}")
            raise

    def find_with_output_fields(
        self,
        collection_name: str,
        query: Dict,
        output_fields: Dict,
    ) -> List[Dict]:
        r"""
        Excute a MongoDB query and return results as dictionary/dictionaries

        Args:
            collection_name (str): name of the collection to query
            query (dict): MongoDB query to execute

        Returns:
            List[Dict]: query results
        """

        try:
            if self._db is None:
                raise ConnectionError("Database not connected")

            collection = self._db[collection_name]

            cursor = collection.find(
                query,
                output_fields
            )

            result = list(cursor)

            return result

        except ConnectionError as e:
            LOGGER.error(f"Connection error during query: {str(e)}")
            raise
        except ValueError as e:
            LOGGER.error(f"Invalid limit parameter: {str(e)}")
            raise
        except Exception as e:
            LOGGER.error(
                f"Error executing query on collection {collection_name}: {str(e)}")
            raise

    def insert(
        self,
        collection_name: str,
        document: Dict
    ) -> bool:
        """
        Insert a single document into a MongoDB collection

        Args:
            collection_name (str): name of the collection to insert into
            document (Dict): document to insert

        Returns:
            bool: True if insertion was successful

        Raises:
            ConnectionError: if database is not connected
            Exception: if insertion fails for any other reason
        """
        try:
            if self._db is None:
                raise ConnectionError("Database not connected")

            collection = self._db[collection_name]

            # Create a copy of the document to avoid modifying the original
            doc_to_insert = document.copy()

            result = collection.insert_one(doc_to_insert)

            return result.acknowledged

        except ConnectionError as e:
            LOGGER.error(f"Connection error during insertion: {str(e)}")
            raise
        except Exception as e:
            LOGGER.error(
                f"Error inserting document into collection {collection_name}: {str(e)}")
            raise Exception(f"Insert operation failed: {str(e)}")


_mongoStorage = MongoStorage(config=MongoConfig.default())


def get_mongodb():
    if _mongoStorage._db is None:
        _mongoStorage.connect()
    else:
        return _mongoStorage._db


MongoStorageDep = Annotated[MongoStorage, Depends(get_mongodb)]


def main():

    mongo_db = MongoStorage(
        MongoConfig.default()
    )

    docs = mongo_db.find(
        collection_name="chunk_data",
        query={
            "chunk_id": "12595b99-86c9-4041-b719-f59b10803dbf"
        }
    )

    print()
    for doc in docs:
        print(doc)


# import threading

# Global counters with lock for thread safety
success_count = 0
failure_count = 0
# counter_lock = threading.Lock()


def single_request(mongodb: MongoStorage, request_id: int) -> List[Dict]:
    """Execute a single request to MongoDB"""
    try:
        start_time = time.time()

        docs = mongodb.find(
            collection_name="chunk_data",
            query={
                "chunk_id": {
                    "$in": [
                        '1033cae2-565b-4348-a81d-26e79dec5658',
                        '27b96d2d-1b3d-4194-974c-7b923a5f82e2',
                        '6ea7e250-5605-4313-960a-ba32673f7f45',
                        '8c5d2545-5335-43b0-8b29-0f1d8cf570ed',
                        'b1fd9e80-1552-48ce-8e3a-0f9a82f990a8',
                        '37d57191-5f94-479d-af26-94117d8692c8',
                    ]
                }
            }
        )

        execution_time = time.time() - start_time
        LOGGER.info(
            f"Request {request_id} completed in {execution_time:.2f} seconds. Found {len(docs)} documents.")

        return docs

    except Exception as e:
        LOGGER.error(f"Request {request_id} failed: {str(e)}")
        raise


def execute_request(mongodb: MongoStorage, request_id: int):
    """Execute a single request and update global counters"""
    global success_count, failure_count

    try:
        docs = single_request(mongodb, request_id)
        # with counter_lock:
        #     global success_count
        #     success_count += 1
        return docs
    except Exception:
        # with counter_lock:
        #     global failure_count
        #     failure_count += 1
        return None


def test_ccu(num_requests: int = 50):
    """
    Test Concurrent User (CCU) handling by sending multiple concurrent requests

    Args:
        num_requests (int): Number of concurrent requests to simulate
    """
    global success_count, failure_count
    success_count = 0
    failure_count = 0

    try:
        # Initialize MongoDB connection
        mongodb = MongoStorage(
            MongoConfig.default()
        )

        start_time = time.time()
        LOGGER.info(
            f"Starting CCU test with {num_requests} concurrent requests...")

        # Use ThreadPoolExecutor to manage concurrent requests
        with ThreadPoolExecutor(max_workers=num_requests) as executor:
            # Submit all requests
            futures = [
                executor.submit(execute_request, mongodb, i)
                for i in range(num_requests)
            ]

            # Wait for all requests to complete
            for future in futures:
                future.result()

        total_time = time.time() - start_time

        # Log results
        LOGGER.info(f"""
CCU Test Results:
----------------
Total Requests: {num_requests}
Successful: {success_count}
Failed: {failure_count}
Total Time: {total_time:.2f} seconds
Average Time per Request: {total_time/num_requests:.2f} seconds
Throughput: {num_requests/total_time:.2f} requests/second
""")

    except Exception as e:
        LOGGER.error(f"CCU test failed: {str(e)}")
        raise
    finally:
        # Ensure we close the MongoDB connection
        mongodb.disconnect()


if __name__ == "__main__":
    main()
