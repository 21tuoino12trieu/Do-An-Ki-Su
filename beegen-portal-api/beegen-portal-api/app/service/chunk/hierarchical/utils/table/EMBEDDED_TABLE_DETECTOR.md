# Embedded Table Detector — Algorithm Design

## Bối cảnh & Vấn đề

### Embedded table là gì?

Embedded table **không phải** nested table theo nghĩa bảng con nằm trong cell của bảng cha (như markdown-in-markdown). Đây là một **pattern phổ biến trong bảng converted từ Word/Excel**: một section bên trong bảng lớn có cấu trúc giống một bảng độc lập (có header rows riêng, data rows riêng), nhưng vẫn nằm trong cùng một markdown table.

### Ví dụ minh họa (bảng Yody)

```
| Danh sách cửa hàng & SĐT | Thông tin cửa hàng Yody.xlsx | <merged> ... |
| <merged> Danh sách cửa hàng & SĐT | Tên cửa hàng | Tên viết tắt | SĐT | Full địa chỉ | TerminalID |   ← EMBEDDED HEADER
| <merged> Danh sách cửa hàng & SĐT | Yody Admin   |              | 397 | 90 Đ. Nguyễn Tuân... |  |     ← EMBEDDED DATA
| <merged> Danh sách cửa hàng & SĐT | Yody Vĩnh Long | YODYTVL   | 834 | 55A Phạm Thái Bường... | YODY1 |
| Mục tiếp theo...           | ...                           |              |                           ← kết thúc embedded
```

Cột đầu (`Danh sách cửa hàng & SĐT`) là label của section — được vertically merge qua tất cả rows của section đó. Các cột còn lại của một row nào đó trong section lại trở thành tên cột của "bảng con" này.

---

## Signals phân biệt các loại row

```
Ký hiệu trong bảng gốc:
  fm  = cell đầu KHÔNG phải <merged>  (first cell is non-merged)
  m   = cell đầu là <merged>          (first cell is merged)
  all = TẤT CẢ cells đều là <merged>  (fully merged row)
```

| Pattern row                       | Ý nghĩa hiện tại             | Xử lý hiện tại           |
|-----------------------------------|------------------------------|--------------------------|
| `all`                             | Heading (fully merged)       | → update heading_tree    |
| `fm` + không all                  | Thường là data row bình thường | → LLM classify           |
| `m` + không all + **LLM header?** | **(MỚI) Embedded col header**| → update embedded_cols   |
| `m` + không all + không header    | Embedded data row            | → chunk với embedded_cols|
| `fm` bất kỳ                       | Kết thúc embedded section    | → reset embedded state   |

---

## Algorithm: Detect & Process Embedded Table

### State mới cần thêm vào loop

```python
# Thêm vào state của process_table() loop
in_embedded: bool = False                # đang trong embedded table?
embedded_column_names: list[str] = []    # column names của embedded table
parent_column_names: list[str] = []      # backup column_names bảng cha
```

### Decision tree tổng thể (mở rộng từ flow hiện tại)

```
Với mỗi row trong loop:
  │
  ├── separator row?
  │     └── skip
  │
  ├── placeholder row? (nested table)
  │     └── process nested (như cũ)
  │
  ├── fully merged row?
  │     ├── nếu in_embedded → EXIT embedded (xem bên dưới)
  │     └── update heading_tree (như cũ)
  │
  ├── cell đầu KHÔNG phải <merged>?   ← signal kết thúc embedded
  │     ├── nếu in_embedded → EXIT embedded
  │     └── LLM: heading? / col_header? / data? (flow bình thường)
  │
  └── cell đầu LÀ <merged> (và không fully merged):
        ├── nếu CHƯA in_embedded:
        │     └── LLM: is_embedded_col_header?
        │           ├── True  → ENTER embedded, lưu embedded_column_names
        │           └── False → format chunk bình thường (data row)
        │
        └── nếu ĐÃ in_embedded:
              └── format chunk với embedded_column_names
```

---

## Chi tiết: Signal ENTER embedded table

