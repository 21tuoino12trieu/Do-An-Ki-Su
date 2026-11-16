"""Shared helpers for metadata QA search in text-to-SQL chit-chat."""

import html
import re
import unicodedata
from typing import Any, Dict, List, Tuple

from beeportal.bot_text2sql.text2sql.metadata import METADATA_CONFIG


METADATA_SEARCH_CATALOG_NAME = "metadata_search_catalog"
LIST_ACCESSIBLE_TABLES_LIMIT = 50
EXACT_TABLE_LIMIT = 10
LIST_TABLE_COLUMNS_PER_TABLE_LIMIT = 50
MAX_FULL_COLUMN_TABLES = 2
EXPLAIN_COLUMN_LIMIT = 50
SEMANTIC_BRANCH_LIMIT = 50
SEMANTIC_RRF_FINAL_LIMIT = 20
SEMANTIC_CONTEXT_MAX_TABLES = 5
SEMANTIC_CONTEXT_MAX_COLUMNS_PER_TABLE = 5
# Raw RRF cũng cap theo số cột tối đa đưa vào context để tránh một bảng
# có nhiều cột chiếm toàn bộ top-N trước khi formatter group lại.
SEMANTIC_RRF_MAX_ROWS_PER_TABLE = SEMANTIC_CONTEXT_MAX_COLUMNS_PER_TABLE
SEMANTIC_CONTEXT_MAX_TOTAL_COLUMNS = 20
RRF_K = 60
SEARCH_MODES = {
    "no_metadata",
    "list_accessible_tables",
    "exact_table",
    "list_table_columns",
    "explain_column",
    "semantic_metadata",
}
METADATA_SELECT_FIELDS = """
    m.id, m.object_type, m.table_id, m.schema_name, m.table_name,
    m.column_name, m.column_type, m.description,
    m.table_description, m.example
"""
METADATA_PLAIN_FIELDS = """
    id, object_type, table_id, schema_name, table_name,
    column_name, column_type, description,
    table_description, example
"""


def _normalize_list(value: Any) -> List[Any]:
    """Đưa input từ CodeNode/LLM về list, kể cả khi input là scalar hoặc CSV."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [item for item in value if item not in (None, "")]
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]
    return [value]


def _str_list(value: Any) -> List[str]:
    """Chuẩn hóa input dạng list thành danh sách chuỗi đã strip và không rỗng."""
    return [
        str(item).strip()
        for item in _normalize_list(value)
        if str(item).strip()
    ]


def _int_flag(value: Any) -> int:
    """Chuyển flag từ planner về số nguyên ổn định 0/1."""
    if isinstance(value, bool):
        return 1 if value else 0
    try:
        return 1 if int(value) == 1 else 0
    except (TypeError, ValueError):
        return 0


def _normalize_text_for_match(value: Any) -> str:
    """Chuẩn hóa text để detect intent theo keyword ổn định hơn."""
    text = str(value or "").lower().replace("đ", "d")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9_]+", " ", text)
    return " ".join(text.split())


def _clean_text(value: Any, max_length: int = 500) -> str:
    """Chuẩn hóa khoảng trắng và cắt ngắn text khi đóng gói vào prompt context."""
    if value is None:
        return ""
    text = " ".join(html.unescape(str(value)).split())
    if max_length is None:
        return text
    if len(text) <= max_length:
        return text
    return f"{text[:max_length].rstrip()}..."


def _business_definition(value: Any) -> str:
    """Trích phần định nghĩa nghiệp vụ ngắn từ mô tả cột có cấu trúc."""
    text = _clean_text(value, 2000)
    if not text:
        return ""

    start_marker = "Định nghĩa nghiệp vụ:"
    if start_marker not in text:
        return ""
    text = text.split(start_marker, 1)[1].strip()

    stop_markers = ["Logic tính toán:", "Miền giá trị:", "Lưu ý sử dụng:", "Ví dụ:"]
    stop_positions = [text.find(marker) for marker in stop_markers if text.find(marker) >= 0]
    if stop_positions:
        text = text[: min(stop_positions)].strip()

    text = text.strip(" .")
    return f"{text}." if text else ""


def _metadata_table() -> str:
    """Trả về tên bảng catalog metadata đầy đủ kèm schema cấu hình."""
    schema = METADATA_CONFIG["database"]["schema"]
    return f"{schema}.{METADATA_SEARCH_CATALOG_NAME}"


def _empty_query(table: str = None) -> Dict[str, Any]:
    """Tạo SQL hợp lệ nhưng không trả row, vẫn giữ shape metadata chuẩn."""
    table = table or _metadata_table()
    return {"query": f"SELECT {METADATA_SELECT_FIELDS} FROM {table} m WHERE false", "params": []}


def _table_domain_pairs(metadata: Dict[str, Any] = None) -> List[Tuple[str, str]]:
    """Lấy danh sách cặp schema/table được phép truy cập từ metadata runtime."""
    pairs: List[Tuple[str, str]] = []
    for table in (metadata or {}).get("TableDomain", []):
        if not isinstance(table, dict):
            continue
        schema_name = table.get("schemaName") or table.get("schema_name")
        table_name = table.get("tableName") or table.get("table_name")
        if schema_name and table_name:
            pairs.append((schema_name, table_name))
    return pairs


def _scope_sql(role_ids: Any, metadata: Dict[str, Any] = None, alias: str = "m") -> Tuple[str, List[Any]]:
    """Tạo filter quyền truy cập và phạm vi bảng dùng chung cho các query metadata."""
    clauses = [f"{alias}.is_active = true"]
    params: List[Any] = []

    roles = _normalize_list(role_ids)
    if not roles:
        clauses.append("false")
        return " AND ".join(clauses), params

    role_placeholders = ", ".join(["%s"] * len(roles))
    clauses.append(f"{alias}.channel IN ({role_placeholders})")
    params.extend(roles)

    domain_pairs = _table_domain_pairs(metadata)
    if domain_pairs:
        domain_placeholders = ", ".join(["(%s, %s)"] * len(domain_pairs))
        clauses.append(f"({alias}.schema_name, {alias}.table_name) IN ({domain_placeholders})")
        params.extend([value for pair in domain_pairs for value in pair])

    return " AND ".join(clauses), params


def _compact_identifier_len(value: str) -> int:
    """Đếm độ dài identifier sau khi bỏ dấu phân cách thường gặp."""
    return len(re.sub(r"[_\.\s]+", "", (value or "").strip()))


def _fuzzy_threshold(value: str, object_type: str) -> float:
    """Trả threshold fuzzy thận trọng; identifier quá ngắn chỉ được exact."""
    compact_len = _compact_identifier_len(value)
    if object_type == "column":
        if compact_len <= 3:
            return 0.0
        if compact_len <= 5:
            return 0.55
        return 0.40

    if compact_len <= 5:
        return 0.0
    if compact_len <= 8:
        return 0.55
    return 0.40


def _int_value(value: Any, default: int = 0) -> int:
    """Ép giá trị về int với default an toàn khi dữ liệu metadata thiếu hoặc lỗi kiểu."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _table_name(row: Dict[str, Any]) -> str:
    """Trả về tên bảng kèm schema từ một row metadata."""
    return ".".join(
        item for item in [str(row.get("schema_name") or ""), str(row.get("table_name") or "")]
        if item
    )
