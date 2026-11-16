# beedocV2/entities/document.py
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Union, Tuple
from pathlib import Path
from datetime import datetime
from .document_types import DocumentType, DocumentTypeDetector
from .output_formats import ProcessingStrategy, OutputStructure, OutputFormat


@dataclass
class Document:
    """Document metadata with auto-detection capabilities."""
    
    # Basic identification
    name: str
    document_type: DocumentType
    
    # Content sources (one of these should be provided)
    file_path: Optional[str] = None
    content: Optional[bytes] = None
    url: Optional[str] = None
    
    # File properties
    size_bytes: Optional[int] = None
    last_modified: Optional[datetime] = None
    
    # Processing hints
    is_large_file: bool = False
    
    # Custom metadata
    custom_metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Auto-detect and set properties after initialization."""
        # Validate input sources
        if not any([self.file_path, self.content, self.url]):
            raise ValueError("One of file_path, content, or url must be provided")
        
        # Set file properties
        self._set_file_properties()
        
        # Set processing flags
        self._set_processing_flags()
    
    def _set_file_properties(self):
        """Set file properties like size and modification time."""
        if self.file_path:
            try:
                path = Path(self.file_path)
                if path.exists():
                    stat = path.stat()
                    if not self.size_bytes:
                        self.size_bytes = stat.st_size
                    if not self.last_modified:
                        self.last_modified = datetime.fromtimestamp(stat.st_mtime)
            except (OSError, IOError):
                pass
        elif self.content and not self.size_bytes:
            self.size_bytes = len(self.content)
    
    def _set_processing_flags(self):
        """Set flags that affect processing strategy."""
        # Large file detection (100MB threshold)
        if self.size_bytes and self.size_bytes > 100 * 1024 * 1024:
            self.is_large_file = True
    
    @classmethod
    def from_file_path(cls, file_path: Union[str, Path], **kwargs) -> 'Document':
        """Create document from file path."""
        path = Path(file_path)
        doc_type = DocumentTypeDetector.detect_type(str(path))
        
        return cls(
            name=path.name,
            document_type=doc_type,
            file_path=str(path),
            **kwargs
        )
    
    @classmethod
    def from_content(cls, name: str, content: bytes, **kwargs) -> 'Document':
        """Create document from content bytes."""
        doc_type = DocumentTypeDetector.detect_type(name)
        
        return cls(
            name=name,
            document_type=doc_type,
            content=content,
            **kwargs
        )
    
    @classmethod
    def from_url(cls, url: str, name: Optional[str] = None, **kwargs) -> 'Document':
        """Create document from URL."""
        if not name:
            # Extract name from URL
            name = Path(url).name or "remote_document"
        
        return cls(
            name=name,
            document_type=DocumentType.URL,
            url=url,
            **kwargs
        )
    
    def get_processing_hints(self) -> Dict[str, Any]:
        """Get hints for processing strategy selection."""
        structure, format = ProcessingStrategy.get_processing_plan(self.document_type)
        
        return {
            'document_type': self.document_type,
            'is_large': self.is_large_file,
            'size_bytes': self.size_bytes,
            'has_content': self.content is not None,
            'is_remote': self.url is not None,
            'recommended_structure': structure,
            'recommended_format': format,
            'should_use_pages': structure == OutputStructure.PAGES
        }
    
    def is_page_based(self) -> bool:
        """Check if this document should use page-based processing."""
        return ProcessingStrategy.get_default_structure(self.document_type) == OutputStructure.PAGES
    
    def get_recommended_structure(self) -> OutputStructure:
        """Get recommended output structure for this document."""
        return ProcessingStrategy.get_default_structure(self.document_type)
    
    def get_recommended_format(self) -> OutputFormat:
        """Get recommended output format for this document."""
        return ProcessingStrategy.get_default_format(self.document_type)
    
    def get_available_formats(self, structure: Optional[OutputStructure] = None) -> list[OutputFormat]:
        """Get available formats for this document type and structure."""
        if structure is None:
            structure = self.get_recommended_structure()
        return ProcessingStrategy.get_available_formats(self.document_type, structure)
    
    def get_processing_plan(self, requested_structure: Optional[OutputStructure] = None,
                          requested_format: Optional[OutputFormat] = None) -> Tuple[OutputStructure, OutputFormat]:
        """Get complete processing plan for this document."""
        return ProcessingStrategy.get_processing_plan(
            self.document_type, 
            requested_structure, 
            requested_format
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert document to dictionary."""
        return {
            'name': self.name,
            'document_type': self.document_type.value,
            'file_path': self.file_path,
            'url': self.url,
            'size_bytes': self.size_bytes,
            'last_modified': self.last_modified.isoformat() if self.last_modified else None,
            'is_large_file': self.is_large_file,
            'custom_metadata': self.custom_metadata
        }
    
    def update_custom_metadata(self, **metadata):
        """Update custom metadata fields."""
        self.custom_metadata.update(metadata)
    
    def __str__(self):
        """String representation of document."""
        return f"Document(name='{self.name}', type={self.document_type})"