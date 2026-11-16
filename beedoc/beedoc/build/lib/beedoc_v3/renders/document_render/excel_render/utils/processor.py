import numpy as np
import openpyxl
import re
from typing import List, Dict, Tuple, Any, Optional
from openpyxl.cell.rich_text import CellRichText
from openpyxl.utils.cell import coordinate_from_string

from beedoc_v3.utils.image_processor import ImageProcessor


def _col_letter(idx: int) -> str:
    letters = ""
    while idx:
        idx, rem = divmod(idx - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, CellRichText):
        fragments: List[str] = []
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


def _image_anchor_to_cell(image: Any) -> Optional[Tuple[int, int]]:
    anchor = getattr(image, "anchor", None)
    if anchor is None:
        return None
    if isinstance(anchor, str):
        try:
            col_letter, row = coordinate_from_string(anchor)
            col = openpyxl.utils.column_index_from_string(col_letter)
            return row, col
        except Exception:
            return None
    if hasattr(anchor, "_from"):
        marker = anchor._from
        row = getattr(marker, "row", None)
        col = getattr(marker, "col", None)
        if row is not None and col is not None:
            return int(row) + 1, int(col) + 1
    if hasattr(anchor, "row") and hasattr(anchor, "col"):
        return int(anchor.row) + 1, int(anchor.col) + 1
    return None


def _build_merged_map(ws) -> Dict[Tuple[int, int], Tuple[int, int]]:
    merged_map: Dict[Tuple[int, int], Tuple[int, int]] = {}
    for rng in ws.merged_cells.ranges:
        anchor = (rng.min_row, rng.min_col)
        for r in range(rng.min_row, rng.max_row + 1):
            for c in range(rng.min_col, rng.max_col + 1):
                merged_map[(r, c)] = anchor
    return merged_map


def _effective_used_range(ws) -> Optional[Tuple[int, int, int, int]]:
    min_row = None
    min_col = None
    max_row = 0
    max_col = 0

    for row in ws.iter_rows(values_only=False):
        for cell in row:
            text = _cell_text(cell.value)
            if text.strip():
                r = cell.row
                c = cell.column
                min_row = r if min_row is None else min(min_row, r)
                min_col = c if min_col is None else min(min_col, c)
                max_row = max(max_row, r)
                max_col = max(max_col, c)

    for rng in ws.merged_cells.ranges:
        min_row = rng.min_row if min_row is None else min(min_row, rng.min_row)
        min_col = rng.min_col if min_col is None else min(min_col, rng.min_col)
        max_row = max(max_row, rng.max_row)
        max_col = max(max_col, rng.max_col)

    for image in getattr(ws, "_images", []) or []:
        anchor = _image_anchor_to_cell(image)
        if anchor:
            r, c = anchor
            min_row = r if min_row is None else min(min_row, r)
            min_col = c if min_col is None else min(min_col, c)
            max_row = max(max_row, r)
            max_col = max(max_col, c)

    if min_row is None or min_col is None:
        return None
    return min_row, min_col, max_row, max_col


def _build_binary_matrix(ws, bounds: Tuple[int, int, int, int]) -> "np.ndarray":
    min_row, min_col, max_row, max_col = bounds
    rows = max_row - min_row + 1
    cols = max_col - min_col + 1
    matrix = np.zeros((rows, cols), dtype=np.uint8)

    for rng in ws.merged_cells.ranges:
        for r, c in rng.cells:
            if min_row <= r <= max_row and min_col <= c <= max_col:
                matrix[r - min_row, c - min_col] = 1

    for r in range(min_row, max_row + 1):
        for c in range(min_col, max_col + 1):
            cell = ws.cell(r, c)
            text = _cell_text(cell.value)
            if cell.data_type == "f" and text.strip() == "":
                continue
            if text.strip():
                matrix[r - min_row, c - min_col] = 1

    for image in getattr(ws, "_images", []) or []:
        anchor = _image_anchor_to_cell(image)
        if anchor:
            r, c = anchor
            if min_row <= r <= max_row and min_col <= c <= max_col:
                matrix[r - min_row, c - min_col] = 1

    return matrix


def _find_split_points(has_data: "np.ndarray") -> List[Tuple[int, int]]:
    splits: List[Tuple[int, int]] = []
    gap_start = None

    for idx, has in enumerate(has_data):
        if not has:
            if gap_start is None:
                gap_start = idx
        else:
            if gap_start is not None:
                if (idx - gap_start) >= 2:
                    splits.append((gap_start, idx - 1))
                gap_start = None

    if gap_start is not None and (len(has_data) - gap_start) >= 2:
        splits.append((gap_start, len(has_data) - 1))

    return splits


