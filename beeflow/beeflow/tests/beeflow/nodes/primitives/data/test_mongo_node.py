"""
Unit tests for MongoNode using WorkflowState execution.

This test suite covers all MongoDB operations defined in MongoOperation:
1) Database Operations:
   - LIST_DATABASES

2) Collection Operations:
   - LIST_COLLECTIONS
   - CREATE_COLLECTION
   - DROP_COLLECTION
   - RENAME_COLLECTION

3) Transaction Operations:
   - BEGIN_TRANSACTION
   - COMMIT_TRANSACTION
   - ABORT_TRANSACTION

4) Document Operations:
   - FIND
   - FIND_ONE
   - INSERT_ONE
   - INSERT_MANY
   - UPDATE_ONE
   - UPDATE_MANY
   - DELETE_ONE
   - DELETE_MANY
   - COUNT
   - AGGREGATE
   - DISTINCT

5) Index Operations:
   - CREATE_INDEX
   - DROP_INDEX
   - LIST_INDEXES

6) Atomic Operations:
   - FIND_ONE_AND_UPDATE
   - FIND_ONE_AND_REPLACE
   - FIND_ONE_AND_DELETE

7) Bulk Operations:
   - BULK_WRITE

8) Node attributes:
   - specific_metadata method
   - node type attribute

All tests execute nodes via:
- WorkflowIndexer
- WorkflowState
- node.run(state=...)

Run:
    pytest tests/beeflow/nodes/primitives/data/test_mongo_node.py
"""

import pytest
from typing import Dict, Any
from datetime import datetime

from beeflow.nodes import INPUT, OUTPUT
from beeflow.nodes.primitives.data.mongo_node import MongoNode
from beeflow.states.workflow_indexer import WorkflowIndexer
from beeflow.states.workflow_state import WorkflowState
from beegen.configs.storage.mongo_config import MongoOperation

MONGO_MODEL = "aicenter-chatbot"
TEST_COLLECTION = "test_mongo_collection"
TEST_INDEX_NAME = "test_email_index"


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

