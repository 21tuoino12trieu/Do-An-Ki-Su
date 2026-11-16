"""
Unit tests for RedisNode using WorkflowState execution.

This test suite covers all Redis operations defined in RedisOperation:
1) String Operations:
   - GET
   - SET
   - DELETE
   - EXISTS
   - EXPIRE
   - TTL
   - INCR
   - DECR
   - SETEX

2) Hash Operations:
   - HGET
   - HGETALL
   - HSET
   - HMSET
   - HDEL

3) List Operations:
   - LPUSH
   - RPUSH
   - LPOP
   - RPOP
   - LRANGE

4) Set Operations:
   - SADD
   - SMEMBERS
   - SREM

5) Sorted Set Operations:
   - ZADD
   - ZRANGE
   - ZRANK

6) Pub/Sub Operations:
   - PUBLISH

7) Scan Operations:
   - SCAN

8) Node attributes:
   - specific_metadata method
   - node type attribute

All tests execute nodes via:
- WorkflowIndexer
- WorkflowState
- node.run(state=...)

Run:
    pytest tests/beeflow/nodes/primitives/data/test_redis_node.py
"""

import pytest
from typing import Dict, Any

from beeflow.nodes import INPUT, OUTPUT
from beeflow.nodes.primitives.data.redis_node import RedisNode
from beeflow.states.workflow_indexer import WorkflowIndexer
from beeflow.states.workflow_state import WorkflowState
from beegen.configs.cache.redis_config import RedisOperation

REDIS_MODEL = "aicenter-chatbot"
TEST_KEY_PREFIX = "test:redis:node:"


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


def generate_test_key(suffix: str) -> str:
    """Generate a unique test key."""
    import time
    return f"{TEST_KEY_PREFIX}{suffix}:{int(time.time())}"


# =========================================================================
# String Operations
# =========================================================================

@pytest.mark.asyncio
async def test_redis_node_set():
    """
    SET operation - set a key with a value.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "ok" key with True
    """
    node = RedisNode(
        name="redis_set",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.SET,
        inputs={
            "key": INPUT,
            "value": INPUT
        },
        outputs=OUTPUT,
    )

    test_key = generate_test_key("set")
    output = await run_node(node, inputs={"key": test_key, "value": "Hello Redis!"})

    assert "status" in output
    assert output["status"] == "success"
    assert "ok" in output
    assert output["ok"] is True


@pytest.mark.asyncio
async def test_redis_node_get():
    """
    GET operation - retrieve a value by key.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "value" key
    """
    # First set a value
    set_node = RedisNode(
        name="redis_set_before_get",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.SET,
        inputs={
            "key": INPUT,
            "value": INPUT
        },
        outputs=OUTPUT,
    )
    test_key = generate_test_key("get")
    await run_node(set_node, inputs={"key": test_key, "value": "Test Value"})

    # Then get it
    get_node = RedisNode(
        name="redis_get",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.GET,
        inputs={"key": INPUT},
        outputs=OUTPUT,
    )

    output = await run_node(get_node, inputs={"key": test_key})

    assert "status" in output
    assert "value" in output
    assert output["value"] == "Test Value"


@pytest.mark.asyncio
async def test_redis_node_delete():
    """
    DELETE operation - delete one or more keys.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "deleted_count" key
    """
    # First set some keys
    test_key1 = generate_test_key("delete1")
    test_key2 = generate_test_key("delete2")

    set_node = RedisNode(
        name="redis_set_before_delete",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.SET,
        inputs={
            "key": INPUT,
            "value": INPUT
        },
        outputs=OUTPUT,
    )
    await run_node(set_node, inputs={"key": test_key1, "value": "val1"})
    await run_node(set_node, inputs={"key": test_key2, "value": "val2"})

    # Then delete them
    delete_node = RedisNode(
        name="redis_delete",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.DELETE,
        inputs={"keys": INPUT},
        outputs=OUTPUT,
    )

    output = await run_node(delete_node, inputs={"keys": [test_key1, test_key2]})

    assert "status" in output
    assert "deleted_count" in output
    assert output["deleted_count"] == 2


