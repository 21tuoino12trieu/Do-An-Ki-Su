import codecs
import re
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlsplit

from bs4 import BeautifulSoup, NavigableString, Tag, UnicodeDammit

from beedoc_v3.renders.document_render.html_render.utils.image_pipeline import (
    render_image_output,
)


def detect_html_encoding(raw_bytes: bytes) -> str:
    sample = raw_bytes[:4096]
    if raw_bytes.startswith(b"\x00\x00\xfe\xff"):
        return "utf-32-be"
    if raw_bytes.startswith(b"\xff\xfe\x00\x00"):
        return "utf-32-le"
    if raw_bytes.startswith(b"\xfe\xff"):
        return "utf-16-be"
    if raw_bytes.startswith(b"\xff\xfe"):
        return "utf-16-le"
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"

    charset_match = re.search(
        rb"charset\s*=\s*[\"']?\s*([a-z0-9._-]+)", sample, flags=re.IGNORECASE,
    )
    if charset_match:
        try:
            encoding = charset_match.group(1).decode("ascii")
            codecs.lookup(encoding)
            return encoding
        except (LookupError, UnicodeDecodeError):
            pass
    try:
        raw_bytes.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        detected = UnicodeDammit(raw_bytes, is_html=True).original_encoding
        if detected:
            try:
                codecs.lookup(detected)
                return detected
            except LookupError:
                pass
        return "cp1252"


def prepare_html_source(file_path: str) -> Dict[str, Any]:
    if not file_path:
        return {"normalized_raw_content": ""}
    raw_bytes = Path(file_path).read_bytes()
    html_text = raw_bytes.decode(detect_html_encoding(raw_bytes), errors="replace")
    normalized = html_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    return {"normalized_raw_content": normalized}


def normalize_whitespace(text: str) -> str:
    return re.sub(r"[ \t\n\r\f\v]+", " ", str(text or "")).strip()


def sanitize_link_href(href: Any) -> str:
    value = str(href or "").strip()
    if not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
        return ""

    try:
        scheme = urlsplit(value).scheme.lower()
    except ValueError:
        return ""
    if scheme not in {"", "http", "https", "mailto"}:
        return ""
    return quote(value, safe="/:#?&=@%+~.,;_-")


def markdown_code_fence(text: Any, minimum_length: int) -> str:
    content = str(text or "")
    longest_run = max((len(run) for run in re.findall(r"`+", content)), default=0)
    return "`" * max(minimum_length, longest_run + 1)


def render_inline_code(text: Any) -> str:
    content = str(text or "").strip()
    if not content:
        return ""
    fence = markdown_code_fence(content, 1)
    padding = " " if content.startswith("`") or content.endswith("`") else ""
    return f"{fence}{padding}{content}{padding}{fence}"


def render_link_text(node: Any) -> str:
    if isinstance(node, NavigableString):
        return (escape(str(node), quote=False).replace("\\", r"\\").replace("[", r"\[").replace("]", r"\]"))
    if not isinstance(node, Tag):
        return ""
    if node.name in {"script", "style", "meta", "link", "title"}:
        return ""
    if node.name == "br":
        return "<br>"
    text = "".join(render_link_text(child) for child in node.children)
    if node.name in {"strong", "b"}:
        return f"**{text}**" if text else ""
    if node.name in {"em", "i"}:
        return f"*{text}*" if text else ""
    if node.name == "code":
        return render_inline_code(text)
    return text


def collect_image_html_attrs(node: Tag) -> Dict[str, Any]:
    attrs: Dict[str, Any] = {}
    for raw_name, raw_value in node.attrs.items():
        name = str(raw_name or "").strip()
        if not name or name.lower() == "src":
            continue
        if isinstance(raw_value, list):
            attrs[name] = " ".join(str(value) for value in raw_value)
        elif raw_value is None:
            attrs[name] = None
        else:
            attrs[name] = str(raw_value)
    return attrs


def build_image_block(node: Tag) -> Dict[str, Any]:
    src = str(node.get("src") or "").strip()
    return {
        "type": "image",
        "attrs": {"src": src, "html_attrs": collect_image_html_attrs(node)},
    }