**Điều kiện cần** để gọi LLM check embedded header:
1. `cell[0]` là `<merged>` (tức vertical merge từ section label ở trên)
2. Không phải fully merged row
3. `in_embedded == False` (chưa trong embedded)

**Prompt LLM** (`_llm_is_embedded_col_header`):

```
Context:
  Row trước đó (resolved): <section_label_row>
  Row hiện tại (raw): | <merged> label | col1 | col2 | col3 | ...

Câu hỏi: Row hiện tại có phải là ROW ĐẦU CỦA MỘT BẢNG CON không?
Tức là, các cell từ index 1 trở đi là TÊN CỘT của một embedded table?

Dấu hiệu nhận biết:
- Các cell (từ index 1) là tên trường/tiêu đề cột (vd: "Tên cửa hàng", "SĐT", "Địa chỉ")
- Không phải giá trị dữ liệu cụ thể (vd: số tiền, ngày tháng, mô tả dài)
- Các row phía dưới sẽ có dữ liệu tương ứng với các tên cột này

Trả lời JSON: {"is_embedded_col_header": true/false}
```

**Input cho LLM**:
- Pass **resolved row** — không phải raw row.
  - Lý do: trong loop của `process_table()`, `resolve_row()` được gọi **trước** khi bước detect embedded. Tại thời điểm LLM nhận input, `resolved[0]` đã là giá trị thực (vd: "Danh sách cửa hàng & SĐT"), `resolved[1:]` là các cell values không còn `<merged>` tag nào. LLM thấy trực tiếp nội dung, không cần đoán.
- Pass raw row của row ngay bên dưới (nếu có) để LLM verify "row dưới là data của embedded này"

---

## Chi tiết: Signal EXIT embedded table

**Trigger EXIT** khi:
- Gặp row mà `cell[0]` **KHÔNG phải** `<merged>` (new section/label bắt đầu)
- HOẶC gặp fully merged row (heading mới bắt đầu)
- HOẶC hết rows

**Hành động khi EXIT**:
```python
in_embedded = False
embedded_column_names = []
# KHÔNG restore parent_column_names → column_names tiếp tục là của bảng cha
# (các data row sau embedded sẽ map theo column_names bảng cha)
```

> **Design decision**: Không restore `parent_column_names` vì sau section embedded,
> các data row tiếp theo vẫn thuộc cột của bảng cha, không phải embedded.
> `column_names` của bảng cha vốn đã được set từ trước khi gặp embedded.

---

## Chi tiết: Format chunk khi TRONG embedded table

```python
# Khi in_embedded == True và gặp data row:
resolved = resolve_row(raw_cells, prev_resolved_row)

# Lấy context label từ cell[0] (đã resolved = section label)
section_label = resolved[0]  # vd: "Danh sách cửa hàng & SĐT"

# Format chunk với:
#   heading_tree (bảng cha) + section_label (nếu muốn thêm context)
#   embedded_column_names
#   resolved[1:]  ← bỏ cell[0] vì đó là section label, không phải data
chunk_heading = heading_tree + [section_label]  # optional
lines = chunk_heading[:]
for i, col in enumerate(embedded_column_names):
    data_idx = i + 1  # shift 1 vì cell[0] là label
    if data_idx < len(resolved) and resolved[data_idx].strip():
        lines.append(f"{col}: {resolved[data_idx]}")

chunk = "\n".join(lines)
```

---

## Pseudo-code tích hợp vào `process_table()`

