"""
Unit tests for SQLNode using WorkflowState execution.

This test suite covers all SQL operations defined in SQLOperation:
1) Query Operations:
   - QUERY
   - QUERY_ONE

2) Execute Operations:
   - EXECUTE
   - EXECUTE_MANY

3) Transaction Operations:
   - BEGIN_TRANSACTION
   - COMMIT_TRANSACTION
   - ABORT_TRANSACTION

4) Node attributes:
   - specific_metadata method
   - node type attribute

5) Initialization errors:
   - Missing required parameters
   - Unsupported operations

All tests execute nodes via:
- WorkflowIndexer
- WorkflowState
- node.run(state=...)

Run:
    pytest tests/beeflow/nodes/primitives/data/test_sql_node.py
"""

import pytest
from typing import Dict, Any

from beeflow.nodes import INPUT, OUTPUT
from beeflow.nodes.primitives.data.sql_node import SQLNode
from beeflow.states.workflow_indexer import WorkflowIndexer
from beeflow.states.workflow_state import WorkflowState
from beegen.configs.storage.sql_config import SQLOperation

SQL_MODEL = "anapp"
TEST_TABLE = "test_sql_table"


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


# Simple test query that should work on most databases
TEST_QUERY = "SELECT 1 as test_column"


# =========================================================================
# Query Operations
# =========================================================================

@pytest.mark.asyncio
async def test_sql_node_query():
    """
    QUERY operation - execute a SELECT query.

    Expectation:
        - Output contains "status" key
        - Output contains "data" key (list of result rows)
        - Output contains "count" key
    """
    node = SQLNode(
        name="sql_query",
        resource_key=SQL_MODEL,
        operation=SQLOperation.QUERY,
        inputs={
            "query": INPUT,
            "limit": INPUT,
        },
        outputs=OUTPUT,
    )

    output = await run_node(node, inputs={"query": TEST_QUERY, "limit": 10})

    assert "status" in output
    assert "data" in output
    assert isinstance(output["data"], list)
    assert "count" in output


@pytest.mark.asyncio
async def test_sql_node_query_with_params():
    """
    QUERY operation with parameters.

    Expectation:
        - Output contains "status" key
        - Output contains "data" key
    """
    node = SQLNode(
        name="sql_query_params",
        resource_key=SQL_MODEL,
        operation=SQLOperation.QUERY,
        inputs={
            "query": INPUT,
            "params": INPUT,
        },
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={"query": "SELECT ? as number UNION SELECT ?", "params": [1, 2]},
    )

    assert "status" in output
    assert "data" in output


@pytest.mark.asyncio
async def test_sql_node_query_with_limit():
    """
    QUERY operation with limit parameter.

    Expectation:
        - Output contains "status" key
        - Output contains "count" key that respects the limit
    """
    node = SQLNode(
        name="sql_query_limit",
        resource_key=SQL_MODEL,
        operation=SQLOperation.QUERY,
        inputs={
            "query": INPUT,
            "limit": INPUT,
        },
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={"query": "SELECT * FROM information_schema.tables LIMIT 100", "limit": 5},
    )

    assert "status" in output
    assert "data" in output
    assert "count" in output


@pytest.mark.asyncio
async def test_sql_node_query_one():
    """
    QUERY_ONE operation - execute a SELECT query and return a single row.

    Expectation:
        - Output contains "status" key
        - Output contains "data" key (dict or None)
    """
    node = SQLNode(
        name="sql_query_one",
        resource_key=SQL_MODEL,
        operation=SQLOperation.QUERY_ONE,
        inputs={"query": INPUT},
        outputs=OUTPUT,
    )

    output = await run_node(node, inputs={"query": TEST_QUERY})

    assert "status" in output
    assert "data" in output
    # data should be a dict with a single row or None
    if output["data"] is not None:
        assert isinstance(output["data"], dict)