def render_children_inline_text(node: Tag) -> str:
    return "".join(render_inline_text(child) for child in node.children)


def render_inline_text(node: Any) -> str:
    if isinstance(node, NavigableString):
        return escape(str(node), quote=False)
    if not isinstance(node, Tag):
        return ""
    if node.name in {"script", "style", "meta", "link", "title"}:
        return ""
    if node.name == "br":
        return "<br>"
    if node.name == "img":
        return render_image_output(
            html_attrs=collect_image_html_attrs(node),
        )
    if node.name == "a":
        safe_text = normalize_whitespace(render_link_text(node))
        safe_href = sanitize_link_href(node.get("href"))
        return (f"[{safe_text}]({safe_href})" if safe_href and safe_text else safe_text or safe_href)
    if node.name in {"strong", "b"}:
        text = normalize_whitespace(render_children_inline_text(node))
        return f"**{text}**" if text else ""
    if node.name in {"em", "i"}:
        text = normalize_whitespace(render_children_inline_text(node))
        return f"*{text}*" if text else ""
    if node.name == "code":
        text = normalize_whitespace(render_children_inline_text(node))
        return render_inline_code(text)
    return render_children_inline_text(node)


def has_direct_block_child(node: Tag) -> bool:
    return any(
        isinstance(child, Tag) and child.name in {"blockquote","div","h1","h2","h3","h4","h5","h6","img","ol","p","pre","table","ul"}
        for child in node.children
    )


def build_blocks_from_container_children(node: Tag) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    inline_parts: List[str] = []

    def flush_inline_parts() -> None:
        text = normalize_whitespace("".join(inline_parts))
        inline_parts.clear()
        if text:
            blocks.append({"type": "paragraph", "text": text})

    for child in node.children:
        if isinstance(child, Tag) and child.name in {"blockquote","div","h1","h2","h3","h4","h5","h6","img","ol","p","pre","table","ul"}:
            flush_inline_parts()
            blocks.extend(build_blocks_from_node(child))
            continue
        inline_parts.append(render_inline_text(child))

    flush_inline_parts()
    return blocks


def build_list_block(node: Tag) -> Dict[str, Any]:
    ordered = node.name == "ol"
    items: List[Dict[str, Any]] = []
    for child in node.find_all("li", recursive=False):
        item_blocks: List[Dict[str, Any]] = []
        text_parts: List[str] = []
        for item_child in child.children:
            if isinstance(item_child, Tag) and item_child.name in {"ul", "ol"}:
                nested = build_list_block(item_child)
                if nested.get("items"):
                    item_blocks.append(nested)
                continue
            text_parts.append(render_inline_text(item_child))
        text = normalize_whitespace("".join(text_parts))
        items.append({"text": text, "children": item_blocks})
    return {"type": "list", "ordered": ordered, "items": items}


def build_mixed_content_blocks(node: Any) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    inline_parts: List[str] = []

    def flush_inline_parts() -> None:
        text = normalize_whitespace("".join(inline_parts))
        inline_parts.clear()
        if text:
            blocks.append({"type": "paragraph", "text": text})

    def visit(child: Any) -> None:
        if isinstance(child, NavigableString):
            inline_parts.append(str(child))
            return
        if not isinstance(child, Tag):
            return
        if child.name == "table":
            return
        if child.name == "img":
            flush_inline_parts()
            blocks.append(build_image_block(child))
            return
        if child.find(["img", "table"]) is not None:
            for nested_child in child.children:
                visit(nested_child)
            return
        inline_parts.append(render_inline_text(child))

    for child in node.children:
        visit(child)
    flush_inline_parts()
    return blocks


def build_table_context_label(
    row_cells: List[Dict[str, Any]], owner_cell_index: int, fallback: str,
) -> str:
    context_parts: List[str] = []
    candidate_indexes = [0, owner_cell_index] if owner_cell_index else [0]

    for cell_index in candidate_indexes:
        if cell_index >= len(row_cells):
            continue
        blocks = row_cells[cell_index].get("blocks") or []
        text = " ".join(
            str(block.get("text") or "")
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "paragraph"
        )
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = normalize_whitespace(re.sub(r"[*_`#|]", " ", text))
        text = text.rstrip(" ,:;.")
        if text and text not in context_parts:
            context_parts.append(text)

    if not context_parts:
        return fallback

    context = ": ".join(context_parts)
    if len(context) > 160:
        context = context[:157].rsplit(" ", 1)[0].rstrip(" ,:;.") + "..."
    return context


