"""
HTML output variant of logic.py. Mirrors the Markdown pipeline (prompts,
heading-tree tracking, continues-block merging) but the VLM emits standard
HTML tags instead of Markdown syntax. Kept fully separate from logic.py so
the existing Markdown renderer path (used by process()) is untouched.
"""
import re
from html.parser import HTMLParser
from typing import List, Dict, Any, Tuple, Optional

# Reuse everything that is format-agnostic (PDF -> images, image extraction,
# image-tag insertion already emits raw <img> HTML) straight from logic.py.
from beedoc_v3.renders.document_render.pdf_render.utils.logic import (  # noqa: F401
    render_pdf_to_images,
    normalize_text,
    strip_images_from_pdf,
    insert_images_into_text,
    get_doc_metadata_system_prompt,
    get_doc_metadata_user_prompt,
    parse_doc_metadata_response,
    should_skip_image,
    filter_repetitive_layout_images,
)

PDF_EXTRACT_HTML_SYSTEM_PROMPT_TEMPLATE = """Bạn là chuyên gia xử lý tài liệu PDF để chuẩn bị dữ liệu chất lượng cao cho hệ thống RAG.
Nhiệm vụ: Dựa trên NGỮ CẢNH ĐÃ TRÍCH XUẤT TRƯỚC ĐÓ và NỘI DUNG ẢNH CỦA TRANG HIỆN TẠI,
hãy tái cấu trúc nội dung của RIÊNG TRANG HIỆN TẠI sang HTML chuẩn, đảm bảo tính
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
- TUYỆT ĐỐI không tự ý thêm các mô tả hình ảnh hoặc chú thích ảnh (ví dụ: "Hình ảnh minh họa...", "*Hình ảnh...*", "Sơ đồ..."). Bỏ qua việc mô tả hình ảnh trong văn bản vì đã có luồng xử lý và mô tả hình ảnh riêng biệt.
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
- Sử dụng thẻ <h1> cho cấp 1, <h2> cho cấp 2, <h3> cho cấp 3, <h4> cho cấp 4,
  <h5> cho cấp 5, <h6> cho cấp 6
- Giới hạn tối đa 6 cấp heading (<h6>); KHÔNG dùng heading sâu hơn cấp 6
- Gán heading cho:
  - Những dòng là tiêu đề IN ĐẬM toàn dòng (không lẫn văn bản thường trên cùng dòng)
  - Đề mục có cấu trúc pháp lý/hành chính rõ ràng, kể cả khi không in đậm:
    Chương, Phần, Mục, Điều, Khoản (đứng độc lập), Phụ lục, Biểu mẫu, Schedule,
    Annex, Article, Section, Exhibit — dạng "Chương I", "Điều 3", "Phụ lục A"...
  - Tên của toàn bộ văn bản → gán heading cấp 1 (<h1>)
- TUYỆT ĐỐI không dùng <strong>...</strong> để đánh dấu tiêu đề → chuyển sang
  đúng cấp <h1>-<h6>
- Không chuyển sang heading nếu dòng đậm nằm bên trong danh sách, blockquote, code
KIỂM TRA THỨ TỰ HEADING TRƯỚC KHI GÁN (BẮT BUỘC):
  Trước khi gán một heading có số thứ tự (ví dụ: <h4>3. ...</h4>), kiểm tra cây tiêu đề:
  - Các heading cùng cấp có số thứ tự liền trước phải đã tồn tại trong cây
    Ví dụ: định gán <h4>3. thì trong cây phải đã có <h4>1. và <h4>2.
  - Nếu KHÔNG có heading liền trước trong cây → đây là dấu hiệu gán sai cấp;
    xem xét lại cấp độ heading cho phù hợp với ngữ cảnh tài liệu
  - Nếu CÓ đủ heading liền trước → gán bình thường
  - Nếu tài liệu thực sự bắt đầu từ số giữa chừng (ví dụ phụ lục bắt đầu từ
    Điều 10 tiếp nối từ phần trước) → chấp nhận, không ép tạo heading giả
### 4. Bảng biểu
- Đọc kỹ và hiểu chính xác cấu trúc: số cột, hàng, quan hệ giữa các ô
- KHÔNG bỏ sót bất kỳ dữ liệu nào; KHÔNG thêm thông tin không có trong ảnh
- Giữ nguyên thứ tự và vị trí các cột; dùng thẻ <table>, <thead>, <tbody>, <tr>,
  <th>, <td> chuẩn HTML
- Duy trì cấu trúc bảng nhất quán khi bảng kéo dài qua nhiều trang
- Nếu context trạng thái báo "Đang trong bảng: CÓ":
  - BẮT BUỘC kế thừa đúng header và số cột từ minh họa trong context
  - KHÔNG tự thêm <thead> mới vào output — tiếp tục thẳng vào các hàng <tr><td>
  - CHỈ xuất <thead> mới nếu trang hiện tại có dòng tiêu đề cột mới rõ ràng trong ảnh
- Nếu phát hiện heading nằm trong bảng (dạng I, 1, 1.1,...):
  - Phân tách thành bảng <table> mới ngay sau heading đó
  - Bảng mới MẶC ĐỊNH kế thừa toàn bộ tên cột của bảng trước
  - CHỈ đổi tên cột nếu có dòng tiêu đề cột mới rõ ràng trong ảnh
- Ô gộp (merged cells):
  - Nếu một ô trải rộng qua NHIỀU CỘT (gộp ngang): dùng thuộc tính
    `colspan="n"` trên <th>/<td> đó, KHÔNG lặp lại nội dung ô ở các cột bị gộp
  - Nếu một ô trải dài qua NHIỀU HÀNG (gộp dọc): dùng thuộc tính
    `rowspan="n"` trên <th>/<td> đó ở hàng đầu tiên, KHÔNG tạo <td> rỗng lặp
    lại ở các hàng bị gộp phía dưới
  - Nếu một ô vừa gộp ngang vừa gộp dọc: dùng cả hai thuộc tính
    `colspan="n" rowspan="m"` trên cùng một ô
  - Đếm kỹ số ô thực tế mỗi hàng sau khi trừ các ô bị gộp — tổng số <td>/<th>
    cộng với colspan phải khớp đúng số cột thực của bảng
- Bảng không có đường viền/kẻ ô (thường gặp trong đơn từ, công văn, biểu mẫu
  hành chính dạng scan):
  - Nội dung được căn theo CỘT bằng khoảng cách/tab dù không có đường kẻ vẫn
    PHẢI được nhận diện là bảng và chuyển sang <table> nếu có từ 2 cột dữ liệu
    trở lên lặp lại nhất quán qua nhiều hàng (ví dụ: "Họ tên .... Chức vụ ....",
    "STT | Nội dung | Số lượng | Đơn giá" liệt kê nhiều dòng)
  - KHÔNG nhầm lẫn với danh sách nhãn-giá-trị đơn lẻ (label: value) xuất hiện
    một lần duy nhất, không lặp lại theo hàng — trường hợp này giữ nguyên dạng
    đoạn văn/danh sách, KHÔNG ép thành bảng
  - Khi không chắc chắn giữa bảng-không-viền và danh sách thông thường: nếu có
    từ 2 hàng trở lên cùng chung cấu trúc cột → ưu tiên coi là bảng
### 5. Nhận diện và xử lý steps/danh sách quy trình
Nhận diện steps/quy trình khi thấy bất kỳ dấu hiệu nào sau đây:
- Danh sách có đánh số mô tả một quy trình hoặc thủ tục
- Nội dung có từ/cụm từ tuần tự rõ ràng: First, Next, Then, Finally, Bước 1, Tiếp theo...
- Nội dung mô tả cách thực hiện một tác vụ hoặc quy trình
- Tiêu đề mục là: Instructions, Procedure, How to, Guide, Hướng dẫn, Quy trình...
- Nhiều đoạn văn liên tiếp rõ ràng thuộc cùng một quy trình
Quy tắc xử lý:
- Dùng <ol> cho danh sách có thứ tự (steps/quy trình), <ul> cho danh sách không thứ tự
- Giữ toàn bộ nội dung steps/danh sách nguyên vẹn trong output trang hiện tại
- Nếu steps từ trang trước tiếp tục sang trang này → tiếp nối liền mạch (các <li>
  bổ sung), không thêm heading giả hay ngắt cấu trúc
- Bảo toàn cấu trúc phân cấp của danh sách (danh sách lồng nhau <ul>/<ol> trong <li>)
### 6. Layout đa cột
- Nếu trang có bố cục nhiều cột:
  - Layout 2 cột kiểu báo: đọc hết cột trái từ trên xuống, rồi đến cột phải
  - Layout song ngữ (trái-phải): ưu tiên cột ngôn ngữ chính; nếu không xác định
    được thì đọc cột trái trước
  - Đảm bảo không trộn lẫn nội dung giữa các cột
  - Bảo toàn khoảng cách đoạn (dùng nhiều thẻ <p> riêng biệt) theo bản gốc
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
  vào cuối đoạn văn (thẻ <p>) gần nhất có liên quan
- Sau khi đã gán xong toàn bộ citation: loại bỏ hoàn toàn phần footer
- Output cuối KHÔNG chứa bất kỳ dòng footer hay ký hiệu [n] nào
### 8. Nội dung đặc biệt
- Flowchart/sơ đồ luồng: mô tả từng bước theo đúng chiều luồng bằng <ol>,
  dùng → để thể hiện chiều đi giữa các bước
- Diagram/hình minh họa có text liên quan: trích xuất phần text có liên quan đến
  nội dung xung quanh, đặt trong thẻ <p>
- Hình ảnh không extract được text: thêm mô tả alt text ngắn gọn phản ánh nội dung
- Screenshot: BỎ QUA hoàn toàn, không mô tả, không thêm alt text
- Trang scan (OCR): xử lý như trang thường, giữ nguyên định dạng text đã nhận diện
- FAQ: tách mỗi cặp câu hỏi-trả lời thành đoạn riêng — câu hỏi bọc trong
  <p><strong>...</strong></p>, phần trả lời trong <p> ngay bên dưới
### 9. Độ chính xác
- CỰC KỲ CẨN THẬN với nhận diện số và ký tự
- Tránh nhầm lẫn: 2 với 1, 0 với O, l với 1 hoặc I
- Kiểm tra kỹ mọi số liệu và dữ liệu định lượng
### 10. Cấu trúc và định dạng
- Giữ nguyên cấu trúc phân đoạn, mục con, tiểu mục; KHÔNG sắp xếp lại
- Mỗi đoạn văn bọc trong thẻ <p> riêng biệt; giữ khoảng cách đoạn theo bản gốc
- Bảo toàn cấu trúc phân cấp của danh sách bullet (<ul>) và danh sách số (<ol>)
- Chữ đậm: <strong>text</strong> | Chữ nghiêng: <em>text</em> | Code: <code>text</code>
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
Mỗi trang chỉ có MỘT flag [CONTINUES] duy nhất, đặt ở đầu output (KHÔNG phải
thẻ HTML, giữ nguyên dạng text thuần này để hệ thống xử lý), thể hiện quan hệ
của PHẦN ĐẦU TRANG với phần cuối trang trước.
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
  nội dung HTML thuần của toàn trang...
Quy tắc:
  - Heading (<h1> đến <h6>): CHỈ gán khi trang THỰC SỰ có tiêu đề đó trong ảnh
  - Trang tiếp nối (True): bắt đầu thẳng vào nội dung, không thêm heading giả
  - CHỈ trả về các thẻ HTML thuần (p, h1-h6, table/thead/tbody/tr/th/td, ul/ol/li,
    strong, em, code, blockquote); KHÔNG bọc trong ```html hoặc markdown code block
  - KHÔNG xuất thẻ <html>, <head>, <body> — chỉ xuất các thẻ nội dung nói trên
  - KHÔNG thêm chú thích, mô tả, giải thích ngoài lề
  - KHÔNG bịa đặt thông tin không có trong tài liệu gốc
Ví dụ 1 — trang bắt đầu bằng heading mới:
  [CONTINUES]False[/CONTINUES]
  <h2>Chương II. Điều khoản thanh toán</h2>
  <h3>Điều 5. Phương thức thanh toán</h3>
  <p>Bên mua có nghĩa vụ thanh toán toàn bộ giá trị hợp đồng trong vòng 30 ngày...</p>
Ví dụ 2 — trang tiếp nối giữa chừng đoạn văn:
  [CONTINUES]True[/CONTINUES]
  <p>phải được lập thành văn bản và có chữ ký xác nhận của cả hai bên.</p>
  <h3>Điều 6. Đồng tiền thanh toán</h3>
  <p>Mọi khoản thanh toán được thực hiện bằng đồng Việt Nam (VNĐ)...</p>
Ví dụ 3 — trang tiếp nối bảng, ô đầy đủ (False dù bảng vẫn tiếp tục):
  [CONTINUES]False[/CONTINUES]
  <table><tbody>
  <tr><td>SP003</td><td>Màn hình LCD 27"</td><td>15</td><td>4.500.000</td><td>67.500.000</td></tr>
  <tr><td>SP004</td><td>Bàn phím cơ</td><td>30</td><td>850.000</td><td>25.500.000</td></tr>
  </tbody></table>
Ví dụ 4 — trang tiếp nối bảng, ô bị cắt đứt từ trang trước:
  [CONTINUES]True[/CONTINUES]
  <table><tbody>
  <tr><td>được áp dụng trong trường hợp thanh toán chậm hơn 30 ngày.</td><td>15</td><td>4.500.000</td></tr>
  <tr><td>SP004</td><td>Bàn phím cơ</td><td>30</td><td>850.000</td></tr>
  </tbody></table>
Ví dụ 5 — trang tiếp nối steps của cùng quy trình:
  [CONTINUES]True[/CONTINUES]
  <ol start="3">
  <li>Kiểm tra lại toàn bộ thông tin trước khi ký kết.</li>
  <li>Gửi bản scan cho bên B trong vòng 24 giờ.</li>
  </ol>
=====================================
VI. KIỂM TRA CUỐI TRƯỚC KHI XUẤT
=====================================
Trước khi trả kết quả, tự kiểm tra:
- [ ] Toàn trang chỉ có đúng MỘT flag [CONTINUES] ở đầu không?
- [ ] Flag được xác định dựa trên PHẦN ĐẦU trang không?
- [ ] Với bảng: flag dựa trên nội dung ô (bị cắt hay đầy đủ), không phải việc
      bảng có tiếp tục không?
- [ ] Với steps: trang tiếp tục cùng quy trình → True không?
- [ ] Heading <h1>-<h6> chỉ xuất hiện khi trang thực sự có tiêu đề đó trong ảnh không?
- [ ] Trang tiếp nối có bị ép thêm heading không cần thiết không?
- [ ] Có dòng nào dùng <strong>Tiêu đề</strong> thay vì <h#>Tiêu đề</h#> không?
- [ ] Heading có nhất quán với cây tiêu đề không?
- [ ] Bảng tiếp nối có tự thêm <thead> không cần thiết không?
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
- [ ] Output có lẫn code block ```html hoặc thẻ <html>/<body> không?
Nếu phát hiện bất kỳ vi phạm nào → sửa ngay trước khi xuất kết quả cuối.
"""

