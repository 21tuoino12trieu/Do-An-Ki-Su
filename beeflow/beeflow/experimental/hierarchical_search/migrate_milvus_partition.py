from email.policy import default
from typing import List, Union, Dict, Any, Dict
from httpx import delete
from huggingface_hub import create_collection
from networkx import partition_spanning_tree
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

from collections import defaultdict
from sklearn.metrics.pairwise import cosine_distances



import uuid
import numpy as np 
from experimental.test_mongo import MongoNode
from experimental.test_embed_node import Embedding
from experimental.test_llm import LLM

class Migrate():
    def __init__(self, client: MilvusClient):
        self.mongo = MongoNode()
        self.client = client
        self.embedder = Embedding()
        self.llm = LLM()

        self.centroids: Dict[np.array] = None 

    async def _prepare(self, collection_name: str):
        partition_names = self.client.list_partitions(collection_name= collection_name)
        centroids = defaultdict(list)
        topics = dict()
        
        batch_size = 1000
        offset = 0
        while True:
            res = self.client.query(
                collection_name=collection_name,
                filter= "",
                output_fields=["vector", "topic", "chunk_id"],
                limit=batch_size,
                offset=offset
            )

            if not res:
                break

            for data in res:
                centroids[data["topic"]].append(data["vector"])


            offset += batch_size

        result = dict() 
        for topic, vectors in centroids.items():
            centroid = np.mean(np.vstack(vectors), axis= 0)
            result[topic] = centroid 

        self.centroids = result

    def drop_partitions(self,collection_name: str,  exceptions: List[str]):

        self.client.release_collection(collection_name)

        partition_names= self.client.list_partitions(collection_name= collection_name)
        for name in partition_names:
            if name in exceptions: 
                continue 
            self.client.drop_partition(collection_name= collection_name, partition_name= name)
        print(f"drop all partition, except: {exceptions}")

    async def query(self, query: str, collection_name: str, top_k_topic: int, top_k: int, export: bool= True):
        query_embedding = await self.embedder.embed([query])
        query_embedding = query_embedding["embeddings"][0]

        ###############################################
        # choose partitions 
        vec = np.array(query_embedding).reshape(1, -1)

        centroid_ids = list(self.centroids.keys())
        centroid_matrix = np.vstack(
            [self.centroids[t] for t in centroid_ids]
        )
        distances = cosine_distances(vec, centroid_matrix)[0]

        nearest_idx = np.argsort(distances)[:top_k_topic]
        nearest_partitions = [centroid_ids[i] for i in nearest_idx]

        print(f"Searching in topics: {nearest_partitions}")

        #######################################################
        #search 

        expr = f"topic in {nearest_partitions}"

        results = self.client.search(
            collection_name=collection_name,
            data=[query_embedding],
            anns_field="vector",
            limit=top_k,
            output_fields=["chunk_id", "topic"], 
            filter= expr,
        )
        dense_results = results[0]

        # Print results
        export_contents = [f"Query: {query}"] 
        for i, result in enumerate(dense_results):
            chunk_content = await self.mongo.search_chunk(chunk_id= result['entity']['chunk_id'] )
            topic_name = await self.mongo.get_chunk_topic(result['entity']['chunk_id'])
            # print(
            #     f"{i+1}. Topic: {topic_name} Score: {result['distance']:.4f}, Content: {chunk_content}"
            # )
            if export: 
                export_contents.append(f"{i+1}. Topic: {topic_name} Score: {result['distance']:.4f}, Content: {chunk_content}")
           
        if export:
            self.write_json(chunks= export_contents, filepath= "hierarchical_search.json")
        
        return export_contents
    
    
    def caculate_weight(self, similarities: list[float], tau: float= 0.5):
        d = np.array(similarities)
        exp_d = np.exp((d - min(d)) / tau)
        weight = exp_d / np.sum(exp_d)

        return weight.astype(float).tolist()
    
    async def weighted_query(self, query: str, collection_name: str, top_k_topic: int, top_k: int, export: bool= True):
        query_embedding = await self.embedder.embed([query])
        query_embedding = query_embedding["embeddings"][0]

        ###############################################
        # choose partitions 
        vec = np.array(query_embedding).reshape(1, -1)

        centroid_ids = list(self.centroids.keys())
        centroid_matrix = np.vstack(
            [self.centroids[t] for t in centroid_ids]
        )
        distances = cosine_distances(vec, centroid_matrix)[0]

        nearest_idx = np.argsort(distances)[:top_k_topic]
        nearest_partitions = [centroid_ids[i] for i in nearest_idx]

        #######################################################
        #search requests

        requests = [] 
        for idx in nearest_idx:
            expr = f"topic == '{centroid_ids[idx]}'"
            # print(expr)
            req = AnnSearchRequest(
                data= [query_embedding],
                anns_field= "vector", 
                param= {"metric_type": "COSINE", "params": {"nprobe": 10}},
                limit= top_k, 
                expr= expr, 
            )
            requests.append(req)

        #######################################################
        # search 

        dis = [distances[idx] for idx in nearest_idx] 
        search_weight = self.caculate_weight(dis)

        reranker = WeightedRanker(*search_weight)
        print(f"distances to all centroid {distances}")
        print(f"distances to nearest centroid {dis}")
        print(f"Searching in topics: {nearest_partitions} with score: {search_weight}")

        results = self.client.hybrid_search(
            collection_name=collection_name,
            reqs= requests,
            limit=top_k,
            ranker= reranker,
            output_fields=["chunk_id", "topic"],
        )
        dense_results = results[0]
        # print("result: ", dense_results)

        # Print results
        export_contents = [f"Query: {query}"] 
        for i, result in enumerate(dense_results):
            chunk_content = await self.mongo.search_chunk(chunk_id= result['entity']['chunk_id'] )
            topic_name = await self.mongo.get_chunk_topic(result['entity']['chunk_id'])
            # print(
            #     f"{i+1}. Topic: {topic_name} Score: {result['distance']:.4f}, Content: {chunk_content}"
            # )
            if export: 
                export_contents.append(f"{i+1}. Topic: {topic_name} Score: {result['distance']:.4f}, Content: {chunk_content}")
           
        if export:
            self.write_json(chunks= export_contents, filepath= "hierarchical_search.json")
        
        return export_contents
    
    
    async def weighted_hybrid_query(self, query: str, collection_name: str, top_k_topic: int, top_k: int, export: bool= True):
        query_embedding = await self.embedder.embed([query])
        query_embedding = query_embedding["embeddings"][0]

        ###############################################
        # choose partitions 
        vec = np.array(query_embedding).reshape(1, -1)

        centroid_ids = list(self.centroids.keys())
        centroid_matrix = np.vstack(
            [self.centroids[t] for t in centroid_ids]
        )
        distances = cosine_distances(vec, centroid_matrix)[0]

        nearest_idx = np.argsort(distances)[:top_k_topic]
        nearest_partitions = [centroid_ids[i] for i in nearest_idx]

        #######################################################
        #search requests

        requests = [] 
        for idx in nearest_idx:
            expr = f"topic == '{centroid_ids[idx]}'"
            # print(expr)
            req = AnnSearchRequest(
                data= [query_embedding],
                anns_field= "vector", 
                param= {"metric_type": "COSINE", "params": {"nprobe": 10}},
                limit= top_k, 
                expr= expr, 
            )
            requests.append(req)
        
        sparse_search_params = {"metric_type": "BM25"}
        sparse_request = AnnSearchRequest(
            data= [query], 
            anns_field= "sparse_vector", 
            param= sparse_search_params, 
            limit=top_k,
            expr= f"topic in {nearest_partitions}"
        )

        requests.append(sparse_request)

        #######################################################
        # search 

        dis = [distances[idx] for idx in nearest_idx] 
        search_weight = self.caculate_weight(dis)
        search_weight.append(1/(top_k_topic))

        reranker = WeightedRanker(*search_weight)
        print(f"distances to all centroid {distances}")
        print(f"distances to nearest centroid {dis}")
        print(f"Searching in topics: {nearest_partitions} with score: {search_weight}")

        results = self.client.hybrid_search(
            collection_name=collection_name,
            reqs= requests,
            limit=top_k,
            ranker= reranker,
            output_fields=["chunk_id", "topic", "content"],
        )
        dense_results = results[0]
        # print("result: ", dense_results)

        # Print results
        export_contents = [f"Query: {query}"] 
        export_text_contents = [f"Query: {query}"] 
        for i, result in enumerate(dense_results):
            chunk_content = await self.mongo.search_chunk(chunk_id= result['entity']['chunk_id'] )
            topic_name = await self.mongo.get_chunk_topic(result['entity']['chunk_id'])
            # print(
            #     f"{i+1}. Topic: {topic_name} Score: {result['distance']:.4f}, Content: {chunk_content}"
            # )
            if export: 
                export_contents.append(f"{i+1}. Topic: {topic_name} Score: {result['distance']:.4f}, Content: {chunk_content}")
                export_text_contents.append(f"{i+1}. Topic: {topic_name} Chunk_id: {result["entity"]["chunk_id"]} Text Search Content: {result["entity"]["content"]}")
           
        if export:
            self.write_json(chunks= export_contents, filepath= "hierarchical_search.json")
            self.write_json(chunks= export_text_contents, filepath= "hierarchical_search_content.json")
        
        return export_contents
    
    def write_json(self, chunks, filepath):
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    data = []
        else:
            data = []

        if isinstance(chunks, list):
            data.extend(chunks)
        else:
            data.append(chunks)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print("done")

    def create_new_collection(self, collection_name: str):
        analyzer_params = {"tokenizer": "standard", "filter": ["lowercase"]}

        schema = MilvusClient.create_schema()
        schema.add_field(
            field_name="chunk_id",
            datatype=DataType.VARCHAR,
            is_primary=True,
            auto_id=False,
            max_length=65535,
        )
        schema.add_field(
            field_name="content",
            datatype=DataType.VARCHAR,
            max_length=65535,
            analyzer_params=analyzer_params,
            enable_match=True,  # Enable text matching
            enable_analyzer=True,  # Enable text analysis
        )

        schema.add_field(field_name="sparse_vector", 
                         datatype=DataType.SPARSE_FLOAT_VECTOR)

        schema.add_field(
            field_name="vector",
            datatype=DataType.FLOAT_VECTOR,
            dim=1024, 
        )

        schema.add_field(
            field_name= "topic",
            datatype= DataType.VARCHAR,
            is_partition_key=True,
            max_length= 65535,
        )

        schema.add_field(
            field_name="type", 
            datatype=DataType.VARCHAR, 
            max_length=65535,
        )


        bm25_function = Function(
            name="bm25",
            function_type=FunctionType.BM25,
            input_field_names=["content"],
            output_field_names="sparse_vector",
        )

        schema.add_function(bm25_function)

        index_params = MilvusClient.prepare_index_params()
        index_params.add_index(field_name="vector", index_type="IVF_FLAT", metric_type="COSINE")
        index_params.add_index(
            field_name="sparse_vector",
            index_type="SPARSE_INVERTED_INDEX",
            metric_type="BM25",
        )


        collections = self.client.list_collections()
        ################################ add collection
        if collection_name in collections: 
            print("collection existed")
            return False
        else:
            self.client.create_collection(
            collection_name=collection_name,
            schema=schema,
            index_params=index_params,)

        print(f"Collection '{collection_name}' created successfully")
        return True

    async def migrate_to_new_partition(self, old_collection_name: str, new_collection_name: str, old_partition: str= "document"):
       
        # 1. Get collection schema (for field names)
        check = self.create_new_collection(new_collection_name)
        if not check: return 

        # 2. Query all data from old partition (no filter)
        offset = 0
        total_inserted = 0
        batch_size = 100

        entities = [] 

        while True:
            results: List[Dict[str, Any]] = self.client.query(
                collection_name=old_collection_name,
                filter="",
                output_fields=["chunk_id", "vector", "topic", "type"],
                partition_names=["document"],
                limit=batch_size,
                offset=offset
            )
            if not results: 
                break

            for data in results:
                chunk_content= await self.mongo.search_chunk(chunk_id= data["chunk_id"])
                extract_content= await self.llm.generate(text= chunk_content)

                entities.append(
                    {
                        "chunk_id": data["chunk_id"],
                        "content": extract_content, 
                        "vector": data["vector"],
                        "topic": data["topic"], 
                        "type": data["type"],
                    }
                )

            total_inserted += len(results)
            offset += batch_size
            print(f"done {offset - batch_size} samples")

        self.client.insert(collection_name= new_collection_name, data= entities)

       
        print(
            "done migrate"
        )