def parse_table_span(value: Any) -> int:
    try:
        return min(max(int(str(value or "1")), 1), 1000)
    except (TypeError, ValueError):
        return 1


def build_empty_table_cell(
    is_header: bool = False, colspan_placeholder: bool = False
) -> Dict[str, Any]:
    return {
        "blocks": [],
        "is_header": is_header,
        "colspan_placeholder": colspan_placeholder,
    }


def find_available_table_column(
    row_map: Dict[int, Dict[str, Any]], start_column: int, colspan: int,
) -> int:
    column = start_column
    while any(column + offset in row_map for offset in range(colspan)):
        column += 1
    return column


def build_table_block(
    node: Tag,
    label_path: str = "",
    context_path: Optional[List[str]] = None,
    depth: int = 0,
) -> Dict[str, Any]:
    parent_context = list(context_path or [])
    rows: List[Dict[str, Any]] = []
    nested_blocks: List[Dict[str, Any]] = []
    active_rowspans: Dict[int, Dict[str, Any]] = {}

    direct_rows = [
        row for row in node.find_all("tr") if row.find_parent("table") is node
    ]
    for row in direct_rows:
        row_map: Dict[int, Dict[str, Any]] = {}
        next_rowspans: Dict[int, Dict[str, Any]] = {}
        for column, span_state in active_rowspans.items():
            row_map[column] = span_state["cell"]
            remaining_rows = int(span_state["remaining_rows"]) - 1
            if remaining_rows > 0:
                next_rowspans[column] = {
                    "cell": span_state["cell"],
                    "remaining_rows": remaining_rows,
                }
        active_rowspans = next_rowspans

        cells = row.find_all(["th", "td"], recursive=False)
        nested_cell_records: List[Dict[str, Any]] = []
        next_column = 0
        for cell in cells:
            rowspan = parse_table_span(cell.get("rowspan"))
            colspan = parse_table_span(cell.get("colspan"))
            start_column = find_available_table_column(row_map, next_column, colspan,)
            parsed_cell = {
                "blocks": build_mixed_content_blocks(cell),
                "is_header": cell.name == "th",
                "colspan_placeholder": False,
            }
            row_map[start_column] = parsed_cell

            for offset in range(1, colspan):
                row_map[start_column + offset] = build_empty_table_cell(
                    is_header=cell.name == "th", colspan_placeholder=True
                )

            if rowspan > 1:
                for offset in range(colspan):
                    active_rowspans[start_column + offset] = {
                        "cell": build_empty_table_cell(
                            is_header=cell.name == "th", colspan_placeholder=offset > 0,
                        ),
                        "remaining_rows": rowspan - 1,
                    }

            nested_cell_records.append(
                {"cell": cell, "column": start_column,}
            )
            next_column = start_column + colspan

        if row_map:
            last_column = max(row_map)
            row_cells = [
                row_map.get(column, build_empty_table_cell(),)
                for column in range(last_column + 1)
            ]

            for record in nested_cell_records:
                cell = record["cell"]
                cell_index = int(record["column"])
                nested_tables = [
                    table
                    for table in cell.find_all("table")
                    if table.find_parent("table") is node
                ]
                for nested_table in nested_tables:
                    nested_index = len(nested_blocks) + 1
                    nested_path = (
                        f"{label_path}.{nested_index}"
                        if label_path
                        else str(nested_index)
                    )
                    fallback_label = f"Bảng chi tiết {nested_path}"
                    local_context = build_table_context_label(
                        row_cells, cell_index, fallback_label,
                    )
                    nested_context = [*parent_context, local_context]
                    label = (
                        fallback_label
                        if local_context == fallback_label and not parent_context
                        else f"Chi tiết cho {' > '.join(nested_context)}"
                    )
                    reference = (
                        f"Xem phần {label[0].lower() + label[1:]} bên dưới."
                        if label != fallback_label
                        else f"Xem {fallback_label} bên dưới."
                    )
                    row_cells[cell_index]["blocks"].append(
                        {"type": "paragraph", "text": reference}
                    )
                    nested_depth = depth + 1
                    nested_block = build_table_block(
                        nested_table, nested_path, nested_context, nested_depth,
                    )
                    if nested_block.get("rows"):
                        nested_blocks.append(
                            {
                                "label": label,
                                "heading_level": min(2 + nested_depth, 6),
                                "block": nested_block,
                            }
                        )

            rows.append({"cells": row_cells})
    return {"type": "table", "rows": rows, "nested_blocks": nested_blocks}


