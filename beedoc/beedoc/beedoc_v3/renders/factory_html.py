from typing import Dict, Type, Optional
from beedoc_v3.renders.base import BaseRenderer
from beedoc_v3.renders.document_render.pdf_render.render_html import PdfHtmlRenderer
from beedoc_v3.renders.document_render.docx_render.render_html import DocxHtmlRenderer
from beedoc_v3.renders.document_render.excel_render.render_html import ExcelHtmlRenderer
from beedoc_v3.core.exceptions import RendererError

class RendererHtmlFactory:
    """Factory to return the appropriate HTML-output Renderer based on extension."""

    _extension_map: Dict[str, Type[BaseRenderer]] = {
        "pdf": PdfHtmlRenderer,
        "docx": DocxHtmlRenderer,
        "doc": DocxHtmlRenderer,
        "xlsx": ExcelHtmlRenderer,
        "xls": ExcelHtmlRenderer,
    }

    @classmethod
    def get_renderer(cls, extension: str) -> BaseRenderer:
        ext: str = extension.lower().lstrip('.')
        renderer_class: Optional[Type[BaseRenderer]] = cls._extension_map.get(ext)

        if not renderer_class:
            raise RendererError(f"No HTML renderer found for extension {ext}")

        return renderer_class()
