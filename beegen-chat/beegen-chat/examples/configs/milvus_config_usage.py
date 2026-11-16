from pathlib import Path
from beegenerate.configs.yaml_model import YamlModel
from beegenerate.configs.db.vectordb.milvus_config import MilvusConfig, MilvusCollectionConfig

def save_and_load_config():
    # Create a MilvusConfig instance
    config = MilvusConfig(
        uri="localhost:19530",
        username="default",
        password="123456",
        db_name="default",
        timeout=10.0,
        connection_pool_size=5,
        enable_ssl=False,
        collections={
            "my_collection": MilvusCollectionConfig(
                collection_name="my_collection",
                embedding_size=768,
                fields=[
                    {"name": "id", "dtype": "INT64", "is_primary": True},
                    {"name": "text", "dtype": "VARCHAR", "max_length": 65535},
                ],
                index_params={
                    "index_type": "IVF_FLAT",
                    "metric_type": "L2",
                    "params": {"nlist": 1024},
                },
                search_params={
                    "nprobe": 10
                }
            ),
            "my_collection2": MilvusCollectionConfig(
                collection_name="my_collection2",
                embedding_size=768,
                fields=[
                    {"name": "id", "dtype": "INT64", "is_primary": True},
                    {"name": "name", "dtype": "VARCHAR", "max_length": 100},
                    {"name": "age", "dtype": "INT"},
                ],
                index_params={
                    "index_type": "IVF_FLAT",
                    "metric_type": "L2",
                    "params": {"nlist": 1024},
                },
                search_params={
                    "nprobe": 10
                }
            )
        }
    )

    # Save the config to a YAML file
    config_file = Path("milvus_config.yaml")
    config.to_yaml_file(config_file)
    print(f"Config saved to {config_file}")

    # Load the config from the YAML file
    loaded_config = MilvusConfig.from_yaml_file(config_file)
    print("Config loaded from file")

    # Verify that the loaded config matches the original
    assert config.model_dump() == loaded_config.model_dump(), "Loaded config doesn't match the original"
    print("Loaded config matches the original")

    # Access and print some values from the loaded config
    print(f"Milvus URI: {loaded_config.uri}")
    print(f"Database name: {loaded_config.db_name}")
    print(f"Number of collections: {len(loaded_config.collections)}")
    
    for collection_name, collection_config in loaded_config.collections.items():
        print(f"\nCollection: {collection_name}")
        print(f"  Embedding size: {collection_config.embedding_size}")
        print(f"  Number of fields: {len(collection_config.fields)}")
        print(f"  Index type: {collection_config.index_params['index_type']}")
        
    print(loaded_config.model_dump_json())


import time
from pymilvus import connections, Collection, FieldSchema, CollectionSchema, DataType
from beegenerate.configs.db.vectordb.milvus_config import MilvusConfig, MilvusCollectionConfig

def connect_to_milvus(config: MilvusConfig):
    """Establish a connection to Milvus server"""
    connections.connect(
        alias="default",
        uri=config.uri,
        user=config.username,
        password=config.password,
        db_name=config.db_name,
        timeout=config.timeout,
        pool_size=config.connection_pool_size,
        secure=config.enable_ssl,
        ca_cert=config.ca_path
    )
    print(f"Connected to Milvus server at {config.uri}")

def create_collection(collection_config: MilvusCollectionConfig):
    """Create a collection based on the provided configuration"""
    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=collection_config.embedding_size)
    ]

    # Add additional fields from the configuration
    for field in collection_config.fields:
        if field["name"] != "id" and field["name"] != "embedding":
            dtype = getattr(DataType, field["dtype"])
            fields.append(FieldSchema(name=field["name"], dtype=dtype, **{k: v for k, v in field.items() if k not in ["name", "dtype"]}))

    schema = CollectionSchema(fields=fields, description=f"Collection for {collection_config.collection_name}")
    collection = Collection(name=collection_config.collection_name, schema=schema)
    
    # Create index on the embedding field
    collection.create_index(field_name="embedding", index_params=collection_config.index_params)
    
    print(f"Created collection: {collection_config.collection_name}")
    return collection

def main():
    from pathlib import Path
    # Load MilvusConfig (assuming it's saved in a file named 'milvus_config.yaml')
    config = MilvusConfig.from_yaml_file(Path("milvus_config.yaml"))

    # Connect to Milvus
    connect_to_milvus(config)

    # Create collections based on the configuration
    for collection_name, collection_config in config.collections.items():
        collection = create_collection(collection_config)
        
        # Load the collection and print some information
        collection.load()
        print(f"Collection {collection_name} schema:")
        print(collection.schema)
        print(f"Number of entities: {collection.num_entities}")
        
        # Set the search parameters for the collection
        collection.set_properties({"search_params": collection_config.search_params})
        
        # Release the collection
        collection.release()

    # Disconnect from Milvus
    connections.disconnect("default")
    print("Disconnected from Milvus server")

if __name__ == "__main__":
    main()