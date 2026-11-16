from beegenerate.storage import MongoStorage
from beegenerate.vectordb import MilvusStorage
from beegenerate.configs import MongoConfig
from beegenerate.configs import MilvusConfig
from pymilvus import connections, Collection
from pymilvus.exceptions import SchemaNotReadyException
from typing import Dict, List, Any


if __name__ == "__main__":
    mongo = MongoStorage(config=MongoConfig.default())
    
    mil_config=MilvusConfig.default()
    
    bot_info = mongo.find(
        collection_name="botinfo",
        query={"_id": "711bd760-5824-4772-addd-e038633c7847"}
    )
        
    connections.connect(
        alias=mil_config.alias,
        uri=mil_config.uri,
        user=mil_config.username,
        password=mil_config.password,
        db_name=mil_config.db_name
    )
    
    from tqdm import tqdm
    
    non_existed_collections = []
    
    logging = {}
    
    for bot in bot_info:
        try:
            bot_id = bot['_id'].replace('-', '_')
            collection_name = f"bot_{bot_id}"

            collection = Collection(collection_name)
            
            # Load collection into memory (required before search/query)
            collection.load()
            
                
            # Prepare search parameters to get all records
            search_params = {
                "expr": "",  # Empty expression means get all
                "output_fields": ["chunk_id"],  # Get all fields
                "limit": 10000  # Set limit to total number of entities
            }
            
            # Execute the query
            results = collection.query(**search_params)
            
            chunk_ids = [r['chunk_id'] for r in results]

            mongo_chunks = mongo.find(
                collection_name="chunk_data",
                query = {"chunk_id": {"$in": chunk_ids}}
            )
            
            print(bot['_id'], len(results), len(mongo_chunks))                
                
            logging[collection_name] = {
                "pulled_records": len(results)
            }
        except SchemaNotReadyException as e:
            non_existed_collections.append(collection_name)
            
    logging['non_existed_collections'] = len(non_existed_collections)
    
    import json
    print(json.dumps(logging, indent=2))