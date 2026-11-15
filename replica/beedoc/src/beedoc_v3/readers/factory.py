from typing import Dict, Optional, Type

from beedoc_v3.core.exceptions import UnsupportedFormatError
from beedoc_v3.readers.base import BaseReader
from beedoc_v3.readers.document_reader.html_reader import HtmlReader


class ReaderFactory:
    """Giữ factory của bản gốc, chỉ đăng ký nhánh HTML."""

    _readers: Dict[str, Type[BaseReader]] = {"html": HtmlReader}

    @classmethod
    def get_reader(cls, extension: str) -> BaseReader:
        ext = extension.lower().lstrip(".")
        reader_class: Optional[Type[BaseReader]] = cls._readers.get(ext)
        if not reader_class:
            raise UnsupportedFormatError(f"Không có reader cho định dạng: {ext}")
        return reader_class()
