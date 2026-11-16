import fitz  # PyMuPDF
import os
from typing import List, Dict, Tuple
import asyncio
from dotenv import load_dotenv


def normalize_spans(block):
    words = []
    last_x1 = None

    for line in block["lines"]:
        for span in line["spans"]:
            text = span["text"]

            if last_x1 is not None:
                gap = span["bbox"][0] - last_x1
                if gap < 2:  # adjacent char
                    words[-1] += text
                else:
                    words.append(text)
            else:
                words.append(text)

            last_x1 = span["bbox"][2]

    return " ".join(words)


class PDFExtractor():

    def __init__(self,):
        pass

    def _should_skip_image(self, image_item: dict) -> bool:
        """
        Geometric heuristic to skip noise/layout images (headers, footers, watermarks, decorative slices, tiny icons).
        Returns True if the image should be skipped, False otherwise.
        """
        if not isinstance(image_item, dict):
            return True

        bbox = image_item.get("bbox")
        if not bbox or len(bbox) != 4:
            return True

        x0, y0, x1, y1 = bbox
        display_w = x1 - x0
        display_h = y1 - y0

        page_width = image_item.get("page_width")
        page_height = image_item.get("page_height")

        # If page dimensions are missing, fallback to fitz default A4 size
        if not page_width:
            page_width = 595.27
        if not page_height:
            page_height = 841.89

        # 1. Skip tiny display elements (icons, markers, buttons)
        if display_w < 50 and display_h < 50:
            return True

        # 2. Skip full-page background templates/watermarks
        display_area = display_w * display_h
        page_area = page_width * page_height
        if display_area / page_area > 0.95:
            return True

        # 3. Skip repetitive background slices or full-width layout bands
        # Background slices usually span almost the entire page width (> 90%), but are relatively thin (height < 150)
        is_full_width_band = (display_w > 0.9 * page_width) and (display_h < 150)
        if is_full_width_band:
            return True

        return False

    def save_temporary_image(
        self,
        doc: fitz.Document,
        page: fitz.Page,
        image_items: List[dict],
        document_name: str,
    ):
        """
        Extract images from PDF by rendering their visual bounding boxes as clips at high resolution
        and save them into /tmp/{document_name}/
        Attach local file path back to image_item.
        """

        pdf_file_name = os.path.splitext(os.path.basename(document_name))[0]

        save_folder = os.path.join("/tmp", pdf_file_name)
        os.makedirs(save_folder, exist_ok=True)

        for image_item in image_items:

            assert image_item["type"] == "image"

            xref = image_item["image"]["xref"]
            bbox = image_item["bbox"]
            rect = fitz.Rect(bbox)

            # --------------------
            # Render visual clip of the image bounding box from page at zoom 2.0 (144 DPI)
            # --------------------
            try:
                zoom = 2.0
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat, clip=rect)
                img_bytes = pix.tobytes("png")
                ext = "png"
            except Exception:
                # Fallback to extract raw image bytes if rendering fails
                try:
                    img_info = doc.extract_image(xref)
                    img_bytes = img_info["image"]
                    ext = img_info["ext"]
                except Exception:
                    pix = fitz.Pixmap(doc, xref)
                    if pix.n - pix.alpha > 3:
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                    if pix.alpha:
                        pix = fitz.Pixmap(pix, 0)
                    img_bytes = pix.tobytes("png")
                    ext = "png"

            # --------------------
            # Save file
            # --------------------
            file_name = f"xref{xref}.{ext}"
            local_path = os.path.join(save_folder, file_name)

            with open(local_path, "wb") as f:
                f.write(img_bytes)

            # --------------------
            # Attach local path
            # --------------------
            image_item["image"]["path"] = local_path
            image_item["image"]["ext"] = ext

    async def  extract_page_items(self, doc: fitz.Document , page: fitz.Page, bot_id: str, document_id: str, pdf_path: str):
        page_height = page.rect.height
        page_width = page.rect.width
        page_items = []

        # --------------------
        # TEXT BLOCKS
        # --------------------
        text_dict = page.get_text("dict")
        for block in text_dict["blocks"]:
            if block["type"] != 0:
                continue

            content = normalize_spans(block)
            if not content.strip():
                continue

            page_items.append({
                "type": "text",
                "bbox": list(block["bbox"]),
                "content": content
            })

        # --------------------
        # IMAGE BLOCKS
        # --------------------
        images = page.get_images(full=True)
        image_items = []
        for img in images:
            xref = img[0]
            width = img[2]
            height = img[3]
            ext = img[7]

            rects = page.get_image_rects(xref)
            for rect in rects:
                # skip tiny images (spacer, icons, decorations)
                if rect.width < 15 or rect.height < 15 or width < 15 or height < 15:
                    continue

                # skip full-page image
                rect_area = rect.width * rect.height
                if rect_area / (page_width * page_height) > 0.98:
                    # print(f"skip adding image tag {width}, {height}, {page_width}, {page_height}, {float(width) * height / (page_width * page_height)}")
                    continue

                image_item = {
                    "type": "image",
                    "bbox": [rect.x0, rect.y0, rect.x1, rect.y1],
                    "page_width": page_width,
                    "page_height": page_height,
                    "image": {
                        "xref": xref,
                        "width": width,
                        "height": height,
                        "ext": ext if ext in ("png", "jpg", "jpeg") else "jpeg"
                    }
                }
                if self._should_skip_image(image_item):
                    continue
                image_items.append(image_item)
        
        self.save_temporary_image(doc, page, image_items, pdf_path)
        page_items += image_items

        return page_items 

    def get_pdf_images_reference(self, pdf_path: str, document_id: str, bot_id: str) -> Dict[int, List[Tuple[dict, str]]]:
        doc = fitz.open(pdf_path)
        results = {}

        for page_index, page in enumerate(doc):
            # print(f"procesisng page {page_index}")

            # extract_page_items is async, but we are in a sync function
            # Since this is a utility, we should make it properly async or use asyncio.run
            # For now, let's fix the call
            import asyncio
            page_items = asyncio.run(self.extract_page_items(doc, page, bot_id, document_id, pdf_path))

            
            # Natural reading order: top → bottom, left → right
            page_items.sort(key=lambda x: (x["bbox"][1], x["bbox"][0]))

            # --------------------
            # COLLECT IMAGE REFERENCES
            # --------------------
            page_refs = []
            n = len(page_items)

            for i, item in enumerate(page_items):
                if item["type"] != "image":
                    continue

                # Find 1 text block physically above the image
                above_text = ""
                j = i - 1
                while j >= 0:
                    prev_item = page_items[j]
                    if prev_item["type"] == "text":
                        above_text = prev_item["content"].strip()
                        break
                    j -= 1

                # Find 1 text block physically below the image
                below_text = ""
                j = i + 1
                while j < n:
                    next_item = page_items[j]
                    if next_item["type"] == "text":
                        below_text = next_item["content"].strip()
                        break
                    j += 1

                # Combine them as context
                ref_dict = {
                    "above_text": above_text,
                    "below_text": below_text
                }
                page_refs.append((item, ref_dict))

            if page_refs:
                results[page_index + 1] = page_refs

        return results