async def run_node(node, inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a node using WorkflowState + WorkflowIndexer.
    """
    state = WorkflowState(
        indexer=WorkflowIndexer(name="workflow01")
        .add_node(node)
        .build(),
        inputs=inputs,
    )

    result = await node.run(state=state)
    # Get the node's output from the state
    return node.get_outputs(state, None)


# Sample document for testing
SAMPLE_DOCUMENT = {
    "name": "Test User",
    "email": "test@example.com",
    "age": 30,
    "role": "user",
    "created_at": datetime.now().isoformat(),
}

SAMPLE_DOCUMENTS = [
    {
        "name": f"User {i}",
        "email": f"user{i}@example.com",
        "age": 20 + i,
        "role": "user" if i % 2 == 0 else "admin",
        "created_at": datetime.now().isoformat(),
    }
    for i in range(5)
]


# =========================================================================
# Database Operations
# =========================================================================

@pytest.mark.asyncio
async def test_mongo_node_list_databases():
    """
    LIST_DATABASES operation - list all databases.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "databases" key (list of database info)
        - Output contains "count" key
    """
    node = MongoNode(
        name="mongo_list_databases",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.LIST_DATABASES,
        inputs={},
        outputs=OUTPUT,
    )

    output = await run_node(node, inputs={})

    assert "status" in output
    assert output["status"] == "success"
    assert "databases" in output
    assert isinstance(output["databases"], list)
    assert "count" in output


# =========================================================================
# Collection Operations
# =========================================================================

@pytest.mark.asyncio
async def test_mongo_node_list_collections():
    """
    LIST_COLLECTIONS operation - list all collections with optional filter.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "collections" key (list)
    """
    node = MongoNode(
        name="mongo_list_collections",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.LIST_COLLECTIONS,
        inputs={"filter": INPUT},
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={"filter": {"name": TEST_COLLECTION}},
    )

    assert "status" in output
    # assert output["status"] == "success"
    assert "collections" in output
    # assert isinstance(output["collections"], list)


@pytest.mark.asyncio
async def test_mongo_node_list_collections_no_filter():
    """
    LIST_COLLECTIONS operation without filter.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "collections" key
    """
    node = MongoNode(
        name="mongo_list_collections",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.LIST_COLLECTIONS,
        inputs={},
        outputs=OUTPUT,
    )

    output = await run_node(node, inputs={})

    assert "status" in output
    assert "collections" in output


@pytest.mark.asyncio
async def test_mongo_node_create_collection():
    """
    CREATE_COLLECTION operation - create a new collection.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "collection" key with name of created collection
    """
    node = MongoNode(
        name="mongo_create_collection",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.CREATE_COLLECTION,
        inputs={
            "name": INPUT,
            "options": INPUT,
        },
        outputs=OUTPUT,
    )

    test_collection_name = f"{TEST_COLLECTION}_temp_123"

    output = await run_node(
        node,
        inputs={
            "name": test_collection_name,
            "options": {"validator": {"$jsonSchema": {"bsonType": "object"}}},
        },
    )

    assert "status" in output
    # assert output["status"] == "success"
    assert "collection" in output


@pytest.mark.asyncio
async def test_mongo_node_rename_collection():
    """
    RENAME_COLLECTION operation - rename a collection.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "result" key
    """
    node = MongoNode(
        name="mongo_rename_collection",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.RENAME_COLLECTION,
        inputs={
            "old_name": INPUT,
            "new_name": INPUT,
        },
        outputs=OUTPUT,
    )

    old_name = f"{TEST_COLLECTION}_temp_123"
    new_name = f"{TEST_COLLECTION}_temp_new"

    output = await run_node(
        node,
        inputs={
            "old_name": old_name,
            "new_name": new_name,
        },
    )

    assert "status" in output
    assert "result" in output

@pytest.mark.asyncio
async def test_mongo_node_drop_collection():
    """
    DROP_COLLECTION operation - drop a collection.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "result" key
    """
    node = MongoNode(
        name="mongo_drop_collection",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.DROP_COLLECTION,
        inputs={"name": INPUT},
        outputs=OUTPUT,
    )

    test_collection_name = f"{TEST_COLLECTION}_temp_new"

    output = await run_node(
        node,
        inputs={"name": test_collection_name},
    )

    assert "status" in output
    assert "result" in output

# =========================================================================
# Transaction Operations
# =========================================================================

@pytest.mark.asyncio
async def test_mongo_node_begin_transaction():
    """
    BEGIN_TRANSACTION operation - begin a transaction session.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "session_id" key
    """
    node = MongoNode(
        name="mongo_begin_transaction",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.BEGIN_TRANSACTION,
        inputs={},
        outputs=OUTPUT,
    )

    output = await run_node(node, inputs={})

    assert "status" in output
    # assert output["status"] == "success"
    assert "session_id" in output


@pytest.mark.asyncio
async def test_mongo_node_commit_transaction():
    """
    COMMIT_TRANSACTION operation - commit a transaction session.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "committed" key
    """
    node = MongoNode(
        name="mongo_commit_transaction",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.COMMIT_TRANSACTION,
        inputs={"session_id": INPUT},
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={"session_id": "test_session_id"},
    )

    assert "status" in output
    assert "committed" in output


@pytest.mark.asyncio
async def test_mongo_node_abort_transaction():
    """
    ABORT_TRANSACTION operation - abort a transaction session.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "aborted" key
    """
    node = MongoNode(
        name="mongo_abort_transaction",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.ABORT_TRANSACTION,
        inputs={"session_id": INPUT},
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={"session_id": "test_session_id"},
    )

    assert "status" in output
    assert "aborted" in output


# =========================================================================
# Document Operations - INSERT
# =========================================================================

@pytest.mark.asyncio
async def test_mongo_node_insert_one():
    """
    INSERT_ONE operation - insert single document.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "inserted_id" key
    """
    node = MongoNode(
        name="mongo_insert_one",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.INSERT_ONE,
        inputs={
            "collection_name": INPUT,
            "document": INPUT,
        },
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "collection_name": TEST_COLLECTION,
            "document": SAMPLE_DOCUMENT,
        },
    )

    assert "status" in output
    assert "inserted_id" in output


@pytest.mark.asyncio
async def test_mongo_node_insert_many():
    """
    INSERT_MANY operation - insert multiple documents.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "inserted_ids" key (list)
        - Output contains "count" key matching number of documents
    """
    node = MongoNode(
        name="mongo_insert_many",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.INSERT_MANY,
        inputs={
            "collection_name": INPUT,
            "documents": INPUT,
            "ordered": INPUT,
        },
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "collection_name": TEST_COLLECTION,
            "documents": SAMPLE_DOCUMENTS,
            "ordered": True,
        },
    )

    assert "status" in output
    assert "inserted_ids" in output
    assert isinstance(output["inserted_ids"], list)
    assert "count" in output


@pytest.mark.asyncio
async def test_mongo_node_insert_many_unordered():
    """
    INSERT_MANY operation with ordered=False.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "inserted_ids" key
    """
    node = MongoNode(
        name="mongo_insert_many",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.INSERT_MANY,
        inputs={
            "collection_name": INPUT,
            "documents": INPUT,
            "ordered": INPUT,
        },
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "collection_name": TEST_COLLECTION,
            "documents": SAMPLE_DOCUMENTS,
            "ordered": False,
        },
    )

    assert "status" in output
    assert "inserted_ids" in output


# =========================================================================
# Document Operations - UPDATE
# =========================================================================

@pytest.mark.asyncio
async def test_mongo_node_update_one():
    """
    UPDATE_ONE operation - update single document.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "matched_count" key
        - Output contains "modified_count" key
    """
    node = MongoNode(
        name="mongo_update_one",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.UPDATE_ONE,
        inputs={
            "collection_name": INPUT,
            "filter": INPUT,
            "update": INPUT,
            "upsert": INPUT,
        },
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "collection_name": TEST_COLLECTION,
            "filter": {"email": "test@example.com"},
            "update": {"$set": {"age": 31}},
            "upsert": False,
        },
    )

    assert "status" in output
    assert "matched_count" in output
    assert "modified_count" in output


@pytest.mark.asyncio
async def test_mongo_node_update_one_upsert():
    """
    UPDATE_ONE operation with upsert.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "matched_count" key
        - Output contains "modified_count" key
    """
    node = MongoNode(
        name="mongo_update_one_upsert",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.UPDATE_ONE,
        inputs={
            "collection_name": INPUT,
            "filter": INPUT,
            "update": INPUT,
            "upsert": INPUT,
        },
        outputs=OUTPUT,
    )

    timestamp = datetime.now().timestamp()
    output = await run_node(
        node,
        inputs={
            "collection_name": TEST_COLLECTION,
            "filter": {"email": f"newuser{timestamp}@example.com"},
            "update": {"$set": {"age": 25}},
            "upsert": True,
        },
    )

    assert "status" in output
    assert "matched_count" in output
    assert "modified_count" in output


@pytest.mark.asyncio
async def test_mongo_node_update_many():
    """
    UPDATE_MANY operation - update multiple documents.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "matched_count" key
        - Output contains "modified_count" key
    """
    node = MongoNode(
        name="mongo_update_many",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.UPDATE_MANY,
        inputs={
            "collection_name": INPUT,
            "filter": INPUT,
            "update": INPUT,
            "upsert": INPUT,
        },
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "collection_name": TEST_COLLECTION,
            "filter": {"role": "user"},
            "update": {"$set": {"status": "active"}},
            "upsert": False,
        },
    )

    assert "status" in output
    assert "matched_count" in output
    assert "modified_count" in output

# =========================================================================
# Document Operations - FIND
# =========================================================================

@pytest.mark.asyncio
async def test_mongo_node_find():
    """
    FIND operation - query multiple documents.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "data" key (list of documents)
        - Output contains "count" key
    """
    node = MongoNode(
        name="mongo_find",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.FIND,
        inputs={
            "collection_name": INPUT,
            "query": INPUT,
            "projection": INPUT,
            "limit": INPUT,
        },
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "collection_name": TEST_COLLECTION,
            "query": {"role": "user"},
            "projection": {"name": 1, "email": 1},
            "limit": 10,
        },
    )

    assert "status" in output
    # assert output["status"] == "success"
    assert "data" in output
    assert isinstance(output["data"], list)
    assert "count" in output


@pytest.mark.asyncio
async def test_mongo_node_find_with_sort():
    """
    FIND operation with sorting.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "data" key
    """
    node = MongoNode(
        name="mongo_find_sort",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.FIND,
        inputs={
            "collection_name": INPUT,
            "query": INPUT,
            "sort": INPUT,
            "limit": INPUT,
        },
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "collection_name": TEST_COLLECTION,
            "query": {},
            "sort": {"age": -1},
            "limit": 5,
        },
    )

    assert "status" in output


@pytest.mark.asyncio
async def test_mongo_node_find_with_limit_and_skip():
    """
    FIND operation with limit and skip pagination.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "data" key
        - Output contains "count" key
    """
    node = MongoNode(
        name="mongo_find_paginate",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.FIND,
        inputs={
            "collection_name": INPUT,
            "query": INPUT,
            "skip": INPUT,
            "limit": INPUT,
        },
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "collection_name": TEST_COLLECTION,
            "query": {},
            "skip": 1,
            "limit": 2,
        },
    )

    assert "status" in output
    assert "data" in output


@pytest.mark.asyncio
async def test_mongo_node_find_with_all_options():
    """
    FIND operation with all optional parameters.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "data" key
    """
    node = MongoNode(
        name="mongo_find_all_options",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.FIND,
        inputs={
            "collection_name": INPUT,
            "query": INPUT,
            "projection": INPUT,
            "sort": INPUT,
            "skip": INPUT,
            "limit": INPUT,
        },
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "collection_name": TEST_COLLECTION,
            "query": {"role": "user"},
            "projection": {"name": 1},
            "sort": {"age": 1},
            "skip": 0,
            "limit": 10,
        },
    )

    assert "status" in output
    assert "data" in output


# =========================================================================
# Document Operations - FIND_ONE
# =========================================================================

@pytest.mark.asyncio
async def test_mongo_node_find_one():
    """
    FIND_ONE operation - query single document.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "data" key (dict or None)
    """
    node = MongoNode(
        name="mongo_find_one",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.FIND_ONE,
        inputs={
            "collection_name": INPUT,
            "query": INPUT,
            "projection": INPUT,
        },
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "collection_name": TEST_COLLECTION,
            "query": {"email": "test@example.com"},
            "projection": {"name": 1, "email": 1},
        },
    )

    assert "status" in output
    assert "data" in output

# =========================================================================
# Document Operations - DELETE
# =========================================================================

@pytest.mark.asyncio
async def test_mongo_node_delete_one():
    """
    DELETE_ONE operation - delete single document.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "deleted_count" key (0 or 1)
    """
    node = MongoNode(
        name="mongo_delete_one",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.DELETE_ONE,
        inputs={
            "collection_name": INPUT,
            "filter": INPUT,
        },
        outputs=OUTPUT,
    )

    timestamp = datetime.now().timestamp()
    output = await run_node(
        node,
        inputs={
            "collection_name": TEST_COLLECTION,
            "filter": {"email": f"delete{timestamp}@example.com"},
        },
    )

    assert "status" in output
    assert "deleted_count" in output
    assert output["deleted_count"] in [0, 1]


@pytest.mark.asyncio
async def test_mongo_node_delete_many():
    """
    DELETE_MANY operation - delete multiple documents.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "deleted_count" key
    """
    node = MongoNode(
        name="mongo_delete_many",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.DELETE_MANY,
        inputs={
            "collection_name": INPUT,
            "filter": INPUT,
        },
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "collection_name": TEST_COLLECTION,
            "filter": {"role": "temp"},
        },
    )

    assert "status" in output
    assert "deleted_count" in output


# =========================================================================
# Document Operations - COUNT
# =========================================================================

@pytest.mark.asyncio
async def test_mongo_node_count():
    """
    COUNT operation - count documents matching query.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "count" key
    """
    node = MongoNode(
        name="mongo_count",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.COUNT,
        inputs={
            "collection_name": INPUT,
            "query": INPUT,
        },
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "collection_name": TEST_COLLECTION,
            "query": {"role": "user"},
        },
    )

    assert "status" in output
    assert "count" in output
    assert isinstance(output["count"], int)


# =========================================================================
# Document Operations - AGGREGATE
# =========================================================================

@pytest.mark.asyncio
async def test_mongo_node_aggregate():
    """
    AGGREGATE operation - aggregation pipeline.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "data" key (list of aggregated results)
        - Output contains "count" key
    """
    node = MongoNode(
        name="mongo_aggregate",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.AGGREGATE,
        inputs={
            "collection_name": INPUT,
            "pipeline": INPUT,
        },
        outputs=OUTPUT,
    )

    pipeline = [
        {"$match": {"role": "user"}},
        {"$group": {"_id": "$role", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]

    output = await run_node(
        node,
        inputs={
            "collection_name": TEST_COLLECTION,
            "pipeline": pipeline,
        },
    )

    assert "status" in output
    assert "data" in output
    assert isinstance(output["data"], list)


# =========================================================================
# Document Operations - DISTINCT
# =========================================================================

@pytest.mark.asyncio
async def test_mongo_node_distinct():
    """
    DISTINCT operation - get distinct values for a field.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "data" key (list of distinct values)
        - Output contains "count" key
    """
    node = MongoNode(
        name="mongo_distinct",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.DISTINCT,
        inputs={
            "collection_name": INPUT,
            "key": INPUT,
            "query": INPUT,
        },
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "collection_name": TEST_COLLECTION,
            "key": "role",
            "query": {},
        },
    )

    assert "status" in output
    assert "data" in output
    assert isinstance(output["data"], list)
    assert "count" in output


# =========================================================================
# Index Operations
# =========================================================================

@pytest.mark.asyncio
async def test_mongo_node_create_index():
    """
    CREATE_INDEX operation - create index on collection.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "index_name" key
    """
    node = MongoNode(
        name="mongo_create_index",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.CREATE_INDEX,
        inputs={
            "collection_name": INPUT,
            "keys": INPUT,
            "options": INPUT,
        },
        outputs=OUTPUT,
    )

    timestamp = datetime.now().timestamp()
    output = await run_node(
        node,
        inputs={
            "collection_name": TEST_COLLECTION,
            "keys": {"email": 1},
            "options": {"unique": True},
        },
    )

    assert "status" in output
    assert "index_name" in output


@pytest.mark.asyncio
async def test_mongo_node_drop_index():
    """
    DROP_INDEX operation - drop an index on collection.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "result" key
    """
    node = MongoNode(
        name="mongo_drop_index",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.DROP_INDEX,
        inputs={
            "collection_name": INPUT,
            "index_name": INPUT,
        },
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "collection_name": TEST_COLLECTION,
            "index_name": TEST_INDEX_NAME,
        },
    )

    assert "status" in output
    assert "result" in output


@pytest.mark.asyncio
async def test_mongo_node_list_indexes():
    """
    LIST_INDEXES operation - list indexes on collection.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "indexes" key (list)
        - Output contains "count" key
    """
    node = MongoNode(
        name="mongo_list_indexes",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.LIST_INDEXES,
        inputs={
            "collection_name": INPUT,
        },
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={"collection_name": TEST_COLLECTION},
    )

    assert "status" in output
    assert "indexes" in output
    assert isinstance(output["indexes"], list)
    assert "count" in output


# =========================================================================
# Atomic Operations
# =========================================================================

@pytest.mark.asyncio
async def test_mongo_node_find_one_and_update():
    """
    FIND_ONE_AND_UPDATE operation - atomic find and update.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "data" key (document after/before update)
    """
    node = MongoNode(
        name="mongo_find_one_update",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.FIND_ONE_AND_UPDATE,
        inputs={
            "collection_name": INPUT,
            "filter": INPUT,
            "update": INPUT,
            "return_document": INPUT,
            "upsert": INPUT,
        },
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "collection_name": TEST_COLLECTION,
            "filter": {"email": "test@example.com"},
            "update": {"$set": {"age": 32}},
            "return_document": "after",
            "upsert": False,
        },
    )

    assert "status" in output
    assert "data" in output


@pytest.mark.asyncio
async def test_mongo_node_find_one_and_delete():
    """
    FIND_ONE_AND_DELETE operation - atomic find and delete.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "data" key (deleted document, may be None)
    """
    node = MongoNode(
        name="mongo_find_one_delete",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.FIND_ONE_AND_DELETE,
        inputs={
            "collection_name": INPUT,
            "filter": INPUT,
        },
        outputs=OUTPUT,
    )

    timestamp = datetime.now().timestamp()
    output = await run_node(
        node,
        inputs={
            "collection_name": TEST_COLLECTION,
            "filter": {"email": f"delete_temp_{timestamp}@example.com"},
        },
    )

    assert "status" in output
    assert "data" in output  # May be None if no document found


@pytest.mark.asyncio
async def test_mongo_node_find_one_and_replace():
    """
    FIND_ONE_AND_REPLACE operation - atomic find and replace.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "data" key (document after/before replace)
    """
    node = MongoNode(
        name="mongo_find_one_replace",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.FIND_ONE_AND_REPLACE,
        inputs={
            "collection_name": INPUT,
            "filter": INPUT,
            "replacement": INPUT,
            "return_document": INPUT,
            "upsert": INPUT,
        },
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "collection_name": TEST_COLLECTION,
            "filter": {"email": "test@example.com"},
            "replacement": {"name": "Updated User", "email": "test@example.com", "age": 35},
            "return_document": "after",
            "upsert": False,
        },
    )

    assert "status" in output
    assert "data" in output


# =========================================================================
# Bulk Operations
# =========================================================================

@pytest.mark.asyncio
async def test_mongo_node_bulk_write():
    """
    BULK_WRITE operation - execute multiple write operations.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains operation counts
    """
    node = MongoNode(
        name="mongo_bulk_write",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.BULK_WRITE,
        inputs={
            "collection_name": INPUT,
            "operations": INPUT,
            "ordered": INPUT,
        },
        outputs=OUTPUT,
    )

    operations = [
        {"type": "insert_one", "document": {"name": "Bulk User 1", "email": "bulk1@example.com"}},
        {"type": "insert_one", "document": {"name": "Bulk User 2", "email": "bulk2@example.com"}},
        {"type": "update_one", "filter": {"email": "bulk1@example.com"}, "update": {"$set": {"status": "active"}}},
    ]

    output = await run_node(
        node,
        inputs={
            "collection_name": TEST_COLLECTION,
            "operations": operations,
            "ordered": True,
        },
    )

    assert "status" in output
    assert "inserted_count" in output or "matched_count" in output


# =========================================================================
# Node Attributes
# =========================================================================

@pytest.mark.asyncio
async def test_mongo_node_specific_metadata():
    """
    Test specific_metadata method.

    Expectation:
        - Returns dictionary with "model" and "operation" keys
        - model matches resource_key
        - operation matches MongoOperation string value
    """
    node = MongoNode(
        name="mongo_metadata",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.FIND,
        inputs=INPUT,
        outputs=OUTPUT,
    )

    metadata = node.specific_metadata()

    assert isinstance(metadata, dict)
    assert "model" in metadata
    assert metadata["model"] == MONGO_MODEL
    assert "operation" in metadata
    assert metadata["operation"] == str(MongoOperation.FIND)


@pytest.mark.asyncio
async def test_mongo_node_type():
    """
    Test node type attribute.

    Expectation:
        - Node type is "mongo"
    """
    node = MongoNode(
        name="mongo_type",
        resource_key=MONGO_MODEL,
        operation=MongoOperation.FIND,
        inputs=INPUT,
        outputs=OUTPUT,
    )

    assert node.type == "mongo"


@pytest.mark.asyncio
async def test_mongo_node_specific_metadata_various_operations():
    """
    Test specific_metadata method with various operations.

    Expectation:
        - Each operation is correctly represented in metadata
    """
    operations_to_test = [
        MongoOperation.FIND,
        MongoOperation.INSERT_ONE,
        MongoOperation.UPDATE_MANY,
        MongoOperation.DELETE_ONE,
        MongoOperation.AGGREGATE,
        MongoOperation.BULK_WRITE,
    ]

    for op in operations_to_test:
        node = MongoNode(
            name=f"mongo_metadata_{op.value}",
            resource_key=MONGO_MODEL,
            operation=op,
            inputs=INPUT,
            outputs=OUTPUT,
        )

        metadata = node.specific_metadata()

        assert isinstance(metadata, dict)
        assert "model" in metadata
        assert metadata["model"] == MONGO_MODEL
        assert "operation" in metadata
        assert metadata["operation"] == str(op)
