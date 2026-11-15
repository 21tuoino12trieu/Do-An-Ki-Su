from typing import Dict, Optional, Type

from beedoc_v3.core.exceptions import RendererError
from beedoc_v3.renders.base import BaseRenderer
from beedoc_v3.renders.document_render.html_render.render import HtmlRenderer


class RendererFactory:
    """Giữ factory của bản gốc, chỉ đăng ký renderer HTML → Markdown."""

    _extension_map: Dict[str, Type[BaseRenderer]] = {"html": HtmlRenderer}

    @classmethod
    def get_renderer(cls, extension: str) -> BaseRenderer:
        ext = extension.lower().lstrip(".")
        renderer_class: Optional[Type[BaseRenderer]] = cls._extension_map.get(ext)
        if not renderer_class:
            raise RendererError(f"Không có renderer cho định dạng: {ext}")
        return renderer_class()
