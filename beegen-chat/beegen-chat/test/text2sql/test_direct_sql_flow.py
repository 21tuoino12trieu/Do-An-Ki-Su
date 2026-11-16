import json

import pytest

from beeportal.bot_text2sql.text2sql.nlp import (
    init_query,
    persist_latest_sql,
    resolve_direct_metadata_tables,
)
from beeportal.bot_text2sql.text2sql.post_processing_sql import inspect_sql


ALLOWED = [{"schema_name": "sales", "table_name": "orders"}]


def test_history_excludes_current_message():
    result = init_query([
        {"role": "assistant", "content": "SELECT * FROM sales.orders"},
        {"role": "user", "content": "Chạy câu SQL đó"},
    ])
    assert result["conversation"] == ["BOT: SELECT * FROM sales.orders"]


def test_inspect_extracts_physical_tables_but_not_cte_aliases():
    result = inspect_sql(
        "WITH recent AS (SELECT * FROM sales.orders) "
        "SELECT * FROM recent JOIN crm.customers c ON c.id = recent.customer_id",
        "postgres",
    )
    assert result["physical_tables"] == ["sales.orders", "crm.customers"]
    assert result["is_read_only"] == 1


@pytest.mark.parametrize(
    ("sql", "syntax_valid", "statement_count", "read_only"),
    [
        ("SELECT 1; SELECT 2", 1, 2, 0),
        ("DELETE FROM sales.orders", 1, 1, 0),
        ("DELETE FORM sales.orders", 0, 1, 0),
        ("SELECT pg_sleep(1) FROM sales.orders", 1, 1, 0),
    ],
)
def test_inspect_blocks_multi_statement_dml_and_unverified_functions(
    sql, syntax_valid, statement_count, read_only
):
    result = inspect_sql(sql, "postgres")
    assert (result["syntax_valid"], result["statement_count"], result["is_read_only"]) == (
        syntax_valid,
        statement_count,
        read_only,
    )


def test_inspect_extracts_dml_table_for_permission_check():
    checked = inspect_sql("DELETE FROM sales.Orders WHERE id = 1", "postgres")
    assert checked["physical_tables"] == ["sales.orders"]
    assert checked["metadata_references_valid"] == 1
    assert resolve_direct_metadata_tables(
        checked["physical_tables"],
        checked["metadata_references_valid"],
        ALLOWED,
    )["use_metadata"] == 1


def test_inspect_aggregates_tables_from_multi_statement_batch():
    checked = inspect_sql(
        "SELECT * FROM sales.orders; DELETE FROM crm.customers WHERE id = 1",
        "postgres",
    )
    assert checked["syntax_valid"] == 1
    assert checked["statement_count"] == 2
    assert checked["is_read_only"] == 0
    assert checked["physical_tables"] == ["sales.orders", "crm.customers"]


@pytest.mark.parametrize(
    ("sql", "metadata_valid"),
    [
        ("SELECT * FROM sales.orders", 1),
        ("SELECT * FROM orders", 1),
        ('SELECT * FROM "sales.orders"', 0),
        ("SELECT * FROM catalog.sales.orders", 0),
        ('SELECT * FROM sales.orders JOIN "outside.secret" x ON x.id = orders.id', 0),
    ],
)
def test_metadata_reference_shape_guards(sql, metadata_valid):
    result = inspect_sql(sql, "postgres")
    assert result["metadata_references_valid"] == metadata_valid


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT * FROM orders", 1),
        ("SELECT * FROM sales.orders", 1),
        ("SELECT * FROM sales.Orders", 1),
        ("SELECT * FROM outside.secret", 0),
        ("SELECT * FROM sales.orders JOIN outside.secret x ON x.id = orders.id", 0),
        ('SELECT * FROM "Sales"."Orders"', 0),
        ('SELECT * FROM "sales"."orders"', 1),
        ('SELECT * FROM "sales.orders"', 0),
    ],
)
def test_metadata_is_all_or_nothing_for_authorized_ast_tables(sql, expected):
    checked = inspect_sql(sql, "postgres")
    result = resolve_direct_metadata_tables(
        checked["physical_tables"],
        checked["metadata_references_valid"],
        ALLOWED,
    )
    assert result["use_metadata"] == expected


def test_redis_policy_persists_latest_attempt_including_zero_rows():
    sql = "SELECT * FROM sales.orders"
    saved = persist_latest_sql(sql, "success", 1, "session", [{"id": 1}])
    assert json.loads(saved["redis_value"])["sql"] == sql
    zero_rows = persist_latest_sql(sql, "success", 0, "session")
    assert zero_rows["should_persist"] == 1
    assert json.loads(zero_rows["redis_value"])["count"] == 0
