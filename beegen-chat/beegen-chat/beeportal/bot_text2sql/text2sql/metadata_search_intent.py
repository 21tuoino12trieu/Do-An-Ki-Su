"""Intent normalization for metadata QA in text-to-SQL chit-chat."""

from typing import Any, Dict

from beeportal.bot_text2sql.text2sql.metadata_search_common import (
    MAX_FULL_COLUMN_TABLES,
    SEARCH_MODES,
    _int_flag,
    _normalize_text_for_match,
    _str_list,
)


FULL_COLUMN_LIST_PHRASES = (
    "liet ke tat ca cot",
    "liet ke tat ca cac cot",
    "tat ca cot",
    "tat ca cac cot",
    "toan bo cot",
    "toan bo cac cot",
    "danh sach day du cot",
    "danh sach day du cac cot",
    "day du cot",
    "day du cac cot",
    "list all columns",
    "all columns",
    "list all fields",
    "all fields",
    "full columns",
    "full column list",
)


def _is_full_column_list_request(query: Any) -> bool:
    """Chỉ bật full-list khi user nêu rõ muốn tất cả/toàn bộ cột."""
    normalized = _normalize_text_for_match(query)
    return bool(normalized) and any(phrase in normalized for phrase in FULL_COLUMN_LIST_PHRASES)


def _full_column_reject_reason(full_column_list: int, table_names: list[str]) -> str:
    """Trả lý do từ chối full-list nếu request thiếu bảng hoặc vượt giới hạn bảng."""
    if not full_column_list:
        return ""
    if len(table_names) > MAX_FULL_COLUMN_TABLES:
        return "too_many_tables"
    if not table_names:
        return "missing_table"
    return ""


def _fallback_allowed(
    mode: str,
    column_names: list[str],
    table_names: list[str],
    value_terms: list[str],
    planner_fallback_allowed: Any,
) -> int:
    """Chuẩn hóa chính sách fallback semantic sau khi đã siết mode/tên bảng/cột."""
    if mode == "semantic_metadata":
        return 1
    if mode == "explain_column" and column_names:
        return 0
    if mode == "explain_column" and value_terms:
        return 1
    if mode in {"exact_table", "list_table_columns"} and table_names:
        return 0
    if mode == "no_metadata":
        return 0
    return _int_flag(planner_fallback_allowed)


def normalize_metadata_search_intent(
    query: str = "",
    planner_search_mode: str = "no_metadata",
    planner_column_names: Any = None,
    planner_table_names: Any = None,
    planner_search_terms: Any = None,
    planner_value_terms: Any = None,
    planner_full_column_list: Any = None,
    planner_fallback_allowed: Any = 0,
) -> Dict[str, Any]:
    """Chuẩn hóa và siết output YAML từ metadata intent planner."""
    mode = str(planner_search_mode or "no_metadata").strip()
    if mode not in SEARCH_MODES:
        mode = "no_metadata"

    column_names = _str_list(planner_column_names)
    table_names = _str_list(planner_table_names)
    search_terms = _str_list(planner_search_terms)
    value_terms = _str_list(planner_value_terms)
    full_column_list = (
        _int_flag(planner_full_column_list)
        if planner_full_column_list is not None
        else 1 if _is_full_column_list_request(query) else 0
    )
    full_column_list = 1 if mode == "list_table_columns" and full_column_list else 0

    return {
        "search_mode": mode,
        "column_names": column_names,
        "table_names": table_names,
        "search_terms": search_terms,
        "value_terms": value_terms,
        "fallback_allowed": _fallback_allowed(
            mode,
            column_names,
            table_names,
            value_terms,
            planner_fallback_allowed,
        ),
        "full_column_list": full_column_list,
        "full_column_reject_reason": _full_column_reject_reason(
            full_column_list,
            table_names,
        ),
    }
