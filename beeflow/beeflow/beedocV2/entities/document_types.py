# beedocV2/entities/document_types.py
from enum import Enum
from typing import Dict, Set, Optional
from pathlib import Path


class DocumentType(Enum):
    """Document types supported by the pipeline."""
    # Office Documents
    PDF = "pdf"
    DOCX = "docx"
    XLSX = "xlsx"
    PPTX = "pptx"
    
    # Legacy Office
    DOC = "doc"
    XLS = "xls"
    PPT = "ppt"
    
    # Images
    JPG = "jpg"
    JPEG = "jpeg"
    PNG = "png"
    GIF = "gif"
    BMP = "bmp"
    TIFF = "tiff"
    SVG = "svg"
    
    # Text & Code
    TXT = "txt"
    MD = "md"
    HTML = "html"
    CSS = "css"
    PY = "py"
    JS = "js"
    
    # Structured Data
    CSV = "csv"
    JSON = "json"
    XML = "xml"
    YAML = "yaml"
    
    # Web
    URL = "url"


class DocumentTypeDetector:
    """Document type detection from file extensions and URLs."""
    
    EXTENSION_MAP: Dict[str, DocumentType] = {
        '.pdf': DocumentType.PDF,
        '.docx': DocumentType.DOCX,
        '.xlsx': DocumentType.XLSX,
        '.pptx': DocumentType.PPTX,
        '.doc': DocumentType.DOC,
        '.xls': DocumentType.XLS,
        '.ppt': DocumentType.PPT,
        '.jpg': DocumentType.JPG,
        '.jpeg': DocumentType.JPEG,
        '.png': DocumentType.PNG,
        '.gif': DocumentType.GIF,
        '.bmp': DocumentType.BMP,
        '.tiff': DocumentType.TIFF,
        '.tif': DocumentType.TIFF,
        '.svg': DocumentType.SVG,
        '.txt': DocumentType.TXT,
        '.md': DocumentType.MD,
        '.html': DocumentType.HTML,
        '.htm': DocumentType.HTML,
        '.css': DocumentType.CSS,
        '.py': DocumentType.PY,
        '.js': DocumentType.JS,
        '.csv': DocumentType.CSV,
        '.json': DocumentType.JSON,
        '.xml': DocumentType.XML,
        '.yaml': DocumentType.YAML,
        '.yml': DocumentType.YAML,
    }
    
    @classmethod
    def detect_from_path(cls, file_path: str) -> Optional[DocumentType]:
        """Detect document type from file path."""
        extension = Path(file_path).suffix.lower()
        return cls.EXTENSION_MAP.get(extension)
    
    @classmethod
    def detect_type(cls, input_path: str) -> DocumentType:
        """Detect document type with fallback."""
        # Check if URL
        if input_path.startswith(('http://', 'https://')):
            return DocumentType.URL
            
        # Detect from extension
        doc_type = cls.detect_from_path(input_path)
        return doc_type or DocumentType.TXT
    
    @classmethod
    def get_supported_extensions(cls) -> Set[str]:
        """Get all supported file extensions."""
        return set(cls.EXTENSION_MAP.keys())