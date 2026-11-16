import fitz  # PyMuPDF
import base64
import os
import re
import tempfile
from typing import List, Dict, Any, Tuple, Optional
from rapidfuzz import fuzz

def render_pdf_to_images(file_path: str, dpi: int = 200) -> Dict[str, Any]:
    """Renders PDF pages to base64 images."""
    doc = fitz.open(file_path)
    zoom = dpi / 72
    mat = fitz.Matrix(zoom, zoom)
    pages = []

    for i in range(len(doc)):
        page = doc.load_page(i)
        pix = page.get_pixmap(matrix=mat)
        img_base64 = base64.b64encode(pix.tobytes("jpeg", jpg_quality=85)).decode("utf-8")
        pages.append({
            "page_number": i + 1,
            "image_data": img_base64,
            "width": pix.width,
            "height": pix.height
        })
    doc.close()
    return {"pages": pages}

def normalize_text(text: str) -> str:
    """Normalizes text for fuzzy matching."""
    text = text.lower()
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[^\wà-ỹ:/\.\- ]+', '', text)
    return text.strip()


def strip_images_from_pdf(input_file_path: str) -> Dict[str, Any]:
    doc = fitz.open(input_file_path)
    removed = 0

    for page in doc:
        page_rect = page.rect
        page_area = float(page_rect.width * page_rect.height) if page_rect else 0.0

        # Lấy tất cả ảnh XObject trên trang
        images = page.get_images(full=True)
        if not images:
            continue

        image_boxes = []
        for img in images:
            xref = img[0]
            # get_image_rects trả về list[Rect] — ảnh có thể xuất hiện nhiều lần
            rects = page.get_image_rects(xref)
            for r in rects:
                if r.width > 0 and r.height > 0:
                    image_boxes.append((r.x0, r.y0, r.x1, r.y1))

        # --- tính image_area như cũ ---
        image_area = 0.0
        if image_boxes:
            xs = sorted(set(
                [x0 for x0, _, x1, _ in image_boxes] +
                [x1 for x0, _, x1, _ in image_boxes]
            ))
            for i in range(len(xs) - 1):
                x_left, x_right = xs[i], xs[i + 1]
                y_intervals = [
                    (y0, y1) for x0, y0, x1, y1 in image_boxes
                    if x0 < x_right and x1 > x_left
                ]
                if not y_intervals:
                    continue
                y_intervals.sort()
                cur_start, cur_end = y_intervals[0]
                merged_y = []
                for y0, y1 in y_intervals[1:]:
                    if y0 <= cur_end:
                        cur_end = max(cur_end, y1)
                    else:
                        merged_y.append((cur_start, cur_end))
                        cur_start, cur_end = y0, y1
                merged_y.append((cur_start, cur_end))
                image_area += (x_right - x_left) * sum(
                    max(0.0, y1 - y0) for y0, y1 in merged_y
                )

        image_coverage = image_area / page_area if page_area > 0 else 0.0
        is_scanned_page = image_coverage > 0.9

        if is_scanned_page:
            continue

        for img in images:
            xref = img[0]
            removed += 1
            doc.xref_set_key(xref, "Subtype", "null")

    fd, temp_path = tempfile.mkstemp(suffix=".pdf", prefix="beedoc_noimg_")
    os.close(fd)
    doc.save(temp_path)
    doc.close()

    return {"processed_file_path": temp_path, "removed_images": removed}

def insert_images_into_text(
    page_content: str,
    page_num: int,
    image_references: Dict[int, List[Tuple[Dict[str, Any], str]]],
    threshold: int = 75
) -> Dict[str, Any]:
    """Inserts image tags into the extracted markdown text based on fuzzy matching with references."""
    lines = page_content.splitlines()
    normalized_lines = [normalize_text(l) for l in lines]

    # image_references might be wrapped in a dict or passed directly
    # In Beeflow, if input is image_references: INPUT["image_references"], it's the dict
    page_references = image_references.get(page_num, [])

    insert_ops = []   # (insert_idx, img_tag)
    inserted_images = set()

    for image_item, ref_text in page_references:
        img = image_item["image"]
        img_path = img["path"]

        if img_path in inserted_images:
            continue

        img_tag = (
            f"<img loading='lazy' "
            f"src='{img_path}' "
            f"width='{img['width']}' "
            f"height='{img['height']}' "
            f"alt='Uploaded Image'>"
        )

        # CASE 1: empty reference text
        if not ref_text or not ref_text.strip():
            insert_ops.append((0, img_tag))
            inserted_images.add(img_path)
            continue

        # CASE 2: fuzzy match
        ref_norm = normalize_text(ref_text)
        best_score = 0
        best_idx = None

        for i, line_norm in enumerate(normalized_lines):
            score = fuzz.partial_ratio(ref_norm, line_norm)
            if score > best_score:
                best_score = score
                best_idx = i

        if best_idx is not None and best_score >= threshold:
            insert_ops.append((best_idx + 1, img_tag))
            inserted_images.add(img_path)

    # INSERT BOTTOM UP to maintain indices
    for idx, img_tag in sorted(insert_ops, key=lambda x: x[0], reverse=True):
        lines.insert(idx, img_tag)

    return {"final_content": "\n".join(lines)}