def _splits_to_bands(total: int, splits: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    cut_points = [0]
    for gap_start, gap_end in splits:
        cut_points.append(gap_start)
        cut_points.append(gap_end + 1)
    cut_points.append(total)

    bands: List[Tuple[int, int]] = []
    for idx in range(0, len(cut_points) - 1, 2):
        start = cut_points[idx]
        end = cut_points[idx + 1] - 1
        if start <= end:
            bands.append((start, end))
    return bands


def detect_sheet_zones(ws) -> List[Dict[str, int]]:
    bounds = _effective_used_range(ws)
    if not bounds:
        return []
    min_row, min_col, max_row, max_col = bounds

    matrix = _build_binary_matrix(ws, bounds)

    row_has_data = matrix.any(axis=1)
    col_has_data = matrix.any(axis=0)

    row_bands = _splits_to_bands(matrix.shape[0], _find_split_points(row_has_data))
    col_bands = _splits_to_bands(matrix.shape[1], _find_split_points(col_has_data))

    zones: List[Dict[str, int]] = []
    for r_start, r_end in row_bands:
        for c_start, c_end in col_bands:
            sub = matrix[r_start : r_end + 1, c_start : c_end + 1]
            if not sub.any():
                continue

            rs, re = r_start, r_end
            cs, ce = c_start, c_end

            while rs <= re and not matrix[rs, cs : ce + 1].any():
                rs += 1
            while rs <= re and not matrix[re, cs : ce + 1].any():
                re -= 1
            while cs <= ce and not matrix[rs : re + 1, cs].any():
                cs += 1
            while cs <= ce and not matrix[rs : re + 1, ce].any():
                ce -= 1

            if rs <= re and cs <= ce:
                zones.append(
                    {
                        "min_row": min_row + rs,
                        "max_row": min_row + re,
                        "min_col": min_col + cs,
                        "max_col": min_col + ce,
                    }
                )

    return zones


def serialize_zone_grid(ws, zone: Dict[str, int], merged_map: Optional[Dict[Tuple[int, int], Tuple[int, int]]] = None) -> str:
    if merged_map is None:
        merged_map = _build_merged_map(ws)
    lines: List[str] = []
    for r in range(zone["min_row"], zone["max_row"] + 1):
        for c in range(zone["min_col"], zone["max_col"] + 1):
            anchor = merged_map.get((r, c))
            if anchor:
                value = _cell_text(ws.cell(anchor[0], anchor[1]).value)
                if value.strip():
                    value = f"<merged> {value}"
            else:
                value = _cell_text(ws.cell(r, c).value)
            if value.strip():
                lines.append(f"[R{r}C{c}] {value}")
    return "\n".join(lines)


def _extract_sheet_images(ws) -> List[Dict[str, Any]]:
    images: List[Dict[str, Any]] = []
    for image in getattr(ws, "_images", []) or []:
        anchor = _image_anchor_to_cell(image)
        if not anchor:
            continue
        row, col = anchor
        data = None
        if hasattr(image, "_data"):
            data_attr = image._data
            data = data_attr() if callable(data_attr) else data_attr
        if data:
            data = ImageProcessor.resize_image(data)
            images.append({"row": row, "col": col, "data": data})
    return images


def _filter_zone_images(images: List[Dict[str, Any]], zone: Dict[str, int]) -> List[Dict[str, Any]]:
    return [
        img
        for img in images
        if zone["min_row"] <= img.get("row", 0) <= zone["max_row"]
        and zone["min_col"] <= img.get("col", 0) <= zone["max_col"]
    ]


def render_excel_to_images(file_path: str) -> Dict[str, Any]:
    wb = openpyxl.load_workbook(file_path, data_only=True)
    pages: List[Dict[str, Any]] = []

    for idx, sheet_name in enumerate(wb.sheetnames):
        pages.append(
            {
                "page_number": idx + 1,
                "image_data": "",
                "metadata": {
                    "sheet_name": sheet_name,
                },
            }
        )

    if not pages:
        raise ValueError("No sheets found in Excel file")

    return {"pages_images": pages}


def extract_excel_zone_payloads(file_path: str) -> Dict[str, Any]:
    wb = openpyxl.load_workbook(file_path, read_only=False, data_only=True, rich_text=True)
    sheet_payloads: List[Dict[str, Any]] = []

    for idx, ws in enumerate(wb.worksheets):
        zones = detect_sheet_zones(ws)
        merged_map = _build_merged_map(ws)
        zone_payloads = []
        image_first_payloads = []
        sheet_images = _extract_sheet_images(ws)

        table_rows = set()
        for r in range(1, ws.max_row + 1):
            filled = 0
            for c in range(1, ws.max_column + 1):
                text = _cell_text(ws.cell(r, c).value)
                if text.strip():
                    filled += 1
            if filled >= 2:
                table_rows.add(r)

        image_anchors = {(img.get("row"), img.get("col")) for img in sheet_images}
        standalone_anchors = {anchor for anchor in image_anchors if anchor[0] not in table_rows}

        for row, col in sorted(standalone_anchors):
            image_zone = {
                "min_row": row,
                "max_row": row,
                "min_col": col,
                "max_col": col,
            }
            grid_text = serialize_zone_grid(ws, image_zone, merged_map)
            if grid_text.strip():
                continue
            images = _filter_zone_images(sheet_images, image_zone)
            if images:
                image_first_payloads.append(
                    {
                        "zone": image_zone,
                        "grid_text": grid_text,
                        "images": images,
                    }
                )

        for zone in zones:
            grid_text = serialize_zone_grid(ws, zone, merged_map)
            images = _filter_zone_images(sheet_images, zone)
            zone_payloads.append(
                {
                    "zone": zone,
                    "grid_text": grid_text,
                    "images": images,
                }
            )

        sheet_payloads.append(
            {
                "sheet_name": ws.title,
                "file_path": file_path,
                "zones": image_first_payloads + zone_payloads,
                "page_num": idx + 1,
            }
        )

    return {"sheet_payloads": {"zones": sheet_payloads}}
