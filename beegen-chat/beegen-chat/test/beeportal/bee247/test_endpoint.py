import requests
import json
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



url = "http://10.1.27.43:8831/auth/realms/ms-core/protocol/openid-connect/token"

payload = 'client_id=ai_center&client_secret=REPLACE_WITH_LOCAL_SECRET&grant_type=client_credentials'
headers = {
  'Content-Type': 'application/x-www-form-urlencoded',
  'Accept': 'application/json'
}

response = requests.request("POST", url, headers=headers, data=payload).json()

token = response['access_token']




doc_store=DocumentStore(config=MongoConfig.from_yaml_file(
    BEEGEN_ROOT / "config/mongo.yaml")
)

chunks = doc_store.find(collection_name="dialogue", query={
    'bot_id': '4aa0843a-46d2-4acf-8b96-84d0d144a862'
})

dialogue_ids = [chunk['_id'] for chunk in chunks]
print(dialogue_ids)

# url = "https://beegen-portal.tanzu-dev.mbbank.com.vn/beegen-qa-api/update_data_new"

# payload = json.dumps({
#   "bot_id": "bot_4aa0843a_46d2_4acf_8b96_84d0d144a862",
#   "type": "QA",
#   "ids": dialogue_ids
# })
# headers = {
#   'accept': 'application/json',
#   'Content-Type': 'application/json',
#   'Authorization': f"Bearer {token}"
# }

# response = requests.request("POST", url, headers=headers, data=payload, verify=False)

# print(response.text)


