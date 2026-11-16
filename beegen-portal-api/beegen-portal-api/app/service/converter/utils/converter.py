import os
import tempfile
import subprocess
import logging
from typing import Any, Optional, Union
from math import ceil
from openpyxl.utils import get_column_letter
from openpyxl.cell.rich_text import CellRichText

logger = logging.getLogger(__name__)

class ExcelFormatter:
    """
    - Wrap text
    - AutoFit Row Height tuyệt đối (không mất chữ)
    - KHÔNG chỉnh column width
    - Layout: fit ngang mặc định (Width=1, Height=0) để giảm scale dọc
    - Không auto set print_area theo calculate_dimension (tránh cắt hàng trống/border)
    - Tuỳ chọn print_area_strategy: 'keep' | 'clear' | 'full'
        - keep: giữ nguyên (mặc định)
        - clear: xoá print area (in toàn vùng 'used' của Excel/Calc)
        - full: ép vùng in = A1 : (last_col_letter, ws.max_row) để giữ cả hàng trống cuối
    - Tự bỏ filter, unhide rows/cols
    """
    def __init__(
        self,
        paper: str = "A4",
        landscape: bool = True,
        fit_width: int = 1,
        fit_height: int = 0,
        line_height_pt: float = 15.0,
        extra_pt: float = 2.0,
        margins_in: tuple = (0.3, 0.3, 0.3, 0.3, 0.2, 0.2),
        print_area_strategy: str = "keep",   # 'keep' | 'clear' | 'full'
        clear_filters_and_hidden: bool = True,
    ):
        self.paper = paper
        self.landscape = landscape
        self.fit_width = fit_width
        self.fit_height = fit_height
        self.line_height_pt = line_height_pt
        self.extra_pt = extra_pt
        self.margins_in = margins_in
        self.print_area_strategy = print_area_strategy
        self.clear_filters_and_hidden = clear_filters_and_hidden

    def _cell_text(self, value: Any) -> str:
        """Extract text from a cell, filtering out strikethrough text from RichText."""
        if value is None:
            return ""
        if isinstance(value, CellRichText):
            fragments: list[str] = []
            for segment in value:
                if isinstance(segment, str):
                    fragments.append(segment)
                    continue
                font = getattr(segment, "font", None)
                if font and getattr(font, "strike", False):
                    continue
                text = getattr(segment, "text", None)
                if text is None and hasattr(segment, "content"):
                    text = getattr(segment, "content")
                if text is None:
                    text = str(segment)
                if text:
                    fragments.append(text)
            return "".join(fragments)
        return str(value)

    def preprocess_workbook(self, xlsx_path: str, output_dir: str) -> str:
        from openpyxl import load_workbook
        from openpyxl.styles import Alignment

        wb = load_workbook(xlsx_path, data_only=True, rich_text=True)

        for ws in wb.worksheets:
            # (A) Optionally clear filters & unhide
            if self.clear_filters_and_hidden:
                try:
                    ws.auto_filter.ref = None
                except Exception:
                    pass
                # unhide rows
                for r in range(1, ws.max_row + 1):
                    rd = ws.row_dimensions.get(r)
                    if rd and rd.hidden:
                        rd.hidden = False
                        if rd.height == 0:
                            rd.height = None
                # unhide columns
                for c in range(1, ws.max_column + 1):
                    letter = get_column_letter(c)
                    cd = ws.column_dimensions.get(letter)
                    if cd and cd.hidden:
                        cd.hidden = False
                        if getattr(cd, "width", None) == 0:
                            cd.width = None

            # (B) Margins
            try:
                L, R, T, B, H, F = self.margins_in
                ws.page_margins.left = L
                ws.page_margins.right = R
                ws.page_margins.top = T
                ws.page_margins.bottom = B
                ws.page_margins.header = H
                ws.page_margins.footer = F
            except Exception:
                pass

            # (C) Paper & orientation
            try:
                ws.page_setup.paperSize = ws.PAPERSIZE_A3 if self.paper.upper() == "A3" else ws.PAPERSIZE_A4
                ws.page_setup.orientation = ws.ORIENTATION_LANDSCAPE if self.landscape else ws.ORIENTATION_PORTRAIT
            except Exception:
                pass

            # (D) Fit settings
            ws.sheet_properties.pageSetUpPr.fitToPage = True
            ws.page_setup.fitToWidth = self.fit_width
            ws.page_setup.fitToHeight = self.fit_height

            # (E) Print area strategy
            try:
                if self.print_area_strategy == "clear":
                    ws.print_area = None
                elif self.print_area_strategy == "full":
                    # Keep existing print area if defined by the user to preserve custom layouts
                    if not ws.print_area:
                        last_row, last_col = self._get_actual_dimensions(ws)
                        last_letter = get_column_letter(last_col)
                        ws.print_area = f"A1:{last_letter}{last_row}"
                else:  # 'keep' => không đụng tới print_area hiện có
                    pass
            except Exception:
                # nếu có lỗi, bỏ qua để không chặn flow
                pass

            # (F) Wrap text cho ô text và filter strikethrough
            for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=1, max_col=ws.max_column):
                for cell in row:
                    cell_text = self._cell_text(cell.value)
                    if cell_text:
                        cell.value = cell_text
                        cell.alignment = Alignment(
                            wrap_text=True,
                            horizontal=(cell.alignment.horizontal if cell.alignment else None),
                            vertical=(cell.alignment.vertical if cell.alignment else "top"),
                        )

            # (G) AutoFit Row Height tuyệt đối (không mất chữ)
            self._autofit_rows_absolute(ws)

        # Save ra file tạm
        tmp_xlsx = os.path.join(output_dir, os.path.basename(xlsx_path))
        wb.save(tmp_xlsx)
        wb.close()
        return tmp_xlsx

    # ---------- helpers ----------

    def _get_actual_dimensions(self, ws) -> tuple[int, int]:
        max_row = 1
        max_col = 1
        
        # Scan only existing cells in openpyxl's memory to avoid creating empty cell objects and save memory/time
        for (r, c), cell in ws._cells.items():
            val = cell.value
            if val is not None and str(val).strip() != "":
                if r > max_row:
                    max_row = r
                if c > max_col:
                    max_col = c
                    
        return max_row, max_col

    def _col_width_chars(self, ws, col_idx: int) -> float:
        letter = get_column_letter(col_idx)
        dim = ws.column_dimensions.get(letter)
        return dim.width if (dim and dim.width) else 8.43

    def _autofit_rows_absolute(self, ws):
        max_c = ws.max_column
        max_r = ws.max_row

        # Map merged cells
        cell_to_merge = {}
        for rng in ws.merged_cells.ranges:
            key = (rng.min_col, rng.min_row, rng.max_col, rng.max_row)
            for rr in range(rng.min_row, rng.max_row + 1):
                for cc in range(rng.min_col, rng.max_col + 1):
                    cell_to_merge[(rr, cc)] = key

        for r in range(1, max_r + 1):
            needed_lines_row = 1
            for c in range(1, max_c + 1):
                val = ws.cell(row=r, column=c).value
                if val is None:
                    continue

                text = self._cell_text(val)
                merge_key = cell_to_merge.get((r, c))
                if merge_key:
                    (min_c, min_r, max_c_m, max_r_m) = merge_key
                    if (r, c) != (min_r, min_c):
                        continue
                    chars_per_line = int(sum(self._col_width_chars(ws, cc) for cc in range(min_c, max_c_m + 1)))
                else:
                    chars_per_line = int(self._col_width_chars(ws, c))

                chars_per_line = max(chars_per_line, 1)

                logical_lines = text.splitlines() or [""]
                need = 0
                for line in logical_lines:
                    # nếu dòng không có space, vẫn wrap theo chars_per_line
                    need += 1 if not line else ceil(len(line) / chars_per_line)

                needed_lines_row = max(needed_lines_row, need)

            ws.row_dimensions[r].height = needed_lines_row * self.line_height_pt + self.extra_pt




