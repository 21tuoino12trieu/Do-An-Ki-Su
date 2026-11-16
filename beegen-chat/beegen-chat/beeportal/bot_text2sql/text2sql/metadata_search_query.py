"""SQL builders for metadata QA search in text-to-SQL chit-chat."""

import json
from typing import Any, Dict, List, Tuple

from beeportal.bot_text2sql.text2sql.metadata_search_common import (
    EXACT_TABLE_LIMIT,
    EXPLAIN_COLUMN_LIMIT,
    LIST_ACCESSIBLE_TABLES_LIMIT,
    LIST_TABLE_COLUMNS_PER_TABLE_LIMIT,
    METADATA_PLAIN_FIELDS,
    METADATA_SELECT_FIELDS,
    RRF_K,
    SEMANTIC_BRANCH_LIMIT,
    SEMANTIC_RRF_FINAL_LIMIT,
    SEMANTIC_RRF_MAX_ROWS_PER_TABLE,
    _empty_query,
    _fuzzy_threshold,
    _int_flag,
    _metadata_table,
    _normalize_list,
    _scope_sql,
    _str_list,
)


def _matched_tables_by_value_cte(table: str, scope_sql: str, object_filter: str) -> str:
    """Tạo CTE match bảng exact-first theo từng identifier riêng lẻ."""
    return f"""
        input_table_names(match_value, fuzzy_threshold, match_order) AS (
            VALUES {{input_values}}
        ),
        exact_tables AS (
            SELECT DISTINCT
                iv.match_order,
                m.schema_name,
                m.table_name
            FROM input_table_names iv
            JOIN {table} m
              ON {scope_sql}
             AND {object_filter}
             AND (
                 lower(m.table_name) = lower(iv.match_value)
                 OR lower(m.schema_name || '.' || m.table_name) = lower(iv.match_value)
             )
        ),
        fuzzy_tables AS (
            SELECT DISTINCT
                iv.match_order,
                m.schema_name,
                m.table_name
            FROM input_table_names iv
            JOIN {table} m
              ON {scope_sql}
             AND {object_filter}
             AND iv.fuzzy_threshold > 0
             AND NOT EXISTS (
                 SELECT 1
                 FROM exact_tables et
                 WHERE et.match_order = iv.match_order
             )
             AND (
                 m.table_name ILIKE ('%' || iv.match_value || '%')
                 OR similarity(coalesce(m.table_name, ''), iv.match_value) >= iv.fuzzy_threshold
                 OR similarity(coalesce(m.schema_name || '.' || m.table_name, ''), iv.match_value) >= iv.fuzzy_threshold
             )
        ),
        matched_tables AS (
            SELECT schema_name, table_name, min(match_order) AS match_order
            FROM (
                SELECT match_order, schema_name, table_name FROM exact_tables
                UNION ALL
                SELECT match_order, schema_name, table_name FROM fuzzy_tables
            ) matched
            GROUP BY schema_name, table_name
        )
    """


def _matched_table_values_params(
    values: List[str],
    allow_fuzzy: bool = True,
) -> Tuple[str, List[Any]]:
    """Tạo VALUES và params cho CTE match bảng theo thứ tự input planner."""
    placeholders = []
    params: List[Any] = []
    for index, value in enumerate(values):
        placeholders.append("(%s::text, %s::float8, %s::int)")
        fuzzy_threshold = _fuzzy_threshold(value, "table") if allow_fuzzy else 0.0
        params.extend([value, fuzzy_threshold, index])
    return ", ".join(placeholders), params


def _matched_columns_by_value_cte(table: str, scope_sql: str) -> str:
    """Tạo CTE match cột exact-first theo từng identifier riêng lẻ."""
    return f"""
        input_column_names(match_value, fuzzy_threshold, match_order) AS (
            VALUES {{input_values}}
        ),
        exact_columns AS (
            SELECT
                {METADATA_SELECT_FIELDS},
                iv.match_order,
                0 AS match_rank
            FROM input_column_names iv
            JOIN {table} m
              ON {scope_sql}
             AND m.object_type = 'column'
             AND lower(m.column_name) = lower(iv.match_value)
        ),
        fuzzy_columns AS (
            SELECT
                {METADATA_SELECT_FIELDS},
                iv.match_order,
                1 AS match_rank
            FROM input_column_names iv
            JOIN {table} m
              ON {scope_sql}
             AND m.object_type = 'column'
             AND iv.fuzzy_threshold > 0
             AND NOT EXISTS (
                 SELECT 1
                 FROM exact_columns ec
                 WHERE ec.match_order = iv.match_order
             )
             AND (
                 m.column_name ILIKE ('%' || iv.match_value || '%')
                 OR similarity(coalesce(m.column_name, ''), iv.match_value) >= iv.fuzzy_threshold
             )
        ),
        matched_columns AS (
            SELECT * FROM exact_columns
            UNION ALL
            SELECT * FROM fuzzy_columns
        )
    """


