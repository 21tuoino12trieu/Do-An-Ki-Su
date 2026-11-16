# HTML Renderer Flow

## Tổng quan
HtmlRenderer thực hiện 4 nhóm việc: (1) đọc và chuẩn hóa HTML local, (2) parse HTML thành block tree, (3) lọc ảnh inline base64 và chạy image gate qua VLM, (4) render block tree thành markdown cuối.

## Workflow DAG (thứ tự node)
`START -> prepare_html_source -> parse_html_to_structure -> resolve_html_images -> html_image_gate_loop -> finalize_html_images -> render_blocks_to_markdown -> END`

## Diễn giải luồng (bằng lời)
1. Đọc HTML nguồn và detect encoding.
2. Parse HTML thành block tree trung gian.
3. Lọc các ảnh inline base64 trong block tree và chuẩn bị batch cho image gate.
4. Chạy image gate cho từng ảnh để quyết định có cần bóc tách text từ ảnh hay không.
5. Gắn kết quả gate trực tiếp trở lại các image block.
6. Render block tree thành `reconstructed_content`.

### Node chi tiết
1. **prepare_html_source**
   - **Input:** `file_path`
   - **Output:** `normalized_raw_content`
   - **Mục đích:** Chuẩn hóa HTML đầu vào trước khi parse.

2. **parse_html_to_structure**
   - **Input:** `normalized_raw_content`
   - **Output:** `html_payload`
   - **Mục đích:** Parse HTML thành payload tối giản: `{"blocks": [...]}`.

3. **resolve_html_images**
   - **Input:** `parsed_html_payload`
   - **Output:** `html_payload`, `image_batch_data`
   - **Mục đích:** Chỉ nhận `src` dạng `data:image/...;base64,...` và tạo batch cho image gate.

4. **html_image_gate_loop** (ForLoop)
   - **Input:** `batch_data`
   - **Mục đích:** Chạy VLM trên từng ảnh đã resolve.
   - **Bên trong:**
     - **html_image_gate_prompt**
       - **Input:** `image_id`, `image_base64`, `image_format`
       - **Output:** `messages`, `payload`
       - **Mục đích:** Decode base64 và build message cho image gate.
     - **html_image_gate_llm**
       - **Input:** `messages`
       - **Output:** `content`
       - **Mục đích:** Gọi model `gemini-3.1-flash-lite-chat` với tối đa 15 ảnh xử lý đồng thời.
     - **html_image_gate_collect**
       - **Input:** `content`, `payload`
       - **Output:** `gate_result`
       - **Mục đích:** Parse response image gate thành kết quả theo `image_id`.

5. **finalize_html_images**
   - **Input:** `resolved_html_payload`, `gate_results`
   - **Output:** `html_payload`
   - **Mục đích:** Gắn nội dung VLM vào image block tương ứng; ảnh Base64 không có nội dung bóc tách được ghi ra file tạm và cập nhật `src`.

6. **render_blocks_to_markdown**
   - **Input:** `finalized_html_payload`
   - **Output:** `reconstructed_content`
   - **Mục đích:** Render block tree cuối cùng thành markdown output.

## Logic tái dựng nội dung
- **HTML normalization**: `prepare_html_source` đọc `file_path`, detect encoding và chuẩn hóa ký tự xuống dòng.
- **Block parsing**: `parse_html_to_structure` chuyển DOM thành block tree gồm heading, paragraph, list, table, link, image, code, quote. Mỗi table cell giữ danh sách block con để ảnh lồng trong `span` hoặc phần tử inline không bị mất.
- **Nested tables**: nội dung bảng con không bị trộn vào text cell cha; bảng con được render riêng với breadcrumb ngữ cảnh từ các cấp cha. Heading tăng từ `###` đến tối đa `######`, fallback về `Bảng chi tiết N` khi thiếu ngữ cảnh.
- **Merged cells**: nội dung `rowspan` chỉ nằm ở cell gốc; các hàng tiếp nối nhận cell rỗng. `colspan` giữ nội dung ở cột đầu và tạo các cell trống còn lại. Ảnh và bảng lồng không bị nhân bản.
- **Image blocks**: parser tách mọi thẻ `img` thành block riêng; `resolve_html_images` chỉ nhận ảnh inline base64 và đánh số tạm thời cho image gate.
- **Image gate**: `prepare_image_gate_prompt` decode `image_base64` và build message multimodal; ảnh file local không được đưa vào image gate.
- **Image merge**: `finalize_html_images` map `image_id -> extracted_text`. Ảnh có nội dung được thay bằng text đã trích xuất; ảnh không có nội dung được ghi ra file tạm và giữ lại dưới dạng thẻ `<img>` trong Markdown.
- **Markdown rendering**: `render_blocks_to_markdown` render tuần tự các block qua `render_markdown_from_block`.

## Đầu ra cuối
- `reconstructed_content`: markdown cuối cùng của toàn bộ tài liệu HTML.