PDF_EXTRACT_HTML_USER_PROMPT_TEMPLATE = """Hãy tái cấu trúc nội dung TRANG HIỆN TẠI dưới đây:
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

PDF_SUMMARY_HTML_SYSTEM_PROMPT_TEMPLATE = """Bạn là hệ thống theo dõi TRẠNG THÁI tài liệu PDF qua nhiều trang.
Nhiệm vụ: Dựa trên CONTEXT TRƯỚC, CÂY TIÊU ĐỀ HIỆN TẠI và NỘI DUNG TRANG HIỆN TẠI,
cập nhật đồng thời:
  1. CONTEXT TRẠNG THÁI — trạng thái cấu trúc đang dở để trang tiếp theo xử lý đúng
  2. CÂY TIÊU ĐỀ — toàn bộ hệ thống tiêu đề tích lũy từ đầu tài liệu đến trang này
==============================
QUY TẮC CẬP NHẬT CONTEXT TRẠNG THÁI:
==============================
1. Heading đang mở:
   - Trang có heading mới → cập nhật sang heading mới nhất (heading cuối cùng
     xuất hiện trên trang), ghi kèm cấp độ
     Ví dụ: <h3>Điều 5. Phương thức thanh toán</h3>
   - Trang không có heading mới → giữ nguyên từ context trước