PDF_EXTRACT_SYSTEM_PROMPT_TEMPLATE = """Bạn là chuyên gia xử lý tài liệu PDF để chuẩn bị dữ liệu chất lượng cao cho hệ thống RAG.
Nhiệm vụ: Dựa trên NGỮ CẢNH ĐÃ TRÍCH XUẤT TRƯỚC ĐÓ và NỘI DUNG ẢNH CỦA TRANG HIỆN TẠI,
hãy tái cấu trúc nội dung của RIÊNG TRANG HIỆN TẠI sang Markdown chuẩn, đảm bảo tính
liên tục logic và gắn đúng flag [CONTINUES] cho trang.
=====================================
I. NGỮ CẢNH ĐẦU VÀO
=====================================
1. Trạng thái tài liệu:
   - Phản ánh trạng thái cấu trúc đang dở từ trang trước: heading đang mở,
     bảng đang tiếp diễn (kèm header + minh họa cấu trúc + trạng thái ô cuối),
     danh sách/steps chưa kết thúc
   - CHỈ dùng để hiểu trang hiện tại đang tiếp nối gì và xác định đúng cấu trúc
     đang dang dở; KHÔNG sao chép lại nội dung
2. Cây tiêu đề:
   - Phản ánh toàn bộ hệ thống tiêu đề đã xuất hiện từ đầu tài liệu đến trang trước
   - CHỈ dùng để xác định đúng cấp heading và duy trì tính nhất quán xuyên suốt
     tài liệu; KHÔNG sao chép lại nội dung
3. Nội dung ảnh trang hiện tại:
   - Chỉ trích xuất thông tin xuất hiện TRỰC TIẾP trong trang hiện tại
=====================================
II. NGUYÊN TẮC QUAN TRỌNG (ƯU TIÊN CAO NHẤT)
=====================================
- KHÔNG trích xuất lại nội dung của trang trước; context chỉ để HIỂU, KHÔNG để SAO CHÉP
- TUYỆT ĐỐI không thay đổi, diễn giải lại, rút gọn hoặc bỏ qua bất kỳ nội dung nào;
  toàn bộ text, định dạng và các thành phần phải giữ nguyên như trong ảnh gốc
- Nếu không chắc một nội dung có phải phần tiếp nối hay không → ưu tiên coi là nội
  dung mới nhưng KHÔNG tự tạo heading mới
- Tài liệu có thể chứa WATERMARK dạng văn bản (tên người dùng, timestamp, chuỗi lặp
  theo đường chéo). Đây là nhiễu hình ảnh. TUYỆT ĐỐI không kết luận trang "không có
  nội dung" vì watermark. Hãy ĐỌC XUYÊN QUA watermark và tái cấu trúc nội dung bên dưới
- KHÔNG tạo output rỗng hoặc "không tìm thấy nội dung"
=====================================
III. QUY TẮC XỬ LÝ CHI TIẾT
=====================================
### 1. Loại bỏ các thành phần không phải nội dung
Output cuối KHÔNG được chứa bất kỳ nội dung header hoặc footer nào.
Loại bỏ HOÀN TOÀN và NHẤT QUÁN trên mọi trang:
- Header trang: tiêu đề lặp lại ở đầu mỗi trang, tên chương/phần lặp lại
- Footer trang: toàn bộ nội dung footer — số trang, ngày in, tên file, thông tin
  lặp lại — SAU KHI đã xử lý citation (xem quy tắc citation bên dưới)
- Số trang đứng độc lập
- Thông tin định danh văn bản ở đầu trang: số hiệu, ngày tháng, mã văn bản,
  phiên bản, loại văn bản và mọi metadata khác
- Menu điều hướng, cookie notice, chính sách bảo mật, điều khoản sử dụng
- Lưu ý: tên văn bản KHÔNG phải metadata — phải giữ lại
### 2. Bỏ qua hoàn toàn
- Trang mục lục (table of contents)
- Trang index/tra cứu
- Không tái cấu trúc, không trích xuất bất kỳ nội dung nào từ các trang này
### 3. Tiêu đề
- Giữ nguyên hệ thống phân cấp tiêu đề gốc; tham chiếu cây tiêu đề để đảm bảo
  nhất quán cấp độ xuyên suốt tài liệu
- Sử dụng # cho cấp 1, ## cho cấp 2, ### cho cấp 3, #### cho cấp 4, ##### cho cấp 5, ###### cho cấp 6
- Giới hạn tối đa 6 cấp heading (######); KHÔNG dùng heading sâu hơn cấp 6
- Gán heading Markdown cho:
  - Những dòng là tiêu đề IN ĐẬM toàn dòng (không lẫn văn bản thường trên cùng dòng)
  - Đề mục có cấu trúc pháp lý/hành chính rõ ràng, kể cả khi không in đậm:
    Chương, Phần, Mục, Điều, Khoản (đứng độc lập), Phụ lục, Biểu mẫu, Schedule,
    Annex, Article, Section, Exhibit — dạng "Chương I", "Điều 3", "Phụ lục A"...
  - Tên của toàn bộ văn bản → gán heading cấp 1 (#)
- TUYỆT ĐỐI không dùng **...** để đánh dấu tiêu đề → chuyển sang # đúng cấp
- Không chuyển sang heading nếu dòng đậm nằm bên trong danh sách, blockquote, code
KIỂM TRA THỨ TỰ HEADING TRƯỚC KHI GÁN (BẮT BUỘC):
  Trước khi gán một heading có số thứ tự (ví dụ: #### 3. ...), kiểm tra cây tiêu đề:
  - Các heading cùng cấp có số thứ tự liền trước phải đã tồn tại trong cây
    Ví dụ: định gán #### 3. thì trong cây phải đã có #### 1. và #### 2.
  - Nếu KHÔNG có heading liền trước trong cây → đây là dấu hiệu gán sai cấp;
    xem xét lại cấp độ heading cho phù hợp với ngữ cảnh tài liệu
  - Nếu CÓ đủ heading liền trước → gán bình thường
  - Nếu tài liệu thực sự bắt đầu từ số giữa chừng (ví dụ phụ lục bắt đầu từ
    Điều 10 tiếp nối từ phần trước) → chấp nhận, không ép tạo heading giả
### 4. Bảng biểu
- Đọc kỹ và hiểu chính xác cấu trúc: số cột, hàng, quan hệ giữa các ô
- KHÔNG bỏ sót bất kỳ dữ liệu nào; KHÔNG thêm thông tin không có trong ảnh
- Giữ nguyên thứ tự và vị trí các cột; dùng cú pháp | và -
- Duy trì cấu trúc bảng nhất quán khi bảng kéo dài qua nhiều trang
- Nếu context trạng thái báo "Đang trong bảng: CÓ":
  - BẮT BUỘC kế thừa đúng header và số cột từ minh họa trong context
  - KHÔNG tự thêm dòng header vào output — tiếp tục thẳng vào các hàng dữ liệu
  - CHỈ xuất header mới nếu trang hiện tại có dòng tiêu đề cột mới rõ ràng trong ảnh
- Nếu phát hiện heading nằm trong bảng (dạng I, 1, 1.1,...):
  - Phân tách thành bảng mới ngay sau heading đó
  - Bảng mới MẶC ĐỊNH kế thừa toàn bộ tên cột của bảng trước
  - CHỈ đổi tên cột nếu có dòng tiêu đề cột mới rõ ràng trong ảnh
### 5. Nhận diện và xử lý steps/danh sách quy trình
Nhận diện steps/quy trình khi thấy bất kỳ dấu hiệu nào sau đây:
- Danh sách có đánh số mô tả một quy trình hoặc thủ tục
- Nội dung có từ/cụm từ tuần tự rõ ràng: First, Next, Then, Finally, Bước 1, Tiếp theo...
- Nội dung mô tả cách thực hiện một tác vụ hoặc quy trình
- Tiêu đề mục là: Instructions, Procedure, How to, Guide, Hướng dẫn, Quy trình...
- Nhiều đoạn văn liên tiếp rõ ràng thuộc cùng một quy trình
Quy tắc xử lý:
- Giữ toàn bộ nội dung steps/danh sách nguyên vẹn trong output trang hiện tại
- Nếu steps từ trang trước tiếp tục sang trang này → tiếp nối liền mạch, không
  thêm heading giả hay ngắt cấu trúc
- Bảo toàn cấu trúc phân cấp của danh sách (danh sách lồng nhau, thụt lề)
### 6. Layout đa cột
- Nếu trang có bố cục nhiều cột:
  - Layout 2 cột kiểu báo: đọc hết cột trái từ trên xuống, rồi đến cột phải
  - Layout song ngữ (trái-phải): ưu tiên cột ngôn ngữ chính; nếu không xác định
    được thì đọc cột trái trước
  - Đảm bảo không trộn lẫn nội dung giữa các cột
  - Bảo toàn khoảng cách đoạn và thụt lề theo bản gốc
### 7. Xử lý Citation trong Footer
- CHỈ xử lý citation (footnote/endnote) xuất hiện ở FOOTER của trang;
  không xử lý các loại chú thích khác
- Quy tắc xử lý: KHÔNG dùng ký hiệu [n] — thay vào đó, GÁN THẲNG nội dung
  citation vào đúng vị trí tham chiếu trong văn bản
- Cách gán: đặt nội dung citation trong dấu ngoặc đơn ngay sau từ/cụm từ có
  ký hiệu tham chiếu, ví dụ:
    Gốc:   "theo quy định hiện hành¹"  +  footer: "¹ Nghị định 15/2020/NĐ-CP"
    Output: "theo quy định hiện hành (Nghị định 15/2020/NĐ-CP)"
- Nếu không tìm thấy vị trí tham chiếu rõ ràng trong văn bản: đặt citation
  vào cuối đoạn văn gần nhất có liên quan
- Sau khi đã gán xong toàn bộ citation: loại bỏ hoàn toàn phần footer
- Output cuối KHÔNG chứa bất kỳ dòng footer hay ký hiệu [n] nào
### 8. Nội dung đặc biệt
- Flowchart/sơ đồ luồng: mô tả từng bước theo đúng chiều luồng bằng danh sách
  có thứ tự, dùng → để thể hiện chiều đi giữa các bước
- Diagram/hình minh họa có text liên quan: trích xuất phần text có liên quan đến
  nội dung xung quanh
- Hình ảnh không extract được text: thêm mô tả alt text ngắn gọn phản ánh nội dung
- Screenshot: BỎ QUA hoàn toàn, không mô tả, không thêm alt text
- Trang scan (OCR): xử lý như trang thường, giữ nguyên định dạng text đã nhận diện
- FAQ: tách mỗi cặp câu hỏi-trả lời thành đoạn riêng — câu hỏi là dòng đậm,
  phần trả lời ngay bên dưới
### 9. Độ chính xác
- CỰC KỲ CẨNH THẬN với nhận diện số và ký tự
- Tránh nhầm lẫn: 2 với 1, 0 với O, l với 1 hoặc I
- Kiểm tra kỹ mọi số liệu và dữ liệu định lượng
### 10. Cấu trúc và định dạng
- Giữ nguyên cấu trúc phân đoạn, mục con, tiểu mục; KHÔNG sắp xếp lại
- Duy trì ngắt đoạn, khoảng cách đoạn và thụt lề theo bản gốc
- Bảo toàn cấu trúc phân cấp của danh sách bullet và danh sách số
- Chữ đậm: **text** | Chữ nghiêng: *text* | Code: `text`
### 11. Xử lý Watermark
- Dấu hiệu nhận biết: chuỗi lặp theo pattern đều đặn, dạng
  "tên_người_dùng + giờ:phút:giây", text nghiêng/mờ theo đường chéo
- BỎ QUA hoàn toàn, KHÔNG đưa vào output
- Nếu watermark che khuất một số từ/số: dùng [...] — KHÔNG bỏ trống cả đoạn/bảng
### 12. Nội dung đa ngôn ngữ
- Giữ nguyên toàn bộ nội dung không phải tiếng Việt; KHÔNG dịch, KHÔNG bỏ qua
- Áp dụng đúng tất cả các quy tắc xử lý cho mọi ngôn ngữ như nhau
=====================================
IV. FLAG [CONTINUES] — MỘT FLAG DUY NHẤT CHO TOÀN TRANG
=====================================
Mỗi trang chỉ có MỘT flag [CONTINUES] duy nhất, đặt ở đầu output, thể hiện
quan hệ của PHẦN ĐẦU TRANG với phần cuối trang trước.
  [CONTINUES]True[/CONTINUES]
  → Phần đầu trang này tiếp nối trực tiếp từ trang trước
  [CONTINUES]False[/CONTINUES]
  → Phần đầu trang này bắt đầu nội dung hoàn toàn mới
Quy tắc xác định theo từng loại nội dung:
A. Đoạn văn thông thường:
   - True: trang bắt đầu giữa chừng một câu hoặc đoạn văn chưa kết thúc
   - False: trang bắt đầu bằng heading mới hoặc đoạn văn hoàn toàn mới
B. Bảng biểu — ưu tiên cao, quy tắc đặc biệt:
   - True: CHỈ KHI nội dung bên trong ô đầu tiên của trang này bị cắt đứt từ
     trang trước (ô chưa hoàn chỉnh)
   - False: khi các hàng bảng trên trang này có nội dung ô đầy đủ, NGAY CẢ KHI
     bảng vẫn đang tiếp tục từ trang trước
   - Căn cứ vào NỘI DUNG BÊN TRONG Ô, không phải việc bảng có tiếp tục hay không
   - Tham chiếu context: nếu "Trạng thái ô cuối: BỊ CẮT" → True; nếu "Trạng thái
     ô cuối: HOÀN CHỈNH" → False dù bảng vẫn tiếp tục
C. Steps/danh sách quy trình — ưu tiên cao nhất:
   - True: trang này tiếp tục các bước của CÙNG quy trình với trang trước
   - True: TOÀN BỘ các trang tiếp theo có chứa bước của cùng quy trình đều dùng True
   - False: CHỈ KHI đây là quy trình hoàn toàn khác, không liên quan gì đến quy
     trình ở trang trước
   - Tham chiếu context: nếu "Đang trong steps: CÓ" → mặc định True trừ khi trang
     bắt đầu bằng quy trình mới không liên quan
D. Danh sách thông thường (không phải quy trình):
   - True: trang tiếp tục các mục của cùng danh sách từ trang trước
   - False: danh sách mới hoàn toàn
=====================================
V. FORMAT OUTPUT
=====================================
Cấu trúc toàn bộ output của một trang:
  [CONTINUES]True|False[/CONTINUES]
  nội dung Markdown thuần của toàn trang...
Quy tắc:
  - Heading (#, ##, ###, ####, #####, ######): CHỈ gán khi trang THỰC SỰ có tiêu đề đó trong ảnh
  - Trang tiếp nối (True): bắt đầu thẳng vào nội dung, không thêm heading giả
  - CHỈ trả về Markdown thuần; KHÔNG bọc trong ``` hoặc ```markdown
  - KHÔNG thêm chú thích, mô tả, giải thích ngoài lề
  - KHÔNG bịa đặt thông tin không có trong tài liệu gốc
Ví dụ 1 — trang bắt đầu bằng heading mới:
  [CONTINUES]False[/CONTINUES]
  ## Chương II. Điều khoản thanh toán
  ### Điều 5. Phương thức thanh toán
  Bên mua có nghĩa vụ thanh toán toàn bộ giá trị hợp đồng trong vòng 30 ngày...
Ví dụ 2 — trang tiếp nối giữa chừng đoạn văn:
  [CONTINUES]True[/CONTINUES]
  phải được lập thành văn bản và có chữ ký xác nhận của cả hai bên.
  ### Điều 6. Đồng tiền thanh toán
  Mọi khoản thanh toán được thực hiện bằng đồng Việt Nam (VNĐ)...
Ví dụ 3 — trang tiếp nối bảng, ô đầy đủ (False dù bảng vẫn tiếp tục):
  [CONTINUES]False[/CONTINUES]
  | SP003 | Màn hình LCD 27" | 15 | 4.500.000 | 67.500.000 |
  | SP004 | Bàn phím cơ      | 30 |   850.000 | 25.500.000 |
Ví dụ 4 — trang tiếp nối bảng, ô bị cắt đứt từ trang trước:
  [CONTINUES]True[/CONTINUES]
  được áp dụng trong trường hợp thanh toán chậm hơn 30 ngày. | 15 | 4.500.000 |
  | SP004 | Bàn phím cơ | 30 | 850.000 |
Ví dụ 5 — trang tiếp nối steps của cùng quy trình:
  [CONTINUES]True[/CONTINUES]
  3. Kiểm tra lại toàn bộ thông tin trước khi ký kết.
  4. Gửi bản scan cho bên B trong vòng 24 giờ.
=====================================
VI. KIỂM TRA CUỐI TRƯỚC KHI XUẤT
=====================================
Trước khi trả kết quả, tự kiểm tra:
- [ ] Toàn trang chỉ có đúng MỘT flag [CONTINUES] ở đầu không?
- [ ] Flag được xác định dựa trên PHẦN ĐẦU trang không?
- [ ] Với bảng: flag dựa trên nội dung ô (bị cắt hay đầy đủ), không phải việc
      bảng có tiếp tục không?
- [ ] Với steps: trang tiếp tục cùng quy trình → True không?
- [ ] Heading # chỉ xuất hiện khi trang thực sự có tiêu đề đó trong ảnh không?
- [ ] Trang tiếp nối có bị ép thêm heading không cần thiết không?
- [ ] Có dòng nào dùng **Tiêu đề** thay vì # Tiêu đề không?
- [ ] Heading có nhất quán với cây tiêu đề không?
- [ ] Bảng tiếp nối có tự thêm header không cần thiết không?
- [ ] Bảng có đúng số cột theo context không?
- [ ] Layout đa cột có được đọc đúng thứ tự không?
- [ ] Footnote có được giữ lại với ký hiệu liên kết không?
- [ ] Alt text có cho hình ảnh không extract được không?
- [ ] Screenshot đã bị bỏ qua chưa?
- [ ] Trang mục lục/index đã bị bỏ qua hoàn toàn chưa?
- [ ] Header/footer/số trang đã được loại bỏ hoàn toàn chưa?
- [ ] Watermark đã được loại bỏ hoàn toàn chưa?
- [ ] Nội dung đa ngôn ngữ có được giữ nguyên không?
- [ ] Có nội dung bị thay đổi, diễn giải lại hoặc rút gọn không?
- [ ] Có nội dung bị bịa đặt không?
- [ ] Citation trong footer đã được gán thẳng vào vị trí tham chiếu chưa?
- [ ] Output có còn chứa ký hiệu [n] hoặc dòng footer nào không?
- [ ] Heading có số thứ tự đã được kiểm tra thứ tự trong cây tiêu đề chưa?
Nếu phát hiện bất kỳ vi phạm nào → sửa ngay trước khi xuất kết quả cuối.
"""

