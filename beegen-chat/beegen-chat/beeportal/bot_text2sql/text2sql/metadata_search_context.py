"""Context formatting for metadata QA search in text-to-SQL chit-chat."""

import re
from typing import Any, Dict, List, Tuple

from beeportal.bot_text2sql.text2sql.metadata_search_common import (
    MAX_FULL_COLUMN_TABLES,
    SEMANTIC_CONTEXT_MAX_COLUMNS_PER_TABLE,
    SEMANTIC_CONTEXT_MAX_TABLES,
    SEMANTIC_CONTEXT_MAX_TOTAL_COLUMNS,
    SEMANTIC_RRF_FINAL_LIMIT,
    _business_definition,
    _clean_text,
    _int_flag,
    _int_value,
    _str_list,
    _table_name,
)


_VALUE_DOMAIN_PATTERN = re.compile(
    r"Miền giá trị:\s*(.*?)(?=\s*Lưu ý sử dụng:|$)",
    re.IGNORECASE | re.DOTALL,
)
_VALUE_ENTRY_PATTERN = re.compile(
    r"(?:^|,\s*)([A-Za-z][A-Za-z0-9_]*)\s*:\s*(.*?)(?=,\s*[A-Za-z][A-Za-z0-9_]*\s*:|$)",
    re.DOTALL,
)


def _matched_value_definitions(
    columns: List[Dict[str, Any]],
    value_terms: Any,
) -> List[Tuple[str, str, str]]:
    """Lấy entry `MÃ: định nghĩa` đúng với mã do planner trích xuất."""
    requested_codes = {term.casefold() for term in _str_list(value_terms)}
    if not requested_codes:
        return []

    matches: List[Tuple[str, str, str]] = []
    seen = set()
    for column in columns:
        description = str(column.get("description") or "")
        domain_match = _VALUE_DOMAIN_PATTERN.search(description)
        if not domain_match:
            continue
        for value_match in _VALUE_ENTRY_PATTERN.finditer(domain_match.group(1)):
            code, definition = value_match.groups()
            if code.casefold() not in requested_codes:
                continue
            item = (str(column.get("column_name") or ""), code, _clean_text(definition, None))
            if item not in seen:
                seen.add(item)
                matches.append(item)
    return matches


