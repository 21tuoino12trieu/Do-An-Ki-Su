# beedocV2/entities/output_formats.py
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from .document_types import DocumentType


class OutputFormat(Enum):
    """Content format types."""
    # Binary formats
    BYTES = "bytes"
    BASE64 = "base64"
    NUMPY_ARRAY = "numpy_array"
    
    # Text formats
    PLAIN_TEXT = "plain_text"
    MARKDOWN = "markdown"
    HTML = "html"
    
    # Structured formats
    JSON_STRUCTURED = "json_structured"
    DATAFRAME = "dataframe"
    CSV = "csv"


class OutputStructure(Enum):
    """How content is organized."""
    SINGLE = "single"    # Single piece of content
    PAGES = "pages"      # List of pages


@dataclass
class ProcessedContent:
    """Container for processed document content."""
    content: Any = None
    structure: OutputStructure = OutputStructure.SINGLE
    format: OutputFormat = OutputFormat.PLAIN_TEXT
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_content(self) -> Any:
        """Get the actual content."""
        return self.content
    
    def is_paged(self) -> bool:
        """Check if content is organized as pages."""
        return self.structure == OutputStructure.PAGES
    
    def get_page_count(self) -> int:
        """Get number of pages (if paged structure)."""
        if self.is_paged() and isinstance(self.content, list):
            return len(self.content)
        return 1 if self.content else 0


