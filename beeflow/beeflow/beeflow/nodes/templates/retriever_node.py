from typing import Dict, List, Any, Optional

from beeflow.nodes.graph.graph_node import GraphNode
from beeflow.configs.node_config import NodeType
from beeflow.configs.graph_config import GraphNodeConfig


def filter_roles(results: List, roles: List[str]) -> List[Dict[str, Any]]:
    """
    Filters a list of milvus records based on the user's role.
    Only returns records that the user has permission to access according to their role.

    Args:
        results: List of records resulting from milvus to be filtered
        roles: The allowed roles of the user requesting documents
        
    Returns:
        docs (List[Dict]): List of filtered document dictionaries accessible to the user with the given role
    """
        
    if not results:
        return {
            "docs": []
        }
        
    if not roles:
        roles = ["L1"]
        
    records = results[0]
    return {
        "docs": [
            doc 
            for doc in records 
            if doc['role'] in roles
        ]
    }
    

def create_mongo_query(docs: List) -> Dict[str, Any]:
    """Create a MongoDB query to fetch documents by IDs.
    
    Args:
        docs: List of document IDs to retrieve
        
    Returns:
        query (Dict[str, Any]): MongoDB query dictionary
    """
        
    return {
        "query": {
            "chunk_id": {"$in": [r['chunk_id'] for r in docs]}
        }
    }


def join_docs(mongo_docs: List, milvus_docs: List) -> Dict[str, Any]:
    """Format document data into a standardized result structure.
    
    Args:
        mongo_docs: List of document dictionaries retrieved from the mongo
        milvus_docs: List of doc info retrieved from milvus (to merge result)
        
    Returns:
        docs (List[Dict]): List of formatted document dictionaries with id, doc, and content fields
    """
    # Append documents in original order
    milvus_docs_map = {doc['chunk_id']: doc for doc in milvus_docs}
        
    final_docs = []
    for doc in mongo_docs:
        mongo_doc = {
            'id': doc['chunk_id'],
            'doc': doc['doc_id'],
            'content': doc['llm_text']
        }
        milvus_doc = milvus_docs_map[doc['chunk_id']]
        
        # Copy all keys from milvus_doc to mongo_doc except 'chunk_id' and 'id'
        for key, value in milvus_doc.items():
            if key not in ['chunk_id', 'id']:
                mongo_doc[key] = value
                
        final_docs.append(mongo_doc)
    return {
        "docs": final_docs
    }


def final_format(reranks: List) -> Dict[str, Any]:
    """
    Returns:
        docs (List[Dict]): List of final retrieved documents after all
    """
    return {
        "docs": reranks
    }
    

class RetrieverNodeConfig(GraphNodeConfig):
    """Node for retrieving documents using vector similarity search.
    
    This node implements a complete document retrieval pipeline that combines
    vector embeddings, Milvus vector search, and MongoDB document storage to
    perform semantic similarity search and return matching documents.
    
    The processing pipeline consists of:
    1. Generating embeddings for the input query using the specified embed_model
    2. Searching for similar vectors in Milvus using the embedded query
        2.1. Filter the documents with given roles (default to L1)
    3. Collecting document IDs from the Milvus search results
    4. Creating a MongoDB query to fetch the full documents by their IDs
    5. Retrieving the actual document content from MongoDB
    6. Formatting the results into a standardized structure
    
    This node is designed to be used within a larger processing graph and can be
    chained with other nodes for more complex document processing workflows.
    
    Attributes:
        embed_model: Model used for text embedding
        milvus_model: Milvus model identifier
        milvus_coll: Milvus collection name
        mongo_model: MongoDB model identifier
        mongo_coll: MongoDB collection name
        input_schema: Schema defining required and optional input parameters
    """
    type: NodeType = "retriever"
    embedding: str = "bge-m3"
    rerank: str = "bge-m3"
    milvus: str = "chatbot-libra" 
    mongo: str = "aicenter-chatbot"
    use_rerank: bool = True