def build_blocks_from_node(node: Any) -> List[Dict[str, Any]]:
    if isinstance(node, NavigableString):
        text = normalize_whitespace(str(node))
        return [{"type": "paragraph", "text": text}] if text else []
    if not isinstance(node, Tag):
        return []
    if node.name in {"script", "style", "meta", "link", "title"}:
        return []
    if node.name == "img":
        return [build_image_block(node)]
    if node.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        text = normalize_whitespace(render_children_inline_text(node))
        return ([{"type": "heading", "level": int(node.name[1]), "text": text}] if text else [])
    if node.name in {"p", "div", "section", "article", "main", "header", "footer"}:
        if has_direct_block_child(node):
            return build_blocks_from_container_children(node)
        if node.find("img") is not None:
            return build_mixed_content_blocks(node)
        text = normalize_whitespace(render_children_inline_text(node))
        if text:
            return [{"type": "paragraph", "text": text}]
        blocks: List[Dict[str, Any]] = []
        for child in node.children:
            blocks.extend(build_blocks_from_node(child))
        return blocks
    if node.name in {"ul", "ol"}:
        list_block = build_list_block(node)
        return [list_block] if list_block.get("items") else []
    if node.name == "table":
        table_block = build_table_block(node)
        return [table_block] if table_block.get("rows") else []
    if node.name == "blockquote":
        text = normalize_whitespace(render_children_inline_text(node))
        return [{"type": "quote", "text": text}] if text else []
    if node.name == "pre":
        text = escape(node.get_text("\n", strip=True), quote=False)
        return [{"type": "code", "text": text}] if text else []

    blocks: List[Dict[str, Any]] = []
    for child in node.children:
        blocks.extend(build_blocks_from_node(child))
    return blocks


def parse_html_to_structure(normalized_raw_content: str) -> Dict[str, Any]:
    html_text = normalized_raw_content or ""
    if not html_text.strip():
        return {"html_payload": {"blocks": []}}

    soup = BeautifulSoup(html_text, "html.parser")
    container = soup.body or soup
    blocks: List[Dict[str, Any]] = []
    for child in container.children:
        blocks.extend(build_blocks_from_node(child))
    return {"html_payload": {"blocks": blocks}}


def render_markdown_from_list(block: Dict[str, Any], indent: int = 0) -> str:
    lines: List[str] = []
    ordered = bool(block.get("ordered"))
    for index, item in enumerate(block.get("items") or [], start=1):
        marker = f"{index}." if ordered else "-"
        prefix = " " * indent
        text = str(item.get("text") or "").strip()
        lines.append(f"{prefix}{marker} {text}".rstrip())
        for child in item.get("children") or []:
            rendered = render_markdown_from_block(child, indent + 2)
            if rendered.strip():
                lines.append(rendered)
    return "\n".join(lines)