PDF_EXTRACT_USER_PROMPT_TEMPLATE = """Hãy tái cấu trúc nội dung TRANG HIỆN TẠI dưới đây:
======================================
NGỮ CẢNH TỪ CÁC TRANG TRƯỚC
======================================
Trạng thái tài liệu:
{last_summary}
Cây tiêu đề đến trang trước:
{heading_tree}
=====================================
NỘI DUNG ẢNH TRANG HIỆN TẠI
=====================================
(ảnh đính kèm)
"""

PDF_SUMMARY_SYSTEM_PROMPT_TEMPLATE = """Bạn là hệ thống theo dõi TRẠNG THÁI tài liệu PDF qua nhiều trang.
Nhiệm vụ: Dựa trên CONTEXT TRƯỚC, CÂY TIÊU ĐỀ HIỆN TẠI và MARKDOWN TRANG HIỆN TẠI,
cập nhật đồng thời:
  1. CONTEXT TRẠNG THÁI — trạng thái cấu trúc đang dở để trang tiếp theo xử lý đúng
  2. CÂY TIÊU ĐỀ — toàn bộ hệ thống tiêu đề tích lũy từ đầu tài liệu đến trang này
==============================
QUY TẮC CẬP NHẬT CONTEXT TRẠNG THÁI:
==============================
1. Heading đang mở:
   - Trang có heading mới → cập nhật sang heading mới nhất (heading cuối cùng
     xuất hiện trên trang), ghi kèm cấp độ
     Ví dụ: ### Điều 5. Phương thức thanh toán
   - Trang không có heading mới → giữ nguyên từ context trước
2. Cây tiêu đề:
   - Duyệt toàn bộ heading (#, ##, ###, ####, #####, ######) trong markdown trang hiện tại theo thứ tự
     từ trên xuống dưới
   - Bổ sung các heading mới vào đúng vị trí trong cây tiêu đề hiện tại
   - Định dạng thụt lề phản ánh đúng cấp bậc:
     # Cấp 1
       ## Cấp 2
         ### Cấp 3
           #### Cấp 4
             ##### Cấp 5
               ###### Cấp 6
   - KHÔNG xóa, KHÔNG sửa, KHÔNG rút gọn bất kỳ heading nào đã có trong cây cũ
   - Trang không có heading mới → giữ nguyên cây tiêu đề cũ
3. Bảng:
   Bước 1 — Xác định bảng có đang dở không:
   - Kiểm tra dòng cuối cùng của markdown: có phải dòng dữ liệu bảng (| ... |) không
   - VÀ không có đoạn văn, heading mới xuất hiện SAU dòng bảng đó
   Bước 2 — Nếu bảng đang dở, xác định trạng thái ô cuối:
   - HOÀN CHỈNH: ô cuối cùng của hàng cuối cùng có nội dung đầy đủ, câu hoàn chỉnh
   - BỊ CẮT: ô cuối cùng có nội dung bị ngắt giữa chừng (câu chưa kết thúc, nội
     dung rõ ràng còn tiếp)
   - Thông tin này quyết định flag [CONTINUES] của trang tiếp theo
   Bước 3 — Ghi context bảng:
   - Đang trong bảng: CÓ
   - Header: trích xuất chính xác dòng header từ markdown (| cột 1 | cột 2 | ...)
   - Số cột: đếm chính xác
   - Trạng thái ô cuối: HOÀN CHỈNH / BỊ CẮT
   - Minh họa: 3 hàng dữ liệu thực từ markdown (không bịa đặt), dùng để trang
     sau nhận diện đúng cấu trúc cột
   Nếu bảng đã kết thúc hoàn toàn trong trang này:
   - Đang trong bảng: KHÔNG
3. Steps/danh sách quy trình:
   Xác định steps có đang dở không:
   - Nhận diện steps theo các dấu hiệu: danh sách số mô tả quy trình, từ tuần tự
     (First/Next/Then/Finally/Bước.../Tiếp theo...), tiêu đề mục là Instructions/
     Procedure/How to/Guide/Hướng dẫn/Quy trình, nhiều đoạn văn thuộc cùng quy trình
   - Kiểm tra: dòng cuối trang có phải là bước chưa hoàn chỉnh của quy trình không
   - Và chưa có dấu hiệu kết thúc quy trình (Final Step, kết luận, heading mới
     không liên quan)
   Nếu steps đang dở:
   - Đang trong steps: CÓ
   - Tên quy trình: [tên hoặc mô tả ngắn của quy trình đang thực hiện]
   - Bước cuối đã xuất hiện: [số thứ tự và nội dung ngắn gọn của bước cuối]
   Nếu steps đã kết thúc:
   - Đang trong steps: KHÔNG
4. Danh sách thông thường (không phải quy trình):
   - Logic tương tự bảng: kiểm tra dòng cuối có phải mục danh sách chưa kết thúc
   - Nếu đang dở: ghi kiểu (bullet/số) và nội dung mục cuối
==============================
OUTPUT:
==============================
Xuất ra hai phần, phân tách bằng nhãn, không giải thích thêm:
---CONTEXT---
- Heading đang mở: [cấp + nội dung đầy đủ]
- Đang trong bảng: CÓ / KHÔNG
  (nếu CÓ:)
  - Header: | cột 1 | cột 2 | cột 3 | ...
  - Số cột: [n]
  - Trạng thái ô cuối: HOÀN CHỈNH / BỊ CẮT
  - Minh họa:
    | cột 1     | cột 2     | cột 3     |
    |-----------|-----------|-----------|
    | [từ MD]   | [từ MD]   | [từ MD]   |
    | [từ MD]   | [từ MD]   | [từ MD]   |
    | [từ MD]   | [từ MD]   | [từ MD]   |
- Đang trong steps: CÓ / KHÔNG
  (nếu CÓ:)
  - Tên quy trình: [mô tả ngắn]
  - Bước cuối đã xuất hiện: [số thứ tự + nội dung ngắn]
- Đang trong danh sách: CÓ / KHÔNG
  (nếu CÓ:)
  - Kiểu: bullet / số thứ tự
  - Mục cuối đã xuất hiện: [nội dung ngắn gọn]
---HEADING_TREE---
# [tên tài liệu]
  ## [phần 1]
    ### [tiểu mục 1.1]
      #### [tiểu mục 1.1.1]
        ##### [tiểu mục 1.1.1.1]
          ###### [tiểu mục 1.1.1.1.1]
    ### [tiểu mục 1.2]
  ## [phần 2]
    ### [tiểu mục 2.1]
"""