@pytest.mark.asyncio
async def test_redis_node_exists():
    """
    EXISTS operation - check if a key exists.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "exists" key (bool)
    """
    # Set a key
    test_key = generate_test_key("exists")

    set_node = RedisNode(
        name="redis_set_before_exists",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.SET,
        inputs={
            "key": INPUT,
            "value": INPUT
        },
        outputs=OUTPUT,
    )
    await run_node(set_node, inputs={"key": test_key, "value": "test"})

    # Check if exists
    exists_node = RedisNode(
        name="redis_exists",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.EXISTS,
        inputs={"key": INPUT},
        outputs=OUTPUT,
    )

    output = await run_node(exists_node, inputs={"key": test_key})

    assert "status" in output
    assert "exists" in output
    assert output["exists"] is True


@pytest.mark.asyncio
async def test_redis_node_setex():
    """
    SETEX operation - set a key with an expiration time.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "ok" key with True
    """
    node = RedisNode(
        name="redis_setex",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.SETEX,
        inputs={
            "key": INPUT,
            "value": INPUT,
            "seconds": INPUT
        },
        outputs=OUTPUT,
    )

    test_key = generate_test_key("setex")
    output = await run_node(node, inputs={"key": test_key, "value": "expires soon", "seconds": 60})

    assert "status" in output
    assert "ok" in output
    assert output["ok"] is True


@pytest.mark.asyncio
async def test_redis_node_expire():
    """
    EXPIRE operation - set an expiration time on a key.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "success" key (bool)
    """
    # Set a key
    test_key = generate_test_key("expire")

    set_node = RedisNode(
        name="redis_set_before_expire",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.SET,
        inputs={
            "key": INPUT,
            "value": INPUT
        },
        outputs=OUTPUT,
    )
    await run_node(set_node, inputs={"key": test_key, "value": "expires"})

    # Set expiration
    expire_node = RedisNode(
        name="redis_expire",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.EXPIRE,
        inputs={
            "key": INPUT,
            "seconds": INPUT
        },
        outputs=OUTPUT,
    )

    output = await run_node(expire_node, inputs={"key": test_key, "seconds": 120})

    assert "status" in output
    assert "success" in output
    assert output["success"] is True


@pytest.mark.asyncio
async def test_redis_node_ttl():
    """
    TTL operation - get the remaining time to live for a key.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "ttl" key (seconds to expire, -1 if no TTL, -2 if missing)
    """
    # Set a key with expiration
    test_key = generate_test_key("ttl")

    setex_node = RedisNode(
        name="redis_setex_before_ttl",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.SETEX,
        inputs={
            "key": INPUT,
            "value": INPUT,
            "seconds": INPUT
        },
        outputs=OUTPUT,
    )
    await run_node(setex_node, inputs={"key": test_key, "value": "expires", "seconds": 300})

    # Get TTL
    ttl_node = RedisNode(
        name="redis_ttl",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.TTL,
        inputs={"key": INPUT},
        outputs=OUTPUT,
    )

    output = await run_node(ttl_node, inputs={"key": test_key})

    assert "status" in output
    assert "ttl" in output
    assert output["ttl"] > 0  # Should have positive TTL


@pytest.mark.asyncio
async def test_redis_node_incr():
    """
    INCR operation - increment a key by 1.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "value" key with new value
    """
    # Initialize counter
    test_key = generate_test_key("incr")

    set_node = RedisNode(
        name="redis_set_before_incr",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.SET,
        inputs={
            "key": INPUT,
            "value": INPUT
        },
        outputs=OUTPUT,
    )
    await run_node(set_node, inputs={"key": test_key, "value": "10"})

    # Increment
    incr_node = RedisNode(
        name="redis_incr",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.INCR,
        inputs={"key": INPUT},
        outputs=OUTPUT,
    )

    output = await run_node(incr_node, inputs={"key": test_key})

    assert "status" in output
    assert "value" in output
    assert output["value"] == 11


@pytest.mark.asyncio
async def test_redis_node_decr():
    """
    DECR operation - decrement a key by 1.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "value" key with new value
    """
    # Initialize counter
    test_key = generate_test_key("decr")

    set_node = RedisNode(
        name="redis_set_before_decr",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.SET,
        inputs={
            "key": INPUT,
            "value": INPUT
        },
        outputs=OUTPUT,
    )
    await run_node(set_node, inputs={"key": test_key, "value": "20"})

    # Decrement
    decr_node = RedisNode(
        name="redis_decr",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.DECR,
        inputs={"key": INPUT},
        outputs=OUTPUT,
    )

    output = await run_node(decr_node, inputs={"key": test_key})

    assert "status" in output
    assert "value" in output
    assert output["value"] == 19


