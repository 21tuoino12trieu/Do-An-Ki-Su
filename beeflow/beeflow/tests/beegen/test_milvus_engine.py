import time
from beegen.configs import MilvusConfig, MilvusOperation
from beegen.vectordb.milvus_engine import MilvusEngine
from experimental.test_embed_node import Embedding
import asyncio 
import json 

def write_json(chunks, filepath):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)
    print("done")

async def main(): 

    milvus_exec = MilvusEngine(MilvusConfig.default())
    embed_node = Embedding()

    query = "phát hành visa infinite"
    query_embedding = await embed_node.embed([query])
    query_embedding = query_embedding["embeddings"]

    start_time = time.time()
    # result = await milvus_exec.run(
    #     operation=MilvusOperation.SEARCH,
    #     query_vectors = query_embedding,
    #     collection_name = "hybrid_search_extract",
    #     output_fields = ["id", "original_content"],
    #     top_k = 20
    # )

    # result = await milvus_exec.run(
    #     operation=MilvusOperation.HYBRID_SEARCH,
    #     query = [query],
    #     query_vectors = query_embedding,
    #     collection_name = "hybrid_search_extract",
    #     output_fields = ["id", "content"],
    #     top_k = 20
    # )

    result = await milvus_exec.run(
        operation=MilvusOperation.HIERARCHICAL_SEARCH,
        query = [query],
        query_vectors = query_embedding,
        collection_name = "hierarchical_search2",
        output_fields = ["chunk_id", "content", "topic"],
        top_k = 10,
        top_k_topic= 3, 
        top_k_score = 5, 
        use_hybrid_search= True,

    )
    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"search successfully in {elapsed_time:.2f} seconds")

    print(result, flush= True)

    write_content= [f"{data["content"]}" for data in result['results'][0]]
    write_json(chunks= write_content, filepath= "result.json")

if __name__ == "__main__":
    asyncio.run(main())