2. Cây tiêu đề:
   - Duyệt toàn bộ heading (<h1> đến <h6>) trong HTML trang hiện tại theo thứ tự
     từ trên xuống dưới
   - Bổ sung các heading mới vào đúng vị trí trong cây tiêu đề hiện tại
   - Định dạng thụt lề phản ánh đúng cấp bậc, dùng đúng thẻ <h#> làm ký hiệu cấp:
     <h1> Cấp 1
       <h2> Cấp 2
         <h3> Cấp 3
           <h4> Cấp 4
             <h5> Cấp 5
               <h6> Cấp 6
   - KHÔNG xóa, KHÔNG sửa, KHÔNG rút gọn bất kỳ heading nào đã có trong cây cũ
   - Trang không có heading mới → giữ nguyên cây tiêu đề cũ
3. Bảng:
   Bước 1 — Xác định bảng có đang dở không:
   - Kiểm tra cuối cùng của HTML: có phải đang trong một <table> chưa đóng thẻ
     </table> hợp lý (tức là hàng <tr> cuối là dữ liệu bảng) không
   - VÀ không có đoạn văn, heading mới xuất hiện SAU bảng đó
   Bước 2 — Nếu bảng đang dở, xác định trạng thái ô cuối:
   - HOÀN CHỈNH: ô <td> cuối cùng của hàng <tr> cuối cùng có nội dung đầy đủ, câu hoàn chỉnh
   - BỊ CẮT: ô cuối cùng có nội dung bị ngắt giữa chừng (câu chưa kết thúc, nội
     dung rõ ràng còn tiếp)
   - Thông tin này quyết định flag [CONTINUES] của trang tiếp theo
   Bước 3 — Ghi context bảng:
   - Đang trong bảng: CÓ
   - Header: trích xuất chính xác dòng header từ HTML (nội dung các <th> theo thứ tự)
   - Số cột: đếm chính xác
   - Trạng thái ô cuối: HOÀN CHỈNH / BỊ CẮT
   - Minh họa: 3 hàng dữ liệu thực từ HTML (không bịa đặt), dùng để trang
     sau nhận diện đúng cấu trúc cột
   Nếu bảng đã kết thúc hoàn toàn trong trang này:
   - Đang trong bảng: KHÔNG
