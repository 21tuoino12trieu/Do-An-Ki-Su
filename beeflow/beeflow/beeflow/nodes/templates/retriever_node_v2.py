from datetime import datetime
import re
from typing import Dict, List, Any, Optional

from beeflow.nodes.base_node import END, START
from beeflow.nodes.graph.graph_node import GraphNode
from beeflow.configs.node_config import NodeType
from beeflow.configs.graph_config import GraphNodeConfig
from beegen.utils.common import transform_bot_id
from beegen.loggings import LOGGER
def create_role_mongo_pipeline(allowed_roles: List[str], bot_id: str)  -> Dict[str, Any]:
    """
    Args:
        bot_id (str)
        allowed_roles (List[str])
    
    Returns:
        pipeline (Dict)
    """
    return {
        "pipeline": {
            "role_name": {
                "$in": allowed_roles
            },
            "bot_id": bot_id
        }
    }

def create_mongo_pipeline(chunk_ids: List, role_ids: List, document_collection: str) -> Dict[str, Any]:
    """
    Create a MongoDB aggregation pipeline to fetch documents by chunk and role IDs.

    Args:
        chunk_ids (List): List of chunk IDs to retrieve.
        role_ids (List): List of role IDs to filter.
        document_collection (str): Name of the document collection.

    Returns:
        pipeline (Dict[str, Any]): Dictionary with a single key "pipeline" containing the aggregation pipeline as a list.
    """
    return {
        "pipeline": [
            {
                "$match": {
                    "chunk_id": {"$in": chunk_ids}
                }
            },
            {
                "$lookup": {
                    "from": document_collection,
                    "localField": "doc_id",
                    "foreignField": "_id",
                    "as": "docs"
                }
            },
            {"$unwind": "$docs"},
            {
                "$match": {
                    "docs.role_ids": {"$in": role_ids},
                    "$or": [
                        {"docs.valid_from": None},
                        {"docs.valid_from": {"$lte": datetime.utcnow()}}
                    ]
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "chunk_id": 1,
                    "doc_id": 1,
                    "raw_text": 1,
                    "llm_text": 1,
                    "questions": "$docs.questions",
                    "valid_from": "$docs.valid_from",
                    "valid_to": "$docs.valid_to",
                }
            }
        ]
    }

