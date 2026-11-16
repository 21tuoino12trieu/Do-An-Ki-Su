from httpx import delete
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
    WeightedRanker
)



from experimental.test_embed_node import Embedding
from experimental.test_llm import LLM
import uuid

class Solution:

    def __init__(self):
        self.embed_node = Embedding()
        self.llm_node = LLM()

    def add_extract_collection(self, client: MilvusClient, collection_name: str):
        analyzer_params = {"tokenizer": "standard", "filter": ["lowercase"]}

        schema = MilvusClient.create_schema()
        schema.add_field(
            field_name="id",
            datatype=DataType.VARCHAR,
            is_primary=True,
            auto_id=False,
            max_length=100,
        )
        schema.add_field(
            field_name= "original_content",
            datatype= DataType.VARCHAR,
            max_length = 65535
        )

        schema.add_field(
            field_name="content",
            datatype=DataType.VARCHAR,
            max_length=65535,
            analyzer_params=analyzer_params,
            enable_match=True,  # Enable text matching
            enable_analyzer=True,  # Enable text analysis
        )
        schema.add_field(field_name="sparse_vector", datatype=DataType.SPARSE_FLOAT_VECTOR)
        schema.add_field(
            field_name="dense_vector",
            datatype=DataType.FLOAT_VECTOR,
            dim=1024,  # Dimension for text-embedding-3-small
        )

        # Define BM25 function to generate sparse vectors from text
        bm25_function = Function(
            name="bm25",
            function_type=FunctionType.BM25,
            input_field_names=["content"],
            output_field_names="sparse_vector",
        )

        # Add the function to schema
        schema.add_function(bm25_function)

        index_params = MilvusClient.prepare_index_params()
        index_params.add_index(
            field_name="sparse_vector",
            index_type="SPARSE_INVERTED_INDEX",
            metric_type="BM25",
        )
        index_params.add_index(field_name="dense_vector", index_type="FLAT", metric_type="COSINE")
        

        collections = client.list_collections()
        ################################ add collection
        if collection_name in collections: 
            print("collection existed")
        else:
            client.create_collection(
            collection_name=collection_name,
            schema=schema,
            index_params=index_params,)

        print(f"Collection '{collection_name}' created successfully")

    def add_collection(self, client: MilvusClient, collection_name: str):
        analyzer_params = {"tokenizer": "standard", "filter": ["lowercase"]}

        schema = MilvusClient.create_schema()
        schema.add_field(
            field_name="id",
            datatype=DataType.VARCHAR,
            is_primary=True,
            auto_id=False,
            max_length=100,
        )
        schema.add_field(
            field_name="content",
            datatype=DataType.VARCHAR,
            max_length=65535,
            analyzer_params=analyzer_params,
            enable_match=True,  # Enable text matching
            enable_analyzer=True,  # Enable text analysis
        )
        schema.add_field(field_name="sparse_vector", datatype=DataType.SPARSE_FLOAT_VECTOR)
        schema.add_field(
            field_name="dense_vector",
            datatype=DataType.FLOAT_VECTOR,
            dim=1024,  # Dimension for text-embedding-3-small
        )

        # Define BM25 function to generate sparse vectors from text
        bm25_function = Function(
            name="bm25",
            function_type=FunctionType.BM25,
            input_field_names=["content"],
            output_field_names="sparse_vector",
        )

        # Add the function to schema
        schema.add_function(bm25_function)

        index_params = MilvusClient.prepare_index_params()
        index_params.add_index(
            field_name="sparse_vector",
            index_type="SPARSE_INVERTED_INDEX",
            metric_type="BM25",
        )
        index_params.add_index(field_name="dense_vector", index_type="FLAT", metric_type="COSINE")
        

        collections = client.list_collections()
        ################################ add collection
        if collection_name in collections: 
            print("collection existed")
        else:
            client.create_collection(
            collection_name=collection_name,
            schema=schema,
            index_params=index_params,)

        print(f"Collection '{collection_name}' created successfully")

    async def insert_sample_extract(self, client: MilvusClient, chunk: str, extract_chunk: str, collection_name):
        embeds = await self.embed_node.embed([chunk])
        embed_vectors = embeds["embeddings"]

        entities = [] 
        
        embed = embed_vectors[0] 

        entities.append(
            {
                "id": str(uuid.uuid4()),
                "original_content": chunk,
                "content": extract_chunk,
                "dense_vector": embed, 
            }
        )
        client.insert(collection_name= collection_name, data= entities)
        print(f"Successfully add chunk")


    async def insert_document(self, client: MilvusClient, file_path: str, collection_name):
        chunks = chunk_txt_file(file_path)

        embeds = await self.embed_node.embed(chunks)

        embed_vectors = embeds["embeddings"]

        entities = [] 
        for i in range(len(chunks)):
            chunk = chunks[i] 
            embed = embed_vectors[i] 

            entities.append(
                {
                    "id": str(uuid.uuid4()),
                    "content": chunk,
                    "dense_vector": embed, 
                }
            )
        client.insert(collection_name= collection_name, data= entities)
        print(f"Successfully add file {file_path}")

    def read_chunks_json(self, filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    async def insert_chunk_file_extract(self, client: MilvusClient, file_path: str, collection_name):
        chunks = self.read_chunks_json(filepath= file_path)
        embeds = await self.embed_node.embed(chunks)

        embed_vectors = embeds["embeddings"]

        entities = [] 
        for i in range(len(chunks)):
            chunk = chunks[i] 
            embed = embed_vectors[i] 
            extract_content = await self.llm_node.generate(chunk)

            entities.append(
                {
                    "id": str(uuid.uuid4()),
                    "original_content": chunk,
                    "content": extract_content,
                    "dense_vector": embed, 
                }
            )
        client.insert(collection_name= collection_name, data= entities)
        print(f"Successfully add file {file_path}")

    async def insert_chunk_file(self, client: MilvusClient, file_path: str, collection_name):
        chunks = self.read_chunks_json(filepath= file_path)
        embeds = await self.embed_node.embed(chunks)

        embed_vectors = embeds["embeddings"]

        entities = [] 
        for i in range(len(chunks)):
            chunk = chunks[i] 
            embed = embed_vectors[i] 

            entities.append(
                {
                    "id": str(uuid.uuid4()),
                    "content": chunk,
                    "dense_vector": embed, 
                }
            )
        client.insert(collection_name= collection_name, data= entities)
        print(f"Successfully add file {file_path}")

    async def get_embeddings(self, text: str):
        embeds = await self.embed_node.embed(text)

        return embeds["embeddings"]
    
    async def query(self, client: MilvusClient, query: str,collection_name: str, top_k: int):
        query_embedding = await self.get_embeddings([query])
        query_embedding = query_embedding[0]

        # Set up BM25 search request
        sparse_search_params = {"metric_type": "BM25"}
        sparse_request = AnnSearchRequest(
            [query], "sparse_vector", sparse_search_params, limit=top_k
        )

        # Set up dense vector search request
        dense_search_params = {"metric_type": "COSINE"}
        dense_request = AnnSearchRequest(
            [query_embedding], "dense_vector", dense_search_params, limit=top_k
        )

        # Perform hybrid search with reciprocal rank fusion
        results = client.hybrid_search(
            collection_name,
            [sparse_request, dense_request],
            ranker=WeightedRanker(0.6, 0.4),  # Reciprocal Rank Fusion for combining results
            limit=top_k,
            output_fields=["content"],
        )
        hybrid_results = results[0]

        # Print results
        print("\nHybrid Search (Combined):")
        for i, result in enumerate(hybrid_results):
            print(
                f"{i+1}. Score: {result['distance']:.4f}, Content: {result['entity']['content']}"
            )
    def write_json(self, chunks, filepath):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(chunks, f, ensure_ascii=False, indent=2)
        print("done")

    async def log_query(self, client: MilvusClient, query: str,collection_name: str, top_k: int, export: bool= True):
        query_embedding = await self.get_embeddings([query])
        query_embedding = query_embedding[0]

        #############################################
        ## sparse search 
        results = client.search(
            collection_name=collection_name,
            data=[query],
            anns_field="sparse_vector",
            limit=top_k,
            output_fields=["content"],

        )
        sparse_results = results[0]

        # Print results
        print("\nSparse Search (Full-text search):")
        for i, result in enumerate(sparse_results):
            print(
                f"{i+1}. Score: {result['distance']:.4f}, Content: {result['entity']['content']}"
            )
        
        if export: 
            res = [f"{i+1}. Score: {result['distance']:.4f}, Content: {result['entity']['content']}" for i, result in enumerate(sparse_results)]
            res = [f"Query: {query}"] + res
            self.write_json(chunks= res, filepath= "sparse.json")


        ###################################################
        ## dense search 

        # Semantic search using dense vectors
        results = client.search(
            collection_name=collection_name,
            data=[query_embedding],
            anns_field="dense_vector",
            limit=top_k,
            output_fields=["content"],
        )
        dense_results = results[0]

        # Print results
        print("\nDense Search (Semantic):")
        for i, result in enumerate(dense_results):
            print(
                f"{i+1}. Score: {result['distance']:.4f}, Content: {result['entity']['content']}"
            )
        if export: 
            res = [f"{i+1}. Score: {result['distance']:.4f}, Content: {result['entity']['content']}" for i, result in enumerate(dense_results)]
            res = [f"Query: {query}"] + res
            self.write_json(chunks= res, filepath= "dense.json")

        ###############################################
        ## hybrid 
         # Set up BM25 search request
        sparse_search_params = {"metric_type": "BM25"}
        sparse_request = AnnSearchRequest(
            [query], "sparse_vector", sparse_search_params, limit=top_k
        )

        # Set up dense vector search request
        dense_search_params = {"metric_type": "COSINE"}
        dense_request = AnnSearchRequest(
            [query_embedding], "dense_vector", dense_search_params, limit=top_k
        )

         # Perform hybrid search with reciprocal rank fusion
        results = client.hybrid_search(
            collection_name,
            [sparse_request, dense_request],
            ranker=WeightedRanker(0.5, 0.5),  # Reciprocal Rank Fusion for combining results
            # ranker= RRFRanker(),
            limit=top_k,
            output_fields=["content"],
        )
        hybrid_results = results[0]

        # Print results
        print("\nHybrid Search (Combined):")
        for i, result in enumerate(hybrid_results):
            print(
                f"{i+1}. Score: {result['distance']:.4f}, Content: {result['entity']['content']}"
            )

        if export: 
            res = [f"{i+1}. Score: {result['distance']:.4f}, Content: {result['entity']['content']}" for i, result in enumerate(hybrid_results)]
            res = [f"Query: {query}"] + res
            self.write_json(chunks= res, filepath= "hybrid.json")

    
    async def log_query_extract(self, client: MilvusClient, query: str,collection_name: str, top_k: int, export: bool= True):
        query_embedding = await self.get_embeddings([query])
        query_embedding = query_embedding[0]

        #############################################
        ## sparse search 
        results = client.search(
            collection_name=collection_name,
            data=[query],
            anns_field="sparse_vector",
            limit=top_k,
            output_fields=["content", "original_content"],
        )
        sparse_results = results[0]

        # Print results
        print("\nSparse Search (Full-text search):")
        for i, result in enumerate(sparse_results):
            print(
                f"{i+1}. Score: {result['distance']:.4f}, Content: {result['entity']['content']}"
            )
        
        if export: 
            res = [f"{i+1}. Score: {result['distance']:.4f}, Content: {result['entity']['original_content']}" for i, result in enumerate(sparse_results)]
            res += [f"{i+1}. Score: {result['distance']:.4f}, Search_content: {result['entity']['content']}" for i, result in enumerate(sparse_results)]
            res = [f"Query: {query}"] + res
            self.write_json(chunks= res, filepath= "sparse.json")


        ###################################################
        ## dense search 

        # Semantic search using dense vectors
        results = client.search(
            collection_name=collection_name,
            data=[query_embedding],
            anns_field="dense_vector",
            limit=top_k,
            output_fields=["content","original_content"],
        )
        dense_results = results[0]

        # Print results
        print("\nDense Search (Semantic):")
        for i, result in enumerate(dense_results):
            print(
                f"{i+1}. Score: {result['distance']:.4f}, Content: {result['entity']['content']}"
            )
        if export: 
            res = [f"{i+1}. Score: {result['distance']:.4f}, Content: {result['entity']['original_content']}" for i, result in enumerate(dense_results)]
            res += [f"{i+1}. Score: {result['distance']:.4f}, Search_content: {result['entity']['content']}" for i, result in enumerate(dense_results)]
            res = [f"Query: {query}"] + res
            self.write_json(chunks= res, filepath= "dense.json")

        ###############################################
        ## hybrid 
         # Set up BM25 search request
        sparse_search_params = {"metric_type": "BM25"}
        sparse_request = AnnSearchRequest(
            [query], "sparse_vector", sparse_search_params, limit=top_k
        )

        # Set up dense vector search request
        dense_search_params = {"metric_type": "COSINE"}
        dense_request = AnnSearchRequest(
            [query_embedding], "dense_vector", dense_search_params, limit=top_k
        )

         # Perform hybrid search with reciprocal rank fusion
        results = client.hybrid_search(
            collection_name,
            [sparse_request, dense_request],
            # ranker=WeightedRanker(0.5, 0.5),  # Reciprocal Rank Fusion for combining results
            ranker= RRFRanker(),
            limit=top_k,
            output_fields=["content", "original_content"],
        )
        hybrid_results = results[0]

        # Print results
        print("\nHybrid Search (Combined):")
        for i, result in enumerate(hybrid_results):
            print(
                f"{i+1}. Score: {result['distance']:.4f}, Content: {result['entity']['content']}"
            )

        if export: 
            res = [f"{i+1}. Score: {result['distance']:.4f}, Content: {result['entity']['original_content']}" for i, result in enumerate(hybrid_results)]
            res += [f"{i+1}. Score: {result['distance']:.4f}, Search_content: {result['entity']['content']}" for i, result in enumerate(hybrid_results)]
            res = [f"Query: {query}"] + res
            self.write_json(chunks= res, filepath= "hybrid.json")


def delete_collection(client: MilvusClient, collection_name: str):
    collections = client.list_collections()
    
    if collection_name not in collections: 
        print(f"{collection_name} not in collections list to delete")
    client.drop_collection(collection_name= collection_name)
    print("deleted")

async def main():
    default_config = MilvusConfig.default()
    client = MilvusClient(uri= default_config.uri, user= default_config.username, password = default_config.password, db_name= default_config.db_name)



    collection_name = "hybrid_search_test"


    # delete_collection(client, collection_name)
    #--------------------------------------------------------------

    sol = Solution() 
    sol.add_extract_collection(client,collection_name)

    # sol.add_extract_collection(client, collection_name)

    # file_dir = 'test-text'
    # files = os.listdir(file_dir)

    # for file_name in files: 
    #     file_path = os.path.join(file_dir, file_name)
        

    #     await sol.insert_document(client, file_path= file_path, collection_name = collection_name)
    # chunk_file_path = "chunks.json"
    # await sol.insert_chunk_file_extract(client, chunk_file_path, collection_name)

    #----------------------------------------------------------------------
    query = "tôi muốn mở thẻ visa infinite"    # both work 
    # query = "lãi suất thẻ visa infinite là bao nhiêu"  #both work
    # query = "Tôi đã có thẻ tín dụng JCB thì có thể thêm thẻ unionpay để thanh toán online dc ko"   #both not work 
    # query = "Tôi đã có thẻ tín dụng JCB thì có thể phát hành thêm thẻ unionpay để thanh toán online dc ko"   #both not work
    # query = "Tôi đã có thẻ tín dụng JCB, liệu tôi có thuộc đối tượng có thể thêm thẻ unionpay để thanh toán online dc ko"   #both work
    # query = "thẻ UPI có phải là union pay ko"  #both work 
    # query = "số lượng thẻ tối đa"  #both work
    # query = "thẻ upi là gì?"    #both work 
    # query = "tôi muốn mở thẻ hybrid, tôi cần điều kiện gì?"
    # query = "các định nghĩa visa?" # sparse better, dense can not search visa led hi 
    # query = "hạn mức giao dịch của các thẻ visa?"  #both lack of visa led hi, topk = 10 text search better
    await sol.log_query_extract(client, query, collection_name, 15)  



    
    

if __name__ == "__main__":
    asyncio.run(main())