def render_markdown_from_table(block: Dict[str, Any]) -> str:
    rows: List[List[str]] = []
    header_rows: List[bool] = []
    colspan_placeholders: List[List[bool]] = []
    for row in block.get("rows") or []:
        if not isinstance(row, dict):
            continue
        rendered_cells: List[str] = []
        cells = row.get("cells") or []
        for cell in cells:
            cell_blocks = cell.get("blocks") if isinstance(cell, dict) else []
            rendered_blocks = [
                render_markdown_from_block(cell_block).strip()
                for cell_block in (cell_blocks or [])
                if isinstance(cell_block, dict)
            ]
            cell_content = "<br>".join(part for part in rendered_blocks if part)
            rendered_cells.append(cell_content.replace("\n", "<br>"))
        if rendered_cells:
            rows.append(rendered_cells)
            header_rows.append(
                bool(cells)
                and all(isinstance(cell, dict) and bool(cell.get("is_header"))for cell in cells)
            )
            colspan_placeholders.append(
                [
                    bool(cell.get("colspan_placeholder"))
                    if isinstance(cell, dict)
                    else False
                    for cell in cells
                ]
            )
    if not rows:
        return ""
    column_count = max(len(row) for row in rows)
    normalized_rows = [row + [""] * (column_count - len(row)) for row in rows]
    normalized_placeholders = [
        placeholders + [False] * (column_count - len(placeholders))
        for placeholders in colspan_placeholders
    ]

    header_row_count = 0
    for is_header_row in header_rows:
        if not is_header_row:
            break
        header_row_count += 1

    if header_row_count > 1:
        expanded_headers: List[List[str]] = []
        for row_index in range(header_row_count):
            expanded_row: List[str] = []
            previous_value = ""
            for column, value in enumerate(normalized_rows[row_index]):
                if normalized_placeholders[row_index][column]:
                    expanded_row.append(previous_value)
                else:
                    expanded_row.append(value)
                    if value:
                        previous_value = value
            expanded_headers.append(expanded_row)

        combined_header = []
        for column in range(column_count):
            header_parts = []
            for header_row in expanded_headers:
                value = header_row[column].strip()
                if value and value not in header_parts:
                    header_parts.append(value)
            combined_header.append(" - ".join(header_parts))
        normalized_rows = [combined_header, *normalized_rows[header_row_count:]]

    has_explicit_header = bool(header_rows and header_rows[0])
    header = normalized_rows[0] if has_explicit_header else [""] * column_count
    separator = ["---"] * column_count
    body = normalized_rows[1:] if has_explicit_header else normalized_rows
    table_rows = [header, separator, *body]
    rendered_parts = [
        "\n".join(
            "| "
            + " | ".join(str(cell or "").replace("|", r"\|") for cell in row)
            + " |"
            for row in table_rows
        )
    ]
    for nested in block.get("nested_blocks") or []:
        label = str(nested.get("label") or "Bảng chi tiết").strip()
        heading_level = min(max(int(nested.get("heading_level") or 3), 1), 6)
        nested_block = (
            nested.get("block") if isinstance(nested.get("block"), dict) else {}
        )
        nested_markdown = render_markdown_from_table(nested_block).strip()
        if nested_markdown:
            rendered_parts.append(f"{'#' * heading_level} {label}\n\n{nested_markdown}")
    return "\n\n".join(rendered_parts)


def render_markdown_from_block(block: Dict[str, Any], indent: int = 0) -> str:
    block_type = block.get("type")
    if block_type == "heading":
        level = int(block.get("level", 1) or 1)
        return f"{'#' * min(level, 6)} {str(block.get('text') or '').strip()}".strip()
    if block_type == "paragraph":
        return str(block.get("text") or "")
    if block_type == "quote":
        text = str(block.get("text") or "")
        return f"> {text}" if text else ""
    if block_type == "code":
        text = str(block.get("text") or "")
        if not text:
            return ""
        fence = markdown_code_fence(text, 3)
        return f"{fence}\n{text}\n{fence}"
    if block_type == "image":
        attrs = block.get("attrs", {})
        return render_image_output(
            extracted_text=str(attrs.get("gate_extracted_text") or ""),
            html_attrs=(
                attrs.get("html_attrs")
                if isinstance(attrs.get("html_attrs"), dict)
                else None
            ),
        )
    if block_type == "list":
        return render_markdown_from_list(block, indent)
    if block_type == "table":
        return render_markdown_from_table(block)
    return str(block.get("text") or "")


def render_blocks_to_markdown(finalized_html_payload: Any = None) -> Dict[str, Any]:
    payload = finalized_html_payload if isinstance(finalized_html_payload, dict) else {}
    blocks = list(payload.get("blocks") or [])
    rendered_parts = [render_markdown_from_block(block).strip() for block in blocks]
    return {
        "reconstructed_content": "\n\n".join(part for part in rendered_parts if part)
    }
