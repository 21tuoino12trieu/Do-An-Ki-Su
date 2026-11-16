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
    def save_temporary_image(
        self,
        doc: fitz.Document,
        image_items: List[dict],
        document_name: str,
    ):
        """
        Extract images from PDF and save them into /tmp/{document_name}/
        Attach local file path back to image_item.
        """

        pdf_file_name = os.path.splitext(os.path.basename(document_name))[0]

        save_folder = os.path.join("/tmp", pdf_file_name)
        os.makedirs(save_folder, exist_ok=True)

        for image_item in image_items:

            assert image_item["type"] == "image"

            xref = image_item["image"]["xref"]

            # --------------------
            # Extract image bytes from PDF
            # --------------------
            pix = fitz.Pixmap(doc, xref)

            if pix.n - pix.alpha > 3:
                pix = fitz.Pixmap(fitz.csRGB, pix)

            if pix.alpha:
                pix = fitz.Pixmap(pix, 0)

            img_bytes = pix.tobytes("jpeg")
            pix = None

            # --------------------
            # Save file
            # --------------------
            file_name = f"xref{xref}.jpeg"
            local_path = os.path.join(save_folder, file_name)

            with open(local_path, "wb") as f:
                f.write(img_bytes)

            # --------------------
            # Attach local path
            # --------------------
            image_item["image"]["path"] = local_path

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
                # skip full-page image
                rect_area = rect.width * rect.height
                if rect_area / (page_width * page_height) > 0.98:
                    # print(f"skip adding image tag {width}, {height}, {page_width}, {page_height}, {float(width) * height / (page_width * page_height)}")
                    continue

                image_items.append({
                    "type": "image",
                    "bbox": [rect.x0, rect.y0, rect.x1, rect.y1],
                    "image": {
                        "xref": xref,
                        "width": width,
                        "height": height,
                        "ext": ext if ext in ("png", "jpg", "jpeg") else "jpeg"
                    }
                })
        
        self.save_temporary_image(doc, image_items, pdf_path)
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

            
            # SORT: bottom → top, left → right
            # --------------------
            page_items.sort(key=lambda x: (-x["bbox"][1], x["bbox"][0]))

            # --------------------
            # COLLECT IMAGE REFERENCES
            # --------------------
            page_refs = []
            n = len(page_items)

            for i, item in enumerate(page_items):
                if item["type"] != "image":
                    continue

                ref_texts = []
                j = i + 1  # look backward in reading order (since sorted bottom→top)

                while j < n and len(ref_texts) < 2:
                    prev_item = page_items[j]

                    if prev_item["type"] == "image":
                        break  # stop if another image encountered

                    if prev_item["type"] == "text":
                        ref_texts.append(prev_item["content"].strip())

                    j += 1

                page_refs.append((item, " ".join(ref_texts[::-1])))

            if page_refs:
                results[page_index + 1] = page_refs

        return results