# =========================================================================
# Hash Operations
# =========================================================================

@pytest.mark.asyncio
async def test_redis_node_hset():
    """
    HSET operation - set a field in a hash.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "updated_count" key
    """
    node = RedisNode(
        name="redis_hset",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.HSET,
        inputs={
            "key": INPUT,
            "field": INPUT,
            "value": INPUT
        },
        outputs=OUTPUT,
    )

    test_key = generate_test_key("hash")
    output = await run_node(node, inputs={"key": test_key, "field": "name", "value": "John"})

    assert "status" in output
    assert "updated_count" in output
    assert output["updated_count"] == 1


@pytest.mark.asyncio
async def test_redis_node_hget():
    """
    HGET operation - get a field value from a hash.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "value" key
    """
    # Set a hash field
    test_key = generate_test_key("hash_hget")

    hset_node = RedisNode(
        name="redis_hset_before_hget",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.HSET,
        inputs={
            "key": INPUT,
            "field": INPUT,
            "value": INPUT
        },
        outputs=OUTPUT,
    )
    await run_node(hset_node, inputs={"key": test_key, "field": "email", "value": "test@example.com"})

    # Get the hash field
    hget_node = RedisNode(
        name="redis_hget",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.HGET,
        inputs={
            "key": INPUT,
            "field": INPUT
        },
        outputs=OUTPUT,
    )

    output = await run_node(hget_node, inputs={"key": test_key, "field": "email"})

    assert "status" in output
    assert "value" in output
    assert output["value"] == "test@example.com"


@pytest.mark.asyncio
async def test_redis_node_hmset():
    """
    HMSET operation - set multiple fields in a hash.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "updated_count" key
    """
    node = RedisNode(
        name="redis_hmset",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.HMSET,
        inputs={
            "key": INPUT,
            "mapping": INPUT
        },
        outputs=OUTPUT,
    )

    test_key = generate_test_key("hash_hmset")
    mapping = {"name": "Jane", "age": "30", "city": "NYC"}

    output = await run_node(node, inputs={"key": test_key, "mapping": mapping})

    assert "status" in output
    assert "updated_count" in output


@pytest.mark.asyncio
async def test_redis_node_hgetall():
    """
    HGETALL operation - get all fields and values from a hash.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "value" key (dict with all fields)
    """
    # Set up a hash
    test_key = generate_test_key("hash_hgetall")

    hset_node = RedisNode(
        name="redis_hset_before_hgetall",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.HSET,
        inputs={
            "key": INPUT,
            "field": INPUT,
            "value": INPUT
        },
        outputs=OUTPUT,
    )
    await run_node(hset_node, inputs={"key": test_key, "field": "field1", "value": "value1"})
    await run_node(hset_node, inputs={"key": test_key, "field": "field2", "value": "value2"})

    # Get all fields
    hgetall_node = RedisNode(
        name="redis_hgetall",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.HGETALL,
        inputs={"key": INPUT},
        outputs=OUTPUT,
    )

    output = await run_node(hgetall_node, inputs={"key": test_key})

    assert "status" in output
    assert "value" in output
    assert isinstance(output["value"], dict)


@pytest.mark.asyncio
async def test_redis_node_hdel():
    """
    HDEL operation - delete one or more fields from a hash.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "deleted_count" key
    """
    # Set up a hash
    test_key = generate_test_key("hash_hdel")

    hset_node = RedisNode(
        name="redis_hset_before_hdel",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.HSET,
        inputs={
            "key": INPUT,
            "field": INPUT,
            "value": INPUT
        },
        outputs=OUTPUT,
    )
    await run_node(hset_node, inputs={"key": test_key, "field": "del1", "value": "val1"})
    await run_node(hset_node, inputs={"key": test_key, "field": "del2", "value": "val2"})

    # Delete fields
    hdel_node = RedisNode(
        name="redis_hdel",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.HDEL,
        inputs={
            "key": INPUT,
            "fields": INPUT
        },
        outputs=OUTPUT,
    )

    output = await run_node(hdel_node, inputs={"key": test_key, "fields": ["del1", "del2"]})

    assert "status" in output
    assert "deleted_count" in output
    assert output["deleted_count"] == 2


# =========================================================================
# List Operations
# =========================================================================