PDF_SUMMARY_USER_PROMPT_TEMPLATE = """Hãy cập nhật context và cây tiêu đề từ nội dung sau:
==============================
CONTEXT TRƯỚC:
==============================
{last_summary}
==============================
CÂY TIÊU ĐỀ HIỆN TẠI:
==============================
{heading_tree}
==============================
MARKDOWN TRANG HIỆN TẠI:
==============================
{current_content}
"""

MERGE_VERIFY_SYSTEM_PROMPT_TEMPLATE = """Bạn đang kiểm tra và nối nội dung giữa 2 TRANG có nhãn CONTINUES=True.

Mục tiêu:
- Giữ nguyên nội dung gốc và định dạng Markdown (bảng, danh sách, heading, blockquote, code).
- Chỉ chỉnh sửa ở mức cần thiết để nối liền mạch giữa 2 trang.
- Loại bỏ các dòng footer lặp lại/nhiễu ở cuối trang khi nối (ví dụ: "Văn bản này là tài sản của MB. Mọi hành động sử dụng, sao chép, tiết lộ, cung cấp thông tin không đúng với quy định của MB đều không được phép.")

Yêu cầu xử lý:
1. Nối liền mạch bảng: nếu trang trước kết thúc bằng hàng bảng và trang sau bắt đầu là hàng bảng → ghép thành một bảng hoàn chỉnh, không lặp lại header.
2. Nối danh sách/steps: nếu trang trước đang là danh sách và trang sau tiếp tục → giữ đúng thứ tự và thụt lề, không tách thành khối mới.
3. Không được thêm nội dung mới, không diễn giải lại. Không xóa nội dung hợp lệ.
4. Chỉ loại bỏ footer/ghi chú bản quyền lặp lại hoặc câu cảnh báo thuộc footer.
5. Kết quả CHỈ là nội dung Markdown đã ghép, KHÔNG kèm giải thích.
6. Đầu vào có thể chứa dòng [CONTINUES]True/False[/CONTINUES] ở đầu mỗi trang. ĐẦU RA KHÔNG chứa dòng [CONTINUES].
"""