class RetrieverNode(GraphNode):
    
    _config_class = RetrieverNodeConfig
    
    def __init__(
        self,
        config: Optional[RetrieverNodeConfig] = None,
        name: Optional[str] = None,
        embedding: Optional[str] = None,
        rerank: Optional[str] = None,
        milvus: Optional[str] = None,
        mongo: Optional[str] = None,
        use_rerank: Optional[bool] = None,
        # Common node parameters
        description: Optional[str] = None,
        inputs: Optional[dict] = None,
        **kwargs
    ):
        """Initialize RetrieverNode from either config or kwargs."""
        # Merge explicit params with kwargs
        if config is None:
            if name is not None:
                kwargs['name'] = name
            if embedding is not None:
                kwargs['embedding'] = embedding
            if rerank is not None:
                kwargs['rerank'] = rerank
            if milvus is not None:
                kwargs['milvus'] = milvus
            if mongo is not None:
                kwargs['mongo'] = mongo
            if use_rerank is not None:
                kwargs['use_rerank'] = use_rerank
            if description is not None:
                kwargs['description'] = description
            if inputs is not None:
                kwargs['inputs'] = inputs
            
            # Create config from kwargs
            config = RetrieverNodeConfig(**kwargs)
        
        # Set up defaults
        default = {
            'roles': ["L1"],
            'top_k': 10,
            'threshold': 0.0,
            'output_fields': ['chunk_id'],
            'doc_storage': 'chunk_data',
            'rerank_top_k': 1,
            'rerank_threshold': 0.0
        }
        
        for key, default_value in default.items():
            config.inputs.setdefault(key, default_value)
        
        # Initialize parent
        super().__init__(
            name=config.name, 
            description=config.description, 
            inputs=config.inputs,
            end=config.end,
            start=config.start
        )
        
        self.default_inputs = default
        self.config = config
        self._build_graph(config)
            
    def _build_graph(self, config: RetrieverNodeConfig):
        from beeflow.nodes import CodeNode, EmbeddingNode, MilvusNode, MongoNode, RerankNode
        
        def sub(suffix: str):
            return f"{self.name}:{suffix}"
        
        with self:            
            _embed = EmbeddingNode(
                name=sub("embed"),
                resource_key=config.embedding,
                inputs={"texts": {self.name: "query"}},
                start=True
            )
            _vec_search = MilvusNode(
                name=sub("vec_search"),
                resource_key=config.milvus,
                operation="search",
                inputs={
                    "query_vectors": {sub("embed"): "embeddings"},
                    "output_fields": self.name,
                    "partition_names": self.name,
                    "top_k": self.name,
                    "threshold": self.name,
                    "collection_name": {self.name: "collection"}
                }
            )
            _filter_roles = CodeNode(
                name=sub("filter_roles"),
                code_fn=filter_roles,
                inputs={
                    "results": sub("vec_search"), 
                    "roles": self.name
                }
            )
            _mongo_query = CodeNode(
                name=sub("mongo_query"),
                code_fn=create_mongo_query,
                inputs={"docs": sub("filter_roles")}
            )
            _fetch_docs = MongoNode(
                name=sub("fetch_docs"),
                resource_key=config.mongo,
                operation="find",
                inputs={
                    "query": sub("mongo_query"),
                    "collection_name": {self.name: "doc_storage"}
                }
            )
            
            _embed >> _vec_search >> _filter_roles >> _mongo_query >> _fetch_docs
            
        if config.use_rerank:
            with self:
                _join_docs = CodeNode(
                    name=sub("join_docs"),
                    code_fn=join_docs,
                    inputs={
                        "mongo_docs": {sub("fetch_docs"): "data"},
                        "milvus_docs": {sub("filter_roles"): "docs"}
                    }
                )
                _rerank = RerankNode(
                    name=sub("rerank"), 
                    resource_key=config.rerank,
                    inputs={
                        "query": self.name, 
                        "documents": {sub("join_docs"): "docs"},
                        "top_k": {self.name: "rerank_top_k"},
                        "threshold": {self.name: "rerank_threshold"}
                    }
                )
                _final_format = CodeNode(
                    name=sub("final_format"),
                    code_fn=final_format,
                    inputs={"reranks": sub("rerank")},
                    end=True
                )
                _fetch_docs >> _join_docs >> _rerank >> _final_format
        else:
            with self:
                _join_docs = CodeNode(
                    name=sub("join_docs"),
                    code_fn=join_docs,
                    inputs={
                        "mongo_docs": {sub("fetch_docs"): "data"},
                        "milvus_docs": {sub("filter_roles"): "docs"}
                    },
                    end=True
                )
                _fetch_docs >> _join_docs
            
        self.build()
    

async def main():
    
    # retriever_node = RetrieverNode(
    #     name="retriever0", 
    #     description="Retriever pipeline",
    #     inputs={
    #         "collection": "bot_da498399_56c2_479f_80c6_b79e605dcd66_THE",
    #         "partition_names": ["48"],
    #         "top_k": 3,
    #         "rerank_top_k": 1
    #     },
    #     use_rerank=False
    # )
    retriever_node = RetrieverNode(
        name="qa_retriever",
        inputs={"query": "annotate_query",
            "collection": "bot_da498399_56c2_479f_80c6_b79e605dcd66", 
                "partition_names": ["QA"], 
                "top_k": 10, "rerank_top_k": 5}
    )
            
    await retriever_node.simulate(
        inputs={
            "query": "thẻ hi slay có gì hay ho"
        }
    )  


if __name__  == "__main__":
    import asyncio
    asyncio.run(main())