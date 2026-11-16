from typing import Dict, Type, Optional

from beedoc.core.interfaces import DocumentReader, DocumentRenderer
from beedoc.core.entities import DocumentType, OutputFormat
from beedoc.readers.image_reader import ImageReader
from beedoc.readers.pdf_reader import PdfReader
from beedoc.renderers.numpy_renderer import NumpyRenderer
from beedoc.renderers.base64_renderer import Base64Renderer
from beedoc.renderers.text_renderer import TextRenderer
from .exceptions import UnsupportedDocumentTypeError, ProcessorNotFoundError


class DocumentReaderFactory:
    """Factory for creating document readers."""
    
    _readers: Dict[DocumentType, Type[DocumentReader]] = {
        DocumentType.IMAGE: ImageReader,
        DocumentType.PDF: PdfReader,
    }
    
    @classmethod
    def create(cls, document_type: DocumentType) -> DocumentReader:
        """
        Create appropriate document reader for the given type.
        
        Args:
            document_type: Type of document to read
            
        Returns:
            DocumentReader instance
            
        Raises:
            UnsupportedDocumentTypeError: If document type is not supported
        """
        if document_type not in cls._readers:
            raise UnsupportedDocumentTypeError(
                f"No reader available for document type: {document_type.value}",
                details={"supported_types": list(cls._readers.keys())}
            )
        
        reader_class = cls._readers[document_type]
        return reader_class()
    
    @classmethod
    def register_reader(cls, document_type: DocumentType, reader_class: Type[DocumentReader]):
        """
        Register a new reader for a document type.
        
        Args:
            document_type: Document type to register reader for
            reader_class: Reader class to register
        """
        cls._readers[document_type] = reader_class
    
    @classmethod
    def get_supported_types(cls) -> list[DocumentType]:
        """Get list of supported document types."""
        return list(cls._readers.keys())


class DocumentRendererFactory:
    """Factory for creating document renderers."""
    
    _renderers: Dict[OutputFormat, Type[DocumentRenderer]] = {
        OutputFormat.NUMPY_ARRAY: NumpyRenderer,
        OutputFormat.BASE64: Base64Renderer,
        OutputFormat.TEXT: TextRenderer,
    }
    
    @classmethod
    def create(cls, output_format: OutputFormat) -> DocumentRenderer:
        """
        Create appropriate document renderer for the given output format.
        
        Args:
            output_format: Desired output format
            
        Returns:
            DocumentRenderer instance
            
        Raises:
            ProcessorNotFoundError: If no renderer is available for the format
        """
        if output_format not in cls._renderers:
            raise ProcessorNotFoundError(
                f"No renderer available for output format: {output_format.value}",
                details={"supported_formats": list(cls._renderers.keys())}
            )
        
        renderer_class = cls._renderers[output_format]
        return renderer_class()
    
    @classmethod
    def register_renderer(cls, output_format: OutputFormat, renderer_class: Type[DocumentRenderer]):
        """
        Register a new renderer for an output format.
        
        Args:
            output_format: Output format to register renderer for
            renderer_class: Renderer class to register
        """
        cls._renderers[output_format] = renderer_class
    
    @classmethod
    def get_supported_formats(cls) -> list[OutputFormat]:
        """Get list of supported output formats."""
        return list(cls._renderers.keys())