```python
def process_table(table_str, parent_heading_tree, all_tables_in_doc, llm_node):
    # ... setup như cũ ...

    # State cũ
    heading_tree = copy(parent_heading_tree)
    column_names = []
    prev_resolved_row = None

    # State mới cho embedded
    in_embedded = False
    embedded_column_names = []

    for row_idx, raw_row in enumerate(raw_rows):

        # 4a: Skip separator
        if is_separator_row(raw_row):
            continue

        # 4b: Nested table placeholder (không đổi)
        placeholder_uid = _row_contains_placeholder(raw_row)
        if placeholder_uid and placeholder_uid in placeholder_map:
            # ... xử lý như cũ ...
            continue

        raw_cells = parse_raw_row(raw_row)
        if not raw_cells:
            continue

        resolved = resolve_row(raw_cells, prev_resolved_row)

        # 4c: Fully merged → heading (không đổi) + EXIT embedded nếu đang trong
        if is_fully_merged_row(raw_cells):
            if in_embedded:
                in_embedded = False
                embedded_column_names = []
            heading_content = get_cell_content(raw_cells[0])
            if heading_content:
                heading_tree = _update_heading_tree(heading_tree, heading_content)
            prev_resolved_row = resolved
            continue

        # 4d: Cell đầu KHÔNG phải <merged> → EXIT embedded nếu cần
        if not is_cell_merged(raw_cells[0]):
            if in_embedded:
                in_embedded = False
                embedded_column_names = []
            # Tiếp tục flow bình thường: LLM heading / col_header / data
            ...
            continue

        # 4e: Cell đầu LÀ <merged> VÀ không fully merged
        # → đây là row thuộc một section (có label ở trên)
        if not in_embedded:
            # Kiểm tra có phải embedded col header không
            row_below = raw_rows[row_idx + 1] if row_idx < len(raw_rows) - 1 else ""
            if _llm_is_embedded_col_header(resolved, row_below, llm_node):
                in_embedded = True
                # embedded_column_names = cells từ index 1 trở đi (đã resolved)
                embedded_column_names = [c for c in resolved[1:] if c.strip()]
                prev_resolved_row = resolved
                continue
            else:
                # Không phải embedded header → data row bình thường
                chunk = _format_chunk(heading_tree, column_names, resolved)
                if chunk.strip():
                    chunks.append(chunk)
        else:
            # Đang trong embedded → format với embedded_column_names
            chunk = _format_embedded_chunk(
                heading_tree, resolved[0], embedded_column_names, resolved[1:]
            )
            if chunk.strip():
                chunks.append(chunk)

        prev_resolved_row = resolved

    return chunks
```

---

## Helper functions mới cần implement

### `_llm_is_embedded_col_header`

```python
def _llm_is_embedded_col_header(
    resolved_row: list[str],   # row hiện tại đã resolve (dùng để LLM thấy label + values)
    row_below_raw: str,        # raw row ngay bên dưới (context)
    llm_node: Any,
) -> bool:
    """
    Hỏi LLM xem row hiện tại có phải là column header của embedded table không.
    
    resolved_row[0] = section label (vd: "Danh sách cửa hàng & SĐT")
    resolved_row[1:] = các cell cần classify (phải là tên cột hay dữ liệu?)
    
    Pass resolved row (không phải raw) để LLM thấy đầy đủ context,
    không bị confuse bởi "<merged>" tags.
    """
    candidates = resolved_row[1:]
    candidates_str = " | ".join(candidates)
    
    prompt = f"""Bạn đang phân tích một bảng markdown phức tạp.

Section label: {resolved_row[0]}
Các cells cần phân tích: {candidates_str}
Row phía dưới (context): {row_below_raw if row_below_raw else "(không có)"}

Câu hỏi: Các cells trên có phải là TÊN CỘT của một bảng con (embedded table) không?

Dấu hiệu là TRUE:
- Các cells là tên trường/tiêu đề (vd: "Tên cửa hàng", "SĐT", "Full địa chỉ", "TerminalID")
- Row phía dưới sẽ chứa dữ liệu tương ứng với các tên cột đó
- Không phải là dữ liệu, mô tả dài, hay nội dung quy trình

Dấu hiệu là FALSE:
- Các cells là nội dung mô tả, quy trình (vd: "Xin lại thông tin...", "Nếu không tồn tại FT...")
- Là dữ liệu cụ thể (số tiền, ngày tháng, giá trị)

Trả lời JSON (chỉ JSON, không giải thích):
{{"is_embedded_col_header": true}} hoặc {{"is_embedded_col_header": false}}"""

    response = llm_node.call(prompt)
    # parse JSON response...
    return parsed.get("is_embedded_col_header", False)
```

### `_format_embedded_chunk`