def _group_metadata_rows(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Gom row table/column thành payload theo từng bảng để format context."""
    grouped: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        table_id = str(row.get("table_id") or row.get("id") or "")
        table_name = _table_name(row)
        key = table_id or table_name
        table_group = grouped.setdefault(
            key,
            {
                "table_id": table_id,
                "table_name": table_name,
                "table_description": "",
                "columns": [],
                "table_rows": [],
                "total_columns": 0,
                "best_score": 0.0,
            },
        )
        try:
            table_group["best_score"] = max(
                float(row.get("source_score") or 0),
                table_group["best_score"],
            )
        except (TypeError, ValueError):
            pass
        table_group["total_columns"] = max(
            table_group["total_columns"],
            _int_value(row.get("total_columns"), 0),
        )
        if row.get("object_type") == "table":
            table_group["table_rows"].append(row)
            table_group["table_description"] = row.get("description") or table_group["table_description"]
        elif row.get("object_type") == "column":
            table_group["columns"].append(row)
            table_group["table_description"] = (
                table_group["table_description"]
                or row.get("table_description")
                or ""
            )

    for table_group in grouped.values():
        if not table_group["total_columns"]:
            table_group["total_columns"] = len(table_group["columns"])
        table_group["columns"].sort(
            key=lambda item: (
                _int_value(item.get("column_rank"), 999999),
                str(item.get("column_name") or ""),
            )
        )
    return grouped


def _status_lines(
    search_mode: str,
    total_rows: Any = "unknown",
    total_columns: Any = "unknown",
    included_rows: int = 0,
    included_tables: int = 0,
    included_columns: int = 0,
    is_truncated: bool = False,
    detail_level: str = "compact",
    column_list_complete: Any = "unknown",
    note_code: str = "",
) -> List[str]:
    """Tạo phần trạng thái context dạng máy đọc được cho prompt trả lời."""
    return [
        "CONTEXT_STATUS",
        f"search_mode: {search_mode}",
        f"total_rows: {total_rows}",
        f"total_columns: {total_columns}",
        f"included_rows: {included_rows}",
        f"included_tables: {included_tables}",
        f"included_columns: {included_columns}",
        f"is_truncated: {'true' if is_truncated else 'false'}",
        f"detail_level: {detail_level}",
        f"column_list_complete: {column_list_complete}",
        f"note_code: {note_code}",
        "",
    ]


def _append_table_header(lines: List[str], table: Dict[str, Any]) -> None:
    """Thêm tiêu đề bảng và mô tả bảng đầy đủ vào context."""
    lines.append("")
    lines.append(f"Bảng: {table.get('table_name') or '<không có tên bảng>'}")
    if table.get("table_id"):
        lines.append(f"Mã bảng: {table['table_id']}")
    description = _clean_text(table.get("table_description"), None)
    if description:
        lines.append(f"Mô tả bảng: {description}")


def _append_column(lines: List[str], column: Dict[str, Any], detail: str = "none") -> None:
    """Thêm dòng cột, kèm định nghĩa nghiệp vụ hoặc mô tả đầy đủ nếu cần."""
    column_name = column.get("column_name") or "<không có tên cột>"
    column_type = column.get("column_type") or ""
    column_line = f"- {column_name}"
    if column_type:
        column_line += f": {column_type}"
    lines.append(column_line)

    if detail == "business_definition":
        definition = _business_definition(column.get("description"))
        if definition:
            lines.append(f"  Định nghĩa nghiệp vụ: {definition}")
    elif detail == "full":
        description = _clean_text(column.get("description"), None)
        example = _clean_text(column.get("example"), 250)
        if description:
            lines.append(f"  Mô tả: {description}")
        if example:
            lines.append(f"  Ví dụ: {example}")


def _format_full_column_rejection(
    search_mode: str,
    table_names: Any,
    reject_reason: str,
) -> Dict[str, str]:
    """Format context từ chối mềm khi user yêu cầu full-list không hợp lệ."""
    note_code = (
        "full_columns_too_many_tables"
        if reject_reason == "too_many_tables"
        else "full_columns_missing_table"
    )
    requested_table_count = len(_str_list(table_names))
    lines = _status_lines(
        search_mode=search_mode,
        included_rows=0,
        included_tables=0,
        included_columns=0,
        is_truncated=False,
        detail_level="policy_refusal",
        column_list_complete="not_applicable",
        note_code=note_code,
    )
    lines.append("Yêu cầu liệt kê tất cả cột chưa được thực hiện.")
    if note_code == "full_columns_too_many_tables":
        lines.append(f"Lý do: user yêu cầu liệt kê tất cả cột cho {requested_table_count} bảng.")
        lines.append(f"Giới hạn: chỉ liệt kê tất cả cột cho tối đa {MAX_FULL_COLUMN_TABLES} bảng mỗi lần.")
        lines.append("Hãy yêu cầu người dùng chọn tối đa 2 bảng cụ thể.")
    else:
        lines.append("Lý do: chưa xác định được bảng cụ thể trong câu hỏi.")
        lines.append("Hãy yêu cầu người dùng nêu rõ tối đa 2 bảng cần liệt kê tất cả cột.")
    return {"metadata_context": "\n".join(lines)}


def _format_empty_context(search_mode: str) -> Dict[str, str]:
    """Format context rỗng có status để prompt biết search không có kết quả."""
    lines = _status_lines(
        search_mode=search_mode,
        included_rows=0,
        included_tables=0,
        included_columns=0,
        is_truncated=False,
        detail_level="empty",
        column_list_complete="unknown",
        note_code="no_match",
    )
    return {"metadata_context": "\n".join(lines)}


def _format_accessible_tables(rows: List[Dict[str, Any]], total_rows: int) -> Dict[str, str]:
    """Format danh sách bảng được phép truy cập ở dạng compact cho chit-chat."""
    included_tables = len(rows)
    is_truncated = total_rows > included_tables
    lines = _status_lines(
        search_mode="list_accessible_tables",
        total_rows=total_rows,
        included_rows=len(rows),
        included_tables=included_tables,
        is_truncated=is_truncated,
        detail_level="table_list",
        column_list_complete="not_applicable",
        note_code="tables_limited" if is_truncated else "tables_complete",
    )
    lines.append("Danh sách bảng có thể truy cập:")
    for row in rows:
        table_name = _table_name(row)
        table_id = row.get("table_id") or row.get("id")
        line = f"- {table_name or '<không có tên bảng>'}"
        if table_id:
            line += f" (Mã bảng: {table_id})"
        description = _clean_text(row.get("description"), 180)
        if description:
            line += f": {description}"
        lines.append(line)
    return {"metadata_context": "\n".join(lines)}


def _format_exact_table(
    rows: List[Dict[str, Any]],
    grouped: Dict[str, Dict[str, Any]],
    total_rows: int,
) -> Dict[str, str]:
    """Format metadata mô tả bảng, không liệt kê toàn bộ cột."""
    is_truncated = total_rows > len(rows)
    lines = _status_lines(
        search_mode="exact_table",
        total_rows=total_rows,
        included_rows=len(rows),
        included_tables=len(grouped),
        is_truncated=is_truncated,
        detail_level="table_metadata",
        column_list_complete="not_applicable",
        note_code="table_metadata_only",
    )
    lines.append("Metadata bảng:")
    for table in grouped.values():
        _append_table_header(lines, table)
    return {"metadata_context": "\n".join(lines)}


def _format_table_columns(
    rows: List[Dict[str, Any]],
    grouped: Dict[str, Dict[str, Any]],
    is_full_column_list: bool,
) -> Dict[str, str]:
    """Format danh sách cột theo bảng, gồm định nghĩa nghiệp vụ khi có."""
    total_columns = sum(table["total_columns"] for table in grouped.values())
    included_columns = sum(len(table["columns"]) for table in grouped.values())
    column_list_complete = all(
        table["total_columns"] <= len(table["columns"])
        for table in grouped.values()
    )
    note_code = (
        "full_columns_with_business_definition"
        if is_full_column_list
        else "columns_with_business_definition"
    )
    if not column_list_complete:
        note_code += "|columns_limited"

    lines = _status_lines(
        search_mode="list_table_columns",
        total_rows=len(rows),
        total_columns=total_columns,
        included_rows=len(rows),
        included_tables=len(grouped),
        included_columns=included_columns,
        is_truncated=not column_list_complete,
        detail_level="business_definition",
        column_list_complete="true" if column_list_complete else "false",
        note_code=note_code,
    )
    lines.append("Danh sách cột theo bảng:")
    for table in grouped.values():
        _append_table_header(lines, table)
        lines.append(f"Tổng số cột: {table['total_columns']}")
        lines.append("Cột:")
        for column in table["columns"]:
            _append_column(lines, column, detail="business_definition")
    return {"metadata_context": "\n".join(lines)}


def _format_column_detail(
    rows: List[Dict[str, Any]],
    grouped: Dict[str, Dict[str, Any]],
    total_rows: int,
    value_terms: Any = None,
) -> Dict[str, str]:
    """Format thông tin chi tiết cột theo bảng cho intent explain_column."""
    included_columns = sum(len(table["columns"]) for table in grouped.values())
    is_truncated = total_rows > len(rows)
    value_definitions_by_table = {
        id(table): _matched_value_definitions(table["columns"], value_terms)
        for table in grouped.values()
    }
    lines = _status_lines(
        search_mode="explain_column",
        total_rows=total_rows,
        included_rows=len(rows),
        included_tables=len(grouped),
        included_columns=included_columns,
        is_truncated=is_truncated,
        detail_level="column_detail",
        column_list_complete="not_applicable",
        note_code="column_ambiguous" if is_truncated or included_columns > 1 else "column_detail",
    )
    lines.append("Thông tin cột theo bảng:")
    for table in grouped.values():
        _append_table_header(lines, table)
        lines.append("Cột:")
        value_definitions = value_definitions_by_table[id(table)]
        value_columns = {column_name for column_name, _, _ in value_definitions}
        for column in table["columns"]:
            _append_column(
                lines,
                column,
                detail="business_definition" if column.get("column_name") in value_columns else "full",
            )
        if value_definitions:
            lines.append("Giá trị mã liên quan:")
            for column_name, code, definition in value_definitions:
                lines.append(f"- {column_name}.{code}: {definition}")
    return {"metadata_context": "\n".join(lines)}


def _semantic_table_payloads(
    grouped: Dict[str, Dict[str, Any]],
) -> Tuple[List[Tuple[Dict[str, Any], List[Dict[str, Any]]]], int, int, int]:
    """Chọn bảng/cột semantic tốt nhất theo score và giới hạn context."""
    ordered_tables = sorted(grouped.values(), key=lambda item: item["best_score"], reverse=True)
    total_candidate_columns = sum(len(table["columns"]) for table in grouped.values())
    included_columns = 0
    included_rows = 0
    payloads: List[Tuple[Dict[str, Any], List[Dict[str, Any]]]] = []

    # SQL đã giới hạn raw rows theo bảng; formatter tiếp tục giới hạn số bảng,
    # số cột mỗi bảng và tổng số cột để context đủ đa dạng nhưng không phình to.
    for table in ordered_tables[:SEMANTIC_CONTEXT_MAX_TABLES]:
        columns = sorted(
            table["columns"],
            key=lambda item: float(item.get("source_score") or 0),
            reverse=True,
        )
        remaining = SEMANTIC_CONTEXT_MAX_TOTAL_COLUMNS - included_columns
        selected_columns = columns[: min(SEMANTIC_CONTEXT_MAX_COLUMNS_PER_TABLE, max(remaining, 0))]
        included_columns += len(selected_columns)
        included_rows += len(selected_columns) or len(table["table_rows"])
        payloads.append((table, selected_columns))
        if included_columns >= SEMANTIC_CONTEXT_MAX_TOTAL_COLUMNS:
            break

    return payloads, total_candidate_columns, included_columns, included_rows


def _format_semantic_metadata(
    rows: List[Dict[str, Any]],
    grouped: Dict[str, Dict[str, Any]],
    value_terms: Any = None,
) -> Dict[str, str]:
    """Format context semantic metadata từ các bảng/cột đã được RRF xếp hạng."""
    table_payloads, total_candidate_columns, included_columns, included_rows = _semantic_table_payloads(grouped)
    is_truncated = (
        len(grouped) > len(table_payloads)
        or total_candidate_columns > included_columns
        or len(rows) >= SEMANTIC_RRF_FINAL_LIMIT
    )
    lines = _status_lines(
        search_mode="semantic_metadata",
        total_rows=len(rows),
        total_columns=total_candidate_columns,
        included_rows=included_rows,
        included_tables=len(table_payloads),
        included_columns=included_columns,
        is_truncated=is_truncated,
        detail_level="semantic_top_matches",
        column_list_complete="false",
        note_code="semantic_top_matches",
    )
    lines.append("Metadata phù hợp nhất theo semantic search:")
    for table, columns in table_payloads:
        _append_table_header(lines, table)
        if columns:
            lines.append("Cột liên quan:")
            for column in columns:
                _append_column(lines, column, detail="business_definition")
            value_definitions = _matched_value_definitions(columns, value_terms)
            if value_definitions:
                lines.append("Giá trị mã liên quan:")
                for column_name, code, definition in value_definitions:
                    lines.append(f"- {column_name}.{code}: {definition}")
        elif table.get("table_rows"):
            lines.append("- Kết quả khớp ở cấp bảng.")
    return {"metadata_context": "\n".join(lines)}


def format_metadata_search_context(
    rows: List[Dict[str, Any]] = None,
    search_mode: str = "no_metadata",
    table_names: Any = None,
    value_terms: Any = None,
    full_column_list: Any = 0,
    full_column_reject_reason: str = "",
    **_: Any,
) -> Dict[str, str]:
    """Đóng gói các row metadata thành context gọn cho LLM chit-chat."""
    rows = rows or []
    if search_mode == "no_metadata":
        return {"metadata_context": ""}

    is_full_column_list = _int_flag(full_column_list) == 1
    reject_reason = str(full_column_reject_reason or "").strip()
    if search_mode == "list_table_columns" and is_full_column_list and reject_reason:
        return _format_full_column_rejection(search_mode, table_names, reject_reason)

    if not rows:
        return _format_empty_context(search_mode)

    grouped = _group_metadata_rows(rows)
    total_rows = max([_int_value(row.get("total_rows"), 0) for row in rows] or [0]) or len(rows)

    if search_mode == "list_accessible_tables":
        return _format_accessible_tables(rows, total_rows)

    if search_mode == "exact_table":
        return _format_exact_table(rows, grouped, total_rows)

    if search_mode == "list_table_columns":
        return _format_table_columns(rows, grouped, is_full_column_list)

    if search_mode == "explain_column":
        return _format_column_detail(rows, grouped, total_rows, value_terms)

    if search_mode == "semantic_metadata":
        return _format_semantic_metadata(rows, grouped, value_terms)

    return {"metadata_context": ""}


def select_metadata_search_context(
    primary_metadata_context: str = None,
    semantic_metadata_context: str = None,
) -> Dict[str, str]:
    """Ưu tiên semantic context nếu nhánh semantic đã chạy, ngược lại dùng primary."""
    return {"metadata_context": semantic_metadata_context or primary_metadata_context or ""}