def _matched_column_values_params(values: List[str]) -> Tuple[str, List[Any]]:
    """Tạo VALUES và params cho CTE match cột exact-first, có fuzzy theo độ dài tên."""
    placeholders = []
    params: List[Any] = []
    for index, value in enumerate(values):
        placeholders.append("(%s::text, %s::float8, %s::int)")
        params.extend([value, _fuzzy_threshold(value, "column"), index])
    return ", ".join(placeholders), params


def _build_list_accessible_tables_query(
    table: str,
    scope_sql: str,
    scope_params: List[Any],
    limit: int = None,
) -> Dict[str, Any]:
    """Build query liệt kê các bảng user được phép truy cập trong scope hiện tại."""
    query = f"""
        WITH matched_tables AS (
            SELECT {METADATA_SELECT_FIELDS}, count(*) OVER () AS total_rows
            FROM {table} m
            WHERE {scope_sql}
              AND m.object_type = 'table'
        )
        SELECT {METADATA_PLAIN_FIELDS}, total_rows
        FROM matched_tables
        ORDER BY schema_name, table_name
        LIMIT %s
    """
    return {
        "query": query.strip(),
        "params": scope_params + [limit or LIST_ACCESSIBLE_TABLES_LIMIT],
    }


def _build_list_table_columns_query(
    table: str,
    scope_sql: str,
    scope_params: List[Any],
    table_values: List[str],
    full_column_list: Any = 0,
    full_column_reject_reason: str = "",
    limit: int = None,
) -> Dict[str, Any]:
    """Build query lấy danh sách cột theo bảng, có policy full-list và default limit."""
    is_full_column_list = _int_flag(full_column_list) == 1
    if is_full_column_list and str(full_column_reject_reason or "").strip():
        return _empty_query(table)
    if not table_values:
        return _empty_query(table)

    # Full-list phải dùng exact table match; nếu fuzzy ở đây, một tên bảng viết thiếu
    # có thể bị mở rộng sai và làm bot liệt kê toàn bộ cột của bảng không được hỏi.
    input_values_sql, input_values_params = _matched_table_values_params(
        table_values,
        allow_fuzzy=not is_full_column_list,
    )
    matched_tables_cte = _matched_tables_by_value_cte(
        table,
        scope_sql,
        "m.object_type IN ('table', 'column')",
    ).replace("{input_values}", input_values_sql)

    column_rank_filter = "" if is_full_column_list else "WHERE column_rank <= %s"
    query = f"""
        WITH {matched_tables_cte},
        ranked_columns AS (
            SELECT
                {METADATA_SELECT_FIELDS},
                mt.match_order,
                count(*) OVER (
                    PARTITION BY m.schema_name, m.table_name
                ) AS total_columns,
                row_number() OVER (
                    PARTITION BY m.schema_name, m.table_name
                    ORDER BY m.column_name
                ) AS column_rank
            FROM {table} m
            JOIN matched_tables mt
              ON mt.schema_name = m.schema_name AND mt.table_name = m.table_name
            WHERE {scope_sql}
              AND m.object_type = 'column'
        )
        SELECT {METADATA_PLAIN_FIELDS}, total_columns, column_rank
        FROM ranked_columns
        {column_rank_filter}
        ORDER BY match_order, schema_name, table_name, column_rank
    """
    query_params = input_values_params + scope_params + scope_params + scope_params
    if not is_full_column_list:
        query_params.append(limit or LIST_TABLE_COLUMNS_PER_TABLE_LIMIT)
    return {"query": query.strip(), "params": query_params}


def _build_explain_column_query(
    table: str,
    scope_sql: str,
    scope_params: List[Any],
    values: List[str],
    limit: int = None,
) -> Dict[str, Any]:
    """Build query giải thích cột theo tên cột hoặc search term từ planner."""
    if not values:
        return _empty_query(table)

    input_values_sql, input_values_params = _matched_column_values_params(values)
    matched_columns_cte = _matched_columns_by_value_cte(table, scope_sql).replace(
        "{input_values}",
        input_values_sql,
    )

    query = f"""
        WITH {matched_columns_cte},
        ranked_columns AS (
            SELECT *, count(*) OVER () AS total_rows
            FROM matched_columns
        )
        SELECT
            id, object_type, table_id, schema_name, table_name,
            column_name, column_type, description,
            table_description, example, total_rows
        FROM ranked_columns
        ORDER BY match_order, match_rank, schema_name, table_name, column_name
        LIMIT %s
    """
    return {
        "query": query.strip(),
        "params": input_values_params + scope_params + scope_params + [limit or EXPLAIN_COLUMN_LIMIT],
    }