3. Steps/danh sách quy trình:
   Xác định steps có đang dở không:
   - Nhận diện steps theo các dấu hiệu: <ol> mô tả quy trình, từ tuần tự
     (First/Next/Then/Finally/Bước.../Tiếp theo...), tiêu đề mục là Instructions/
     Procedure/How to/Guide/Hướng dẫn/Quy trình, nhiều đoạn văn thuộc cùng quy trình
   - Kiểm tra: <li> cuối trang có phải là bước chưa hoàn chỉnh của quy trình không
   - Và chưa có dấu hiệu kết thúc quy trình (Final Step, kết luận, heading mới
     không liên quan)
   Nếu steps đang dở:
   - Đang trong steps: CÓ
   - Tên quy trình: [tên hoặc mô tả ngắn của quy trình đang thực hiện]
   - Bước cuối đã xuất hiện: [số thứ tự và nội dung ngắn gọn của bước cuối]
   Nếu steps đã kết thúc:
   - Đang trong steps: KHÔNG
4. Danh sách thông thường (không phải quy trình):
   - Logic tương tự bảng: kiểm tra <li> cuối có phải mục danh sách chưa kết thúc
   - Nếu đang dở: ghi kiểu (<ul>/<ol>) và nội dung mục cuối
==============================
OUTPUT:
==============================
Xuất ra hai phần, phân tách bằng nhãn, không giải thích thêm:
---CONTEXT---
- Heading đang mở: [cấp + nội dung đầy đủ]
- Đang trong bảng: CÓ / KHÔNG
  (nếu CÓ:)
  - Header: cột 1 | cột 2 | cột 3 | ...
  - Số cột: [n]
  - Trạng thái ô cuối: HOÀN CHỈNH / BỊ CẮT
  - Minh họa:
    | cột 1     | cột 2     | cột 3     |
    |-----------|-----------|-----------|
    | [từ HTML] | [từ HTML] | [từ HTML] |
    | [từ HTML] | [từ HTML] | [từ HTML] |
    | [từ HTML] | [từ HTML] | [từ HTML] |
