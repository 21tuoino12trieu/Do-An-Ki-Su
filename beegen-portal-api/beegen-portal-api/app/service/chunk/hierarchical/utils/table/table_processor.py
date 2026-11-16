"""
Markdown table chunking with Beeflow.

The parser helpers own row parsing and merge resolution. This module owns the
table-level state machine and uses LLMNode only for weak row classification:
heading rows and column header rows in complex tables.
"""

from __future__ import annotations

import ast
import json
import re
import uuid
from typing import Any, Optional

from beeflow.nodes.base_node import CONTINUE, END, INPUT, OUTPUT, START
from beeflow.nodes.flow.branch_node import BranchNode
from beeflow.nodes.flow.while_loop_node import WhileLoopNode
from beeflow.nodes.primitives.ai.llm_node import LLMNode
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beeflow.workflow import WorkflowEngine

from .parser import (
    get_cell_content,
    is_cell_merged,
    is_embedded_header_row,
    is_fully_merged_row,
    is_separator_row,
    parse_raw_row,
    parse_table,
    resolve_row,
)
from .table_detector import detect_tables

MAX_WORD_COUNT = 2048


def _as_table_text(table_value: Any) -> str:
    if isinstance(table_value, str):
        text = table_value.strip()
        if text.startswith(("[", "{")):
            parsed: Any = None
            try:
                parsed = json.loads(text)
            except Exception:
                try:
                    parsed = ast.literal_eval(text)
                except Exception:
                    parsed = None
            if parsed is not None and parsed is not table_value:
                return _as_table_text(parsed)
        if "\\n" in text and "\n" not in text:
            text = text.replace("\\n", "\n")
        return text
    if isinstance(table_value, dict):
        for key in ("table_str", "table_markdown", "table_text", "markdown"):
            if key in table_value:
                return _as_table_text(table_value.get(key))
        return ""
    if isinstance(table_value, list):
        return "\n\n".join(_as_table_text(item) for item in table_value if item is not None)
    if table_value is None:
        return ""
    return str(table_value)


def _table_rows(table_str: Any) -> list[str]:
    table_text = _as_table_text(table_str)
    return [
        line.strip()
        for line in table_text.splitlines()
        if line.strip() and line.strip().startswith("|")
    ]


def _table_text_items(table_value: Any) -> list[str]:
    if isinstance(table_value, list):
        return [_as_table_text(item) for item in table_value if _as_table_text(item).strip()]
    if isinstance(table_value, dict):
        text = _as_table_text(table_value)
        return [text] if text.strip() else []
    text = _as_table_text(table_value)
    return [text] if text.strip() else []


def _parse_table_row_lenient(raw_row: str) -> list[str]:
    row = (raw_row or "").strip()
    if not row:
        return []
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    return [cell.strip() for cell in row.split("|")]


def _is_simple_table_node(table_str: Any) -> dict[str, Any]:
    raw_rows = _table_rows(table_str)
    if not raw_rows:
        return {"is_simple": False}

    for raw_row in raw_rows:
        if is_separator_row(raw_row):
            continue
        cells = parse_raw_row(raw_row)
        if any(is_cell_merged(cell) for cell in cells):
            return {"is_simple": False}

    return {"is_simple": True}


def _process_simple_table_node(table_str: Any) -> dict[str, Any]:
    chunks: list[str] = []
    table_items = _table_text_items(table_str)
    if not table_items:
        return {"chunks": chunks}

    for table_item in table_items:
        raw_rows = _table_rows(table_item)
        if not raw_rows:
            continue

        # Find header row: first non-separator row
        header_row = next((r for r in raw_rows if not is_separator_row(r)), None)
        if header_row is None:
            continue
        column_names = _parse_table_row_lenient(header_row)
        header_idx = raw_rows.index(header_row)
        data_rows = raw_rows[header_idx + 1 :]

        for raw_row in data_rows:
            if is_separator_row(raw_row):
                continue

            cells = _parse_table_row_lenient(raw_row)
            lines: list[str] = []
            max_len = min(len(column_names), len(cells))
            for idx in range(max_len):
                column_name = column_names[idx].strip()
                cell_value = cells[idx].strip()
                if column_name and cell_value:
                    lines.append(f"{column_name}: {cell_value}")

            if lines:
                chunks.append("\n".join(lines))

    return {"chunks": chunks}


