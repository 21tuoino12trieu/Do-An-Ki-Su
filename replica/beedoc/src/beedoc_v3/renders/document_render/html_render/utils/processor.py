"""Phân tích HTML và dựng Markdown, tách từ Beedoc gốc.

Nguồn: beedoc_v3/renders/document_render/html_render/utils/processor.py.
Các từ điển block là chi tiết nội bộ, không thuộc giao diện công khai.
"""

import re
from html import escape
from typing import Any, Dict, List
from urllib.parse import quote, urlsplit

from bs4 import BeautifulSoup, Comment, NavigableString, Tag


def build_image_block(node: Tag) -> Dict[str, Any]:
    return {"type": "image", "html": str(node)}


def render_embedded_media(node: Tag) -> str:
    # Media ngoài phạm vi; giữ liên kết khi có sẵn, không tải nội dung.
    source = node.get("src")
    if node.name == "video" and not source:
        source_node = node.find("source", src=True)
        source = source_node.get("src") if source_node else None
    href = sanitize_link_href(source)
    label = normalize_whitespace(node.get("title") or node.get("aria-label") or "Video")
    label = escape(label, quote=False).replace("[", r"\[").replace("]", r"\]")
    return f"[{label}]({href})" if href else ""


def build_table_block(node: Tag) -> Dict[str, Any]:
    rows = []
    for row in node.find_all("tr"):
        cells = row.find_all(["th", "td"], recursive=False)
        if cells:
            rows.append({"cells": [
                {"blocks": build_mixed_content_blocks(cell), "is_header": cell.name == "th"}
                for cell in cells
            ]})
    return {"type": "table", "rows": rows}



def normalize_whitespace(text: str) -> str:
    return re.sub(r"[ \t\n\r\f\v]+", " ", str(text or "")).strip()


def sanitize_link_href(href: Any) -> str:
    value = str(href or "").strip()
    if not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
        return ""

    if value.startswith("//"):
        value = f"https:{value}"

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
        return str(node)
    if node.name in {"iframe", "video", "source"}:
        return render_embedded_media(node)
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
            inline_parts.append(escape(str(child), quote=False))
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
    if node.name in {"iframe", "video", "source"}:
        media_link = render_embedded_media(node)
        return [{"type": "paragraph", "text": media_link}] if media_link else []
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
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()
    container = soup.body or soup
    blocks = build_blocks_from_container_children(container)
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
        return str(block.get("html") or "")
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