- Đang trong steps: CÓ / KHÔNG
  (nếu CÓ:)
  - Tên quy trình: [mô tả ngắn]
  - Bước cuối đã xuất hiện: [số thứ tự + nội dung ngắn]
- Đang trong danh sách: CÓ / KHÔNG
  (nếu CÓ:)
  - Kiểu: <ul> / <ol>
  - Mục cuối đã xuất hiện: [nội dung ngắn gọn]
---HEADING_TREE---
<h1> [tên tài liệu]
  <h2> [phần 1]
    <h3> [tiểu mục 1.1]
      <h4> [tiểu mục 1.1.1]
        <h5> [tiểu mục 1.1.1.1]
          <h6> [tiểu mục 1.1.1.1.1]
    <h3> [tiểu mục 1.2]
  <h2> [phần 2]
    <h3> [tiểu mục 2.1]
"""

PDF_SUMMARY_HTML_USER_PROMPT_TEMPLATE = """Hãy cập nhật context và cây tiêu đề từ nội dung sau:
==============================
CONTEXT TRƯỚC:
==============================
{last_summary}
==============================
CÂY TIÊU ĐỀ HIỆN TẠI:
==============================
{heading_tree}
==============================
NỘI DUNG TRANG HIỆN TẠI:
==============================
{current_content}
"""

MERGE_VERIFY_HTML_SYSTEM_PROMPT_TEMPLATE = """Bạn đang kiểm tra và nối nội dung giữa 2 TRANG có nhãn CONTINUES=True.