def _init_batch_state_node(
    table_markdown: str,
    parent_heading: list[str],
    in_context_before: str,
    in_context_after: str,
) -> dict[str, Any]:
    raw_rows = _table_rows(table_markdown)
    batch_size = 10
    row_batches = []
    for i in range(0, len(raw_rows), batch_size):
        row_batches.append("\n".join(raw_rows[i : i + batch_size]))

    # Pre-analyze all rows for structural metadata
    _, parsed_rows = parse_table(table_markdown)

    init_context = "\n".join(parent_heading) if parent_heading else "(No overarching heading)"
    return {
        "iteration_count": 0,
        "row_batches": row_batches,
        "parsed_rows": parsed_rows,
        "batch_count": len(row_batches),
        "context_summary": init_context,
        "accumulated_chunks": [],
        "last_resolved_cells": [],
        "table_summary": "",
        "context_before": in_context_before,
        "context_after": in_context_after,
    }


def _check_batch_continue_node(iteration_count: int, batch_count: int) -> dict[str, Any]:
    return {"continue_loop": iteration_count < batch_count}


TABLE_BATCH_PROMPT_TEMPLATE = """Bạn là chuyên gia phân tích cấu trúc bảng Markdown phức tạp.
Nhiệm vụ: Dựa trên NGỮ CẢNH TỪ CÁC BATCH TRƯỚC (Heading tree, Column names) và BATCH MARKDOWN HIỆN TẠI (10 dòng), hãy trích xuất các dòng dữ liệu thành các đoạn văn bản có ý nghĩa (Semantic Chunks) và xuất ra TRẠNG THÁI MỚI để truyền sang batch tiếp theo.

======================================
I. NGỮ CẢNH TỪ CÁC BATCH TRƯỚC
======================================
{context_summary}

---LAST_ROW_VALUES--- (Giá trị đã resolve của dòng CUỐI CÙNG trong batch trước, dùng để propagate vertical merge cho dòng đầu batch này nếu cell chứa `<merged>`)
{last_resolved_cells_str}

---PRE_DETECTED_EMBEDDED_HEADERS--- (Các dòng trong batch này đã được hệ thống phát hiện là Embedded Column Header bằng rule-based. Hãy xác nhận và ghi nhận chúng làm tên cột nội bộ.)
{embedded_header_hints_str}

======================================
II. BATCH MARKDOWN HIỆN TẠI CẦN XỬ LÝ
======================================
{batch_rows}

======================================
III. QUY TẮC CẬP NHẬT TRẠNG THÁI (HEADING & COLUMNS)
======================================
Mục tiêu: Theo dõi chính xác vị trí ngữ cảnh của dòng dữ liệu hiện tại bằng cách liên tục cập nhật Heading Tree và Column Names.

1. Xử lý Heading Tree:
   - Dòng "Fully merged" (các ô từ vị trí thứ 2 trở đi đều chứa tag `<merged>`) chắc chắn là Heading (tiêu đề nhóm/section).
   - QUAN TRỌNG - GIỮ NGUYÊN THỨ TỰ/SỐ ĐẦU DÒNG: Khi ghi nhận heading, PHẢI giữ nguyên toàn bộ nội dung gốc bao gồm số La Mã (I, II, III, IV...), số Ả Rập (1, 2, 3, 1.1, 1.2...), ký tự đầu dòng. VD: heading là "I. PHÍ PHÁT HÀNH" thì ghi "I. PHÍ PHÁT HÀNH", KHÔNG ghi chỉ "PHÍ PHÁT HÀNH".
   - QUAN TRỌNG - CẬP NHẬT CÙNG CẤP (Same-Level Replace): Heading tree phản ánh VỊ TRÍ HIỆN TẠI trong tài liệu, KHÔNG phải toàn bộ lịch sử.
     + Khi phát hiện heading MỚI ở CÙNG CẤP với heading trước đó → THAY THẾ heading cũ cùng cấp đó, KHÔNG append thêm.
     + Heading cấp con của heading cũ cũng bị XÓA khi heading cha bị thay thế.
     + Ví dụ: Heading tree đang là "I. PHÍ PHÁT HÀNH > 1.1 Phí phát hành lần đầu", gặp "II. PHÍ PHÁT HÀNH LẠI THẺ / PIN" → Heading tree mới là "II. PHÍ PHÁT HÀNH LẠI THẺ / PIN" (thay thế cả "I. PHÍ PHÁT HÀNH" và con của nó).
     + Quy tắc: so sánh CẤP ĐỘ heading (dựa trên vị trí cột bị merge, font, số thứ tự) để xác định cùng cấp hay cấp con.

2. Xử lý Column Names (Tên Cột Chính):
   - Đứng trước các hàng dữ liệu, chứa tên các thuộc tính (VD: STT, Tên Cửa Hàng, SĐT...).
   - BẢNG KEY-VALUE KHÔNG CÓ TÊN CỘT: Rất nhiều bảng chỉ là dạng Key-Value lưu thông tin (cột trái là Key, cột phải là Value) và hoàn toàn KHÔNG có dòng tiêu đề cột. Nếu rơi vào trường hợp này, hãy để trống hoặc ghi "Không xác định" cho mục `---COLUMN_NAMES---`.
   - QUY TẮC GỘP NGANG (Horizontal Merge): Khi thu thập Tên Cột, MỖI GIÁ TRỊ CHỈ ĐƯỢC GHI 1 LẦN. Tuyệt đối KHÔNG LẶP LẠI (Duplicate) tên cột nếu nó bị merged ngang. (Ví dụ: `Thông tin chung | QR động | <merged> QR động` → CHỈ lấy `Thông tin chung | QR động`).

3. Xử lý logic Column Name khi xuất hiện EMBEDDED TABLE (Bảng Lồng):
   - Xảy ra khi ô đầu tiên chứa `<merged>` nhưng các ô tiếp theo lại chứa "Tên Cột Nội Bộ" (không bị merged, nội dung ngắn).
   - Bạn GHI NHẬN Embedded Column Names vào field `current_embedded_columns` trong output JSON. Tên cột của bảng lồng (Embedded) sẽ KẾT HỢP với Tên Cột Chính để trích xuất chunk.
   - Tham khảo `---PRE_DETECTED_EMBEDDED_HEADERS---` phía trên: nếu hệ thống đã phát hiện sẵn, hãy XÁC NHẬN và sử dụng.

4. Xử lý Intro Row (Dòng giới thiệu bảng con):
   - Dạng: cell[0] KHÔNG bị merged + cell[1] là tên file / mô tả ngắn + cell[2..] bị merged ngang.
   - Ví dụ: `| Danh sách cửa hàng & SĐT | Thông tin cửa hàng Yody.xlsx | <merged> ... |`
   - Dòng này KHÔNG phải heading, KHÔNG phải data → BỎ QUA khi tạo chunk. Ghi nhận nội dung cell[0] vào Heading Tree như một sub-heading.

======================================
IV. QUY TẮC TRÍCH XUẤT CHUNKS
======================================
1. Trích xuất Semantic Chunks linh hoạt:
   - Mặc định MỖI DÒNG (Row) CẦN ĐƯỢC TRÍCH XUẤT THÀNH 1 CHUNK ĐỘC LẬP để giữ cấu trúc.
   - TRƯỜNG HỢP Ô MERGED THEO CHIỀU DỌC: Nếu ô đầu tiên ở dòng này hiển thị `<merged>` trống không, hãy TỰ ĐỘNG SAO CHÉP giá trị nằm ngay phía trên nó tại cùng một cột. Nếu đây là dòng ĐẦU TIÊN trong batch và không có dòng trước, hãy sử dụng `---LAST_ROW_VALUES---` từ Section I. Không xuất ra chữ `<merged>` trong chunk.
   - CHỈ GỘP DÒNG KHI CẦN THIẾT (Bảng Key-Value / 2 Cột): Chỉ khi nhận thấy bảng có cấu trúc Key-Value rất đơn giản (ví dụ cột trái là Header lớn cõng theo nhiều dòng giá trị ở cột phải), bạn mới nên GỘP các cell có chung gốc (ô được `<merged>` từ trên xuống) thành 1 Chunk tổng thống nhất để tránh manh mún. Nếu bảng có nhiều cột chằng chịt, HÃY TÁCH RA THÀNH TỪNG CHUNK RIÊNG CHO MỖI DÒNG.

2. Những dòng BỎ QUA (Không được tạo Chunk):
   - Dòng phân cách Markdown: `| --- | --- |`
   - Dòng Header cột thuần túy (Is Column Name).
   - Dòng Heading phân nhóm thuần túy (Is Heading).
   - Dòng Embedded Column Header (tên cột bảng con) – ghi nhận vào `current_embedded_columns` nhưng KHÔNG tạo chunk.
   - Dòng Intro Row (giới thiệu bảng con, cell[1] là filename/mô tả) – ghi nhận vào Heading Tree nhưng KHÔNG tạo chunk.
   - Dòng mà TẤT CẢ cell dữ liệu (cell[1..n]) đều rỗng – đây là dòng trống, BỎ QUA.

======================================
V. FORMAT OUTPUT BẮT BUỘC
======================================
TUYỆT ĐỐI chỉ trả về 1 Object JSON (Không bọc Markdown ` ```json `, không có text giải thích thừa):
{{
  "extracted_chunks": [
     "I. PHÍ PHÁT HÀNH > 1.1 Phí phát hành lần đầu\\nTên cột chính 1: Dữ liệu 1\\nTên cột chính 2 - Tên cột lồng 1: Dữ liệu lồng",
     "..."
  ],
  "updated_context_summary": "---HEADING_TREE---\\nI. PHÍ PHÁT HÀNH > 1.1 Phí phát hành lần đầu\\n---COLUMN_NAMES---\\nCột A | Cột B\\n---EMBEDDED_COLUMNS---\\n(Ghi nhận nếu đang trong bảng lồng, có thể để trống)",
  "current_embedded_columns": ["Tên cột lồng 1", "Tên cột lồng 2"]
}}
LƯU Ý:
- Heading tree trong updated_context_summary phản ánh VỊ TRÍ HIỆN TẠI (heading cuối cùng đang active + tổ tiên), KHÔNG phải toàn bộ heading đã qua. Khi heading cùng cấp xuất hiện, cây cũ bị thay thế.
- Trong extracted_chunks, PHẢI giữ nguyên số La Mã/Ả Rập đầu heading (VD: "I. PHÍ PHÁT HÀNH", "II. PHÍ PHÁT HÀNH LẠI", "1.1 Phí...").
"""