@pytest.mark.asyncio
async def test_redis_node_lpush():
    """
    LPUSH operation - push values to the left (head) of a list.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "length" key
    """
    node = RedisNode(
        name="redis_lpush",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.LPUSH,
        inputs={
            "key": INPUT,
            "values": INPUT
        },
        outputs=OUTPUT,
    )

    test_key = generate_test_key("list")
    output = await run_node(node, inputs={"key": test_key, "values": ["first", "second", "third"]})

    assert "status" in output
    assert "length" in output
    assert output["length"] == 3


@pytest.mark.asyncio
async def test_redis_node_rpush():
    """
    RPUSH operation - push values to the right (tail) of a list.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "length" key
    """
    node = RedisNode(
        name="redis_rpush",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.RPUSH,
        inputs={
            "key": INPUT,
            "values": INPUT
        },
        outputs=OUTPUT,
    )

    test_key = generate_test_key("list_rpush")
    output = await run_node(node, inputs={"key": test_key, "values": ["a", "b", "c"]})

    assert "status" in output
    assert "length" in output
    assert output["length"] == 3


@pytest.mark.asyncio
async def test_redis_node_lpop():
    """
    LPOP operation - pop a value from the left (head) of a list.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "value" key (may be None if list is empty)
    """
    # Set up a list
    test_key = generate_test_key("list_lpop")

    lpush_node = RedisNode(
        name="redis_lpush_before_lpop",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.LPUSH,
        inputs={
            "key": INPUT,
            "values": INPUT
        },
        outputs=OUTPUT,
    )
    await run_node(lpush_node, inputs={"key": test_key, "values": ["pop_me"]})

    # Pop from left
    lpop_node = RedisNode(
        name="redis_lpop",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.LPOP,
        inputs={"key": INPUT},
        outputs=OUTPUT,
    )

    output = await run_node(lpop_node, inputs={"key": test_key})

    assert "status" in output
    assert "value" in output
    assert output["value"] == "pop_me"


@pytest.mark.asyncio
async def test_redis_node_rpop():
    """
    RPOP operation - pop a value from the right (tail) of a list.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "value" key (may be None if list is empty)
    """
    # Set up a list
    test_key = generate_test_key("list_rpop")

    rpush_node = RedisNode(
        name="redis_rpush_before_rpop",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.RPUSH,
        inputs={
            "key": INPUT,
            "values": INPUT
        },
        outputs=OUTPUT,
    )
    await run_node(rpush_node, inputs={"key": test_key, "values": ["x", "y", "z"]})

    # Pop from right
    rpop_node = RedisNode(
        name="redis_rpop",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.RPOP,
        inputs={"key": INPUT},
        outputs=OUTPUT,
    )

    output = await run_node(rpop_node, inputs={"key": test_key})

    assert "status" in output
    assert "value" in output
    assert output["value"] == "z"


@pytest.mark.asyncio
async def test_redis_node_lrange():
    """
    LRANGE operation - get a range of elements from a list.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "values" key (list of elements)
    """
    # Set up a list
    test_key = generate_test_key("list_lrange")

    lpush_node = RedisNode(
        name="redis_lpush_before_lrange",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.LPUSH,
        inputs={
            "key": INPUT,
            "values": INPUT
        },
        outputs=OUTPUT,
    )
    await run_node(lpush_node, inputs={"key": test_key, "values": ["one", "two", "three", "four"]})

    # Get range
    lrange_node = RedisNode(
        name="redis_lrange",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.LRANGE,
        inputs={
            "key": INPUT,
            "start": INPUT,
            "stop": INPUT
        },
        outputs=OUTPUT,
    )

    output = await run_node(lrange_node, inputs={"key": test_key, "start": 0, "stop": 2})

    assert "status" in output
    assert "values" in output
    assert isinstance(output["values"], list)
    assert len(output["values"]) == 3


# =========================================================================
# Set Operations
# =========================================================================

@pytest.mark.asyncio
async def test_redis_node_sadd():
    """
    SADD operation - add members to a set.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "added_count" key
    """
    node = RedisNode(
        name="redis_sadd",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.SADD,
        inputs={
            "key": INPUT,
            "members": INPUT
        },
        outputs=OUTPUT,
    )

    test_key = generate_test_key("set")
    output = await run_node(node, inputs={"key": test_key, "members": ["a", "b", "c"]})

    assert "status" in output
    assert "added_count" in output
    # assert output["added_count"] == 3

