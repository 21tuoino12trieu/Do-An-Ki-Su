from beegenerate.configs.db.mongo_config import MongoConfig
from typing import Dict, List, Optional, Any, Union
from pymongo import MongoClient
from pymongo.database import Database
from pathlib import Path
from beegenerate.loggings import LOGGER


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
            raise ConnectionError(f"Failed to disconnect from MongoDB: {str(e)}")
        
    @property
    def db(self) -> Database:
        if self._db is None:
            raise ConnectionError("Database not connected")
        return self._db
    
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
            LOGGER.error(f"Error executing query on collection {collection_name}: {str(e)}")
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
            LOGGER.error(f"Error executing query on collection {collection_name}: {str(e)}")
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
            LOGGER.error(f"Error inserting document into collection {collection_name}: {str(e)}")
            raise Exception(f"Insert operation failed: {str(e)}")
    


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
        print(type(doc))

# main()