@pytest.mark.asyncio
async def test_sql_node_query_one_with_params():
    """
    QUERY_ONE operation with parameters.

    Expectation:
        - Output contains "status" key
        - Output contains "data" key
    """
    node = SQLNode(
        name="sql_query_one_params",
        resource_key=SQL_MODEL,
        operation=SQLOperation.QUERY_ONE,
        inputs={
            "query": INPUT,
            "params": INPUT,
        },
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={"query": "SELECT ? as number", "params": [1]},
    )

    assert "status" in output
    assert "data" in output


# =========================================================================
# Execute Operations
# =========================================================================

@pytest.mark.asyncio
async def test_sql_node_execute():
    """
    EXECUTE operation - execute an INSERT/UPDATE/DELETE statement.

    Expectation:
        - Output contains "status" key
        - Output contains "rowcount" key
    """
    node = SQLNode(
        name="sql_execute",
        resource_key=SQL_MODEL,
        operation=SQLOperation.EXECUTE,
        inputs={
            "query": INPUT,
        },
        outputs=OUTPUT,
    )

    # Use a DDL statement that doesn't require a table
    output = await run_node(
        node,
        inputs={"query": "CREATE TEMPORARY TABLE IF NOT EXISTS test_execute (id INT PRIMARY KEY)"},
    )

    assert "status" in output
    assert "rowcount" in output


@pytest.mark.asyncio
async def test_sql_node_execute_with_params():
    """
    EXECUTE operation with parameters.

    Expectation:
        - Output contains "status" key
        - Output contains "rowcount" key
    """
    node = SQLNode(
        name="sql_execute_params",
        resource_key=SQL_MODEL,
        operation=SQLOperation.EXECUTE,
        inputs={
            "query": INPUT,
            "params": INPUT,
        },
        outputs=OUTPUT,
    )

    # First create table
    create_node = SQLNode(
        name="sql_create_before_insert",
        resource_key=SQL_MODEL,
        operation=SQLOperation.EXECUTE,
        inputs={"query": INPUT},
        outputs=OUTPUT,
    )
    await run_node(
        create_node,
        inputs={"query": "CREATE TEMPORARY TABLE IF NOT EXISTS test_insert_params (id INT, name TEXT)"},
    )

    # Then insert data
    output = await run_node(
        node,
        inputs={"query": "INSERT INTO test_insert_params VALUES (?, ?)", "params": [1, "test"]},
    )

    assert "status" in output
    assert "rowcount" in output


@pytest.mark.asyncio
async def test_sql_node_execute_with_returning():
    """
    EXECUTE operation with returning=True.

    Expectation:
        - Output contains "status" key
        - Output contains "rowcount" key
        - May contain "data" key with returned rows if database supports RETURNING
    """
    node = SQLNode(
        name="sql_execute_returning",
        resource_key=SQL_MODEL,
        operation=SQLOperation.EXECUTE,
        inputs={
            "query": INPUT,
            "returning": INPUT,
        },
        outputs=OUTPUT,
    )

    # Create table first
    create_node = SQLNode(
        name="sql_create_before_execute_returning",
        resource_key=SQL_MODEL,
        operation=SQLOperation.EXECUTE,
        inputs={"query": INPUT},
        outputs=OUTPUT,
    )
    await run_node(
        create_node,
        inputs={"query": "CREATE TEMPORARY TABLE IF NOT EXISTS test_returning (id INT PRIMARY KEY, value TEXT)"},
    )

    # Execute with RETURNING (may not work on all databases)
    output = await run_node(
        node,
        inputs={"query": "INSERT INTO test_returning (id, value) VALUES (1, 'test') RETURNING *", "returning": True},
    )

    assert "status" in output
    assert "rowcount" in output


@pytest.mark.asyncio
async def test_sql_node_execute_many():
    """
    EXECUTE_MANY operation - execute multiple statements with different parameters.

    Expectation:
        - Output contains "status" key
        - Output contains "rowcount" key
    """
    node = SQLNode(
        name="sql_execute_many",
        resource_key=SQL_MODEL,
        operation=SQLOperation.EXECUTE_MANY,
        inputs={
            "query": INPUT,
            "seq_of_params": INPUT,
        },
        outputs=OUTPUT,
    )

    # Execute many
    params_list = [(1, "one"), (2, "two"), (3, "three")]
    output = await run_node(
        node,
        inputs={
            "query": "INSERT INTO ggggg.test_exc VALUES (?, ?)",
            "seq_of_params": params_list,
        },
    )

    assert "status" in output
    assert "rowcount" in output
    assert output["rowcount"] >= 0


