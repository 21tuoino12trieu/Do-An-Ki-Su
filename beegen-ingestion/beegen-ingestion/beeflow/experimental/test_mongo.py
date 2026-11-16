from beegen.storage import mongo
from beegen.storage.mongo.mongo_engine import AsyncMongoEngine
import datetime
import json
import asyncio
from pymongo import ASCENDING, DESCENDING, InsertOne, UpdateOne, DeleteOne, ReplaceOne
from beegen.configs import MongoOperation, MongoConfig

class MongoNode():
    def __init__(self):
        try:
            self.executor = AsyncMongoEngine(
                config=MongoConfig.default()
            )
        except Exception as e: 
            data = MongoConfig.read_yaml("config/beeflow.yaml")
            config = MongoConfig(**data)
            self.executor = AsyncMongoEngine(
                config= config
            )


        self.mem = dict()


    async def search_chunk(self, chunk_id: str, collection_name: str= "chunk_data"):
        result = await self.executor.run(
            MongoOperation.FIND_ONE,
            {
                "collection_name": collection_name,
                "query": {
                    "chunk_id": chunk_id
                }
            }
        )

        return result["data"]["raw_text"]
    
    async def get_topic_name(self, id: str, collection_name: str = "category"):
        result = await self.executor.run(
            MongoOperation.FIND_ONE,
            {
                "collection_name": collection_name,
                "query": {
                    "_id": id
                }
            }
        )

        return result["data"]["name"]
    
    async def get_topic_id(self, topic_name:str):
        if topic_name in self.mem: 
            return self.mem[topic_name]
        
        res = await self.executor.run(
            MongoOperation.FIND_ONE,
            {
                "collection_name": "category",
                "query": {
                    "name": topic_name
                },
                "projection": {
                    "_id": 1
                }
            }
        )
        self.mem[topic_name] = res['data']['_id']

        return res['data']['_id']

    
    async def get_chunk_topic(self, chunk_id: str):
        # 1. chunk_id -> doc_id (collection: chunk_data)
        chunk = await self.executor.run(
            MongoOperation.FIND_ONE,
            {
                "collection_name": "chunk_data",
                "query": {
                    "chunk_id": chunk_id
                },
                "projection": {
                    "doc_id": 1
                }
            }
        )

        if not chunk or "doc_id" not in chunk["data"]:
            return None

        doc_id = chunk["data"]["doc_id"]

        # 2. doc_id -> category_id (collection: document)
        document = await self.executor.run(
            MongoOperation.FIND_ONE,
            {
                "collection_name": "documents",
                "query": {
                    "_id": doc_id
                },
                "projection": {
                    "category_id": 1
                }
            }
        )

        if not document or "category_id" not in document["data"]:
            return None

        category_id = document["data"]["category_id"]

        # 3. category_id -> category.name (collection: category)
        category = await self.executor.run(
            MongoOperation.FIND_ONE,
            {
                "collection_name": "category",
                "query": {
                    "_id": category_id
                },
                "projection": {
                    "name": 1
                }
            }
        )

        if not category:
            return None

        return category["data"].get("name")

    
async def main():
    # executor = AsyncMongoEngine(
    #     config=MongoConfig.default()
    # )
    
    # timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    # test_collection = "chunk_data"
        
    chunk_id = "c4f6cb03-3247-49d8-a4af-a012d6307228"

    # find_one_result = await executor.run(
    #     MongoOperation.FIND,
    #     {
    #         "collection_name": "chunk_data",
    #         "query": {
    #             "chunk_id": chunk_id
    #         }
    #     }
    # )

    # print(json.dumps(find_one_result, indent=2, ensure_ascii=False))
    mongo_node = MongoNode()
    # res = await mongo_node.search_chunk(chunk_id= chunk_id)
    # res = await mongo_node.get_chunk_topic(chunk_id)
    res = await mongo_node.get_topic_id("Hướng-dẫn/hướng-dẫn-nhập-liệu")
    print(res)

if __name__ =="__main__":
    asyncio.run(main())