async def test_time(sol: Migrate, collection_name: str, texts: list[str], iteration: int, warm_up: bool= False):
    import time 

    if warm_up: 
        for i in range(warm_up):
            for text in texts:
                await sol.query(query= text, colelction_name= collection_name, top_k_topic=3, top_k=10) 
    
    res = 0
    for i in range(iteration):
        tmp = 0
        for text in texts: 
            start_time = time.perf_counter()
            await sol.weighted_query(query= text, collection_name= collection_name, top_k_topic=3, top_k=10, export=False) 
            end_time = time.perf_counter()
            tmp += end_time - start_time 
        print(f"iter {i}: {tmp}")
        res += tmp 
    print(f"Average_time: {res/ iteration}")


async def main():
    default_config = MilvusConfig.default()
    client = MilvusClient(uri= default_config.uri, user= default_config.username, password = default_config.password, db_name= default_config.db_name)

    old_collection_name = "bot_a6cb68dd_b472_4183_ad26_d406c5c3b841"
    new_collection_name = "hierarchical_search2"
    sol = Migrate(client)

    ####################################################################
    # migrate 
    ###client.drop_collection(new_collection_name)

    await sol.migrate_to_new_partition(old_collection_name= old_collection_name, new_collection_name= new_collection_name) 
    print(client.list_partitions(collection_name= new_collection_name))

    ##################################################################
    # search 
    # await sol._prepare(collection_name= new_collection_name)
    # from experimental.hierarchical_search.utils import questions, fail_questions, llm_questions


    # for text in llm_questions:
    #     # res = await sol.query(query= text, collection_name= new_collection_name, top_k= 10, top_k_topic= 3)
    #     res = await sol.weighted_hybrid_query(query= text, collection_name= new_collection_name, top_k=10, top_k_topic=5)

    # print(res)


    #############################################################################
    # time perf 
    # from experimental.hierarchical_search.utils import questions 
    # await sol._prepare(collection_name= new_collection_name)
    # await test_time(sol= sol, collection_name= new_collection_name, texts= questions, iteration= 1, warm_up=False)

if __name__ == "__main__":
    asyncio.run(main())