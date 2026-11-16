import email
from litellm import EmbeddingInput
from pymilvus import MilvusClient 
from collections import defaultdict
import numpy as np 
import asyncio
from typing import Dict, List 
from sklearn.metrics.pairwise import cosine_distances

class NaiveNavigator():
    def __init__(self, client: MilvusClient):
        self.client = client
    
    def _prepare(self, collection_name: str):
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

    def navigate(self, query_embedding: List[float], top_k_topic: int) -> List[str]:
        vec = np.array(query_embedding).reshape(1, -1)

        centroid_ids = list(self.centroids.keys())
        centroid_matrix = np.vstack(
            [self.centroids[t] for t in centroid_ids]
        )
        distances = cosine_distances(vec, centroid_matrix)[0]

        nearest_idx = np.argsort(distances)[:top_k_topic]
        nearest_partitions = [centroid_ids[i] for i in nearest_idx]

        print(f"Searching in topics: {nearest_partitions}")

        return nearest_partitions 
    
async def main():
    from experimental.test_embed_node import Embedding 
    from beegen.configs import MilvusConfig, MilvusOperation

    default_config = MilvusConfig.default()
    client = MilvusClient(uri= default_config.uri, user= default_config.username, password = default_config.password, db_name= default_config.db_name)

    embed_node = Embedding()
    query = "tôi muốn mở thẻ priority pass"
    collection_name = "hierarchical_search2"
    query_embedding = await embed_node.embed([query])
    query_embedding = query_embedding["embeddings"][0]

    naive_navigator = NaiveNavigator(client)
    naive_navigator._prepare(collection_name= collection_name)
    partitions = naive_navigator.navigate(query_embedding= query_embedding, top_k_topic= 3)
    print(partitions)



    ##########################
    import pandas as pd 
    from experimental.hierarchical_search.utils import is_path_match_topic, write_json

    df = pd.read_excel("all_qa_merged.xlsx")
    # print(df.head())

    wrongs = []
    true_cnt = 0
    for idx, row in df.iterrows():
        query = row["query"]
        query_embedding = await embed_node.embed([query])
        query_embedding = query_embedding["embeddings"][0]
        partitions = naive_navigator.navigate(query_embedding= query_embedding, top_k_topic= 3)
        check = False
        for i in partitions: 
            if is_path_match_topic(row["source_file"], i): 
                true_cnt += 1 
                check = True 
                break 
        if not check: #wrong 
            wrongs.append({"index": idx, "query": query, "source_file": row["source_file"], "predicted-topic": partitions})

    
    print(f"result: get {true_cnt}/{len(df)} true")
    write_json(wrongs, "naive_navigator.json")

        
        



if __name__ == "__main__":
    asyncio.run(main())
    
    