Mục tiêu:
- Giữ nguyên nội dung gốc và định dạng HTML (table, list, heading, blockquote, code).
- Chỉ chỉnh sửa ở mức cần thiết để nối liền mạch giữa 2 trang.
- Loại bỏ các dòng footer lặp lại/nhiễu ở cuối trang khi nối (ví dụ: "Văn bản này là tài sản của MB. Mọi hành động sử dụng, sao chép, tiết lộ, cung cấp thông tin không đúng với quy định của MB đều không được phép.")

Yêu cầu xử lý:
1. Nối liền mạch bảng: nếu trang trước kết thúc bằng hàng <tr> của một <table> và
   trang sau bắt đầu là hàng <tr> tiếp theo → ghép thành một <table> hoàn chỉnh,
   không lặp lại <thead>.
2. Nối danh sách/steps: nếu trang trước đang là <ul>/<ol> và trang sau tiếp tục →
   ghép các <li> vào cùng một <ul>/<ol>, không tách thành danh sách mới.
3. Không được thêm nội dung mới, không diễn giải lại. Không xóa nội dung hợp lệ.
4. Chỉ loại bỏ footer/ghi chú bản quyền lặp lại hoặc câu cảnh báo thuộc footer.
5. Kết quả CHỈ là các thẻ HTML đã ghép, KHÔNG kèm giải thích, KHÔNG bọc trong
   ```html hoặc thẻ <html>/<body>.
6. Đầu vào có thể chứa dòng [CONTINUES]True/False[/CONTINUES] ở đầu mỗi trang. ĐẦU RA KHÔNG chứa dòng [CONTINUES].
"""

MERGE_VERIFY_HTML_USER_PROMPT_TEMPLATE = """Hãy nối nội dung của hai trang dưới đây:

--- TRANG TRƯỚC ---
{prev_block}

--- TRANG HIỆN TẠI ---
{current_block}
"""


def get_pdf_html_system_prompt() -> str:
    return PDF_EXTRACT_HTML_SYSTEM_PROMPT_TEMPLATE


def get_pdf_html_user_prompt(context_summary: str, heading_tree: str = "") -> str:
    return PDF_EXTRACT_HTML_USER_PROMPT_TEMPLATE.format(
        last_summary=context_summary or "",
        heading_tree=heading_tree or "",
    )


def get_summary_html_system_prompt() -> str:
    return PDF_SUMMARY_HTML_SYSTEM_PROMPT_TEMPLATE


def _strip_html_tags_for_summary(html_text: str) -> str:
    """Convert HTML content to plain text for use in summary prompts.

    Stripping HTML tags before passing content to summary_context_node
    reduces payload size significantly and prevents Gateway WAF from
    throttling/blocking requests that contain raw HTML tags like <ul>,
    <table>, <h1>-<h6> in the JSON body.

    The summary LLM only needs structural/semantic context (headings,
    paragraph text, list items) to update the document state tracker —
    it does not need to see or reproduce HTML markup.
    """
    if not html_text:
        return ""
    # Remove the [CONTINUES] control tag first
    text = re.sub(
        r"^\s*\[CONTINUES\](?:True|False)\[/CONTINUES\]\s*",
        "",
        html_text.strip(),
        count=1,
        flags=re.IGNORECASE,
    )
    # Convert block-level tags to newlines for readability
    text = re.sub(r"<(?:br|/p|/div|/li|/tr|/td|/th|/h[1-6])[^>]*>", "\n", text, flags=re.IGNORECASE)
    # Strip all remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def get_summary_html_user_prompt(last_summary: str, heading_tree: str, current_content: str) -> str:
    # Strip HTML tags from content before including in prompt to avoid
    # Gateway WAF throttling on HTML tags in request body, and to reduce
    # payload size (summary LLM only needs semantic/structural context).
    plain_content = _strip_html_tags_for_summary(current_content or "")
    return PDF_SUMMARY_HTML_USER_PROMPT_TEMPLATE.format(
        last_summary=last_summary or "",
        heading_tree=heading_tree or "",
        current_content=plain_content,
    )


def _escape_html_for_gateway(html_text: str) -> str:
    """HTML-encode angle brackets so WAF treats the body as plain text.

    The MB Bank Gateway WAF throttles/blocks requests whose JSON body
    contains raw HTML angle brackets (<, >), interpreted as HTML markup.
    Replacing < with &lt; and > with &gt; makes the content opaque to the
    WAF while remaining fully readable by LLMs (which understand HTML entities
    just as well as raw tags). Use this for merge_verify_llm which must see
    the HTML structure to properly join tables and lists across page breaks.
    """
    if not html_text:
        return ""
    return html_text.replace("<", "&lt;").replace(">", "&gt;")


def extract_html_boundary_blocks(
    prev_html: str, current_html: str, max_boundary_len: int = 1500
) -> Tuple[str, str, str, str]:
    """Splits prev_html into (prev_prefix, prev_tail) and current_html into
    (current_head, current_suffix). Isolating the boundary tail of page N-1 and
    the boundary head of page N keeps the prompt and response for
    merge_verify_llm extremely small, reducing inference time from ~70s down to
    ~2-5s per call.
    """
    prev_clean = (prev_html or "").strip()
    curr_clean = (current_html or "").strip()

    pattern = r"(?i)(?=<(?:\/?(?:h[1-6]|p|table|ul|ol|div|blockquote)|tr|tbody)[\s>])"
    prev_parts = [p for p in re.split(pattern, prev_clean) if p]

    if len(prev_parts) > 1:
        prev_prefix = "".join(prev_parts[:-1])
        prev_tail = prev_parts[-1]
    else:
        prev_prefix = ""
        prev_tail = prev_clean

    if len(prev_tail) > max_boundary_len:
        split_idx = len(prev_tail) - max_boundary_len
        prev_prefix += prev_tail[:split_idx]
        prev_tail = prev_tail[split_idx:]

    curr_parts = [p for p in re.split(pattern, curr_clean) if p]

    if len(curr_parts) > 1:
        current_head = curr_parts[0]
        current_suffix = "".join(curr_parts[1:])
    else:
        current_head = curr_clean
        current_suffix = ""

    if len(current_head) > max_boundary_len:
        current_suffix = current_head[max_boundary_len:] + current_suffix
        current_head = current_head[:max_boundary_len]

    return prev_prefix, prev_tail, current_head, current_suffix


def reconstruct_merged_boundary(prev_prefix: str, merged_boundary: str, current_suffix: str) -> str:
    """Recombines the unchanged page prefix, the LLM-merged boundary, and the
    unchanged page suffix."""
    parts = []
    if prev_prefix and prev_prefix.strip():
        parts.append(prev_prefix.strip())
    if merged_boundary and merged_boundary.strip():
        parts.append(merged_boundary.strip())
    if current_suffix and current_suffix.strip():
        parts.append(current_suffix.strip())
    return "\n".join(parts)


def get_merge_verify_html_system_prompt() -> str:
    return MERGE_VERIFY_HTML_SYSTEM_PROMPT_TEMPLATE


def get_merge_verify_html_user_prompt(prev_block: str, current_block: str) -> str:
    # HTML-encode angle brackets to avoid Gateway WAF throttling.
    # LLMs understand &lt;tag&gt; just as well as <tag>.
    encoded_prev = _escape_html_for_gateway(prev_block or "")
    encoded_current = _escape_html_for_gateway(current_block or "")
    return MERGE_VERIFY_HTML_USER_PROMPT_TEMPLATE.format(
        prev_block=encoded_prev,
        current_block=encoded_current,
    )




def _filter_heading_tree_html(
    heading_tree_text: Optional[str],
) -> Optional[str]:
    """Same ancestor/sibling filtering as logic._filter_heading_tree, but parses
    <h1>-<h6> tags instead of #-###### Markdown heading markers."""
    if not heading_tree_text:
        return heading_tree_text

    parsed: list[tuple[int, str]] = []
    for line in heading_tree_text.splitlines():
        m = re.match(r"^\s*<h([1-6])>", line.strip(), flags=re.IGNORECASE)
        if m:
            parsed.append((int(m.group(1)), line))

    if not parsed:
        return heading_tree_text

    current_idx = len(parsed) - 1
    current_level = parsed[current_idx][0]

    ancestors: dict[int, int] = {}
    for i in range(current_idx - 1, -1, -1):
        lvl = parsed[i][0]
        if lvl < current_level and lvl not in ancestors:
            ancestors[lvl] = i

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
        for i, (lvl, _) in enumerate(parsed):
            if lvl == 1:
                sibling_indices.add(i)
    else:
        sibling_indices.add(current_idx)

    keep = set(ancestors.values()) | sibling_indices
    result_lines = [parsed[i][1] for i in sorted(keep)]
    return "\n".join(result_lines) if result_lines else None


def parse_summary_html_sections(summary_output: str) -> Dict[str, Optional[str]]:
    """Same as logic.parse_summary_sections but applies the HTML heading-tree filter."""
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

    heading_tree = _filter_heading_tree_html(raw_heading_tree)

    return {"page_context": page_context, "heading_tree": heading_tree}


def strip_continues_tag_html(text: str) -> str:
    """Removes a leading [CONTINUES]True/False[/CONTINUES] control tag, if
    present. Used to sanitize page content before it's fed into a prompt as
    context (so the model isn't shown the tag and doesn't echo it back) and
    to sanitize LLM output as a safety net in case it does anyway."""
    if not text:
        return text or ""
    return re.sub(
        r"^\s*\[CONTINUES\](?:True|False)\[/CONTINUES\]\s*",
        "",
        text.strip(),
        count=1,
        flags=re.IGNORECASE,
    )


def merge_continues_blocks_html(text: str, verify_fn=None) -> str:
    """Identical splitting/merging logic to logic.merge_continues_blocks; the
    [CONTINUES] control tag is format-agnostic plain text, so this only needs
    to exist separately to keep the HTML pipeline fully decoupled from the
    Markdown one (verify_fn callers pass HTML blocks here)."""
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
                combined_body = "".join([b for b in [prev_body, body] if b])
            merged.append(combined_body)
        else:
            merged.append(body)

    # HTML block tags already delimit content on their own, so blocks are
    # joined without inserting extra newlines (unlike the Markdown path,
    # where blank lines are semantically meaningful paragraph separators).
    return "".join([b for b in merged if b])