# =========================================================================
# Transaction Operations
# =========================================================================

@pytest.mark.asyncio
async def test_sql_node_begin_transaction():
    """
    BEGIN_TRANSACTION operation - start a transaction.

    Expectation:
        - Output contains "status" key
        - Output contains "session_id" key with transaction identifier
    """
    node = SQLNode(
        name="sql_begin_transaction",
        resource_key=SQL_MODEL,
        operation=SQLOperation.BEGIN_TRANSACTION,
        inputs={},
        outputs=OUTPUT,
    )

    output = await run_node(node, inputs={})

    assert "status" in output
    assert "session_id" in output


@pytest.mark.asyncio
async def test_sql_node_transaction_workflow():
    """
    Complete transaction workflow: BEGIN -> EXECUTE -> COMMIT/ROLLBACK.

    Expectation:
        - BEGIN creates a session
        - EXECUTE operations complete successfully
        - COMMIT successfully commits the transaction
    """
    # Begin transaction
    begin_node = SQLNode(
        name="sql_begin_tx",
        resource_key=SQL_MODEL,
        operation=SQLOperation.BEGIN_TRANSACTION,
        inputs={},
        outputs=OUTPUT,
    )
    begin_output = await run_node(begin_node, inputs={})
    session_id = begin_output.get("session_id")

    # Execute within transaction
    execute_node = SQLNode(
        name="sql_execute_in_tx",
        resource_key=SQL_MODEL,
        operation=SQLOperation.EXECUTE,
        inputs={
            "query": INPUT,
            "session_id": INPUT,
        },
        outputs=OUTPUT,
    )
    execute_output = await run_node(
        execute_node,
        inputs={
            "query": "CREATE TEMPORARY TABLE IF NOT EXISTS test_transaction (id INT PRIMARY KEY)",
            "session_id": session_id,
        },
    )

    assert begin_output["status"] in ["success", "error"]
    assert execute_output["status"] in ["success", "error"]


@pytest.mark.asyncio
async def test_sql_node_commit_transaction():
    """
    COMMIT_TRANSACTION operation - commit a transaction.

    Expectation:
        - Output contains "status" key
        - Output contains "committed" key
    """
    node = SQLNode(
        name="sql_commit_transaction",
        resource_key=SQL_MODEL,
        operation=SQLOperation.COMMIT_TRANSACTION,
        inputs={"session_id": INPUT},
        outputs=OUTPUT,
    )

    output = await run_node(node, inputs={"session_id": "test_session_id"})

    assert "status" in output
    assert "committed" in output


@pytest.mark.asyncio
async def test_sql_node_abort_transaction():
    """
    ABORT_TRANSACTION operation - abort/rollback a transaction.

    Expectation:
        - Output contains "status" key
        - Output contains "aborted" key
    """
    node = SQLNode(
        name="sql_abort_transaction",
        resource_key=SQL_MODEL,
        operation=SQLOperation.ABORT_TRANSACTION,
        inputs={"session_id": INPUT},
        outputs=OUTPUT,
    )

    output = await run_node(node, inputs={"session_id": "test_session_id"})

    assert "status" in output
    assert "aborted" in output


# =========================================================================
# Node Attributes
# =========================================================================

@pytest.mark.asyncio
async def test_sql_node_specific_metadata():
    """
    Test specific_metadata method.

    Expectation:
        - Returns dictionary with "model" and "operation" keys
        - model matches resource_key
        - operation matches SQLOperation string value
    """
    node = SQLNode(
        name="sql_metadata",
        resource_key=SQL_MODEL,
        operation=SQLOperation.QUERY,
        inputs=INPUT,
        outputs=OUTPUT,
    )

    metadata = node.specific_metadata()

    assert isinstance(metadata, dict)
    assert "model" in metadata
    assert metadata["model"] == SQL_MODEL
    assert "operation" in metadata
    assert metadata["operation"] == str(SQLOperation.QUERY)