class ProcessingStrategy:
    """Processing strategy based on your refined type map."""
    
    # Document type → Output structure → Available formats map
    TYPE_MAP = {
        # PDF
        DocumentType.PDF: {
            OutputStructure.SINGLE: [
                OutputFormat.PLAIN_TEXT, OutputFormat.MARKDOWN, OutputFormat.HTML,
                OutputFormat.JSON_STRUCTURED, OutputFormat.NUMPY_ARRAY, OutputFormat.BASE64
            ],
            OutputStructure.PAGES: [  # default structure
                OutputFormat.PLAIN_TEXT, OutputFormat.MARKDOWN, OutputFormat.HTML,  # default format
                OutputFormat.JSON_STRUCTURED, OutputFormat.NUMPY_ARRAY, OutputFormat.BASE64
            ]
        },
        
        # DOCX, DOC
        DocumentType.DOCX: {
            OutputStructure.SINGLE: [
                OutputFormat.PLAIN_TEXT, OutputFormat.MARKDOWN, OutputFormat.HTML, OutputFormat.JSON_STRUCTURED
            ],
            OutputStructure.PAGES: [  # default structure
                OutputFormat.PLAIN_TEXT, OutputFormat.MARKDOWN, OutputFormat.HTML, OutputFormat.JSON_STRUCTURED  # default format
            ]
        },
        DocumentType.DOC: {
            OutputStructure.SINGLE: [
                OutputFormat.PLAIN_TEXT, OutputFormat.MARKDOWN, OutputFormat.HTML, OutputFormat.JSON_STRUCTURED
            ],
            OutputStructure.PAGES: [  # default structure
                OutputFormat.PLAIN_TEXT, OutputFormat.MARKDOWN, OutputFormat.HTML, OutputFormat.JSON_STRUCTURED  # default format
            ]
        },
        
        # PPTX, PPT
        DocumentType.PPTX: {
            OutputStructure.SINGLE: [
                OutputFormat.PLAIN_TEXT, OutputFormat.MARKDOWN, OutputFormat.HTML,
                OutputFormat.JSON_STRUCTURED, OutputFormat.NUMPY_ARRAY, OutputFormat.BASE64
            ],
            OutputStructure.PAGES: [  # default structure
                OutputFormat.PLAIN_TEXT, OutputFormat.MARKDOWN, OutputFormat.HTML,  # default format
                OutputFormat.JSON_STRUCTURED, OutputFormat.NUMPY_ARRAY, OutputFormat.BASE64
            ]
        },
        DocumentType.PPT: {
            OutputStructure.SINGLE: [
                OutputFormat.PLAIN_TEXT, OutputFormat.MARKDOWN, OutputFormat.HTML,
                OutputFormat.JSON_STRUCTURED, OutputFormat.NUMPY_ARRAY, OutputFormat.BASE64
            ],
            OutputStructure.PAGES: [  # default structure
                OutputFormat.PLAIN_TEXT, OutputFormat.MARKDOWN, OutputFormat.HTML,  # default format
                OutputFormat.JSON_STRUCTURED, OutputFormat.NUMPY_ARRAY, OutputFormat.BASE64
            ]
        },
        
        # XLSX, XLS
        DocumentType.XLSX: {
            OutputStructure.PAGES: [  # default structure
                OutputFormat.DATAFRAME, OutputFormat.CSV, OutputFormat.JSON_STRUCTURED  # default format
            ],
            OutputStructure.SINGLE: [
                OutputFormat.DATAFRAME, OutputFormat.JSON_STRUCTURED
            ]
        },
        DocumentType.XLS: {
            OutputStructure.PAGES: [  # default structure
                OutputFormat.DATAFRAME, OutputFormat.CSV, OutputFormat.JSON_STRUCTURED  # default format
            ],
            OutputStructure.SINGLE: [
                OutputFormat.DATAFRAME, OutputFormat.JSON_STRUCTURED
            ]
        },
        
        # CSV
        DocumentType.CSV: {
            OutputStructure.SINGLE: [  # default structure
                OutputFormat.DATAFRAME, OutputFormat.CSV, OutputFormat.JSON_STRUCTURED  # default format
            ]
        },
        
        # Images
        DocumentType.JPG: {
            OutputStructure.SINGLE: [  # default structure
                OutputFormat.NUMPY_ARRAY, OutputFormat.BASE64, OutputFormat.BYTES  # default format
            ]
        },
        DocumentType.JPEG: {
            OutputStructure.SINGLE: [  # default structure
                OutputFormat.NUMPY_ARRAY, OutputFormat.BASE64, OutputFormat.BYTES  # default format
            ]
        },
        DocumentType.PNG: {
            OutputStructure.SINGLE: [  # default structure
                OutputFormat.NUMPY_ARRAY, OutputFormat.BASE64, OutputFormat.BYTES  # default format
            ]
        },
        DocumentType.GIF: {
            OutputStructure.SINGLE: [  # default structure
                OutputFormat.NUMPY_ARRAY, OutputFormat.BASE64, OutputFormat.BYTES  # default format
            ]
        },
        DocumentType.BMP: {
            OutputStructure.SINGLE: [  # default structure
                OutputFormat.NUMPY_ARRAY, OutputFormat.BASE64, OutputFormat.BYTES  # default format
            ]
        },
        DocumentType.SVG: {
            OutputStructure.SINGLE: [  # default structure
                OutputFormat.NUMPY_ARRAY, OutputFormat.BASE64, OutputFormat.BYTES  # default format
            ]
        },
        DocumentType.TIFF: {
            OutputStructure.SINGLE: [  # default structure
                OutputFormat.NUMPY_ARRAY, OutputFormat.BASE64, OutputFormat.BYTES  # default format
            ]
        },
        
        # Text Files
        DocumentType.TXT: {
            OutputStructure.SINGLE: [  # default structure
                OutputFormat.PLAIN_TEXT, OutputFormat.MARKDOWN, OutputFormat.HTML  # default format
            ]
        },
        DocumentType.MD: {
            OutputStructure.SINGLE: [  # default structure
                OutputFormat.PLAIN_TEXT, OutputFormat.MARKDOWN, OutputFormat.HTML  # default format
            ]
        },
        DocumentType.HTML: {
            OutputStructure.SINGLE: [  # default structure
                OutputFormat.PLAIN_TEXT, OutputFormat.MARKDOWN, OutputFormat.HTML  # default format
            ]
        },
        DocumentType.CSS: {
            OutputStructure.SINGLE: [  # default structure
                OutputFormat.PLAIN_TEXT, OutputFormat.MARKDOWN, OutputFormat.HTML  # default format
            ]
        },
        DocumentType.PY: {
            OutputStructure.SINGLE: [  # default structure
                OutputFormat.PLAIN_TEXT, OutputFormat.MARKDOWN, OutputFormat.HTML  # default format
            ]
        },
        DocumentType.JS: {
            OutputStructure.SINGLE: [  # default structure
                OutputFormat.PLAIN_TEXT, OutputFormat.MARKDOWN, OutputFormat.HTML  # default format
            ]
        },
        
        # Structured Data
        DocumentType.JSON: {
            OutputStructure.SINGLE: [  # default structure
                OutputFormat.JSON_STRUCTURED, OutputFormat.PLAIN_TEXT  # default format
            ]
        },
        DocumentType.XML: {
            OutputStructure.SINGLE: [  # default structure
                OutputFormat.JSON_STRUCTURED, OutputFormat.PLAIN_TEXT  # default format
            ]
        },
        DocumentType.YAML: {
            OutputStructure.SINGLE: [  # default structure
                OutputFormat.JSON_STRUCTURED, OutputFormat.PLAIN_TEXT  # default format
            ]
        },
        
        # URL
        DocumentType.URL: {
            OutputStructure.SINGLE: [  # default structure
                OutputFormat.HTML, OutputFormat.PLAIN_TEXT, OutputFormat.MARKDOWN  # default format
            ]
        }
    }
    
    @classmethod
    def get_default_structure(cls, document_type: DocumentType) -> OutputStructure:
        """Get default structure for document type."""
        type_config = cls.TYPE_MAP.get(document_type, {})
        # Return the first structure in the map (which is the default)
        return next(iter(type_config.keys()), OutputStructure.SINGLE)
    
    @classmethod
    def get_default_format(cls, document_type: DocumentType) -> OutputFormat:
        """Get default format for document type."""
        default_structure = cls.get_default_structure(document_type)
        type_config = cls.TYPE_MAP.get(document_type, {})
        formats = type_config.get(default_structure, [OutputFormat.PLAIN_TEXT])
        # Return the first format in the list (which is the default)
        return formats[0] if formats else OutputFormat.PLAIN_TEXT
    
    @classmethod
    def get_available_formats(cls, document_type: DocumentType, structure: OutputStructure) -> List[OutputFormat]:
        """Get available formats for document type and structure."""
        type_config = cls.TYPE_MAP.get(document_type, {})
        return type_config.get(structure, [])
    
    @classmethod
    def is_compatible(cls, document_type: DocumentType, structure: OutputStructure, format: OutputFormat) -> bool:
        """Check if document type, structure, and format are compatible."""
        available_formats = cls.get_available_formats(document_type, structure)
        return format in available_formats
    
    @classmethod
    def get_processing_plan(cls, document_type: DocumentType, 
                          requested_structure: Optional[OutputStructure] = None,
                          requested_format: Optional[OutputFormat] = None) -> Tuple[OutputStructure, OutputFormat]:
        """Get the optimal structure and format for processing."""
        
        # Start with defaults
        structure = cls.get_default_structure(document_type)
        format = cls.get_default_format(document_type)
        
        # Apply requested structure if valid
        if requested_structure and requested_structure in cls.TYPE_MAP.get(document_type, {}):
            structure = requested_structure
            # Update format to default for this structure
            format = cls.get_available_formats(document_type, structure)[0]
        
        # Apply requested format if compatible
        if requested_format and cls.is_compatible(document_type, structure, requested_format):
            format = requested_format
        
        return structure, format


# Factory functions
def create_single_content(content: Any, format: OutputFormat, metadata: Dict = None) -> ProcessedContent:
    """Create single content."""
    return ProcessedContent(
        content=content,
        structure=OutputStructure.SINGLE,
        format=format,
        metadata=metadata or {}
    )


def create_paged_content(pages: List[Dict[str, Any]], format: OutputFormat, metadata: Dict = None) -> ProcessedContent:
    """Create paged content."""
    return ProcessedContent(
        content=pages,
        structure=OutputStructure.PAGES,
        format=format,
        metadata=metadata or {}
    )