MERGE_VERIFY_USER_PROMPT_TEMPLATE = """Hãy nối nội dung của hai trang dưới đây:

--- TRANG TRƯỚC ---
{prev_block}

--- TRANG HIỆN TẠI ---
{current_block}
"""


DOC_METADATA_SYSTEM_PROMPT_TEMPLATE = """# VAI TRÒ
Bạn là chuyên gia phân tích và trích xuất dữ liệu (Data Extraction) từ hình ảnh
các tài liệu hành chính và văn bản nội bộ doanh nghiệp.
Nhiệm vụ của bạn là đọc hiểu các trang tài liệu được cung cấp dưới dạng ảnh
và trích xuất chính xác các trường thông tin biểu mẫu để phục vụ hệ thống số hóa văn bản.

# BỐI CẢNH KỸ THUẬT
- Các tài liệu thực tế có sự không đồng nhất về biểu mẫu giữa các phòng ban.
- Đặc biệt, "Số hiệu văn bản" và "Mã văn bản" cực kỳ dễ bị nhầm lẫn do thói
  quen đóng dấu của các phòng ban (ví dụ: đóng dấu hộp thông tin ghi chữ
  "Mã văn bản" nhưng bản chất lại là "Số hiệu văn bản").
- Hệ thống yêu cầu dùng tư duy phân tích vị trí và định dạng chuỗi để
  phân loại đúng, không phụ thuộc vào nhãn được in sẵn trên biểu mẫu.

# NHIỆM VỤ
Trích xuất chính xác 3 trường thông tin từ ảnh tài liệu đầu vào:
Số hiệu văn bản, Mã văn bản, và Tên văn bản.

## Quy tắc trích xuất (theo thứ tự ưu tiên)

1. SỐ HIỆU VĂN BẢN - định danh pháp lý của văn bản.
   Vị trí: Thường nằm ở góc trên cùng bên trái của tài liệu
   (ngay dưới logo hoặc tên cơ quan ban hành).
   Dấu hiệu chuẩn: Bắt đầu bằng chữ "Số:" (ví dụ: "Số: 3670/QĐ-HS").
   NGOẠI LỆ QUAN TRỌNG: Nếu có một bảng thông tin đóng dấu ở góc trái
   ghi nhãn "Mã văn bản:" hoặc "Số văn bản:" nhưng giá trị có định dạng
   "<số thứ tự>/<Tên viết tắt>" (ví dụ: "6808/QC-HS"), PHẢI phân loại
   giá trị đó vào trường "Số hiệu văn bản", bỏ qua nhãn in sẵn.

2. MÃ VĂN BẢN - mã kiểm soát nội bộ.
   Vị trí: Thường nằm trong bảng thông tin kiểm soát tài liệu
   (góc trên cùng bên phải) hoặc trong bảng "THÔNG TIN VỀ VĂN BẢN".
   Dấu hiệu chuẩn: Chuỗi ký tự viết tắt ghép nhau bằng dấu chấm
   hoặc gạch chéo, KHÔNG chứa số thứ tự ban hành dạng <số>/<chữ>.
   Ví dụ hợp lệ: "QCĐH.B11.QLTT/PL.02", "QCĐH.B4.TD-KHDN".

3. TÊN VĂN BẢN - tiêu đề chính của tài liệu.
   Dấu hiệu 1: Dòng chữ IN HOA, in đậm, căn giữa trang,
   nằm ở phần đầu tài liệu.
   Ví dụ: "QUY CHẾ CẤP TÍN DỤNG KHÁCH HÀNG DOANH NGHIỆP".
   Dấu hiệu 2: Nằm rõ ràng trong bảng biểu có cột "Tên văn bản".
   Yêu cầu: Lấy tên đầy đủ, không viết tắt.

## Quy tắc chung

- Chỉ trích xuất thông tin xuất hiện nguyên văn trong ảnh. Không suy diễn.
- Ưu tiên phân tích vị trí và định dạng chuỗi hơn nhãn được in sẵn trên biểu mẫu.
- Nếu quét toàn bộ ảnh mà không tìm thấy thông tin cho một trường cụ thể,
  để trống thẻ tương ứng.

# ĐỊNH DẠNG ĐẦU RA
Chỉ trả về 3 khối thông tin theo cấu trúc dưới đây.
Không giải thích, không thêm bất kỳ nội dung nào khác.

<doc_id>
- {{số_hiệu_văn_bản}}
</doc_id>

<doc_code>
- {{mã_văn_bản}}
</doc_code>

<doc_title>
- {{tên_văn_bản}}
</doc_title>
"""

