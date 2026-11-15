"""Compatibility entry point for the HTML conversion helper."""
from beedoc_v3.renders.document_render.html_render.utils.converter import (
    ConversionError, UnsupportedHtmlError, convert_html,
)

__all__ = ["ConversionError", "UnsupportedHtmlError", "convert_html"]
