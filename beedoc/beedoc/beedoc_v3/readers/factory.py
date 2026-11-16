from typing import Dict, Type, Optional
from beedoc_v3.readers.base import BaseReader
from beedoc_v3.readers.document_reader.pdf_reader import PdfReader
from beedoc_v3.readers.document_reader.docx_reader import DocxReader
from beedoc_v3.readers.document_reader.excel_reader import ExcelReader
from beedoc_v3.readers.document_reader.html_reader import HtmlReader
from beedoc_v3.readers.image_reader.image_reader import ImageReader
from beedoc_v3.readers.structured_reader.csv_reader import CsvReader
from beedoc_v3.readers.structured_reader.json_reader import JsonReader
from beedoc_v3.core.exceptions import UnsupportedFormatError

class ReaderFactory:
    """Factory to return the appropriate Reader based on file extension."""

    _readers: Dict[str, Type[BaseReader]] = {
        # Documents
        "pdf": PdfReader,
        "docx": DocxReader,
        "doc": DocxReader,
        "xlsx": ExcelReader,
        "xls": ExcelReader,
        "html": HtmlReader,

        # Images
        "png": ImageReader,
        "jpg": ImageReader,
        "jpeg": ImageReader,
        "webp": ImageReader,

        # Structured
        "csv": CsvReader,
        "json": JsonReader
    }

    @classmethod
    def get_reader(cls, extension: str) -> BaseReader:
        ext: str = extension.lower().lstrip('.')
        reader_class: Optional[Type[BaseReader]] = cls._readers.get(ext)
        if not reader_class:
            raise UnsupportedFormatError(f"No reader found for extension: {ext}")
        return reader_class()