```python
def _format_embedded_chunk(
    heading_tree: list[str],
    section_label: str,       # resolved[0] của embedded row
    embedded_cols: list[str], # tên các cột của embedded table
    data_cells: list[str],    # resolved[1:] của embedded row
) -> str:
    """
    Format một data row của embedded table thành chunk.
    
    Output format:
        {heading_1}
        {heading_2}
        ...
        {section_label}   ← label của section chứa embedded table
        {col_1}: {val_1}
        {col_2}: {val_2}
        ...
    """
    lines = list(heading_tree)
    if section_label.strip():
        lines.append(section_label)
    
    for i, col in enumerate(embedded_cols):
        if i < len(data_cells) and data_cells[i].strip():
            lines.append(f"{col}: {data_cells[i]}")
    
    return "\n".join(lines)
```

---

## Tích hợp vào Beeflow Workflow (`table_processor.py`)

Hiện tại `table_processor.py` implement bằng Beeflow nodes. Cần thêm:

### 1. State mới trong `_prepare_complex_state_node`

```python
def _prepare_complex_state_node(modified_table_str, parent_heading):
    return {
        # ... state cũ ...
        "in_embedded": False,
        "embedded_column_names": [],
    }
```

### 2. Node mới: `_check_first_cell_merged_node`

```python
def _check_first_cell_merged_node(raw_cells: list[str]) -> dict:
    """Kiểm tra cell đầu tiên có phải <merged> không."""
    if not raw_cells:
        return {"first_cell_is_merged": False}
    return {"first_cell_is_merged": is_cell_merged(raw_cells[0])}
```

### 3. Node mới: `_build_embedded_col_header_prompt_node`

```python
def _build_embedded_col_header_prompt_node(
    resolved: list[str],
    raw_rows: list[str],
    row_idx: int,
) -> dict:
    row_below = raw_rows[row_idx + 1] if row_idx < len(raw_rows) - 1 else ""
    # build prompt như mô tả ở trên
    return {"messages": [...]}
```

### 4. Node mới: `_parse_embedded_col_header_response_node`

```python
def _parse_embedded_col_header_response_node(content: str) -> dict:
    parsed = _loads_json_object(content)
    return {"is_embedded_col_header": bool(parsed.get("is_embedded_col_header", False))}
```

### 5. Node mới: `_update_enter_embedded_node`

```python
def _update_enter_embedded_node(
    in_row_idx, in_heading_tree, in_column_names, in_chunks,
    resolved, in_prev_resolved_row,
) -> dict:
    # embedded_column_names = resolved[1:] (bỏ cell[0] là section label)
    embedded_cols = [c for c in (resolved or [])[1:] if c.strip()]
    return {
        "row_idx": in_row_idx + 1,
        "heading_tree": list(in_heading_tree or []),
        "column_names": list(in_column_names or []),
        "embedded_column_names": embedded_cols,
        "in_embedded": True,
        "prev_resolved_row": list(resolved or []),
        "chunks": list(in_chunks or []),
    }
```

### 6. Node mới: `_format_embedded_chunk_node`

```python
def _format_embedded_chunk_node(
    heading_tree, resolved, embedded_column_names,
) -> dict:
    section_label = resolved[0] if resolved else ""
    data_cells = resolved[1:] if len(resolved) > 1 else []
    # format theo _format_embedded_chunk
    return {"chunk": ...}
```

### 7. Node mới: `_update_after_embedded_data_node`

Tương tự `_update_after_data_row_node` nhưng giữ nguyên `in_embedded=True` và `embedded_column_names`.

### 8. Node mới: `_exit_embedded_node`

```python
def _exit_embedded_node(
    in_row_idx, in_heading_tree, in_column_names, in_chunks,
    resolved, in_prev_resolved_row,
) -> dict:
    return {
        "row_idx": in_row_idx,   # KHÔNG tăng, để tiếp tục process row này bình thường
        "in_embedded": False,
        "embedded_column_names": [],
        # các state khác giữ nguyên
        ...
    }
```

> **Lưu ý**: Khi EXIT embedded, row trigger exit vẫn cần được process bình thường (heading / col_header / data). Do đó `row_idx` không tăng, loop tiếp tục với row hiện tại nhưng với `in_embedded=False`.

