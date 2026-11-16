from beeflow.workflow import WorkflowEngine
from beeflow.states.workflow_indexer import WorkflowIndexer
from beeflow.states.workflow_state import WorkflowState
from beeflow.nodes.base_node import INPUT, OUTPUT
from beeflow.nodes.templates.retriever_node_v2 import RetrieverNode
import re
from typing import Dict, List, Any, Optional
import asyncio

from beeflow.nodes.base_node import END, START
from beeflow.nodes.graph.graph_node import GraphNode
from beeflow.configs.node_config import NodeType
from beeflow.configs.graph_config import GraphNodeConfig
from beegen.utils.common import transform_bot_id
from beegen.loggings import LOGGER
    

async def main():

    with WorkflowEngine(
        name="test-hybrid-retriever",
        description="đây là luồng test của workflow"
    ) as test_retriever:
        retriever_node = RetrieverNode(
            name="hybrid_retreiver",
            inputs=INPUT,
            outputs=OUTPUT,
            use_hybrid_search= True,
            use_hierarchical_search= True, 
            use_rerank=False,
        )
        START >> retriever_node >> END
        
    test_retriever.compile()

    query = ["các định nghĩa visa"]
    collection_name = "hierarchical_search_no_extract"
    
    result = await test_retriever.run(
        inputs={
            "query": query,
            # "partition_names": ["document"],
            "bot_id": "a6cb68dd-b472-4183-ad26-d406c5c3b841", 
            "collection": collection_name,
            'allowed_roles': ["TEST"],
            'top_k': 10,
            'top_k_topic': 3, 
            'top_k_score': 5,
            'threshold': 0.0,
            'output_fields': ['chunk_id'],
            # 'rerank_top_k': 10,
            'search_weighted_score': [0.5, 0.5]
        }
    )
    
    print(f"result: {result}")

if __name__ == "__main__":
    asyncio.run(main())