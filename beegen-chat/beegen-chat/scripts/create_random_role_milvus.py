from beegenerate.rag import MilvusStorage
from beegenerate.configs.bee_config import TOTAL_CONFIG
from beegenerate.rag import VDBQuery


milvus = MilvusStorage(TOTAL_CONFIG.milvus)
data_count = milvus.status(collection_name="bot_01ad22a3_f07f_4dd8_b3c4_6548ae9e5c95").vector_count
query = VDBQuery(
    query_vector=[0]*1024,
    collection="bot_01ad22a3_f07f_4dd8_b3c4_6548ae9e5c95",
    top_k=data_count,
    output_fields=["chunk_id", "vector", "role", "type", "topic"]
)

results = milvus.run(query=query)

records = [r.record for r in results]

import random

roles = ["L1", "L2", "L3"]
topics = ["thẻ", "vay mua", "tiết kiệm", "du lịch", "rủi ro"]


for i in range(len(records)):
    r = random.choice(roles)
    t = random.choice(topics)
    records[i].payload['role'] = r
    records[i].payload['topic'] = t


milvus.add("bot_hihihaha", records=records)