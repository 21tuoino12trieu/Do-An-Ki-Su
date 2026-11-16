# Excel Renderer Flow

## Tổng quan
ExcelRenderer xử lý file Excel theo 2 nhánh chính: (1) render sheet thành ảnh, (2) trích xuất zone và dựng lại nội dung theo zone. Kết quả được ghép vào Page theo từng sheet.

## Workflow DAG (thứ tự node)
`START -> [render_node, zone_payloads_node] -> unwrap_sheet_payloads -> vlm_page_loop -> finalize_node -> END`

## Diễn giải luồng (bằng lời)
1. Render toàn bộ sheet thành ảnh để có hình ảnh nền cho mỗi page.
2. Trích xuất zone payload (tọa độ, grid text) cho từng sheet.
3. Chuẩn hóa dữ liệu sheet để đưa vào vòng lặp xử lý theo sheet.
4. Với mỗi sheet:
   - Chuẩn hóa danh sách zone.
   - Với mỗi zone: parse grid text thành nội dung markdown.
   - Gom zone của sheet thành content của page.
5. Ghép content vào `final_pages` theo đúng page_number và metadata sheet.

### Node chi tiết
1. **render_node**
   - **Input:** `file_path`
   - **Output:** `pages_images`
   - **Mục đích:** Render từng sheet thành ảnh (base64) để lưu vào Page.

2. **zone_payloads_node**
   - **Input:** `file_path`
   - **Output:** `sheet_payloads`
   - **Mục đích:** Trích xuất zone payload theo sheet (tọa độ, grid text).

3. **unwrap_sheet_payloads**
   - **Input:** `payload` (từ `sheet_payloads`)
   - **Output:** `batch_data`
   - **Mục đích:** Chuẩn hóa dữ liệu cho vòng lặp theo sheet (mỗi phần tử là 1 sheet).

4. **vlm_page_loop** (ForLoop trên sheet)
   - **Input:** `batch_data`
   - **Mục đích:** Xử lý từng sheet.
   - **Bên trong:**
     - **zone_messages_node**
       - **Input:** `sheet_name`, `zones`
       - **Output:** `zone_payloads`
       - **Mục đích:** Chuẩn hóa dữ liệu zone cho vòng lặp zone.
     - **zone_loop** (ForLoop trên zone)
       - **zone_collect_node**
         - **Input:** `zone_grid_text`, `zone_sheet_name`, `zone`
         - **Output:** `zone_result`
         - **Mục đích:** Parse grid text thành nội dung markdown của zone.
     - **sheet_collect_node**
       - **Input:** `sheet_name`, `file_path`, `page_num`, `zones`
       - **Output:** `page_result`
       - **Mục đích:** Gom các zone_result thành content của 1 sheet.

5. **finalize_node**
   - **Input:** `vlm_results`, `pages_images`
   - **Output:** `final_pages`, `reconstructed_content`
   - **Mục đích:** Ghép content zone vào từng Page (sheet), kèm ảnh render.

## Logic tái dựng nội dung
- **Zone parsing**: `_collect_zone_result` đọc `grid_text` theo format `[R{row}C{col}]` → map ô (`cell_map`).
- **Dò dòng dày (dense row)**: nếu một dòng có ≥2 ô có dữ liệu → coi là vùng bảng.
- **Nếu không có dense row**: trả về text list theo thứ tự ô.
- **Nếu có bảng**:
  - Xác định dòng header và vùng bảng.
  - Sinh bảng Markdown `| ... |` và thay `\n` trong ô bằng `<br>`.
  - Text trước/sau bảng được giữ nếu là dòng đơn.
- **Sheet content**: gom các zone theo thứ tự (min_row, min_col).
- **Final**: `final_pages` chứa `content` là list các chunk theo zone của sheet.

## Đầu ra cuối
- `final_pages`: list Page dict gồm `page_number`, `image_data`, `metadata`, `content` (list zone).
- `reconstructed_content`: hiện để trống (chuỗi rỗng).