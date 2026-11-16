from docx import Document
from docx.shared import Inches
from docx.oxml.ns import qn
import tempfile
import os
from docx2pdf import convert
from pdf2image import convert_from_path
from PIL import Image, ImageDraw

def detect_bordered_tables(docx_path):
    """Phát hiện các table có border"""
    doc = Document(docx_path)
    bordered_tables = []
    
    for table_idx, table in enumerate(doc.tables):
        has_border = False
        
        # Kiểm tra border của table
        tbl = table._tbl
        tblPr = tbl.tblPr
        
        if tblPr is not None:
            # Kiểm tra table borders
            tblBorders = tblPr.find(qn('w:tblBorders'))
            if tblBorders is not None:
                # Có border setting
                borders = ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']
                for border in borders:
                    border_elem = tblBorders.find(qn(f'w:{border}'))
                    if border_elem is not None:
                        val = border_elem.get(qn('w:val'))
                        if val and val != 'none' and val != 'nil':
                            has_border = True
                            break
        
        # Kiểm tra border của từng cell
        if not has_border:
            for row in table.rows:
                for cell in row.cells:
                    tcPr = cell._tc.tcPr
                    if tcPr is not None:
                        tcBorders = tcPr.find(qn('w:tcBorders'))
                        if tcBorders is not None:
                            has_border = True
                            break
                if has_border:
                    break
        
        if has_border:
            bordered_tables.append((table_idx, table))
    
    return bordered_tables

def extract_bordered_tables_to_images(docx_path, output_dir):
    """Trích xuất chỉ các table có border thành ảnh"""
    
    # 1. Detect tables có border
    bordered_tables = detect_bordered_tables(docx_path)
    
    if not bordered_tables:
        print("Không tìm thấy table nào có border")
        return []
    
    # 2. Tạo document mới chỉ chứa các table có border
    doc = Document()
    
    original_doc = Document(docx_path)
    for table_idx, table in bordered_tables:
        # Copy table sang document mới
        new_table = doc.add_table(rows=len(table.rows), cols=len(table.columns))
        
        # Copy style và content
        for i, row in enumerate(table.rows):
            for j, cell in enumerate(row.cells):
                new_table.cell(i, j).text = cell.text
                # Copy cell formatting nếu có
                new_cell = new_table.cell(i, j)
                new_cell._element.clear_content()
                new_cell._element.append(cell._element)
        
        # Thêm page break giữa các table
        if table_idx < len(bordered_tables) - 1:
            doc.add_page_break()
    
    # 3. Lưu document mới
    temp_docx = os.path.join(output_dir, 'temp_bordered_tables.docx')
    doc.save(temp_docx)
    
    # 4. Chuyển thành PDF rồi thành ảnh
    temp_pdf = temp_docx.replace('.docx', '.pdf')
    convert(temp_docx, temp_pdf)
    
    # 5. Convert PDF to images
    images = convert_from_path(temp_pdf, dpi=300)
    
    image_paths = []
    for i, image in enumerate(images):
        img_path = os.path.join(output_dir, f'bordered_table_{i+1}.png')
        image.save(img_path)
        image_paths.append(img_path)
    
    # 6. Cleanup
    os.remove(temp_docx)
    os.remove(temp_pdf)
    
    return image_paths

# Sử dụng
docx_path = r"C:\Users\thanglq2\Downloads\BM02.8_Hop dong cho vay (HM_TSBD_VBNN).docx"
output_dir = r"D:\output_images"
os.makedirs(output_dir, exist_ok=True)

image_paths = extract_bordered_tables_to_images(docx_path, output_dir)
print(f"Đã tạo {len(image_paths)} ảnh từ các table có border")