TABLE_SUMMARY_PROMPT_TEMPLATE = """Bạn là chuyên gia phân tích cấu trúc bảng.
Nhiệm vụ: Dựa trên TÓM TẮT TRƯỚC ĐÓ và BATCH MARKDOWN HIỆN TẠI, hãy cập nhật thông tin tổng quan về bảng.

======================================
TÓM TẮT TRƯỚC ĐÓ
======================================
{previous_summary}

======================================
NGỮ CẢNH CẤU TRÚC (từ luồng chunking)
======================================
{context_summary}

{surrounding_text_section}
======================================
BATCH MARKDOWN HIỆN TẠI
======================================
{batch_rows}

======================================
QUY TẮC CẬP NHẬT
======================================
1. Tên bảng: Xác định tên bảng dựa trên heading cấp cao nhất hoặc context heading. Nếu đã xác định từ batch trước thì giữ nguyên, chỉ cập nhật nếu phát hiện tên chính xác hơn.
2. Nội dung: Tóm tắt ngắn gọn bảng nói về chủ đề gì (1-2 câu). Cập nhật lại nếu batch mới cho thấy phạm vi rộng hơn.
3. Kiến trúc cột: Liệt kê tên các cột chính. Nếu có bảng lồng (embedded table), ghi rõ cả tên cột của bảng con.
4. Cấu trúc heading: Heading tree hiện tại, quan hệ cha-con giữa các section.

======================================
FORMAT OUTPUT BẮT BUỘC
======================================
TUYỆT ĐỐI chỉ trả về plain text theo format sau (KHÔNG bọc JSON, KHÔNG bọc Markdown):
---TABLE_NAME---
<tên bảng>
---TABLE_ABOUT---
<mô tả ngắn gọn nội dung bảng, 1-2 câu>
---TABLE_COLUMNS---
<liệt kê tên cột chính, phân cách bằng | . Nếu có bảng lồng ghi thêm dòng "Bảng con: tên cột 1 | tên cột 2">
---TABLE_STRUCTURE---
<heading tree hiện tại, mỗi heading 1 dòng>
"""


