# DOCX Renderer Flow

## Tổng quan
DocxRenderer chuyển DOCX → PDF, sau đó ủy quyền toàn bộ xử lý cho PdfRenderer. Kết quả cuối là các Page và reconstructed_content từ PDF.

## Workflow DAG (thứ tự node)
`START -> convert_docx_to_pdf_node -> delegate_to_pdf_renderer_node -> END`

## Diễn giải luồng (bằng lời)
1. Chuyển DOCX sang PDF tạm thời.
2. Gọi PdfRenderer để xử lý PDF: render ảnh trang, trích xuất nội dung, tái dựng markdown.
3. Map kết quả từ PdfRenderer về Document hiện tại.

### Node chi tiết
1. **convert_docx_to_pdf_node**
   - **Input:** `file_path` (map thành `docx_path`)
   - **Output:** `pdf_path`
   - **Mục đích:** Chuyển DOCX sang PDF bằng `docx2pdf` hoặc lệnh CLI.

2. **delegate_to_pdf_renderer_node**
   - **Input:** `pdf_path`
   - **Output:** `final_pages`, `reconstructed_content`
   - **Mục đích:** Tạo `Document` tạm cho PDF, chạy `PdfRenderer.render`, rồi trả kết quả page/content.

## Logic tái dựng nội dung
- PdfRenderer chịu trách nhiệm trích xuất nội dung và dựng lại cấu trúc Markdown theo từng page.
- DocxRenderer chỉ chuyển đổi và map kết quả từ PDF sang Document hiện tại.

## Đầu ra cuối
- `document.pages`: list Page với `page_number`, `image_data`, `metadata`, `content` (zone list), `image_list`.
- `document.reconstructed_content`: lấy từ PdfRenderer.

## Ghi chú
- Nếu cần chi tiết logic tái dựng, xem tài liệu `pdf_render/FLOW.md`.