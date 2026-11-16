import pytest
import asyncio
from beeflow.workflow import WorkflowEngine
from beeflow.nodes.templates.retriever_node_v2 import RetrieverNode
from beeflow.nodes.base_node import INPUT, OUTPUT, START, END
import sys

# -----------------------------
# Config for hybrdi search test
# -----------------------------
QUERY = ["các định nghĩa visa"]
HYBRID_COLLECTION_NAME = "test_hybrid_search"
HYBRID_BOT_ID = "665fccd5-4be8-4305-b247-4116314d6deb"
HIERARCHICAL_BOT_ID = "a6cb68dd-b472-4183-ad26-d406c5c3b841"
HIERARCHICAL_COLLECTION_NAME = "test_hierarchical_search"

EXPECTED_VISA_PRODUCTS = [
    "Visa Credit",
    "VISA VNA",
    "Visa Hybrid",
    "Visa Debit",
    "Visa Infinite",
    "Visa Platinum Priority",
    "Led Hi Collection",
    "EVIPCARE",
]

# -----------------------------
# Pytest async test
# -----------------------------

@pytest.mark.asyncio
async def test_hierarchical_hybrid_retriever():
    # 1. Build workflow
    with WorkflowEngine(
        name="test-hybrid-retriever",
        description="integration test hybrid retriever"
    ) as workflow:

        retriever_node = RetrieverNode(
            name="hierarchical_bybrid_retriever",
            inputs=INPUT,
            outputs=OUTPUT,
            use_hybrid_search=True,
            use_hierarchical_search= True,
            use_rerank=False,
        )

        START >> retriever_node >> END

    workflow.compile()

    # 2. Run workflow
    result = await workflow.run(
        inputs={
            "query": QUERY,
            "bot_id": HIERARCHICAL_BOT_ID,
            "collection": HIERARCHICAL_COLLECTION_NAME,
            "allowed_roles": ["TEST"],
            "top_k": 15,
            'top_k_topic': 3, 
            'top_k_score': 5,
            "threshold": 0.0,
            "output_fields": ["chunk_id"],
            "search_weighted_score": [0.5, 0.5],
        }
    )

    # print(result)

    # 3. Basic assertions
    assert isinstance(result, dict)
    assert "docs" in result
    assert isinstance(result["docs"], list)
    assert len(result["docs"]) > 0

    # 4. concat content to search
    all_contents = " ".join(
        doc.get("content", "") for doc in result["docs"]
    )

    # 5. Assert search all 8 Visa type
    missing_products = []
    for product in EXPECTED_VISA_PRODUCTS:
        if product not in all_contents:
            missing_products.append(product)

    assert not missing_products, (
        # f"Thiếu các loại thẻ Visa sau: {missing_products}"
        f"Failed test case for milvus search: hierarchical hybrid test"
    )
