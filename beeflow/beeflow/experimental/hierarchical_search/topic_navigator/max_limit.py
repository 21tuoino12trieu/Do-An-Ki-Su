import email
from litellm import EmbeddingInput
from pymilvus import MilvusClient, AnnSearchRequest, WeightedRanker
from collections import defaultdict
import numpy as np 
import asyncio
from typing import Dict, List 
from sklearn.metrics.pairwise import cosine_distances

class AdvancedNavigator():
    def __init__(self, client: MilvusClient):
        self.client = client
    
    def _prepare(self, collection_name: str):
        pass 

    def navigate(self, query, query_embedding: List[float], collection_name: str, top_k_topic: int, top_k: int, top_k_score: int = 5) -> List[str]:
        # get top_k nearest sample for each topic 

        num_topics = len(self.client.list_partitions(collection_name= collection_name))
        # sparse_search_params = {"metric_type": "BM25"}
        # sparse_request = AnnSearchRequest(
        #     [query], "sparse_vector", sparse_search_params, limit=top_k
        # )

        # dense_search_params = {"metric_type": "COSINE"}
        # dense_request = AnnSearchRequest(
        #     [query_embedding], "vector", dense_search_params, limit=top_k
        # )

        # print("search_limit: ", top_k * num_topics * 3 )
        # results = self.client.hybrid_search(
        #     collection_name= collection_name,
        #     reqs= [sparse_request, dense_request],
        #     ranker=WeightedRanker(0.5, 0.5),  # Reciprocal Rank Fusion for combining results
        #     limit= top_k * num_topics * 3,
        #     # strict_group_size=True, 
        #     output_fields=["chunk_id", "content", "topic"],
        # )

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
            topic_results[topic_name].append([data['distance'], data['chunk_id'], data["content"]])

        # print(topic_results)
        topic_scores = []

        for topic, items in topic_results.items():
            distances = [d[0] for d in items]
            mean_distance = sum(distances[:top_k_score]) / min(len(distances), top_k_score)

            topic_scores.append({
                "topic": topic,
                "mean_distance": mean_distance,
                "num_chunks": len(distances)
            })

        # print(f"length topic scores: {len(topic_scores)}")
        # print(topic_scores)
        topic_scores.sort(key=lambda x: x["mean_distance"], reverse= True)

        # return [data["topic"] for data in topic_scores[:top_k_topic]]
        return [data["topic"] for data in topic_scores]
    
    
async def main():
    from experimental.test_embed_node import Embedding 
    from beegen.configs import MilvusConfig, MilvusOperation

    default_config = MilvusConfig.default()
    client = MilvusClient(uri= default_config.uri, user= default_config.username, password = default_config.password, db_name= default_config.db_name)

    embed_node = Embedding()
    query = "tôi muốn mở thẻ priority pass"
    collection_name = "hierarchical_search_no_extract"
    query_embedding = await embed_node.embed([query])
    query_embedding = query_embedding["embeddings"][0]

    naive_navigator = AdvancedNavigator(client)
    naive_navigator._prepare(collection_name= collection_name)
    partitions = naive_navigator.navigate(query= query, query_embedding= query_embedding, collection_name= collection_name, top_k_topic= 3, top_k=10)

    print(partitions)

    ########################################################
    ##########################
    import pandas as pd 
    from experimental.hierarchical_search.utils import is_path_match_topic, write_json

    df = pd.read_excel("all_qa_merged.xlsx")
    # print(df.head())

    wrongs = []
    num_topics = len(client.list_partitions(collection_name= collection_name))
    true_cnt = [0 for i in range(num_topics)]
    queries = [row["query"] for _, row in df.iterrows()]
    query_embeddings = await embed_node.embed(queries)
    query_embeddings = query_embeddings["embeddings"]

    for idx, row in df.iterrows():
        query = row["query"]
        query_embedding = query_embeddings[idx]
        partitions = naive_navigator.navigate(query= query, query_embedding= query_embedding, collection_name= collection_name, top_k_topic= 3, top_k=10)
        check = False
        for i in range(num_topics): 
            if i < len(partitions):
                name = partitions[i]
                if is_path_match_topic(row["source_file"], name): 
                    check = True 
            if check== True: 
                true_cnt[i] += 1 
    
    # print(f"result: get {true_cnt}/{len(df)} true")
    import matplotlib.pyplot as plt 

    top_k = list(range(1, len(true_cnt) + 1))

    total_samples = len(df)

    accuracy = [cnt / total_samples for cnt in true_cnt]
    print(f"accuracy: {accuracy}")

    plt.figure()
    plt.plot(top_k, accuracy, marker='o')
    plt.xlabel("Top-K")
    plt.ylabel("Accuracy")
    plt.title("Top-K Accuracy")

    # Ghi accuracy phía trên mỗi point
    for x, y in zip(top_k, accuracy):
        plt.text(
            x, y,
            f"{y:.3f}",      # format 3 chữ số thập phân
            ha="center",
            va="bottom",
            fontsize=7
        )

    # Lưu ảnh
    plt.savefig("topk_accuracy.png", dpi=300, bbox_inches="tight")
    plt.close()

    # write_json(wrongs, "advanced_navigator.json")

if __name__ == "__main__":
    asyncio.run(main())