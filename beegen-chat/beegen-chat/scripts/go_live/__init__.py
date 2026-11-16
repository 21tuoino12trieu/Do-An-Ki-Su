from pymongo import MongoClient
import uuid

# MongoDB connection configuration
mongo_config = {
    'username': 'nlpdev',
    'password': 'REPLACE_WITH_LOCAL_SECRET',
    'host': '10.215.107.53',
    'port': '27017',
    'authSource': 'aicenter_chatbot',
    'appname': 'MongoDBCompass',
    'ssl': False,
    'readPreference': 'primary',
    'directConnection': True
}

# Construct the connection string
connection_string = f"mongodb://{mongo_config['username']}:{mongo_config['password']}@{mongo_config['host']}:{mongo_config['port']}/{mongo_config['authSource']}"

try:
    # Connect to MongoDB with all config parameters
    client = MongoClient(
        connection_string,
        **{k: v for k, v in mongo_config.items() if k not in ['username', 'password', 'host', 'port']}
    )
    
    # Access the database
    db = client['aicenter_chatbot']
    
    # Define the document to insert
    document = {
        "_id": str(uuid.uuid4()),
        "type": "EMBEDDING",
        "config": {
            "api_type": "vllm",
            "api_key": "mb123456789",
            "base_url": "http://10.1.87.71:30044/v1/embeddings",
            "model": "model/bge-m3",
            "embed_batch_size": 32,
            "dimensions": 1024,
            "model_alias": "mô hình bge-m3 (vllm)",
            "retrieval_threshold": 0,
            "retrieval_top_k": 16,
        }
    }
    
    # Insert the document
    result = db.beegen_configurations.insert_one(document)
    print(f"Document inserted successfully with _id: {result.inserted_id}")

except Exception as e:
    print(f"An error occurred: {e}")

finally:
    if 'client' in locals():
        client.close()