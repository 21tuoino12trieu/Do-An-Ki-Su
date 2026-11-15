"""Chuyển HTML sang Markdown theo phạm vi Beedoc của đồ án."""

from .converter import ConversionError, UnsupportedHtmlError, convert_html

__all__ = ["ConversionError", "UnsupportedHtmlError", "convert_html"]
