from pymilvus import connections, Collection, CollectionSchema, FieldSchema, DataType, utility
from beegenerate.embeddings.emb_factory import EmbeddingFactory
from beegenerate.configs import EmbeddingConfig

# Milvus connection config
MILVUS_CONFIG = {
    "alias": "default",
    "uri": "http://10.215.254.90:19530",
    "db_name": "chatbot_libra",
    "username": "chatbot_user",
    "password": "REPLACE_WITH_LOCAL_SECRET",
    "connection_pool_size": 100,
    "enable_ssl": False,
    "timeout": 10.0
}

# Search parameters
INDEX_PARAMS = {
    "index_type": "IVF_FLAT",
    "metric_type": "COSINE",
    "params": {
        "nlist": 1024
    }
}

SEARCH_PARAMS = {
    "nprobe": 10
}

# Connect to Milvus
connections.connect(
    alias=MILVUS_CONFIG["alias"],
    uri=MILVUS_CONFIG["uri"],
    user=MILVUS_CONFIG["username"],
    password=MILVUS_CONFIG["password"],
    db_name=MILVUS_CONFIG["db_name"]
)


# Define collection name
COLLECTION_NAME = "bot_b10f0d26_4d91_47f5_8cac_034b87e42c7f"

collection = Collection(COLLECTION_NAME)

print(collection.name)

# # Define schema
# id_field = FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True)
# vector_field = FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=768)  # Adjust dim as needed

# schema = CollectionSchema(fields=[id_field, vector_field], description="Chatbot Embeddings Collection")

# # Define schema
# id_field = FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True)
# vector_field = FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=768)  # Adjust dim as needed

# schema = CollectionSchema(fields=[id_field, vector_field], description="Chatbot Embeddings Collection")

# # Create collection if it doesn't exist
# if not utility.has_collection(COLLECTION_NAME):
#     collection = Collection(name=COLLECTION_NAME, schema=schema)
#     print(f"Collection '{COLLECTION_NAME}' created.")
# else:
#     print(f"Collection '{COLLECTION_NAME}' already exists.")

# Verify if collection exists
if utility.has_collection(COLLECTION_NAME):
    print(f"Collection '{COLLECTION_NAME}' exists in Milvus.")
else:
    print(f"Collection '{COLLECTION_NAME}' does not exist.")

# # Delete the collection
# if utility.has_collection(COLLECTION_NAME):
#     utility.drop_collection(COLLECTION_NAME)
#     print(f"Collection '{COLLECTION_NAME}' deleted.")

# # Check if collection is deleted
# if not utility.has_collection(COLLECTION_NAME):
#     print(f"Collection '{COLLECTION_NAME}' successfully deleted.")
# else:
#     print(f"Failed to delete collection '{COLLECTION_NAME}'.")