class LibreOfficePdfConverter:
    def __init__(self, excel_formatter: Optional[ExcelFormatter] = None, timeout_sec: int = 300):
        self.excel_formatter = excel_formatter or ExcelFormatter()
        self.timeout_sec = timeout_sec

    def convert_to_pdf(self, file_path: str) -> Optional[str]:
        abs_path = os.path.abspath(file_path)
        base_dir = os.path.dirname(abs_path)
        base_name, ext = os.path.splitext(os.path.basename(abs_path))
        ext = ext.lower()

        pdf_path = os.path.join(base_dir, f"{base_name}.pdf")
        input_path = abs_path
        convert_filter = "pdf"
        temp_dir = None

        try:
            if ext in (".xlsx", ".xlsm"):
                temp_dir = tempfile.TemporaryDirectory(
                    prefix="xlsx_fmt_autofit_"
                )
                input_path = self.excel_formatter.preprocess_workbook(
                    abs_path,
                    temp_dir.name,
                )
                convert_filter = "pdf:calc_pdf_Export"
            elif ext in (".docx", ".doc"):
                convert_filter = "pdf:writer_pdf_Export"

            cmd = [
                "libreoffice",
                "--headless",
                "--convert-to",
                convert_filter,
                "--outdir",
                base_dir,
                input_path,
            ]
            proc = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=self.timeout_sec)
        except FileNotFoundError:
            logger.error("Lỗi: 'libreoffice' không tìm thấy trong PATH.")
            raise
        except subprocess.CalledProcessError as e:
            logger.error(f"Lỗi LibreOffice, code={e.returncode}\nstdout: {e.stdout}\nstderr: {e.stderr}")
            raise
        except subprocess.TimeoutExpired:
            logger.error("Lỗi: LibreOffice bị timeout.")
            raise
        finally:
            if temp_dir is not None:
                temp_dir.cleanup()

        if not os.path.exists(pdf_path):
            logger.error(f"Không thấy PDF: '{pdf_path}'\nstdout: {proc.stdout}\nstderr: {proc.stderr}")
            return None

        logger.info("Chuyển đổi thành công!")
        return pdf_path
