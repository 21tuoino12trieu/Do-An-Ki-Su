from typing import Collection
from httpx import delete
from huggingface_hub import create_collection
import numpy as np
from time import time
import json
import asyncio
import os 
from beegen.configs import MilvusConfig, MilvusOperation
from beegen.vectordb.milvus_engine import MilvusEngine

from pymilvus import (
    MilvusClient,
    DataType,
    Function,
    FunctionType,
    AnnSearchRequest,
    RRFRanker,
    WeightedRanker,
    Collection
)



import uuid
from experimental.hybrid_search_flow.test_llm import LLM
from experimental.hybrid_search_flow.test_mongo import MongoNode

class Migrate():
    def __init__(self, client: MilvusClient):
        self.llm = LLM() 
        self.mongo = MongoNode()
        self.client = client

    
    def add_extract_collection(self, collection_name: str):
        analyzer_params = {"tokenizer": "standard", "filter": ["lowercase"]}

        schema = MilvusClient.create_schema()
        schema.add_field(
            field_name="chunk_id",
            datatype=DataType.VARCHAR,
            is_primary=True,
            auto_id=False,
            max_length=100,
        )
        schema.add_field(
            field_name= "original_content",
            datatype= DataType.VARCHAR,
            max_length = 65535
        )

        schema.add_field(
            field_name="content",
            datatype=DataType.VARCHAR,
            max_length=65535,
            analyzer_params=analyzer_params,
            enable_match=True,  # Enable text matching
            enable_analyzer=True,  # Enable text analysis
        )
        schema.add_field(field_name="sparse_vector", datatype=DataType.SPARSE_FLOAT_VECTOR)
        schema.add_field(
            field_name="dense_vector",
            datatype=DataType.FLOAT_VECTOR,
            dim=1024,  # Dimension for text-embedding-3-small
        )

        # Define BM25 function to generate sparse vectors from text
        bm25_function = Function(
            name="bm25",
            function_type=FunctionType.BM25,
            input_field_names=["content"],
            output_field_names="sparse_vector",
        )

        # Add the function to schema
        schema.add_function(bm25_function)

        index_params = MilvusClient.prepare_index_params()
        index_params.add_index(
            field_name="sparse_vector",
            index_type="SPARSE_INVERTED_INDEX",
            metric_type="BM25",
        )
        index_params.add_index(field_name="dense_vector", index_type="FLAT", metric_type="COSINE")
        

        collections = self.client.list_collections()
        ################################ add collection
        if collection_name in collections: 
            print("collection existed")
        else:
            self.client.create_collection(
            collection_name=collection_name,
            schema=schema,
            index_params=index_params,)

        print(f"Collection '{collection_name}' created successfully")

    async def migrate(self, old_collection: str, new_collection: str):

        self.add_extract_collection(new_collection)

        old_datas = self.client.query(old_collection, filter= "", output_fields= ["chunk_id", "vector"], limit=1000)

        entities = [] 

        for data in old_datas: 
            chunk_id = data["chunk_id"]
            dense_vector = data["vector"]
            
            chunk = await self.mongo.search_chunk(chunk_id= chunk_id)
            extract_content = await self.llm.generate(chunk)

            entities.append(
                {
                    "chunk_id": chunk_id,
                    "original_content": chunk,
                    "content": extract_content,
                    "dense_vector": dense_vector, 
                }
            ) 

        self.client.insert(collection_name= new_collection, data= entities)
        print(f"Successfully migrate")


def delete_collection(client: MilvusClient, collection_name: str):
    collections = client.list_collections()
    
    if collection_name not in collections: 
        print(f"{collection_name} not in collections list to delete")
    client.drop_collection(collection_name= collection_name)
    print("deleted")


async def main():
    default_config = MilvusConfig.default()
    client = MilvusClient(uri= default_config.uri, user= default_config.username, password = default_config.password, db_name= default_config.db_name)
    # new_collection_name= "hybrid_search"

    # # delete_collection(client, new_collection_name)
    # add_extract_collection(client, new_collection_name)
    # old_collection_name = "hybrid_search_extract"

    # res = client.query(old_collection_name, filter= "", output_fields= ["id", "original_content", "content", "dense_vector"], limit=1000)

    # entities = [] 
    # for data in res:

    #     entities.append(
    #         {
    #             "chunk_id": data["id"],
    #             "original_content": data["original_content"],
    #             "content": data["content"],
    #             "dense_vector": data["dense_vector"], 
    #         }
    #     )
    # client.insert(collection_name= new_collection_name, data= entities)
    # print(f"Successfully migrate")

    # print(type(res))
    # print(len(res))
    # print(res[0])

    sol = Migrate(client) 
    old = "bot_665fccd5_4be8_4305_b247_4116314d6deb"
    new_name =  "test_hybrid_search"

    delete_collection(client, new_name)
    await sol.migrate(old_collection= old, new_collection= new_name)
    
    

if __name__ == "__main__":
    asyncio.run(main())