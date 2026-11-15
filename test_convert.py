
import argparse
import re
from pathlib import Path

import fitz
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


# ==============================
# CẤU HÌNH
# ==============================

MIN_FONT_SIZE = 7
MAX_FONT_SIZE = 18
POSITION_TOLERANCE = 4
DEFAULT_FONT = "Times New Roman"


def set_cell_border(cell):
    """Thêm đường viền cho ô trong bảng Word."""
    tc_pr = cell._tc.get_or_add_tcPr()

    borders = tc_pr.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)

    for edge in ("top", "left", "bottom", "right"):
        tag = "w:" + edge
        element = borders.find(qn(tag))

        if element is None:
            element = OxmlElement(tag)
            borders.append(element)

        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), "4")
        element.set(qn("w:color"), "B8C0CC")


def configure_document(doc, width, height):
    """Thiết lập kích thước trang giống PDF."""
    section = doc.sections[-1]

    section.page_width = Pt(width)
    section.page_height = Pt(height)

    section.top_margin = Pt(35)
    section.bottom_margin = Pt(35)
    section.left_margin = Pt(45)
    section.right_margin = Pt(45)

    style = doc.styles["Normal"]
    style.font.name = DEFAULT_FONT
    style.font.size = Pt(10)

    style.paragraph_format.space_before = Pt(0)
    style.paragraph_format.space_after = Pt(0)
    style.paragraph_format.line_spacing = 1.0


def extract_text_blocks(page):
    """Lấy khối văn bản cùng vị trí và định dạng."""
    data = page.get_text("dict")
    blocks = []

    for block in data["blocks"]:
        if block.get("type") != 0:
            continue

        if not block.get("lines"):
            continue

        blocks.append(block)

    blocks.sort(key=lambda b: (round(b["bbox"][1], 1), b["bbox"][0]))
    return blocks


def rgb_from_pdf(color):
    """Chuyển mã màu PDF sang RGB."""
    r = (color >> 16) & 255
    g = (color >> 8) & 255
    b = color & 255

    return RGBColor(r, g, b)


def apply_span_format(run, span):
    """Giữ định dạng font từ PDF."""
    font = run.font

    font_name = span.get("font", "").lower()
    flags = span.get("flags", 0)

    font.name = DEFAULT_FONT

    size = span.get("size", 10)
    size = max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, size))
    font.size = Pt(size)

    font.bold = (
        bool(flags & 16)
        or "bold" in font_name
        or "black" in font_name
    )

    font.italic = (
        bool(flags & 2)
        or "italic" in font_name
        or "oblique" in font_name
    )

    color = span.get("color", 0)
    font.color.rgb = rgb_from_pdf(color)


def estimate_alignment(line, page_width):
    """Ước lượng căn lề dựa trên vị trí dòng."""
    x0, _, x1, _ = line["bbox"]

    center = (x0 + x1) / 2
    page_center = page_width / 2

    if abs(center - page_center) < 12:
        return WD_ALIGN_PARAGRAPH.CENTER

    if x0 > page_width * 0.65:
        return WD_ALIGN_PARAGRAPH.RIGHT

    return WD_ALIGN_PARAGRAPH.LEFT


def add_line(doc, line, page_width, previous_y=None):
    """Tạo đoạn Word từ một dòng PDF."""
    paragraph = doc.add_paragraph()

    paragraph.alignment = estimate_alignment(
        line, page_width
    )

    paragraph.paragraph_format.space_after = Pt(0)

    if previous_y is not None:
        gap = line["bbox"][1] - previous_y

        if gap > 5:
            paragraph.paragraph_format.space_before = Pt(
                min(gap, 25)
            )

    for span in line.get("spans", []):
        text = span.get("text", "")

        if not text:
            continue

        run = paragraph.add_run(text)
        apply_span_format(run, span)

    return paragraph


def extract_tables(page):
    """Nhận diện bảng bằng PyMuPDF."""
    try:
        finder = page.find_tables()
        return list(finder.tables)
    except Exception as exc:
        print(f"Không thể nhận diện bảng: {exc}")
        return []