@pytest.mark.asyncio
async def test_redis_node_smembers():
    """
    SMEMBERS operation - get all members of a set.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "members" key (list of set members)
    """
    # Set up a set
    test_key = generate_test_key("set_smembers")

    sadd_node = RedisNode(
        name="redis_sadd_before_smembers",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.SADD,
        inputs={
            "key": INPUT,
            "members": INPUT
        },
        outputs=OUTPUT,
    )
    await run_node(sadd_node, inputs={"key": test_key, "members": ["x", "y", "z"]})

    # Get all members
    smembers_node = RedisNode(
        name="redis_smembers",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.SMEMBERS,
        inputs={"key": INPUT},
        outputs=OUTPUT,
    )

    output = await run_node(smembers_node, inputs={"key": test_key})

    assert "status" in output
    assert "members" in output
    assert isinstance(output["members"], list)


@pytest.mark.asyncio
async def test_redis_node_srem():
    """
    SREM operation - remove members from a set.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "removed_count" key
    """
    # Set up a set
    test_key = generate_test_key("set_srem")

    sadd_node = RedisNode(
        name="redis_sadd_before_srem",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.SADD,
        inputs={
            "key": INPUT,
            "members": INPUT
        },
        outputs=OUTPUT,
    )
    await run_node(sadd_node, inputs={"key": test_key, "members": ["keep_me", "remove_me"]})

    # Remove members
    srem_node = RedisNode(
        name="redis_srem",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.SREM,
        inputs={
            "key": INPUT,
            "members": INPUT
        },
        outputs=OUTPUT,
    )

    output = await run_node(srem_node, inputs={"key": test_key, "members": ["remove_me"]})

    assert "status" in output
    assert "removed_count" in output
    assert output["removed_count"] == 1


# =========================================================================
# Sorted Set Operations
# =========================================================================

@pytest.mark.asyncio
async def test_redis_node_zadd():
    """
    ZADD operation - add members to a sorted set with scores.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "added_count" key
    """
    node = RedisNode(
        name="redis_zadd",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.ZADD,
        inputs={
            "key": INPUT,
            "items": INPUT
        },
        outputs=OUTPUT,
    )

    test_key = generate_test_key("zset")
    items = [
        {"score": 1.5, "member": "Alice"},
        {"score": 2.0, "member": "Bob"},
        {"score": 0.5, "member": "Charlie"}
    ]

    output = await run_node(node, inputs={"key": test_key, "items": items})

    assert "status" in output
    assert "added_count" in output
    assert output["added_count"] == 3


@pytest.mark.asyncio
async def test_redis_node_zrange():
    """
    ZRANGE operation - get members from a sorted set by rank.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "members" key (list of members)
    """
    # Set up a sorted set
    test_key = generate_test_key("zset_zrange")

    zadd_node = RedisNode(
        name="redis_zadd_before_zrange",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.ZADD,
        inputs={
            "key": INPUT,
            "items": INPUT
        },
        outputs=OUTPUT,
    )
    items = [{"score": 1.0, "member": "first"}, {"score": 2.0, "member": "second"}, {"score": 3.0, "member": "third"}]
    await run_node(zadd_node, inputs={"key": test_key, "items": items})

    # Get range
    zrange_node = RedisNode(
        name="redis_zrange",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.ZRANGE,
        inputs={
            "key": INPUT,
            "start": INPUT,
            "stop": INPUT,
            "with_scores": INPUT
        },
        outputs=OUTPUT,
    )

    output = await run_node(zrange_node, inputs={"key": test_key, "start": 0, "stop": 1, "with_scores": True})

    assert "status" in output
    assert "members" in output
    assert isinstance(output["members"], list)


@pytest.mark.asyncio
async def test_redis_node_zrank():
    """
    ZRANK operation - get the rank of a member in a sorted set.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "rank" key (may be None if member not found)
    """
    # Set up a sorted set
    test_key = generate_test_key("zset_zrank")

    zadd_node = RedisNode(
        name="redis_zadd_before_zrank",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.ZADD,
        inputs={
            "key": INPUT,
            "items": INPUT
        },
        outputs=OUTPUT,
    )
    items = [{"score": 10.0, "member": "high"}, {"score": 5.0, "member": "low"}]
    await run_node(zadd_node, inputs={"key": test_key, "items": items})

    # Get rank
    zrank_node = RedisNode(
        name="redis_zrank",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.ZRANK,
        inputs={
            "key": INPUT,
            "member": INPUT
        },
        outputs=OUTPUT,
    )

    output = await run_node(zrank_node, inputs={"key": test_key, "member": "low"})

    assert "status" in output
    assert "rank" in output
    assert output["rank"] == 0


