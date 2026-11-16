# PDF Renderer Flow

## Tổng quan
PdfRenderer thực hiện 3 nhóm việc: (1) tiền xử lý PDF (loại bỏ ảnh nhúng để VLM không nhìn thấy), (2) image gate trích xuất ảnh nhúng cần thiết, (3) VLM trích xuất nội dung từng trang và tái dựng Markdown + chèn ảnh.

## Workflow DAG (thứ tự node)
```
START -> [strip_images_node, image_references, init_page_context]
strip_images_node -> render_node
image_references -> image_gate_batch -> image_gate_loop -> image_gate_finalize
[render_node, init_page_context, image_gate_finalize] -> page_loop -> finalize_pdf_node -> END
```

## Diễn giải luồng (bằng lời)
1. Loại bỏ ảnh nhúng khỏi PDF để VLM không nhìn thấy nội dung ảnh.
2. Render từng trang PDF đã loại ảnh thành ảnh base64 + metadata kích thước.
3. Trích xuất ảnh nhúng từ PDF gốc và tạo danh sách tham chiếu.
4. Chạy image gate để quyết định ảnh nào cần trích xuất nội dung.
5. Vòng lặp trang:
   - Tạo prompt VLM theo ngữ cảnh.
   - Trích xuất markdown từ ảnh trang.
   - Chèn ảnh đã gate vào markdown bằng fuzzy match.
   - Tóm tắt ngữ cảnh cho trang tiếp theo.
6. Ghép tất cả page thành `final_pages` và `reconstructed_content`.

### Node chi tiết
1. **strip_images_node**
   - **Input:** `file_path`
   - **Output:** `processed_file_path`, `removed_images`
   - **Mục đích:** Loại bỏ ảnh nhúng khỏi PDF để VLM không trích xuất text từ ảnh.

2. **render_node**
   - **Input:** `processed_file_path`
   - **Output:** `pages`, `total_pages`
   - **Mục đích:** Render từng trang thành ảnh base64 (phục vụ VLM).

3. **init_page_context**
   - **Output:** `page_context`
   - **Mục đích:** Khởi tạo ngữ cảnh cho chuỗi trang.

4. **image_references**
   - **Input:** `file_path` (PDF gốc)
   - **Output:** `image_references`
   - **Mục đích:** Trích xuất ảnh nhúng và văn bản tham chiếu gần ảnh.

5. **image_gate_batch**
   - **Input:** `image_references`
   - **Output:** `batch_data`
   - **Mục đích:** Chuẩn bị batch cho loop gating.

6. **image_gate_loop** (ForLoop)
   - **image_gate_prompt**: tạo messages cho ảnh + text context.
   - **image_gate_llm**: quyết định EXTRACT/SKIP.
   - **image_gate_collect**: parse response.

7. **image_gate_finalize**
   - **Input:** `gate_results`
   - **Output:** `image_references` (đã lọc)
   - **Mục đích:** Chỉ giữ ảnh được phép trích xuất.

8. **page_loop** (WhileLoop)
   - **Input:** `loop_pages`, `total_pages`, `page_context`, `image_references`, `iteration_count`, `loop_page_outputs`, `merge_flag`, `verify_results`
   - **Bên trong (Pipelined Execution):**
     - **check_ending**: kiểm tra dừng loop.
     - **vlm_prep_node** -> **vlm_extract_node**: trích xuất nội dung trang hiện tại.
     - **insert_image_node**: chèn thẻ `<img>` theo ảnh đã gate.
     - **summary_node**: cập nhật context cho trang sau.
     - **merge_branch**: nếu `merge_flag`=True (từ trang trước), chạy **merge_verify_llm** nối trang trước và trang hiện tại.
     - **update_context**: lưu kết quả extract và merge, check thẻ `[CONTINUES]` của trang hiện tại để gán `merge_flag` cho vòng lặp tiếp theo.
     - **prep_output_node**: đóng loop khi hết trang.

9. **finalize_pdf_node**
   - **Input:** `page_outputs`, `pages`
   - **Output:** `final_pages`, `reconstructed_content`
   - **Mục đích:** Ghép text và ảnh vào Page, tạo reconstructed_content.

## Logic tái dựng nội dung
- **Render ảnh trang**: `render_pdf_to_images` xuất ảnh base64 + width/height cho mỗi trang.
- **Image gate**: chỉ trích xuất nội dung ảnh nhúng khi cần; các ảnh bị loại bỏ không được chèn.
- **VLM extraction**: mỗi trang dùng prompt có ngữ cảnh trước đó, tuân thủ quy tắc Markdown (heading/bảng).
- **Chèn ảnh**: `insert_images_into_text` dùng fuzzy match giữa ref_text và dòng trong markdown để chèn `<img>` đúng vị trí.
- **Context tracking**: summary node tạo context cho trang kế tiếp.
- **Finalize**: tạo `final_pages` (Page dict) và `reconstructed_content` (nối text theo thứ tự trang).

## Đầu ra cuối
- `final_pages`: list Page dict gồm `page_number`, `image_data`, `metadata`, `content` (zone list), `image_list`.
- `reconstructed_content`: markdown đầy đủ của toàn bộ PDF.