---

## Branch flow mới trong WhileLoopNode

```
prepare_row
  → separator_check → [skip / resolve_current_row]
  
resolve_current_row
  → placeholder_detect → [process_child / check_first_cell_merged]
  
check_first_cell_merged:
  → first_cell_is_merged == False:
      → exit_embedded_if_needed → [heading / col_header / data flow cũ]
  → first_cell_is_merged == True:
      → fully_merged_check → [update_after_fully_merged + exit_embedded / check_embedded_or_data]
      
check_embedded_or_data:
  → in_embedded == False:
      → embedded_col_header_prompt → LLM → parse
           → is_embedded_col_header == True:  update_enter_embedded
           → is_embedded_col_header == False: format_chunk (data bình thường)
  → in_embedded == True:
      → format_embedded_chunk → update_after_embedded_data
```

---

## Edge cases cần xử lý

### 1. Embedded table xuất hiện ngay sau header, chưa có column_names bảng cha

```
| Col A | Col B | Col C |
| :--- | :--- | :--- |
| Section 1 | ... | ... |
| <merged> Section 1 | Sub Col 1 | Sub Col 2 | ← embedded header ngay sau row đầu tiên
```

Xử lý: `column_names = []` → không ảnh hưởng, lúc format embedded chunk chỉ dùng `embedded_column_names`.

### 2. Multiple embedded tables trong cùng một bảng cha

```
| Section A | ... |
| <merged> Section A | EmbCol1 | EmbCol2 |   ← embedded 1 header
| <merged> Section A | val1    | val2    |   ← embedded 1 data
| Section B | ... |                          ← EXIT embedded 1
| <merged> Section B | EmbCol3 | EmbCol4 |  ← embedded 2 header
| <merged> Section B | val3    | val4    |  ← embedded 2 data
```

Xử lý: Khi gặp `Section B` (first cell không phải `<merged>`) → EXIT embedded 1. Process `Section B` bình thường (data row). Sau đó gặp embedded header của Section B → ENTER embedded 2.

### 3. Embedded table không có data rows (chỉ có header)

```
| Section | File.xlsx |
| <merged> Section | Col1 | Col2 |   ← embedded header nhưng không có data
| Next Section | ... |               ← EXIT ngay sau header
```

Xử lý: `in_embedded = True` nhưng không có chunk nào được tạo. Khi gặp `Next Section` → EXIT. Không gây lỗi.

### 4. Embedded data row với empty cells

```
| <merged> Danh sách | Tên cửa hàng | Tên viết tắt | SĐT |
| <merged> Danh sách | Yody Admin   |              | 397 |  ← Tên viết tắt rỗng
```

Xử lý: Bỏ qua cặp `col: value` nếu value rỗng (giống xử lý hiện tại của `_format_chunk`).

### 5. Row toàn empty trong embedded table

```
| <merged> Danh sách |   |   |   |   |   |   ← row trống
```

Xử lý: `data_cells` sau khi resolve sẽ toàn empty → chunk rỗng → không append.

---

## Kết luận: Module mới `embedded_table_detector.py`

Tách logic ra module riêng `embedded_table_detector.py` với public API:

```python
def is_embedded_col_header_row(
    raw_cells: list[str],
    resolved: list[str],
    row_below_raw: str,
    llm_node: Any,
) -> bool:
    """
    Kiểm tra row có phải là column header của embedded table không.
    
    Preconditions (caller phải check trước):
    - raw_cells[0] là <merged>
    - không phải fully merged row
    - chưa in_embedded
    
    Returns True nếu LLM confirm đây là embedded col header.
    """
    ...

def format_embedded_chunk(
    heading_tree: list[str],
    section_label: str,
    embedded_cols: list[str],
    data_cells: list[str],
) -> str:
    """Format một data row của embedded table thành chunk string."""
    ...
```

Module này KHÔNG gọi `table_detector.detect_tables()`. Logic detect embedded hoàn toàn dựa trên:
1. Cell structure (raw_cells patterns)
2. LLM classification
3. State machine trong loop (in_embedded flag)