def _build_exact_table_query(
    table: str,
    scope_sql: str,
    scope_params: List[Any],
    values: List[str],
    limit: int = None,
) -> Dict[str, Any]:
    """Build query lấy metadata bảng theo tên bảng/search term exact-first."""
    if not values:
        return _empty_query(table)

    input_values_sql, input_values_params = _matched_table_values_params(values)
    matched_tables_cte = _matched_tables_by_value_cte(
        table,
        scope_sql,
        "m.object_type = 'table'",
    ).replace("{input_values}", input_values_sql)

    query = f"""
        WITH {matched_tables_cte},
        ranked_tables AS (
            SELECT {METADATA_SELECT_FIELDS}, mt.match_order, count(*) OVER () AS total_rows
            FROM {table} m
            JOIN matched_tables mt
              ON mt.schema_name = m.schema_name AND mt.table_name = m.table_name
            WHERE {scope_sql}
              AND m.object_type = 'table'
        )
        SELECT {METADATA_PLAIN_FIELDS}, total_rows
        FROM ranked_tables
        ORDER BY match_order, schema_name, table_name
        LIMIT %s
    """
    return {
        "query": query.strip(),
        "params": input_values_params + scope_params + scope_params + scope_params + [limit or EXACT_TABLE_LIMIT],
    }


def build_primary_metadata_query(
    role_ids: Any,
    metadata: Dict[str, Any] = None,
    search_mode: str = "no_metadata",
    column_names: Any = None,
    table_names: Any = None,
    search_terms: Any = None,
    full_column_list: Any = 0,
    full_column_reject_reason: str = "",
    limit: int = None,
) -> Dict[str, Any]:
    """Tạo SQL metadata chính, chưa dùng semantic search."""
    table = _metadata_table()
    scope_sql, scope_params = _scope_sql(role_ids, metadata, alias="m")

    if search_mode == "no_metadata" or search_mode == "semantic_metadata":
        return _empty_query(table)

    if search_mode == "list_accessible_tables":
        return _build_list_accessible_tables_query(table, scope_sql, scope_params, limit)

    table_values = _str_list(table_names)
    column_values = _str_list(column_names)
    term_values = _str_list(search_terms)

    if search_mode == "list_table_columns":
        return _build_list_table_columns_query(
            table,
            scope_sql,
            scope_params,
            table_values,
            full_column_list,
            full_column_reject_reason,
            limit,
        )

    if search_mode == "explain_column":
        return _build_explain_column_query(table, scope_sql, scope_params, column_values or term_values, limit)

    if search_mode == "exact_table":
        return _build_exact_table_query(table, scope_sql, scope_params, table_values or term_values, limit)

    return _empty_query(table)


def should_fallback_semantic(
    rows: List[Dict[str, Any]] = None,
    search_mode: str = "no_metadata",
    column_names: Any = None,
    table_names: Any = None,
    fallback_allowed: Any = 0,
    **_: Any,
) -> Dict[str, int]:
    """Quyết định graph có cần chạy semantic metadata search hay không."""
    if search_mode == "semantic_metadata":
        return {"fallback_semantic": 1}
    if search_mode == "explain_column" and _normalize_list(column_names):
        return {"fallback_semantic": 0}
    if search_mode in {"exact_table", "list_table_columns"} and _normalize_list(table_names):
        return {"fallback_semantic": 0}
    allowed = _int_flag(fallback_allowed) == 1
    return {"fallback_semantic": 1 if allowed and not rows else 0}


def _first_embedding(query_embedding: Any) -> List[float]:
    """Lấy vector embedding đầu tiên từ các shape output có thể có của EmbeddingNode."""
    if isinstance(query_embedding, dict):
        query_embedding = query_embedding.get("embeddings") or query_embedding.get("embedding")
    if isinstance(query_embedding, list) and query_embedding and isinstance(query_embedding[0], list):
        return query_embedding[0]
    if isinstance(query_embedding, list):
        return query_embedding
    return []


