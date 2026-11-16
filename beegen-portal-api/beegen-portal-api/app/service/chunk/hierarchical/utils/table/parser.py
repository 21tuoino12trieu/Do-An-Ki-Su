"""
parser.py
---------
Parse và resolve một markdown table row.

Conventions:
- Cell bị merge được đánh dấu bằng prefix "<merged> " hoặc chính xác là "<merged>"
- Separator row có dạng | :--- | --- | ... |
- Sau khi resolve: tất cả <merged> đều được thay bằng giá trị thực
"""

from __future__ import annotations

import re
from typing import Optional

# Tag đánh dấu cell bị merge
MERGED_TAG = "<merged>"

# Pattern detect separator row: | :--- | --- | :---: | v.v.
_SEPARATOR_PATTERN = re.compile(
    r"^\|[\s]*:?-{3,}:?[\s]*(\|[\s]*:?-{3,}:?[\s]*)+\|?[\s]*$"
)


def parse_raw_row(raw_row: str) -> list[str]:
    """
    Parse một raw markdown row string thành list cells (chưa resolve merged).

    Ví dụ:
        "| foo | <merged> bar | baz |"
        → ["foo", "<merged> bar", "baz"]

    Lưu ý:
        - Strip leading/trailing whitespace từng cell
        - Bỏ pipes đầu và cuối
    """
    parts = raw_row.split("|")
    cells = [p.strip() for p in parts[1:-1]]
    return cells


def is_separator_row(raw_row: str) -> bool:
    """
    Kiểm tra row có phải separator row không.
    Separator row: | :--- | --- | :---: | ...
    """
    return bool(_SEPARATOR_PATTERN.match(raw_row.strip()))


def is_cell_merged(cell: str) -> bool:
    """
    Cell bị merge nếu bắt đầu bằng "<merged>" (có hoặc không có text sau).
    Ví dụ: "<merged> foo" → True, "<merged>" → True, "foo" → False
    """
    return cell.strip().startswith(MERGED_TAG)


def get_cell_content(cell: str) -> str:
    """
    Lấy nội dung thực của cell, bỏ MERGED_TAG prefix nếu có.
    Ví dụ: "<merged> foo" → "foo", "<merged>" → "", "foo" → "foo"
    """
    s = cell.strip()
    if s.startswith(MERGED_TAG):
        return s[len(MERGED_TAG):].strip()
    return s


def resolve_row(
    raw_cells: list[str],
    prev_resolved_row: Optional[list[str]],
) -> list[str]:
    """
    Resolve merged cells trong một row.

    Bước 1 - Horizontal resolve:
        Cell bị merge và có content sau tag → giữ content đó.

    Bước 2 - Vertical resolve:
        Cell bị merge mà KHÔNG có content (chỉ là "<merged>" thuần)
        → copy từ prev_resolved_row cùng cột.
    """
    n = len(raw_cells)
    resolved = [""] * n

    # Bước 1: Strip MERGED_TAG, lấy content
    for i, cell in enumerate(raw_cells):
        resolved[i] = get_cell_content(cell)

    # Bước 2: Vertical resolve
    if prev_resolved_row is not None:
        for i, cell in enumerate(raw_cells):
            if is_cell_merged(cell) and resolved[i] == "":
                if i < len(prev_resolved_row):
                    resolved[i] = prev_resolved_row[i]

    return resolved


def is_fully_merged_row(raw_cells: list[str]) -> bool:
    """
    Row được coi là "fully merged" nếu tất cả cells từ index 1 trở đi
    đều bị merge (bắt đầu bằng MERGED_TAG).
    Đây là signal mạnh nhất để detect heading row mà không cần LLM.
    """
    if len(raw_cells) <= 1:
        return True
    return all(is_cell_merged(c) for c in raw_cells[1:])


def is_embedded_header_row(raw_cells: list[str], max_cell_len: int = 80) -> bool:
    """
    Phát hiện embedded column header row (bảng con nằm trong bảng cha).

    Điều kiện:
        - cell[0] bị merge dọc (vertical continuation từ row trên)
        - cell[1..n] đều KHÔNG bị merge
        - cell[1..n] có ít nhất 2 cell không rỗng, nội dung ngắn (tên cột)

    Ví dụ:
        | <merged> Danh sách... | Tên cửa hàng | Tên viết tắt | SĐT | Địa chỉ | TerminalID |
        → True (embedded column header của bảng con "Danh sách cửa hàng")
    """
    if len(raw_cells) < 3:
        return False
    if not is_cell_merged(raw_cells[0]):
        return False

    rest = raw_cells[1:]
    # Tất cả cell sau cell[0] không được là merged
    if any(is_cell_merged(c) for c in rest):
        return False

    non_empty = [c for c in rest if get_cell_content(c).strip()]
    if len(non_empty) < 2:
        return False

    return all(len(get_cell_content(c).strip()) <= max_cell_len for c in non_empty)


def parse_table(table_str: str) -> tuple[list[str], list[dict]]:
    """
    Parse một markdown table string thành headers và rows.

    Returns:
        - headers: list[str] (đã resolve merged)
        - rows: list[dict] với keys: raw_cells, resolved_cells, is_separator
    """
    lines = [l.strip() for l in table_str.splitlines() if l.strip()]
    if len(lines) < 2:
        return [], []

    # Parse header row
    raw_headers = parse_raw_row(lines[0])
    headers = [get_cell_content(c) for c in raw_headers]
    n_cols = len(headers)

    # Parse data rows
    rows = []
    prev_resolved: Optional[list[str]] = None

    for line in lines[1:]:
        if is_separator_row(line):
            continue

        raw_cells = parse_raw_row(line)
        raw_cells = (raw_cells + [""] * n_cols)[:n_cols]

        resolved = resolve_row(raw_cells, prev_resolved)

        rows.append({
            "raw_cells": raw_cells,
            "resolved_cells": resolved,
            "is_separator": False,
            "is_fully_merged": is_fully_merged_row(raw_cells),
            "is_embedded_header": is_embedded_header_row(raw_cells),
        })

        prev_resolved = resolved

    return headers, rows
