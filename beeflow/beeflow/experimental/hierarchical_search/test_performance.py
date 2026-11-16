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

class Solution():
    def __init__(self, client: MilvusClient):
        self.mongo = MongoNode()
        self.client = client
        self.embedder = Embedding()
        self.llm = LLM()

        self.centroids: Dict[np.array] = None 

    async def _prepare(self, collection_name: str):
        pass 
    
    def caculate_weight(self, similarities: list[float], tau: float= 0.5):
        d = np.array(similarities)
        exp_d = np.exp((d - min(d)) / tau)
        weight = exp_d / np.sum(exp_d)

        return weight.astype(float).tolist()
    
    async def weighted_hybrid_query(self, query: str, collection_name: str, top_k_topic: int, top_k: int, top_k_score: int = 5, use_hybrid_search:bool= True, export: bool= True):
        query_embedding = await self.embedder.embed([query])
        query_embedding = query_embedding["embeddings"][0]

        ###############################################
        # cache search result 
        num_topics = len(self.client.list_partitions(collection_name= collection_name))

        if use_hybrid_search:
            sparse_search_params = {"metric_type": "BM25"}
            sparse_request = AnnSearchRequest(
                [query], "sparse_vector", sparse_search_params, limit=top_k
            )

            dense_search_params = {"metric_type": "COSINE"}
            dense_request = AnnSearchRequest(
                [query_embedding], "vector", dense_search_params, limit=top_k
            )

            
            results = self.client.hybrid_search(
                collection_name= collection_name,
                reqs= [sparse_request, dense_request],
                ranker=WeightedRanker(0.5, 0.5),  
                limit= top_k * num_topics * 3,
                output_fields=["chunk_id", "content", "topic"],
            )

        else: 
            results = self.client.search(
                collection_name=collection_name, 
                data= [query_embedding], 
                anns_field= "vector",
                limit= top_k * num_topics * 3,
                output_fields=["chunk_id", "content", "topic"]
            )

        result = results[0]

        topic_results = defaultdict(list)
        for data in result: 
            topic_name = data["entity"]["topic"]
            if len(topic_results[topic_name]) >= top_k: continue
            topic_results[topic_name].append(
                {
                "distance": data['distance'], 
                "chunk_id": data['chunk_id'], 
                "content": data["content"]
                }
            )

        ######################################################
        # choose topic 
        topic_scores = []

        for topic, items in topic_results.items():
            distances = [d["distance"] for d in items]
            mean_distance = sum(distances[:top_k_score]) / min(len(distances), top_k_score)

            topic_scores.append({
                "topic": topic,
                "mean_distance": mean_distance,
            })

        topic_scores.sort(key=lambda x: x["mean_distance"], reverse= True)

        choosed_topics = [data["topic"] for data in topic_scores[:top_k_topic]]
        scores = self.caculate_weight([data["mean_distance"] for data in topic_scores[:top_k_topic]])
        print(topic_scores)
        print(f"Search in topics: {choosed_topics} with scores : {scores}")
       
        #######################################################
        # rerank search results :
        scored_searchs = []
        for idx, topic in enumerate(choosed_topics):
            score = scores[idx] 
            for data in topic_results[topic]: 
                scored_searchs.append(
                    {
                    "distance": data['distance'] * score, 
                    "chunk_id": data['chunk_id'], 
                    "content": data["content"]
                    }
                )
        scored_searchs.sort(key= lambda x: x["distance"], reverse= True)
        scored_searchs = scored_searchs[:top_k]

        #######################################################
        # export result 
        if export:
            export_contents = [f"Query: {query}"] 
            export_text_contents = [f"Query: {query}"] 
            for i, result in enumerate(scored_searchs):
                chunk_content = await self.mongo.search_chunk(chunk_id= result['chunk_id'] )
                topic_name = await self.mongo.get_chunk_topic(result['chunk_id'])
            
                
                export_contents.append(f"{i+1}. Topic: {topic_name} Score: {result['distance']:.4f}, Content: {chunk_content}")
                export_text_contents.append(f"{i+1}. Topic: {topic_name} Chunk_id: {result["chunk_id"]} Text Search Content: {result["content"]}")
            
            self.write_json(chunks= export_contents, filepath= "hierarchical_search.json")
            self.write_json(chunks= export_text_contents, filepath= "hierarchical_search_content.json")
            
        return [data["chunk_id"] for data in scored_searchs]
    
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

async def test_time(sol: Solution, collection_name: str, texts: list[str], iteration: int, warm_up: bool= False):
    import time 

    if warm_up: 
        for i in range(warm_up):
            for text in texts:
                await sol.weighted_hybrid_query(query= text, collection_name= collection_name, top_k_topic=3, top_k=10) 
    
    res = 0
    for i in range(iteration):
        tmp = 0
        for text in texts: 
            start_time = time.perf_counter()
            await sol.weighted_hybrid_query(query= text, collection_name= collection_name, top_k_topic=3, top_k=10, export=False) 
            end_time = time.perf_counter()
            tmp += end_time - start_time 
        print(f"iter {i}: {tmp}")
        res += tmp 
    print(f"Average_time: {res/ iteration}")

async def main():
    from experimental.hierarchical_search.utils import questions, fail_questions, llm_questions

    default_config = MilvusConfig.default()
    client = MilvusClient(uri= default_config.uri, user= default_config.username, password = default_config.password, db_name= default_config.db_name)

    old_collection_name = "bot_a6cb68dd_b472_4183_ad26_d406c5c3b841"
    new_collection_name = "hierarchical_search_no_extract"
    sol = Solution(client)
    #################################################
    # test

    for text in fail_questions:
        # res = await sol.query(query= text, collection_name= new_collection_name, top_k= 10, top_k_topic= 3)
        res = await sol.weighted_hybrid_query(query= text, collection_name= new_collection_name, top_k=10, top_k_topic=3)
    # text = "Query: phát hành thẻ JCB credit ở trên app MB cần làm gì?"
    # text = "cách mở thẻ visa infinite"
    # text = "phát hành visa infinite"

    # res = await sol.weighted_hybrid_query(query= text, collection_name= new_collection_name, top_k=10, top_k_topic=3)
    # print(res)

    #################################################
    # time perf
    # await test_time(sol, new_collection_name, llm_questions, 10, True)

if __name__ == "__main__":
    asyncio.run(main())