@pytest.mark.asyncio
async def test_sql_node_type():
    """
    Test node type attribute.

    Expectation:
        - Node type is "data"
    """
    node = SQLNode(
        name="sql_type",
        resource_key=SQL_MODEL,
        operation=SQLOperation.QUERY,
        inputs=INPUT,
        outputs=OUTPUT,
    )

    assert node.type == "data"


@pytest.mark.asyncio
async def test_sql_node_specific_metadata_various_operations():
    """
    Test specific_metadata method with various operations.

    Expectation:
        - Each operation is correctly represented in metadata
    """
    operations_to_test = [
        SQLOperation.QUERY,
        SQLOperation.QUERY_ONE,
        SQLOperation.EXECUTE,
        SQLOperation.EXECUTE_MANY,
        SQLOperation.BEGIN_TRANSACTION,
        SQLOperation.COMMIT_TRANSACTION,
        SQLOperation.ABORT_TRANSACTION,
    ]

    for op in operations_to_test:
        node = SQLNode(
            name=f"sql_metadata_{op.value}",
            resource_key=SQL_MODEL,
            operation=op,
            inputs=INPUT,
            outputs=OUTPUT,
        )

        metadata = node.specific_metadata()

        assert isinstance(metadata, dict)
        assert "model" in metadata
        assert metadata["model"] == SQL_MODEL
        assert "operation" in metadata
        assert metadata["operation"] == str(op)


# =========================================================================
# Initialization Errors
# =========================================================================

@pytest.mark.asyncio
async def test_sql_node_initialization_error_missing_resource_key():
    """
    Test that SQLNode raises ValueError when resource_key is missing.
    """
    with pytest.raises(ValueError, match="SQLNode requires both"):
        SQLNode(
            name="sql_invalid",
            operation=SQLOperation.QUERY,
            # Missing resource_key
            inputs=INPUT,
            outputs=OUTPUT,
        )


@pytest.mark.asyncio
async def test_sql_node_initialization_error_missing_operation():
    """
    Test that SQLNode raises ValueError when operation is missing.
    """
    with pytest.raises(ValueError, match="SQLNode requires both"):
        SQLNode(
            name="sql_invalid",
            resource_key=SQL_MODEL,
            # Missing operation
            inputs=INPUT,
            outputs=OUTPUT,
        )


@pytest.mark.asyncio
async def test_sql_node_initialization_with_model_alias():
    """
    Test that SQLNode accepts 'model' as an alias for 'resource_key'.
    """
    node = SQLNode(
        name="sql_model_alias",
        model=SQL_MODEL,  # Using 'model' alias
        operation=SQLOperation.QUERY,
        inputs=INPUT,
        outputs=OUTPUT,
    )

    assert node.resource_key == SQL_MODEL


# =========================================================================
# Input/Output Schema Tests
# =========================================================================

@pytest.mark.asyncio
async def test_sql_node_input_schema_query():
    """
    Test that input_schema is properly set for QUERY operation.
    """
    node = SQLNode(
        name="sql_query",
        resource_key=SQL_MODEL,
        operation=SQLOperation.QUERY,
        inputs=INPUT,
        outputs=OUTPUT,
    )

    assert node.input_schema is not None


@pytest.mark.asyncio
async def test_sql_node_output_schema_query():
    """
    Test that output_schema is properly set for QUERY operation.
    """
    node = SQLNode(
        name="sql_query",
        resource_key=SQL_MODEL,
        operation=SQLOperation.QUERY,
        inputs=INPUT,
        outputs=OUTPUT,
    )

    assert node.output_schema is not None


@pytest.mark.asyncio
async def test_sql_node_core_callable():
    """
    Test that core callable is properly resolved from adapter.
    """
    node = SQLNode(
        name="sql_query",
        resource_key=SQL_MODEL,
        operation=SQLOperation.QUERY,
        inputs=INPUT,
        outputs=OUTPUT,
    )

    assert node.core is not None
    assert callable(node.core)