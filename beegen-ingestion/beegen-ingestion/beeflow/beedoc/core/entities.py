from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
from beegen.configs.yaml_model import YamlModel
from dataclasses import dataclass, field
import numpy as np


class DocumentType(Enum):
    """Supported document types."""
    IMAGE = "image"
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    JSON = "JSON"
    CSV = "csv"
    HTML = "html"
    MARKDOWN = "markdown"


class OutputFormat(Enum):
    """Supported output formats."""
    NUMPY_ARRAY = "numpy"
    BASE64 = "base64"
    TEXT = "text"
    PANDAS = "pandas"


class ProcessingConfig(YamlModel):
    """Configuration for document processing."""
    max_dimension: int = 1200
    output_format: OutputFormat = OutputFormat.NUMPY_ARRAY
    preserve_aspect_ratio: bool = True
    quality: int = 95
    
    def validate(self) -> None:
        """Validate configuration parameters."""
        if self.max_dimension <= 0:
            raise ValueError("max_dimension must be positive")
        if not 1 <= self.quality <= 100:
            raise ValueError("quality must be between 1 and 100")
        
        # Validate output format compatibility
        if self.output_format == OutputFormat.TEXT:
            # TEXT output is only valid for PDF documents - this will be checked at processing time
            pass


class DocumentMetadata(YamlModel):
    """Metadata for a document to be processed."""
    name: str
    document_type: DocumentType
    path: Optional[str] = None
    content: Optional[bytes] = None
    size_bytes: Optional[int] = None
    
    def __post_init__(self):
        if not self.path and not self.content:
            raise ValueError("Either path or content must be provided")
        if self.content:
            self.size_bytes = len(self.content)
    
    @classmethod
    def from_path(cls, file_path: Union[str, Path]) -> 'DocumentMetadata':
        """Create metadata from file path."""
        path = Path(file_path)
        doc_type = cls._detect_type_from_extension(path.suffix)
        return cls(
            name=path.name,
            document_type=doc_type,
            path=str(path),
            size_bytes=path.stat().st_size if path.exists() else None
        )
    
    @classmethod
    def from_content(cls, name: str, content: bytes, document_type: DocumentType) -> 'DocumentMetadata':
        """Create metadata from content bytes."""
        return cls(
            name=name,
            document_type=document_type,
            content=content
        )
    
    @staticmethod
    def _detect_type_from_extension(extension: str) -> DocumentType:
        """Detect document type from file extension."""
        ext_mapping = {
            '.jpg': DocumentType.IMAGE,
            '.jpeg': DocumentType.IMAGE,
            '.png': DocumentType.IMAGE,
            '.gif': DocumentType.IMAGE,
            '.bmp': DocumentType.IMAGE,
            '.tiff': DocumentType.IMAGE,
            '.pdf': DocumentType.PDF,
            '.docx': DocumentType.DOCX,
            '.txt': DocumentType.TXT,
            '.json': DocumentType.JSON,
            '.csv': DocumentType.CSV,
            '.html': DocumentType.HTML,
            '.htm': DocumentType.HTML,
            '.md': DocumentType.MARKDOWN,
            '.markdown': DocumentType.MARKDOWN,
        }
        
        ext_lower = extension.lower()
        if ext_lower not in ext_mapping:
            raise ValueError(f"Unsupported file extension: {extension}")
        
        return ext_mapping[ext_lower]


@dataclass
class ProcessedPage:
    """Represents a processed page from a document."""
    page_number: int
    image_data: Union[np.ndarray, str, None] = None  # numpy array, base64 string, or None for text
    text_data: Optional[str] = None  # extracted text content
    width: Optional[int] = None
    height: Optional[int] = None
    
    def __post_init__(self):
        if isinstance(self.image_data, np.ndarray):
            if len(self.image_data.shape) >= 2:
                self.height, self.width = self.image_data.shape[:2]
        
        # Ensure at least one data type is present
        if self.image_data is None and self.text_data is None:
            raise ValueError("Either image_data or text_data must be provided")


@dataclass
class ProcessingResult:
    """Result of document processing operation."""
    document_name: str
    document_type: DocumentType
    total_pages: int
    pages: List[ProcessedPage] = field(default_factory=list)
    processing_time_ms: Optional[float] = None
    config_used: Optional[ProcessingConfig] = None
    
    def get_page(self, page_number: int) -> Optional[ProcessedPage]:
        """Get a specific page by number."""
        for page in self.pages:
            if page.page_number == page_number:
                return page
        return None
    
    def get_all_page_data(self) -> List[Union[np.ndarray, str]]:
        """Get image or text data from all pages."""
        result = []
        for page in self.pages:
            if page.image_data is not None:
                result.append(page.image_data)
            elif page.text_data is not None:
                result.append(page.text_data)
        return result