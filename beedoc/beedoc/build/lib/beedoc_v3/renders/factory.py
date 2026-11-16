from typing import Dict, Type, Optional
from beedoc_v3.renders.base import BaseRenderer
from beedoc_v3.renders.document_render.pdf_render.render import PdfRenderer
from beedoc_v3.renders.document_render.docx_render.render import DocxRenderer
from beedoc_v3.renders.document_render.excel_render.render import ExcelRenderer
from beedoc_v3.renders.document_render.html_render.render import HtmlRenderer
from beedoc_v3.renders.image_render.image_renderer import ImageRenderer
from beedoc_v3.renders.structured_render.csv.render import CsvRenderer
from beedoc_v3.renders.structured_render.json.render import JsonRenderer
from beedoc_v3.core.exceptions import RendererError

class RendererFactory:
    """Factory to return the appropriate Renderer based on category and extension."""

    # Map extension directly to Renderer class for 1-1 mapping
    _extension_map: Dict[str, Type[BaseRenderer]] = {
        "pdf": PdfRenderer,
        "docx": DocxRenderer,
        "xlsx": ExcelRenderer,
        "xls": ExcelRenderer,
        "png": ImageRenderer,
        "jpg": ImageRenderer,
        "jpeg": ImageRenderer,
        "webp": ImageRenderer,
        "csv": CsvRenderer,
        "json": JsonRenderer,
        "html": HtmlRenderer,
    }

    @classmethod
    def get_renderer(cls, extension: str) -> BaseRenderer:
        ext: str = extension.lower().lstrip('.')
        renderer_class: Optional[Type[BaseRenderer]] = cls._extension_map.get(ext)

        if not renderer_class:
            raise RendererError(f"No renderer found for extension {ext}")

        return renderer_class()