def overlaps(rect1, rect2, tolerance=2):
    """Kiểm tra hai vùng có giao nhau không."""
    a = fitz.Rect(rect1)
    b = fitz.Rect(rect2)

    intersection = a & b

    if intersection.is_empty:
        return False

    return (
        intersection.width > tolerance
        and intersection.height > tolerance
    )


def add_table_to_word(doc, pdf_table):
    """Chuyển bảng PDF thành bảng Word chỉnh sửa được."""
    try:
        rows = pdf_table.extract()
    except Exception:
        return

    if not rows:
        return

    max_cols = max(len(row) for row in rows)

    if max_cols == 0:
        return

    table = doc.add_table(
        rows=len(rows),
        cols=max_cols
    )

    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True

    for row_index, row_data in enumerate(rows):
        for col_index, value in enumerate(row_data):
            cell = table.cell(row_index, col_index)

            cell.text = str(value) if value is not None else ""

            cell.vertical_alignment = (
                WD_CELL_VERTICAL_ALIGNMENT.CENTER
            )

            set_cell_border(cell)

            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.space_after = Pt(0)

                for run in paragraph.runs:
                    run.font.name = DEFAULT_FONT
                    run.font.size = Pt(9)

    doc.add_paragraph()


def page_to_word(doc, page):
    """Chuyển một trang PDF sang nội dung Word."""
    width = page.rect.width

    text_blocks = extract_text_blocks(page)
    pdf_tables = extract_tables(page)

    table_rects = [
        fitz.Rect(table.bbox)
        for table in pdf_tables
    ]

    elements = []

    # Thu thập các dòng văn bản không thuộc bảng
    for block in text_blocks:
        for line in block["lines"]:

            line_rect = fitz.Rect(line["bbox"])

            inside_table = any(
                overlaps(line_rect, table_rect)
                for table_rect in table_rects
            )

            if inside_table:
                continue

            elements.append({
                "type": "text",
                "y": line_rect.y0,
                "x": line_rect.x0,
                "data": line
            })

    # Thu thập bảng
    for table in pdf_tables:
        elements.append({
            "type": "table",
            "y": table.bbox[1],
            "x": table.bbox[0],
            "data": table
        })

    elements.sort(key=lambda e: (e["y"], e["x"]))

    previous_y = None

    for element in elements:
        if element["type"] == "text":
            line = element["data"]

            add_line(
                doc,
                line,
                width,
                previous_y
            )

            previous_y = line["bbox"][3]

        elif element["type"] == "table":
            add_table_to_word(
                doc,
                element["data"]
            )

            previous_y = element["data"].bbox[3]


def convert_pdf_to_word(pdf_path, docx_path):
    """Chuyển toàn bộ PDF sang Word."""
    pdf = fitz.open(str(pdf_path))

    if pdf.page_count == 0:
        raise ValueError("PDF không có trang nào.")

    doc = Document()

    first_page = pdf[0]

    configure_document(
        doc,
        first_page.rect.width,
        first_page.rect.height
    )

    total_pages = len(pdf)

    print(f"Tổng số trang: {total_pages}")

    for index, page in enumerate(pdf):

        print(f"Đang xử lý trang {index + 1}/{total_pages}")

        if index > 0:
            doc.add_page_break()

        page_to_word(doc, page)

    doc.save(str(docx_path))
    pdf.close()

    print("Hoàn thành!")
    print(f"File Word: {docx_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Chuyển PDF sang Word bằng PyMuPDF và python-docx"
    )

    parser.add_argument(
        "input",
        help="Đường dẫn file PDF"
    )

    parser.add_argument(
        "output",
        nargs="?",
        help="Đường dẫn DOCX đầu ra"
    )

    args = parser.parse_args()

    input_file = Path(args.input)

    if not input_file.exists():
        raise FileNotFoundError(
            f"Không tìm thấy file: {input_file}"
        )

    output_file = (
        Path(args.output)
        if args.output
        else input_file.with_suffix(".docx")
    )

    convert_pdf_to_word(
        input_file,
        output_file
    )