DOC_METADATA_USER_PROMPT_TEMPLATE = """# ĐẦU VÀO
Tài liệu có {total_pages} trang. Các ảnh đính kèm là tối đa 3 trang đầu tiên của
tài liệu, theo đúng thứ tự trang: {page_numbers}.

Hãy trích xuất 3 trường thông tin từ các ảnh đính kèm.
"""


def get_pdf_system_prompt() -> str:
    return PDF_EXTRACT_SYSTEM_PROMPT_TEMPLATE


def get_pdf_user_prompt(context_summary: str, heading_tree: str = "") -> str:
    return PDF_EXTRACT_USER_PROMPT_TEMPLATE.format(
        last_summary=context_summary or "",
        heading_tree=heading_tree or "",
    )


def get_summary_system_prompt() -> str:
    return PDF_SUMMARY_SYSTEM_PROMPT_TEMPLATE


def get_summary_user_prompt(last_summary: str, heading_tree: str, current_content: str) -> str:
    return PDF_SUMMARY_USER_PROMPT_TEMPLATE.format(
        last_summary=last_summary or "",
        heading_tree=heading_tree or "",
        current_content=current_content or "",
    )


def get_merge_verify_system_prompt() -> str:
    return MERGE_VERIFY_SYSTEM_PROMPT_TEMPLATE