def _ilike_any_clause(column: str, terms: List[str]) -> Tuple[str, List[str]]:
    """Tạo điều kiện ILIKE dạng OR theo từng term, không dùng chuỗi term đã join."""
    terms = [term for term in terms if term]
    if not terms:
        return "false", []
    return " OR ".join([f"{column} ILIKE %s"] * len(terms)), [f"%{term}%" for term in terms]


def build_rrf_metadata_query(
    user_query: str,
    query_embedding: Any,
    role_ids: Any,
    metadata: Dict[str, Any] = None,
    search_terms: Any = None,
    limit: int = None,
) -> Dict[str, Any]:
    """Tạo SQL hybrid semantic metadata search."""
    embedding = _first_embedding(query_embedding)
    if not embedding:
        return _empty_query()

    query_limit = limit or SEMANTIC_RRF_FINAL_LIMIT
    table = _metadata_table()
    scope_sql, scope_params = _scope_sql(role_ids, metadata, alias="m")
    search_terms_list = _str_list(search_terms)
    search_text = " ".join(search_terms_list)
    if not search_text:
        search_text = user_query or ""
    # Dùng chuỗi term đã join cho semantic scoring/FTS, nhưng ILIKE phải match
    # từng term riêng để tránh tìm literal phrase quá dài và khó khớp.
    like_terms = search_terms_list or _str_list(user_query)
    like_clause, like_params = _ilike_any_clause("search_text", like_terms)
    embedding_json = json.dumps(embedding)

    # ranked_results cap số row mỗi bảng sau khi fusion để tăng diversity;
    # formatter bên dưới vẫn quyết định số bảng/cột cuối cùng vào prompt.
    query_sql = f"""
        WITH scoped AS (
            SELECT m.*
            FROM {table} m
            WHERE {scope_sql}
        ),
        trgm AS (
            SELECT id, row_number() OVER (
                ORDER BY GREATEST(
                    similarity(coalesce(column_name, ''), %s),
                    similarity(coalesce(table_name, ''), %s),
                    similarity(coalesce(search_text, ''), %s)
                ) DESC
            ) AS rank
            FROM scoped
            WHERE object_type IN ('table', 'column')
              AND (
                  {like_clause}
                  OR GREATEST(
                      similarity(coalesce(column_name, ''), %s),
                      similarity(coalesce(table_name, ''), %s),
                      similarity(coalesce(search_text, ''), %s)
                  ) > 0.05
              )
            LIMIT {SEMANTIC_BRANCH_LIMIT}
        ),
        fts AS (
            SELECT id, row_number() OVER (
                ORDER BY ts_rank_cd(search_tsv, websearch_to_tsquery('simple', %s)) DESC
            ) AS rank
            FROM scoped
            WHERE object_type IN ('table', 'column')
              AND search_tsv @@ websearch_to_tsquery('simple', %s)
            LIMIT {SEMANTIC_BRANCH_LIMIT}
        ),
        vec AS (
            SELECT id, row_number() OVER (
                ORDER BY embedding <=> %s::vector
            ) AS rank
            FROM scoped
            WHERE object_type IN ('table', 'column')
              AND embedding IS NOT NULL
            LIMIT {SEMANTIC_BRANCH_LIMIT}
        ),
        rrf AS (
            SELECT id, sum(1.0 / (%s + rank)) AS score
            FROM (
                SELECT id, rank FROM trgm
                UNION ALL
                SELECT id, rank FROM fts
                UNION ALL
                SELECT id, rank FROM vec
            ) ranked
            GROUP BY id
        ),
        ranked_results AS (
            SELECT
                m.id, m.object_type, m.table_id, m.schema_name, m.table_name,
                m.column_name, m.column_type, m.channel, m.description,
                m.table_description, m.example, m.search_text,
                rrf.score AS source_score,
                row_number() OVER (
                    PARTITION BY m.schema_name, m.table_name
                    ORDER BY rrf.score DESC, m.column_name
                ) AS table_row_rank
            FROM rrf
            JOIN {table} m ON m.id = rrf.id
        )
        SELECT
            id, object_type, table_id, schema_name, table_name,
            column_name, column_type, channel, description,
            table_description, example, search_text, source_score
        FROM ranked_results
        WHERE table_row_rank <= %s
        ORDER BY source_score DESC
        LIMIT %s
    """

    params = (
        scope_params
        + [search_text, search_text, search_text]
        + like_params
        + [search_text, search_text, search_text]
        + [search_text, search_text, embedding_json, RRF_K, SEMANTIC_RRF_MAX_ROWS_PER_TABLE, query_limit]
    )
    return {"query": query_sql.strip(), "params": params}
