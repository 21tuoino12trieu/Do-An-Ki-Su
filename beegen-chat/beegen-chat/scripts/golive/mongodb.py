from pymongo import MongoClient
import yaml

# CREATE MONGO COLLECTION
yaml_content = """
authen_source: aicenter_chatbot
cluster:
- 10.215.107.53:27017
password: REPLACE_WITH_LOCAL_SECRET
username: nlpdev
readPreference: primary
appname: MongoDBCompass
ssl: false
directConnection: true
"""

mongo_config = yaml.safe_load(yaml_content)


escaped_username = mongo_config['username']
escaped_password = mongo_config['password']

# Join the hosts with comma separation
host_string = ",".join(mongo_config['cluster'])

# Start with the base URI
uri = f"mongodb://{escaped_username}:{escaped_password}@{host_string}/"

# Build query parameters
params = []

# Add required authSource
params.append(f"authSource={mongo_config['authen_source']}")

# Add optional parameters if they're set
if mongo_config['readPreference'] is not None:
    params.append(f"readPreference={mongo_config['readPreference']}")
    
if mongo_config['appname'] is not None:
    params.append(f"appname={mongo_config['appname']}")
    
# Add boolean parameters
params.append(f"ssl={str(mongo_config['ssl']).lower()}")
params.append(f"directConnection={str(mongo_config['directConnection']).lower()}")

# Join all parameters with '&' and append to URI
uri = f"{uri}?{'&'.join(params)}"

# # Connect to MongoDB to get configs
# client = MongoClient(uri)
# db = client[mongo_config['authen_source']]
# configs_data = list(db.beegen_configurations.find())

configs_data = [
  {
    "_id": "e2ffa1f6-9a77-4949-9385-49cc93b9c4c7",
    "type": "LLM",
    "config": {
      "api_key": "mb123456789",
      "api_type": "vllm",
      "base_url": "http://10.1.39.127:30042/v1",
      "model": "model/beegen-model-v1",
      "model_alias": "mô hình beegen-v1",
      "temperature": 0,
      "top_p": 0.001,
      "frequency_penalty": 0,
      "max_tokens": None,
      "n": 1,
      "presence_penalty": 0,
      "api_version": ""
    },
    "system_prompt": "hihihaha"
  },
  {
    "_id": "4bf58444-0256-4d96-ae4e-f31dd00f6dad",
    "type": "EMBEDDING",
    "config": {
      "api_type": "tei",
      "api_key": "mb123456789",
      "base_url": "http://10.1.39.127:30044/embed",
      "model": "BAAI/bge-m3",
      "embed_batch_size": 32,
      "dimensions": 1024,
      "model_alias": "mô hình bge-m3",
      "retrieval_threshold": 0,
      "retrieval_top_k": 16
    }
  },
  {
    "_id": "857be20a-0a19-405b-8d43-d5547a2cbcf7",
    "type": "RERANKING",
    "config": {
      "api_type": "tei",
      "api_key": "mb123456789",
      "base_url": "http://10.1.39.127:30043/rerank",
      "model": "BAAI/bge-reranker-v2-m3",
      "model_alias": "mô hình bge-m3-rerank",
      "rerank_threshold": 0,
      "rerank_top_k": 4
    }
  },
  {
    "_id": "7ae6db59-6634-4423-ba5c-72c39d418396",
    "type": "LLM",
    "config": {
      "api_key": "REPLACE_WITH_LOCAL_SECRET",
      "api_type": "azure",
      "api_version": "2024-08-01-preview",
      "base_url": "https://10.1.13.168:9443/bee247dev",
      "frequency_penalty": 0,
      "max_tokens": 4096,
      "model": "gpt-4o",
      "model_alias": "mô hình azure openai dev",
      "n": 1,
      "presence_penalty": 0,
      "stream": True,
      "temperature": 0,
      "top_p": 1
    },
    "system_prompt": "hihihaha"
  },
  {
    "_id": "9dc40ddb-123e-4191-b429-5c5bd0f5e772",
    "type": "DEFAULT",
    "config": {
      "llm": {
        "api_key": "mb123456789",
        "api_type": "vllm",
        "base_url": "http://10.1.39.127:30042/v1",
        "model": "model/beegen-model-v1",
        "api_version": "",
        "model_alias": "mô hình beegen-v1"
      },
      "embedding": {
        "api_type": "tei",
        "api_key": "mb123456789",
        "base_url": "http://10.1.39.127:30044/embed",
        "model": "BAAI/bge-m3",
        "embed_batch_size": 32,
        "dimensions": 1024,
        "model_alias": "mô hình bge-m3"
      },
      "reranking": {
        "api_type": "tei",
        "api_key": "mb123456789",
        "base_url": "http://10.1.39.127:30043/rerank",
        "model": "BAAI/bge-reranker-v2-m3",
        "model_alias": "mô hình bge-m3-rerank"
      },
      "retrieval": {
        "retrieval_threshold": 0,
        "retrieval_top_k": 16,
        "rerank_threshold": 0,
        "rerank_top_k": 4
      },
      "completion": {
        "temperature": 0,
        "top_p": 0.001,
        "frequency_penalty": 0,
        "n": 1,
        "presence_penalty": 0,
        "max_tokens": None,
        "model": "model/beegen-model-v1"
      }
    }
  },
  {
    "_id": "d1d45131-6688-4f70-a770-e21980f883dd",
    "type": "EMBEDDING",
    "config": {
      "api_type": "vllm",
      "api_key": "mb123456789",
      "base_url": "http://10.1.87.71:30044/v1/embeddings",
      "model": "model/bge-m3",
      "embed_batch_size": 32,
      "dimensions": 1024,
      "model_alias": "mô hình bge-m3 (vllm)",
      "retrieval_threshold": 0,
      "retrieval_top_k": 16
    }
  },
  {
    "_id": "96f11def-3fd8-4b2b-a911-a06207aaa99b",
    "type": "RERANKING",
    "config": {
      "api_type": "vllm",
      "api_key": "mb123456789",
      "base_url": "http://10.1.87.71:30043/v1/rerank",
      "model": "model/bge-reranker-v2-m3",
      "model_alias": "mô hình bge-m3-rerank (vllm)",
      "rerank_threshold": 0,
      "rerank_top_k": 4
    }
  }
]


# Connect to MongoDB to push configs to given collection

client = MongoClient(uri)
db = client[mongo_config['authen_source']]
result = db.beegen_configurations_v2.insert_many(configs_data)
print(f"Successfully inserted {len(result.inserted_ids)} documents "
      f"into beegen_configurations_v2")