def _prepare_summary_prompt_node(
    iteration_count: int,
    row_batches: list[str],
    context_summary: str,
    table_summary: str,
    context_before: str,
    context_after: str,
) -> dict[str, Any]:
    batch_rows = row_batches[iteration_count] if iteration_count < len(row_batches) else ""
    
    surrounding_text_section = ""
    if iteration_count == 0 and (context_before or context_after):
        surrounding_text_section = (
            "======================================\n"
            "NGỮ CẢNH VĂN BẢN (Text xung quanh bảng)\n"
            "======================================\n"
        )
        if context_before:
            surrounding_text_section += f"[15 dòng trước bảng]:\n{context_before}\n\n"
        if context_after:
            surrounding_text_section += f"[15 dòng sau bảng]:\n{context_after}\n\n"

    prompt = TABLE_SUMMARY_PROMPT_TEMPLATE.format(
        previous_summary=table_summary if table_summary.strip() else "(Đây là batch đầu tiên, chưa có tóm tắt)",
        context_summary=context_summary if context_summary.strip() else "(Chưa có ngữ cảnh)",
        surrounding_text_section=surrounding_text_section,
        batch_rows=batch_rows,
    )
    return {
        "summary_messages": [
            {"role": "user", "content": prompt}
        ]
    }


def _prepare_simple_summary_prompt_node(
    table_markdown: str,
    parent_heading: list[str],
    context_before: str,
    context_after: str,
) -> dict[str, Any]:
    raw_rows = _table_rows(table_markdown)
    first_15 = "\n".join(raw_rows[:15])
    context_summary = "\n".join(parent_heading) if parent_heading else "(No overarching heading)"
    
    surrounding_text_section = ""
    if context_before or context_after:
        surrounding_text_section = (
            "======================================\n"
            "NGỮ CẢNH VĂN BẢN (Text xung quanh bảng)\n"
            "======================================\n"
        )
        if context_before:
            surrounding_text_section += f"[15 dòng trước bảng]:\n{context_before}\n\n"
        if context_after:
            surrounding_text_section += f"[15 dòng sau bảng]:\n{context_after}\n\n"
            
    prompt = TABLE_SUMMARY_PROMPT_TEMPLATE.format(
        previous_summary="(Bảng đơn giản, lấy tối đa 15 dòng đầu để tóm tắt)",
        context_summary=context_summary,
        surrounding_text_section=surrounding_text_section,
        batch_rows=first_15,
    )
    return {
        "summary_messages": [
            {"role": "user", "content": prompt}
        ]
    }