# =========================================================================
# Pub/Sub Operations
# =========================================================================

@pytest.mark.asyncio
async def test_redis_node_publish():
    """
    PUBLISH operation - publish a message to a channel.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "receivers" key (number of subscribers that received message)
    """
    node = RedisNode(
        name="redis_publish",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.PUBLISH,
        inputs={
            "channel": INPUT,
            "input_message": INPUT
        },
        outputs=OUTPUT,
    )

    test_channel = "test:redis:publish:channel"
    output = await run_node(node, inputs={"channel": test_channel, "input_message": "Hello subscribers!"})

    assert "status" in output
    assert "receivers" in output
    assert isinstance(output["receivers"], int)


# =========================================================================
# Scan Operations
# =========================================================================

@pytest.mark.asyncio
async def test_redis_node_scan():
    """
    SCAN operation - iterate over keys in the database.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "next_cursor" key
        - Output contains "keys" key (list of keys in this batch)
    """
    node = RedisNode(
        name="redis_scan",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.SCAN,
        inputs={
            "cursor": INPUT,
            "match": INPUT,
            "count": INPUT
        },
        outputs=OUTPUT,
    )

    output = await run_node(node, inputs={"cursor": 0, "match": "test:*", "count": 100})

    assert "status" in output
    assert "next_cursor" in output
    assert isinstance(output["next_cursor"], int)
    assert "keys" in output
    assert isinstance(output["keys"], list)


# =========================================================================
# Node Attributes
# =========================================================================

@pytest.mark.asyncio
async def test_redis_node_specific_metadata():
    """
    Test specific_metadata method.

    Expectation:
        - Returns dictionary with "model" and "operation" keys
        - model matches resource_key
        - operation matches RedisOperation string value
    """
    node = RedisNode(
        name="redis_metadata",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.GET,
        inputs=INPUT,
        outputs=OUTPUT,
    )

    metadata = node.specific_metadata()

    assert isinstance(metadata, dict)
    assert "model" in metadata
    assert metadata["model"] == REDIS_MODEL
    assert "operation" in metadata
    assert metadata["operation"] == str(RedisOperation.GET)


@pytest.mark.asyncio
async def test_redis_node_type():
    """
    Test node type attribute.

    Expectation:
        - Node type is "data"
    """
    node = RedisNode(
        name="redis_type",
        resource_key=REDIS_MODEL,
        operation=RedisOperation.GET,
        inputs=INPUT,
        outputs=OUTPUT,
    )

    assert node.type == "data"


@pytest.mark.asyncio
async def test_redis_node_specific_metadata_various_operations():
    """
    Test specific_metadata method with various operations.

    Expectation:
        - Each operation is correctly represented in metadata
    """
    operations_to_test = [
        RedisOperation.GET,
        RedisOperation.SET,
        RedisOperation.DELETE,
        RedisOperation.HGET,
        RedisOperation.HSET,
        RedisOperation.LPUSH,
        RedisOperation.SADD,
        RedisOperation.ZADD,
    ]

    for op in operations_to_test:
        node = RedisNode(
            name=f"redis_metadata_{op.value}",
            resource_key=REDIS_MODEL,
            operation=op,
            inputs=INPUT,
            outputs=OUTPUT,
        )

        metadata = node.specific_metadata()

        assert isinstance(metadata, dict)
        assert "model" in metadata
        assert metadata["model"] == REDIS_MODEL
        assert "operation" in metadata
        assert metadata["operation"] == str(op)


@pytest.mark.asyncio
async def test_redis_node_initialization_error():
    """
    Test that RedisNode raises ValueError when required parameters are missing.
    """
    with pytest.raises(ValueError, match="RedisNode requires both"):
        RedisNode(
            name="redis_invalid",
            resource_key=REDIS_MODEL,
            # Missing operation
            inputs=INPUT,
            outputs=OUTPUT,
        )

    with pytest.raises(ValueError, match="RedisNode requires both"):
        RedisNode(
            name="redis_invalid",
            operation=RedisOperation.GET,
            # Missing resource_key
            inputs=INPUT,
            outputs=OUTPUT,
        )