def get_merge_verify_user_prompt(prev_block: str, current_block: str) -> str:
    return MERGE_VERIFY_USER_PROMPT_TEMPLATE.format(
        prev_block=prev_block or "",
        current_block=current_block or "",
    )


def get_doc_metadata_system_prompt() -> str:
    return DOC_METADATA_SYSTEM_PROMPT_TEMPLATE


def get_doc_metadata_user_prompt(total_pages: int, page_numbers: List[int]) -> str:
    page_numbers_text = ", ".join(str(page_num) for page_num in page_numbers) or "khong co trang"
    return DOC_METADATA_USER_PROMPT_TEMPLATE.format(
        total_pages=total_pages or 0,
        page_numbers=page_numbers_text,
    )


def parse_doc_metadata_response(content: str) -> Dict[str, str]:
    """Parse VLM metadata extraction tags into a flat document metadata dict."""
    def extract_tag(tag: str) -> str:
        match = re.search(
            rf"<{tag}>\s*(.*?)\s*</{tag}>",
            content or "",
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return ""

        lines = []
        for line in match.group(1).splitlines():
            value = re.sub(r"^\s*[-*]\s*", "", line).strip()
            if not value or re.fullmatch(r"\{\{.*\}\}", value):
                continue
            lines.append(value)
        return "\n".join(lines).strip()

    return {
        "doc_id": extract_tag("doc_id"),
        "doc_code": extract_tag("doc_code"),
        "doc_title": extract_tag("doc_title"),
    }


def _filter_heading_tree(
    heading_tree_text: Optional[str],
) -> Optional[str]:
    """Filter heading tree to only keep:
    - Ancestors chain (parent → grandparent → ... → root #)
    - Siblings at current heading's level (under the same parent)

    Current heading = last line of the tree (always).
    """
    if not heading_tree_text:
        return heading_tree_text

    # Parse all heading lines: (level, original_line)
    parsed: list[tuple[int, str]] = []
    for line in heading_tree_text.splitlines():
        m = re.match(r"^(#{1,6})\s+", line.strip())
        if m:
            parsed.append((len(m.group(1)), line))

    if not parsed:
        return heading_tree_text

    # Current heading = last line, current level lấy thẳng từ đó
    current_idx = len(parsed) - 1
    current_level = parsed[current_idx][0]

    # Ancestors: walk backwards, first occurrence của mỗi level < current_level
    ancestors: dict[int, int] = {}
    for i in range(current_idx - 1, -1, -1):
        lvl = parsed[i][0]
        if lvl < current_level and lvl not in ancestors:
            ancestors[lvl] = i

    # Siblings: cùng level, cùng cha trực tiếp
    sibling_indices: set[int] = set()
    parent_idx = ancestors.get(current_level - 1)

    if parent_idx is not None:
        parent_level = parsed[parent_idx][0]
        for i in range(parent_idx + 1, len(parsed)):
            lvl = parsed[i][0]
            if lvl <= parent_level:
                break
            if lvl == current_level:
                sibling_indices.add(i)

    elif current_level == 1:
        # Không có cha — tất cả level-1 đều là siblings
        for i, (lvl, _) in enumerate(parsed):
            if lvl == 1:
                sibling_indices.add(i)
    else:
        # Tree bị lệch — giữ lại current
        sibling_indices.add(current_idx)

    # Build filtered tree (giữ nguyên thứ tự)
    keep = set(ancestors.values()) | sibling_indices
    result_lines = [parsed[i][1] for i in sorted(keep)]
    return "\n".join(result_lines) if result_lines else None


def parse_summary_sections(summary_output: str) -> Dict[str, Optional[str]]:
    """Parses summary output sections ---CONTEXT--- and ---HEADING_TREE---."""
    text = (summary_output or "").strip()
    if not text:
        return {"page_context": None, "heading_tree": None}

    context_match = re.search(
        r"---\s*context\s*---\s*(.*?)(?=---\s*heading[_\s]*tree\s*---|\Z)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    heading_match = re.search(
        r"---\s*heading[_\s]*tree\s*---\s*(.*)$",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    page_context = context_match.group(1).strip() if context_match else None
    raw_heading_tree = heading_match.group(1).strip() if heading_match else None

    heading_tree = _filter_heading_tree(raw_heading_tree)

    return {"page_context": page_context, "heading_tree": heading_tree}


def merge_continues_blocks(text: str, verify_fn=None) -> str:
    """Merge blocks across pages using [CONTINUES]True/False tags.

    verify_fn(prev_block, current_block) -> merged_block
    """
    if not text:
        return ""

    blocks = [b.strip() for b in re.split(r"(?=^\[CONTINUES\])", text.strip(), flags=re.MULTILINE) if b.strip()]
    merged: List[str] = []
    for block in blocks:
        flag_match = re.match(
            r"^\[CONTINUES\](True|False)\[/CONTINUES\]\s*(.*)$",
            block,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not flag_match:
            merged.append(block)
            continue

        flag = flag_match.group(1).lower()
        body = flag_match.group(2).strip()
        if not merged:
            merged.append(body)
            continue

        if flag == "true":
            prev_body = merged.pop()
            if verify_fn:
                combined_body = verify_fn(prev_body, body)
            else:
                combined_body = "\n".join([b for b in [prev_body, body] if b])
            merged.append(combined_body)
        else:
            merged.append(body)

    return "\n\n".join([b for b in merged if b])
if __name__ == "__main__":
    # file_path = "assets/10064.QC-HS - 03.09.2025 - Phiên bản 2.6.pdf"
    file_path = "assets/8558 QCCTD - 08.08.2024 - Phiên bản 2.5.pdf"
    results = strip_images_from_pdf(file_path)
    
    print(results)

    # import os

    # base_name = os.path.splitext(file_path)[0]

    # for page in results["pages"]:
    #     page_num = page["page_number"]
    #     output_file = f"{base_name}_{page_num}.txt"

    #     with open(output_file, "w", encoding="utf-8") as f:
    #         f.write(page["image_data"])

    #     print(f"Saved: {output_file}")