def _parse_summary_response_node(summary_content: str) -> dict[str, Any]:
    text = (summary_content or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return {"parsed_table_summary": text.strip()}


def _prepare_batch_prompt_node(
    iteration_count: int,
    row_batches: list[str],
    parsed_rows: list[dict],
    context_summary: str,
    last_resolved_cells: list[str],
) -> dict[str, Any]:
    batch_rows = row_batches[iteration_count] if iteration_count < len(row_batches) else ""

    # Build last_resolved_cells string for cross-batch vertical merge propagation
    if last_resolved_cells:
        last_resolved_cells_str = " | ".join(str(c) for c in last_resolved_cells)
    else:
        last_resolved_cells_str = "(Đây là batch đầu tiên, chưa có dòng trước)"

    # Build embedded header hints from pre-analyzed parsed_rows
    batch_size = 10
    batch_start = iteration_count * batch_size
    batch_end = min(batch_start + batch_size, len(parsed_rows))
    hints: list[str] = []
    for row_idx in range(batch_start, batch_end):
        if row_idx < len(parsed_rows) and parsed_rows[row_idx].get("is_embedded_header", False):
            cols = [
                get_cell_content(c)
                for c in parsed_rows[row_idx]["raw_cells"][1:]
                if get_cell_content(c).strip()
            ]
            local_idx = row_idx - batch_start + 1
            hints.append(f"Dòng {local_idx} trong batch: [{' | '.join(cols)}]")
    embedded_header_hints_str = "\n".join(hints) if hints else "(Không phát hiện embedded header trong batch này)"

    prompt = TABLE_BATCH_PROMPT_TEMPLATE.format(
        context_summary=context_summary if context_summary.strip() else "(Bắt đầu bảng, chưa có ngữ cảnh)",
        batch_rows=batch_rows,
        last_resolved_cells_str=last_resolved_cells_str,
        embedded_header_hints_str=embedded_header_hints_str,
    )

    return {
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }


def _parse_batch_response_node(content: str) -> dict[str, Any]:
    text = (content or "").strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    extracted_chunks: list[str] = []
    updated_context = ""
    embedded_columns: list[str] = []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            extracted_chunks = parsed.get("extracted_chunks", [])
            updated_context = parsed.get("updated_context_summary", "")
            embedded_columns = parsed.get("current_embedded_columns", [])
    except Exception:
        pass

    return {
        "extracted_chunks": extracted_chunks,
        "updated_context": updated_context,
        "embedded_columns": embedded_columns,
    }


def _update_batch_state_node(
    in_iteration_count: int,
    in_accumulated_chunks: list[str],
    in_context_summary: str,
    in_table_summary: str,
    in_parsed_rows: list[dict],
    extracted_chunks: list[str],
    updated_context: str,
    embedded_columns: list[str],
    parsed_table_summary: str,
    in_context_before: str,
    in_context_after: str,
) -> dict[str, Any]:
    new_chunks = list(in_accumulated_chunks or [])
    for c in extracted_chunks:
        if isinstance(c, str) and c.strip():
            new_chunks.append(c.strip())

    # Cascade protection: keep previous context if LLM returned empty
    next_context = updated_context.strip() if updated_context.strip() else in_context_summary

    # Cascade protection for table summary
    next_table_summary = parsed_table_summary.strip() if parsed_table_summary.strip() else in_table_summary

    # Compute last_resolved_cells for the row at the end of the current batch
    batch_size = 10
    batch_end_idx = min((in_iteration_count + 1) * batch_size - 1, len(in_parsed_rows) - 1)
    last_resolved: list[str] = []
    if in_parsed_rows and batch_end_idx >= 0:
        last_resolved = in_parsed_rows[batch_end_idx].get("resolved_cells", [])

    return {
        "iteration_count": in_iteration_count + 1,
        "accumulated_chunks": new_chunks,
        "context_summary": next_context,
        "table_summary": next_table_summary,
        "last_resolved_cells": last_resolved,
        "context_before": in_context_before,
        "context_after": in_context_after,
    } 


def _finalize_batch_chunks_node(accumulated_chunks: list[str], in_table_summary: str) -> dict[str, Any]:
    return {"chunks": accumulated_chunks, "out_table_summary": in_table_summary}



class TableProcessor:
    def __init__(self, max_word_count: int = MAX_WORD_COUNT) -> None:
        self.max_word_count = max_word_count
        self._workflow: Optional[WorkflowEngine] = None

    def _build_workflow(self) -> WorkflowEngine:
        if self._workflow is not None:
            return self._workflow

        with WorkflowEngine(
            name="table_processor_workflow",
            description="Process one markdown table into semantic chunks",
            langfuse="beegen-portal",
            inputs=INPUT,
        ) as workflow:
            classify_simple = CodeNode(
                name="classify_simple_table",
                code_fn=_is_simple_table_node,
                inputs={"table_str": {INPUT: "table_markdown"}},
                return_keys=["is_simple: bool"],
            )

            process_simple = CodeNode(
                name="process_simple_table",
                code_fn=_process_simple_table_node,
                inputs={"table_str": {INPUT: "table_markdown"}},
                return_keys=["chunks: List[str]"],
            )

            start_simple = CodeNode(
                name="start_simple_flow",
                code_fn=lambda: {},
                inputs={},
                return_keys=[],
            )

            prepare_simple_summary = CodeNode(
                name="prepare_simple_summary_prompt",
                code_fn=_prepare_simple_summary_prompt_node,
                inputs={
                    "table_markdown": INPUT["table_markdown"],
                    "parent_heading": INPUT["parent_heading"],
                    "context_before": INPUT["context_before"],
                    "context_after": INPUT["context_after"],
                },
                return_keys=["summary_messages: List[Dict[str, Any]]"],
            )

            simple_summary_llm = LLMNode(
                name="simple_summary_llm",
                resource_key="qwen-instruct-chat",
                inputs={
                    "messages": {prepare_simple_summary: "summary_messages"},
                    "reasoning_effort": "none",
                    "max_tokens": 2000,
                },
            )

            parse_simple_summary = CodeNode(
                name="parse_simple_summary_response",
                code_fn=_parse_summary_response_node,
                inputs={"summary_content": {simple_summary_llm: "content"}},
                return_keys=["parsed_table_summary: str"],
            )

            finalize_simple = CodeNode(
                name="finalize_simple_result",
                code_fn=_finalize_batch_chunks_node,
                inputs={
                    "accumulated_chunks": {process_simple: "chunks"},
                    "in_table_summary": {parse_simple_summary: "parsed_table_summary"},
                },
                return_keys=["chunks: List[str]", "out_table_summary: str"],
                outputs={"chunks": OUTPUT, "out_table_summary": OUTPUT},
            )

            init_state = CodeNode(
                name="init_batch_state",
                code_fn=_init_batch_state_node,
                inputs={
                    "table_markdown": INPUT["table_markdown"],
                    "parent_heading": INPUT["parent_heading"],
                    "in_context_before": INPUT["context_before"],
                    "in_context_after": INPUT["context_after"],
                },
                return_keys=[
                    "iteration_count: int",
                    "row_batches: List[str]",
                    "parsed_rows: List[Dict]",
                    "batch_count: int",
                    "context_summary: str",
                    "accumulated_chunks: List[str]",
                    "last_resolved_cells: List[str]",
                    "table_summary: str",
                    "context_before: str",
                    "context_after: str",
                ],
            )

            with WhileLoopNode(
                name="batch_loop",
                description="Process complex table batches sequentially via LLM",
                inputs={
                    "iteration_count": {init_state: "iteration_count"},
                    "row_batches": {init_state: "row_batches"},
                    "parsed_rows": {init_state: "parsed_rows"},
                    "batch_count": {init_state: "batch_count"},
                    "context_summary": {init_state: "context_summary"},
                    "accumulated_chunks": {init_state: "accumulated_chunks"},
                    "last_resolved_cells": {init_state: "last_resolved_cells"},
                    "table_summary": {init_state: "table_summary"},
                    "context_before": {init_state: "context_before"},
                    "context_after": {init_state: "context_after"},
                },
            ) as batch_loop:

                check_continue = CodeNode(
                    name="check_continue",
                    code_fn=_check_batch_continue_node,
                    inputs={
                        "iteration_count": INPUT["iteration_count"],
                        "batch_count": INPUT["batch_count"],
                    },
                    return_keys=["continue_loop: bool"],
                )

                prepare_prompt = CodeNode(
                    name="prepare_batch_prompt",
                    code_fn=_prepare_batch_prompt_node,
                    inputs={
                        "iteration_count": INPUT["iteration_count"],
                        "row_batches": INPUT["row_batches"],
                        "parsed_rows": INPUT["parsed_rows"],
                        "context_summary": INPUT["context_summary"],
                        "last_resolved_cells": INPUT["last_resolved_cells"],
                    },
                    return_keys=["messages: List[Dict[str, Any]]"],
                )

                batch_llm = LLMNode(
                    name="batch_llm",
                    resource_key="qwen-instruct-chat",
                    inputs={
                        "messages": {prepare_prompt: "messages"},
                        "reasoning_effort": "none",
                        "max_tokens": 16000,
                    },
                )

                parse_response = CodeNode(
                    name="parse_batch_response",
                    code_fn=_parse_batch_response_node,
                    inputs={"content": {batch_llm: "content"}},
                    return_keys=[
                        "extracted_chunks: List[str]",
                        "updated_context: str",
                        "embedded_columns: List[str]",
                    ],
                )

                # --- Parallel summary LLM branch ---
                prepare_summary = CodeNode(
                    name="prepare_summary_prompt",
                    code_fn=_prepare_summary_prompt_node,
                    inputs={
                        "iteration_count": INPUT["iteration_count"],
                        "row_batches": INPUT["row_batches"],
                        "context_summary": INPUT["context_summary"],
                        "table_summary": INPUT["table_summary"],
                        "context_before": INPUT["context_before"],
                        "context_after": INPUT["context_after"],
                    },
                    return_keys=["summary_messages: List[Dict[str, Any]]"],
                )

                summary_llm = LLMNode(
                    name="summary_llm",
                    resource_key="qwen-instruct-chat",
                    inputs={
                        "messages": {prepare_summary: "summary_messages"},
                        "reasoning_effort": "none",
                        "max_tokens": 2000,
                    },
                )

                parse_summary = CodeNode(
                    name="parse_summary_response",
                    code_fn=_parse_summary_response_node,
                    inputs={"summary_content": {summary_llm: "content"}},
                    return_keys=["parsed_table_summary: str"],
                )

                update_state = CodeNode(
                    name="update_batch_state",
                    code_fn=_update_batch_state_node,
                    inputs={
                        "in_iteration_count": INPUT["iteration_count"],
                        "in_accumulated_chunks": INPUT["accumulated_chunks"],
                        "in_context_summary": INPUT["context_summary"],
                        "in_table_summary": INPUT["table_summary"],
                        "in_parsed_rows": INPUT["parsed_rows"],
                        "extracted_chunks": {parse_response: "extracted_chunks"},
                        "updated_context": {parse_response: "updated_context"},
                        "embedded_columns": {parse_response: "embedded_columns"},
                        "parsed_table_summary": {parse_summary: "parsed_table_summary"},
                        "in_context_before": INPUT["context_before"],
                        "in_context_after": INPUT["context_after"],
                    },
                    return_keys=[
                        "iteration_count: int",
                        "accumulated_chunks: List[str]",
                        "context_summary: str",
                        "table_summary: str",
                        "last_resolved_cells: List[str]",
                        "context_before: str",
                        "context_after: str",
                    ],
                    outputs={
                        "iteration_count": INPUT,
                        "accumulated_chunks": INPUT,
                        "context_summary": INPUT,
                        "table_summary": INPUT,
                        "last_resolved_cells": INPUT,
                        "context_before": INPUT,
                        "context_after": INPUT,
                    },
                )

                prepare_loop_output = CodeNode(
                    name="prepare_loop_output",
                    code_fn=_finalize_batch_chunks_node,
                    inputs={
                        "accumulated_chunks": INPUT["accumulated_chunks"],
                        "in_table_summary": INPUT["table_summary"],
                    },
                    return_keys=["chunks: List[str]", "out_table_summary: str"],
                    outputs=OUTPUT,
                )

                continue_branch = BranchNode(
                    name="continue_branch",
                    cases={"continue_loop == True": prepare_prompt},
                    default=prepare_loop_output,
                    inputs={"continue_loop": {check_continue: "continue_loop"}},
                )

                START >> check_continue >> continue_branch >> [prepare_prompt, prepare_loop_output]
                # Parallel fanout: prepare_prompt feeds both batch_llm and summary branch
                prepare_prompt >> [batch_llm, prepare_summary]
                batch_llm >> parse_response >> update_state >> CONTINUE
                prepare_summary >> summary_llm >> parse_summary >> update_state
                prepare_loop_output >> END

            process_complex = CodeNode(
                name="process_complex_result",
                code_fn=_finalize_batch_chunks_node,
                inputs={
                    "accumulated_chunks": {batch_loop: "chunks"},
                    "in_table_summary": {batch_loop: "out_table_summary"},
                },
                return_keys=["chunks: List[str]", "out_table_summary: str"],
                outputs={"chunks": OUTPUT, "out_table_summary": OUTPUT},
            )

            main_branch = BranchNode(
                name="main_branch",
                cases={"is_simple == True": start_simple},
                default=init_state,
                inputs={"is_simple": {classify_simple: "is_simple"}},
            )

            START >> classify_simple >> main_branch >> [start_simple, init_state]
            start_simple >> [process_simple, prepare_simple_summary]
            prepare_simple_summary >> simple_summary_llm >> parse_simple_summary >> finalize_simple
            process_simple >> finalize_simple >> END
            init_state >> batch_loop >> process_complex >> END

        workflow.compile()
        self._workflow = workflow
        return workflow

    async def run_with_summary(
        self,
        table_markdown: str,
        parent_heading: Optional[list[str]] = None,
        context_before: str = "",
        context_after: str = "",
    ) -> tuple[list[str], str]:
        """Run table processor and return (chunks, table_summary)."""
        if self._workflow is None:
            self._workflow = self._build_workflow()

        table_markdown_text = _as_table_text(table_markdown)
        result = await self._workflow.run(
            inputs={
                "table_markdown": table_markdown_text,
                "parent_heading": parent_heading or [],
                "context_before": context_before,
                "context_after": context_after,
            }
        )
        if not isinstance(result, dict):
            return [], ""
        chunks = result.get("chunks", [])
        table_summary = result.get("out_table_summary", "")
        return chunks, table_summary

    async def run(
        self,
        table_markdown: str,
        parent_heading: Optional[list[str]] = None,
        context_before: str = "",
        context_after: str = "",
    ) -> list[str]:
        chunks, _ = await self.run_with_summary(table_markdown, parent_heading, context_before, context_after)
        return chunks


async def process_table(
    table_markdown: str,
    max_word_count: int = MAX_WORD_COUNT,
) -> list[str]:
    return await TableProcessor(max_word_count=max_word_count).run(table_markdown)


async def chunk_markdown_tables(
    markdown_text: str,
    max_word_count: int = MAX_WORD_COUNT,
) -> list[str]:
    all_tables = detect_tables(markdown_text or "")
    if not all_tables:
        return []

    processor = TableProcessor(max_word_count=max_word_count)
    chunks: list[str] = []
    # Since we removed find_root_tables and process each detected table independently:
    for table in all_tables:
        table_chunks = await processor.run(
            table_markdown=table,
            parent_heading=[],
        )
        chunks.extend(table_chunks)
    return chunks


async def main() -> None:
    from pathlib import Path

    table_dir = Path(__file__).resolve().parent
    table_file = table_dir / "detected_table_1.md"
    if not table_file.exists():
        print(f"Missing file: {table_file}")
        return

    table_markdown = table_file.read_text(encoding="utf-8")
    processor = TableProcessor()
    chunks, table_summary = await processor.run_with_summary(table_markdown)

    print(f"=== TABLE SUMMARY ===\n{table_summary}\n")
    for idx, chunk in enumerate(chunks, start=1):
        print(f"--- Chunk {idx} ---\n{chunk}\n")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())

