from beegenerate.configs.bee_config import TOTAL_CONFIG
from beegenerate.rag import MilvusStorage
from beegenerate.rag import VDBQuery

import numpy as np

# Set random seed for reproducibility
np.random.seed(42)

milvus = MilvusStorage(
    config=TOTAL_CONFIG.milvus
)

results = milvus.run(
    VDBQuery(
        collection="bot_01ad22a3_f07f_4dd8_b3c4_6548ae9e5c95",
        query_vector=np.random.uniform(-1, 1, 1024).tolist(),
        top_k=10,
        output_fields=["chunk_id", "role"],
    ),
    # expr='role == "L3"',
)

for r in results:
    print(r)

# samples = [r.record for r in results]

# milvus.add("thanglq2_temp", samples)

# print(milvus._get_primary_and_vector_fields("bot_c15c91eb_7ffc_48f9_803a_2e26c85e398d"))