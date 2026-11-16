from pathlib import Path
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from pymongo.server_api import ServerApi
from beegenerate.configs.db.mongo_config import MongoConfig


def connect_to_mongo(config: MongoConfig) -> MongoClient:
    # First attempt: normal connection with 2-second timeout
    try:
        client = MongoClient(config.uri, server_api=ServerApi('1'), serverSelectionTimeoutMS=2000)
        client.admin.command('ping')
        print("Successfully connected to MongoDB cluster!")
        return client
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        print(f"Failed to connect to MongoDB cluster within 2 seconds: {e}")
        print("Attempting direct connection...")

    # Second attempt: direct connection
    try:
        direct_uri = f"{config.uri}&directConnection=true"
        client = MongoClient(direct_uri, server_api=ServerApi('1'))
        client.admin.command('ping')
        print("Successfully connected to MongoDB using direct connection!")
        return client
    except ConnectionFailure as e:
        print(f"Failed to connect to MongoDB using direct connection: {e}")
        raise

def main():
    # Load configuration from YAML file
    config = MongoConfig.default()
    
    try:
        client = connect_to_mongo(config)

        # List databases (if you have permission)
        print("Available databases:")
        for db_name in client.list_database_names():
            print(f"- {db_name}")

    except Exception as e:
        print(f"An error occurred: {e}")
    else:
        print("Connection and operations successful!")
    finally:
        if 'client' in locals():
            client.close()
            print("Connection closed.")

if __name__ == "__main__":
    main()