def collect_milvus_chunk_ids(milvus_chunks: List[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """
    Collect all chunk_ids using list comprehension.
    
    Args:
        milvus_chunks: List containing sublists of dictionaries with chunk_id keys
        
    Returns:
        chunk_ids (List): List of all chunk_id values.
        distance_map (Dict): Mapping from chunk_id to Milvus distance.
    """
    return {
        "chunk_ids": [item["chunk_id"] for sublist in milvus_chunks for item in sublist if "chunk_id" in item],
        "distance_map": {item["chunk_id"]: item.get("distance") for sublist in milvus_chunks for item in sublist if "chunk_id" in item},
    }

def collect_role_ids(roles: List[Dict[str, Any]]) -> Dict[str, List]:
    """
    Collect all role_ids using list comprehension.
    
    Args:
        roles: List containing sublists of dictionaries with role_ids keys
        
    Returns:
        role_ids (List): List of all role_ids values
    """
    return {
        "role_ids": [item['_id'] for item in roles]
    }

def join_docs(
    chunk_ids: Any,
    document_chunks: List[Dict[str, Any]] | None = None,
    dialogue_chunks: List[Dict[str, Any]] | None = None,
    distance_map: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Merge document and dialogue chunks into a unified list of documents.

    Args:
        document_chunks (List[Dict[str, Any]]): List of document chunk dicts.
        dialogue_chunks (List[Dict[str, Any]]): List of dialogue chunk dicts.
        chunk_ids (List[str] or dict): List of chunk IDs to include in the result, or a dict containing 'ids'.
        distance_map (Dict[str, Any]): Milvus distance keyed by chunk_id.

    Returns:
        docs (Dict[str, Any]): Dictionary with a single key "docs" containing a list of merged document dicts.
    """
    def replace_question(text, new_question):
        # Tìm vị trí bắt đầu của "Câu hỏi:" và "Câu trả lời:"
        question_start = text.find("Câu hỏi:")
        answer_start = text.find("Câu trả lời:")

        if question_start != -1 and answer_start != -1:
            # Tạo văn bản mới với câu hỏi đã được thay thế
            new_text = text[:question_start + len("Câu hỏi: ")] + new_question + text[answer_start - 1:]
            return new_text
        else:
            # Nếu không tìm thấy cả "Câu hỏi:" và "Câu trả lời:", sử dụng regex ban đầu
            return re.sub(r'(Câu hỏi:\s*).*?(?=\n)', r'\1' + new_question, text, flags=re.DOTALL)
    
    chunk_map: Dict[str, Dict[str, Any]] = {}

    # Defensive: ensure document_chunks and dialogue_chunks are lists
    if not isinstance(document_chunks, list):
        document_chunks = []
    if not isinstance(dialogue_chunks, list):
        dialogue_chunks = []
    if not isinstance(distance_map, dict):
        distance_map = {}

    for chunk in document_chunks:
        if isinstance(chunk, dict) and 'chunk_id' in chunk:
            chunk_map[chunk['chunk_id']] = chunk
    for chunk in dialogue_chunks:
        if isinstance(chunk, dict) and 'chunk_id' in chunk:
            chunk_map[chunk['chunk_id']] = chunk

    result: List[Dict[str, Any]] = []

    none_value: None = None

    # Defensive: chunk_ids may be a dict with 'ids' or 'chunk_ids' key
    if isinstance(chunk_ids, dict) and 'ids' in chunk_ids:
        chunk_ids = chunk_ids['ids']
    elif isinstance(chunk_ids, dict) and 'chunk_ids' in chunk_ids:
        chunk_ids = chunk_ids['chunk_ids']
    if not isinstance(chunk_ids, list):
        chunk_ids = []

    for _id in chunk_ids:
        if chunk := chunk_map.get(_id):
            chunk_id: str = chunk.get('chunk_id', _id)
            doc_id: str = chunk.get('doc_id', None)
            llm_text: str = chunk.get('llm_text', "")

            if "questions" in chunk and isinstance(chunk["questions"], list):
                questions: List[Dict[str, Any]] = chunk['questions']
                for question in questions:
                    result.append({
                        'id': chunk_id,
                        'doc': doc_id,
                        'content': replace_question(llm_text, question.get('text', "")),
                        "distance": distance_map.get(chunk_id),
                        "valid_from": none_value,
                        "valid_to": none_value
                    })
            else:
                valid_from: Optional[Any] = chunk.get("valid_from")
                valid_to: Optional[Any] = chunk.get("valid_to")

                result.append({
                    'id': chunk_id,
                    'doc': doc_id,
                    'content': llm_text,
                    "distance": distance_map.get(chunk_id),
                    "valid_from": valid_from,
                    "valid_to": valid_to,
                })

    return {
        "docs": result
    }


def final_format(reranks: Any) -> Dict[str, Any]:
    """
    Format the final list of reranked documents.

    Args:
        reranks (List or dict): List of reranked document dicts, or a dict containing 'docs'.

    Returns:
        docs (Dict[str, Any]): Dictionary with a single key "docs" containing the final list of documents.
    """
    # Defensive: reranks may be a dict with 'docs' key
    if isinstance(reranks, dict) and 'docs' in reranks:
        reranks = reranks['docs']
    if not isinstance(reranks, list):
        reranks = []
    docs = []
    for doc in reranks:
        if not isinstance(doc, dict):
            continue

        distance = doc.get("distance")
        rerank_score = doc.get("score")
        formatted_doc = {
            key: value
            for key, value in doc.items()
            if key not in {"distance", "score"}
        }
        matching_score = get_document_matching_score(distance, rerank_score)
        if matching_score is not None:
            formatted_doc["document_matching_score"] = matching_score
        docs.append(formatted_doc)

    return {
        "docs": docs
    }


def get_document_matching_score(
    distance: Optional[float] = None,
    rerank_score: Optional[float] = None,
) -> Optional[float]:
    if distance is not None and rerank_score is not None:
        return distance * 0.25 + rerank_score * 0.75
    if rerank_score is not None:
        return rerank_score
    return distance


class RetrieverNodeConfig(GraphNodeConfig):
    """Node for retrieving documents using vector similarity search (V2).

    This node implements a document retrieval pipeline that:
    1. Generates embeddings for the input query
    2. Searches for similar vectors in Milvus
    3. Collects document IDs from the Milvus search results
    4. Creates a MongoDB query to fetch the full documents by their IDs
    5. Retrieves the actual document content from MongoDB
    6. Filters the documents by user role
    7. Formats the results into a standardized structure

    Attributes:
        embed_model: Model used for text embedding
        milvus_model: Milvus model identifier
        milvus_coll: Milvus collection name
        mongo_model: MongoDB model identifier
        mongo_coll: MongoDB collection name
        input_schema: Schema defining required and optional input parameters
        use_hybrid_search: Enable search with keyword 
    """
    type: NodeType = "retriever"
    embedding: str = "bge-m3"
    rerank: str = "bge-m3"
    milvus: str = "chatbot-libra"
    mongo: str = "aicenter-chatbot"
    use_rerank: bool = True
    use_priority: bool = False
    use_hybrid_search: bool= False
    use_hierarchical_search: bool= False 

class RetrieverNode(GraphNode):

    type: NodeType = "graph"

    def __init__(
        self,
        embedding: Optional[str] = "bge-m3",
        rerank: Optional[str] = "bge-m3",
        milvus: Optional[str] = "chatbot-libra",
        mongo: Optional[str] = "aicenter-chatbot",
        use_rerank: Optional[bool] = True,
        use_priority: Optional[bool] = False,
        use_hybrid_search: Optional[bool] = False,
        use_hierarchical_search: Optional[bool] = False,
        **kwargs
    ):
        """Initialize RetrieverNodeV2 from either config or kwargs."""
        super().__init__(**kwargs)

        self.embedding = embedding
        self.rerank = rerank
        self.milvus = milvus
        self.mongo = mongo
        self.use_rerank = use_rerank
        self.use_priority = use_priority
        self.use_hybrid_search = use_hybrid_search
        self.use_hierarchical_search = use_hierarchical_search
        
        self.doc_storage = "documents"
        self.qa_storage = "dialogue"
        self.role_storage = "roles"
        self.chunk_storage = "chunk_data"
            
        self._build_graph()

    def _build_graph(self):
        from beeflow.nodes import CodeNode, EmbeddingNode, MilvusNode, MongoNode, RerankNode, START, END, INPUT, OUTPUT

        def sub(suffix: str):
            return suffix

        with self:
            _embed = EmbeddingNode(
                name=sub("embed"),
                resource_key=self.embedding,
                inputs={"texts": INPUT["query"]}
            )
            if self.use_hierarchical_search:
    
                _vec_search = MilvusNode(
                    name=sub("hierarchical_vec_search"),
                    resource_key=self.milvus,
                    operation="hierarchical_search",
                    inputs={
                        "query": INPUT["query"], 
                        "query_vectors": _embed["embeddings"],
                        "output_fields": INPUT,
                        "top_k": INPUT,
                        "top_k_topic": INPUT, 
                        "top_k_score": INPUT,
                        "threshold": INPUT,
                        "collection_name": INPUT["collection"],
                        "search_weighted_score": INPUT["search_weighted_score"],
                        "use_hybrid_search": self.use_hybrid_search,
                        "expr": INPUT,
                    }
                )

            elif self.use_hybrid_search:
                _vec_search = MilvusNode(
                    name=sub("hybrid_vec_search"),
                    resource_key=self.milvus,
                    operation="hybrid_search",
                    inputs={
                        "query": INPUT["query"], 
                        "query_vectors": _embed["embeddings"],
                        "output_fields": INPUT,
                        "partition_names": INPUT,
                        "top_k": INPUT,
                        "threshold": INPUT,
                        "collection_name": INPUT["collection"],
                        "search_weighted_score": INPUT["search_weighted_score"],
                        "partition_names": INPUT, 
                        "expr": INPUT,
                    }
                )
            else: 
                _vec_search = MilvusNode(
                    name=sub("vec_search"),
                    resource_key=self.milvus,
                    operation="search",
                    inputs={
                        "query_vectors": _embed["embeddings"],
                        "output_fields": INPUT,
                        "partition_names": INPUT,
                        "top_k": INPUT,
                        "threshold": INPUT,
                        "collection_name": INPUT["collection"]
                    }
                )
                
            
            _collect_milvus_chunk_ids = CodeNode(
                name=sub("collect_milvus_chunk_ids"),
                code_fn=collect_milvus_chunk_ids,
                inputs={"milvus_chunks": _vec_search["results"]},
                return_keys=[
                    "chunk_ids: List[str]",
                    "distance_map: Dict[str, Any]",
                ]
            )
            
            _roles_ids_query_pipeline = CodeNode(
                name=sub("roles_ids_query_pipeline"),
                code_fn=create_role_mongo_pipeline,
                inputs={
                    "allowed_roles": INPUT,
                    "bot_id": INPUT
                },
                return_keys=["pipeline: Dict[str, Any]"]
            )
            
            _role_ids_search = MongoNode(
                name=sub("role_ids_search"),
                resource_key=self.mongo,
                operation="find",
                inputs={
                    "query": _roles_ids_query_pipeline["pipeline"],
                    "collection_name": self.role_storage
                }
            )
            
            _collect_roles_ids = CodeNode(
                name=sub("collect_roles_ids"),
                code_fn=collect_role_ids,
                inputs={
                    "roles": _role_ids_search["data"],
                }
            )
            
            _doc_mongo_query_pipeline = CodeNode(
                name=sub("doc_mongo_query_pipeline"),
                code_fn=create_mongo_pipeline,
                inputs={
                    "chunk_ids": _collect_milvus_chunk_ids,
                    "role_ids": _collect_roles_ids,
                    "document_collection": self.doc_storage
                }
            )
            
            _qa_mongo_query_pipeline = CodeNode(
                name=sub("qa_mongo_query_pipeline"),
                code_fn=create_mongo_pipeline,
                inputs={
                    "chunk_ids": _collect_milvus_chunk_ids,
                    "role_ids": _collect_roles_ids,
                    "document_collection": self.qa_storage
                }
            )
            
            _fetch_doc = MongoNode(
                name=sub("fetch_doc"),
                resource_key=self.mongo,
                operation="aggregate",
                inputs={
                    "pipeline": _doc_mongo_query_pipeline["pipeline"],
                    "collection_name": self.chunk_storage
                }
            )
            
            _fetch_qa = MongoNode(
                name=sub("fetch_qa"),
                resource_key=self.mongo,
                operation="aggregate",
                inputs={
                    "pipeline": _qa_mongo_query_pipeline["pipeline"],
                    "collection_name": self.chunk_storage
                }
            )

            START >> _embed >> _vec_search >> [_collect_milvus_chunk_ids, 
                                               _roles_ids_query_pipeline] 
            _roles_ids_query_pipeline >> _role_ids_search >> _collect_roles_ids >> [_qa_mongo_query_pipeline, 
                                                                                    _doc_mongo_query_pipeline]
             
            _doc_mongo_query_pipeline >> _fetch_doc
            _qa_mongo_query_pipeline >> _fetch_qa
    
        if self.use_rerank:
            with self:
                _join_docs = CodeNode(
                    name=sub("join_docs"),
                    code_fn=join_docs,
                    inputs={
                        "document_chunks": _fetch_doc["data"],
                        "dialogue_chunks": _fetch_qa["data"],
                        "chunk_ids": _collect_milvus_chunk_ids,
                        "distance_map": _collect_milvus_chunk_ids["distance_map"],
                    }
                )
                _rerank = RerankNode(
                    name=sub("rerank"),
                    resource_key=self.rerank,
                    inputs={
                        "query": INPUT["query"],
                        "documents": _join_docs["docs"],
                        "top_k": INPUT["rerank_top_k"],
                        "threshold": INPUT["rerank_threshold"]
                    }
                )
                _final_format = CodeNode(
                    name=sub("final_format"),
                    code_fn=final_format,
                    inputs={"reranks": _rerank},
                    return_keys=["docs: List[Dict[str, Any]]"],
                    outputs=OUTPUT
                )
                [_fetch_doc, 
                 _fetch_qa, 
                 _collect_milvus_chunk_ids] >> _join_docs >> _rerank >> _final_format >> END
        else:
            with self:
                _join_docs = CodeNode(
                    name=sub("join_docs"),
                    code_fn=join_docs,
                    inputs={
                        "document_chunks": _fetch_doc["data"],
                        "dialogue_chunks": _fetch_qa["data"],
                        "chunk_ids": _collect_milvus_chunk_ids,
                        "distance_map": _collect_milvus_chunk_ids["distance_map"],
                    },
                outputs=OUTPUT
                )
                [_fetch_doc,_fetch_qa] >> _join_docs >> END

        self.build()


async def main():
    from beeflow.workflow import WorkflowEngine
    from beeflow.states.workflow_indexer import WorkflowIndexer
    from beeflow.states.workflow_state import WorkflowState
    from beeflow.nodes.base_node import INPUT, OUTPUT
    
    with WorkflowEngine(
        name="test-retriever",
        description="đây là luồng test của workflow"
    ) as test_retriever:
        retriever_node = RetrieverNode(
            name="qa_retriever_v2",
            inputs=INPUT,
            outputs=OUTPUT
        )
        START >> retriever_node >> END
        
    test_retriever.compile()
    
    # FIXS: chưa check đã compile hay chưa
        
    # indexer = WorkflowIndexer(name="workflow01").add_node(retriever_node).build()
    
    # indexer.show()
    
    # state = WorkflowState(
    #     indexer=indexer, 
    #     inputs={
    #         "query": "quy trinh tuyen dung",
    #         "partition_names": ["document"],
    #         "bot_id": "617fb97e-a3f6-4b52-a7d2-3561cec643f8", 
    #         "collection": transform_bot_id("617fb97e-a3f6-4b52-a7d2-3561cec643f8"),
    #         'allowed_roles': ["L1"],
    #         'top_k': 10,
    #         'threshold': 0.0,
    #         'output_fields': ['chunk_id'],
    #         'rerank_top_k': 5,
    #         'rerank_threshold': 0.0
    #     }
    # )
    
    result = await test_retriever.run(
        inputs={
            "query": "Vay thấu chi bằng tiền gửi tiết kiệm số",
            "partition_names": ["document"],
            "bot_id": "cbc75713-2646-4331-84ad-645664ab86ef", 
            "collection": transform_bot_id("cbc75713-2646-4331-84ad-645664ab86ef"),
            'allowed_roles': ["APP"],
            'top_k': 10,
            'threshold': 0.0,
            'output_fields': ['chunk_id'],
            'rerank_top_k': 5,
            'rerank_threshold': 0.0
        }
    )
    
    print(result)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
