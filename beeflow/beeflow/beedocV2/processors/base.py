# beedocV2/processors/base.py
"""
Base processor abstract class defining the interface for all document processors.

This module provides the foundational BaseProcessor class that all specific processors
must inherit from. It defines the standard interface for processing documents and
converting them to various output formats and structures.

Key responsibilities:
- Define the processing interface that all processors must implement
- Provide common validation and error handling patterns
- Establish the contract between processors and the pipeline
- Handle document content loading from various sources (file, bytes, URL)

Each processor must implement format-specific methods (e.g., to_plain_text, to_markdown)
based on the output formats supported by their document types as defined in the TYPE_MAP.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set
from pathlib import Path

from ..entities.document import Document
from ..entities.document_types import DocumentType
from ..entities.output_formats import OutputFormat, OutputStructure, ProcessedContent
from ..utils.file_utils import read_file_content, fetch_url_content, FileReadError, URLFetchError


class ProcessorError(Exception):
    """Base exception for processor-related errors."""
    pass


class UnsupportedFormatError(ProcessorError):
    """Raised when requested output format is not supported by processor."""
    pass


class DocumentLoadError(ProcessorError):
    """Raised when document content cannot be loaded."""
    pass


class BaseProcessor(ABC):
    """
    Abstract base class for all document processors.
    
    This class defines the standard interface that all document processors must implement.
    Each processor handles specific document types and can convert them to various output
    formats and structures as defined in the ProcessingStrategy TYPE_MAP.
    
    Subclasses must:
    1. Define SUPPORTED_TYPES class attribute with handled DocumentType values
    2. Define SUPPORTED_FORMATS class attribute with available OutputFormat values  
    3. Implement format-specific methods (e.g., to_plain_text, to_markdown, etc.)
    4. Implement the process() method to orchestrate the conversion
    
    The processor handles loading document content from various sources (file paths,
    raw bytes, URLs) and provides a unified interface for format conversion.
    """
    
    # Must be defined by subclasses
    SUPPORTED_TYPES: Set[DocumentType] = set()
    SUPPORTED_FORMATS: Set[OutputFormat] = set()
    
    def __init__(self):
        """Initialize the processor and validate implementation."""
        if not self.SUPPORTED_TYPES:
            raise NotImplementedError(f"{self.__class__.__name__} must define SUPPORTED_TYPES")
        if not self.SUPPORTED_FORMATS:
            raise NotImplementedError(f"{self.__class__.__name__} must define SUPPORTED_FORMATS")
    
    def can_process(self, document_type: DocumentType) -> bool:
        """
        Check if this processor can handle the given document type.
        
        Args:
            document_type: The DocumentType to check
            
        Returns:
            True if this processor supports the document type
        """
        return document_type in self.SUPPORTED_TYPES
    
    def supports_format(self, output_format: OutputFormat) -> bool:
        """
        Check if this processor supports the given output format.
        
        Args:
            output_format: The OutputFormat to check
            
        Returns:
            True if this processor supports the output format
        """
        return output_format in self.SUPPORTED_FORMATS
    
    def load_content(self, document: Document) -> bytes:
        """
        Load document content from various sources (file, bytes, URL).
        
        Args:
            document: Document with content source information
            
        Returns:
            Document content as bytes
            
        Raises:
            DocumentLoadError: If content cannot be loaded from any source
        """
        try:
            # Priority: existing content > file path > URL
            if document.content is not None:
                return document.content
            
            if document.file_path:
                return read_file_content(document.file_path)
            
            if document.url:
                content, _ = fetch_url_content(document.url)
                return content
            
            raise DocumentLoadError("No content source available (file_path, content, or url)")
        
        except (FileReadError, URLFetchError) as e:
            raise DocumentLoadError(f"Failed to load content: {str(e)}")
    
    def validate_request(self, document: Document, output_format: OutputFormat, 
                        output_structure: OutputStructure) -> None:
        """
        Validate that the processing request is supported.
        
        Args:
            document: Document to process
            output_format: Requested output format
            output_structure: Requested output structure
            
        Raises:
            ProcessorError: If document type is not supported
            UnsupportedFormatError: If output format is not supported
        """
        if not self.can_process(document.document_type):
            raise ProcessorError(
                f"{self.__class__.__name__} cannot process {document.document_type.value} documents"
            )
        
        if not self.supports_format(output_format):
            raise UnsupportedFormatError(
                f"{self.__class__.__name__} does not support {output_format.value} format"
            )
    
    @abstractmethod
    def process(self, document: Document, output_format: OutputFormat, 
                output_structure: OutputStructure) -> ProcessedContent:
        """
        Process document and convert to requested format and structure.
        
        This is the main processing method that must be implemented by all processors.
        It should load the document content, perform any necessary processing/parsing,
        and convert to the requested output format and structure.
        
        Args:
            document: Document to process
            output_format: Desired output format (e.g., PLAIN_TEXT, MARKDOWN)
            output_structure: Desired structure (SINGLE or PAGES)
            
        Returns:
            ProcessedContent with the converted content, format, and structure
            
        Raises:
            ProcessorError: If processing fails
            UnsupportedFormatError: If format/structure combination is not supported
        """
        pass
    
    def get_supported_info(self) -> Dict[str, Any]:
        """
        Get information about what this processor supports.
        
        Returns:
            Dictionary with supported types and formats
        """
        return {
            'processor_name': self.__class__.__name__,
            'supported_types': [dt.value for dt in self.SUPPORTED_TYPES],
            'supported_formats': [of.value for of in self.SUPPORTED_FORMATS],
        }


class FormatMethodMixin:
    """
    Mixin providing helper methods for format-specific processing.
    
    This mixin provides a standardized way to dispatch processing to format-specific
    methods. Processors can inherit from this to get automatic method routing based
    on the requested output format.
    
    Processors using this mixin should implement methods named:
    - to_plain_text(content: bytes, structure: OutputStructure) -> Any
    - to_markdown(content: bytes, structure: OutputStructure) -> Any  
    - to_html(content: bytes, structure: OutputStructure) -> Any
    - etc. for each supported format
    """
    
    def dispatch_format_method(self, content: bytes, output_format: OutputFormat, 
                              output_structure: OutputStructure) -> Any:
        """
        Dispatch to the appropriate format-specific method.
        
        Args:
            content: Raw document content
            output_format: Target output format
            output_structure: Target output structure
            
        Returns:
            Processed content in the requested format
            
        Raises:
            UnsupportedFormatError: If no method exists for the format
        """
        # Convert format enum to method name
        method_name = f"to_{output_format.value}"
        
        if not hasattr(self, method_name):
            raise UnsupportedFormatError(
                f"{self.__class__.__name__} does not implement {method_name}() method"
            )
        
        method = getattr(self, method_name)
        return method(content, output_structure)