import re
from beegenerate.prompts.bee247 import *
from bee247.constants import get_card_filename
import asyncio
from beegenerate.configs import (
    LLMConfig,
    RetrievalConfig,
    RerankingConfig,
    MongoConfig,
    MilvusConfig
)

from beegenerate.llms.llm_executor import LLMExecutor
from beegenerate.retrievers import VectorRetriever
from beegenerate.vectordb import MilvusStorage
from beegenerate.storage import (
    DocumentStore,
    BotStore,
    MongoStorage
)

from datetime import datetime
from beegenerate.loggings import LOGGER

from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from typing import List, Dict, AsyncGenerator, Any


from datetime import datetime

from beegenerate.prompts.bee247_v2 import *
from beegenerate.reranks.rerank_factory import RerankingFactory
from bee247.constants import *

import json
import yaml
import pandas as pd

from beegenerate.const import BEEGEN_ROOT
from beeportal.bee247_bot import Bee247Bot

## lấy chunk từ mongo về
doc_store=DocumentStore(config=MongoConfig.from_yaml_file(
    BEEGEN_ROOT / "config/mongo.yaml")
)

chunks = doc_store.find(collection_name="chunk_data", query={
    'collection_name': re.compile(r"bot_4aa0843a_46d2_4acf_8b96_84d0d144a862")
})

## tạo milvus collection mới
from beegenerate.vectordb.milvus_v2 import MilvusExecutor
from beegenerate.configs import MilvusConfig, MilvusOperation

vec_store=MilvusStorage(config=MilvusConfig.default())
# name_collection = vec_store._generate_collection_name()
# print(name_collection)

milvus_exec = MilvusExecutor(MilvusConfig.default())

# create_response = asyncio.run(milvus_exec.run(
#     operation=MilvusOperation.CREATE_COLLECTION,
#     params={
#         "collection_name": name_collection,
#         "fields": [
#             {"name": "role", "type": "varchar", "params": {"max_length": 4048}},
#             {"name": "vector", "type": "vector", "params": {"dim": 1024}},
#             {"name": "chunk_id", "type": "varchar", "is_primary": True, "params": {"max_length": 65535}},
#             {"name": "topic", "type": "varchar", "params": {"max_length": 65535}},
#             {"name": "type", "type": "varchar", "params": {"max_length": 65535}}
#         ],
#         "description": ""
#     }
# ))


## extract ra thông tin từ chunk để embed vào milvus collection đã tạo
bot = Bee247Bot(bot_id="4f2e4935-c8e2-4e81-9879-8533fb2f9998")
embed = bot._retriever._embedder


pairs = [(asyncio.run(embed.run(texts=chunk['llm_text'])), chunk['chunk_id']) for chunk in chunks]

data = [{
    "role": "L1",
    "vector": pair[0][0],
    "chunk_id": pair[1],
    "topic": "default",
    "type": "QA",
} for pair in pairs]

## đẩy data vào milvus
# _ = asyncio.run(milvus_exec.run(
#     operation=MilvusOperation.INSERT,
#     params={
#         "collection_name": "Time2025_04_10T17_11_57_113854",
#         "data": data
#     }
# ))



## tạo query, embed
query = "Phí rút tiền mặt thẻ tín dụng JCB?"

## retrieve
retriever = VectorRetriever(
    config=RetrievalConfig.default(),
    vec_store=MilvusStorage(config=MilvusConfig.default()),
    doc_store=DocumentStore(config=MongoConfig.from_yaml_file(
        BEEGEN_ROOT / "config/mongo.yaml")
    )
)

results = asyncio.run(retriever.run(query=query, collection="Time2025_04_10T17_11_57_113854", top_k=10, threshold=0.0, partition_names=['QA']))
print(results)