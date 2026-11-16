"""
Main document processing pipeline orchestrator.

This module provides the DocumentPipeline class which serves as the central coordinator
for all document processing operations. It manages processor selection, validation,
and orchestrates the complete processing workflow from input documents to formatted output.

Key responsibilities:
- Processor registry and automatic selection based on document type
- Processing request validation and compatibility checking
- Workflow orchestration from document input to processed output
- Integration point between entities, processors, and output formatting
- Error handling and processing status reporting

The pipeline automatically selects the appropriate processor based on document type,
validates format compatibility, and handles the complete processing workflow while
providing clear error messages and processing metadata.

Usage:
    pipeline = DocumentPipeline()
    document = Document.from_file_path("example.pdf")
    result = pipeline.process(document, OutputFormat.MARKDOWN, OutputStructure.PAGES)
"""

from typing import Dict, List, Optional, Type, Any
from dataclasses import dataclass

from .entities.document import Document
from .entities.document_types import DocumentType
from .entities.output_formats import OutputFormat, OutputStructure, ProcessedContent, ProcessingStrategy
from .processors.base import BaseProcessor, ProcessorError, UnsupportedFormatError


class PipelineError(Exception):
    """Base exception for pipeline-related errors."""
    pass


class ProcessorNotFoundError(PipelineError):
    """Raised when no processor can handle the document type."""
    pass


class ValidationError(PipelineError):
    """Raised when processing request validation fails."""
    pass


@dataclass
class ProcessingResult:
    """
    Complete processing result with content and metadata.
    
    Contains the processed content along with processing metadata including
    the selected processor, processing time, and any warnings or additional
    information generated during processing.
    """
    content: ProcessedContent
    processor_used: str
    processing_metadata: Dict[str, Any]
    success: bool = True
    error_message: Optional[str] = None


class ProcessorRegistry:
    """
    Registry for managing document processors.
    
    Maintains a mapping of document types to their corresponding processors
    and provides methods for processor lookup and registration. Supports
    automatic processor discovery and validation of processor capabilities.
    """
    
    def __init__(self):
        self._processors: Dict[DocumentType, BaseProcessor] = {}
        self._processor_instances: Dict[str, BaseProcessor] = {}
    
    def register_processor(self, processor: BaseProcessor) -> None:
        """
        Register a processor for its supported document types.
        
        Args:
            processor: Processor instance to register
        """
        processor_name = processor.__class__.__name__
        self._processor_instances[processor_name] = processor
        
        for doc_type in processor.SUPPORTED_TYPES:
            self._processors[doc_type] = processor
    
    def get_processor(self, document_type: DocumentType) -> BaseProcessor:
        """
        Get processor for document type.
        
        Args:
            document_type: Type of document to process
            
        Returns:
            Processor capable of handling the document type
            
        Raises:
            ProcessorNotFoundError: If no processor supports the document type
        """
        if document_type not in self._processors:
            raise ProcessorNotFoundError(f"No processor found for document type: {document_type.value}")
        
        return self._processors[document_type]
    
    def get_all_processors(self) -> List[BaseProcessor]:
        """Get all registered processor instances."""
        return list(self._processor_instances.values())
    
    def get_supported_types(self) -> List[DocumentType]:
        """Get all supported document types."""
        return list(self._processors.keys())


class DocumentPipeline:
    """
    Main document processing pipeline coordinator.
    
    The DocumentPipeline class orchestrates the complete document processing workflow:
    1. Validates input documents and processing parameters
    2. Selects appropriate processor based on document type
    3. Validates format/structure compatibility
    4. Executes processing with error handling
    5. Returns processed content with metadata
    
    The pipeline automatically handles processor selection, compatibility validation,
    and provides detailed error reporting for processing failures.
    """
    
    def __init__(self):
        """Initialize pipeline with processor registry."""
        self.registry = ProcessorRegistry()
        self._initialize_processors()
    
    def _initialize_processors(self) -> None:
        """
        Initialize and register all available processors.
        
        This method dynamically imports and registers all processor classes.
        Failed imports are silently ignored to allow partial functionality
        when optional dependencies are missing.
        """
        # Import and register processors (with error handling for missing dependencies)
        processor_configs = [
            ('processors.text_processor', 'TextProcessor'),
            ('processors.pdf_processor', 'PDFProcessor'),
            ('processors.image_processor', 'ImageProcessor'),
            ('processors.structured_processor', 'StructuredProcessor'),
            ('processors.url_processor', 'URLProcessor'),
            ('processors.excel.csv_processor', 'CSVProcessor'),
            ('processors.excel.spreadsheet_processor', 'SpreadsheetProcessor'),
            ('processors.office.word_processor', 'WordProcessor'),
            ('processors.office.presentation_processor', 'PresentationProcessor'),
        ]
        
        for module_path, class_name in processor_configs:
            try:
                module = __import__(f"beedocV2.{module_path}", fromlist=[class_name])
                processor_class = getattr(module, class_name)
                processor_instance = processor_class()
                self.registry.register_processor(processor_instance)
            except (ImportError, AttributeError, Exception):
                # Skip processors with missing dependencies
                continue
    
    def validate_processing_request(self, document: Document, output_format: OutputFormat,
                                   output_structure: OutputStructure) -> None:
        """
        Validate that the processing request is feasible.
        
        Args:
            document: Document to validate
            output_format: Requested output format
            output_structure: Requested output structure
            
        Raises:
            ValidationError: If request is invalid
            ProcessorNotFoundError: If no processor supports the document type
        """
        # Check if document type is supported
        try:
            processor = self.registry.get_processor(document.document_type)
        except ProcessorNotFoundError:
            raise ValidationError(f"Document type {document.document_type.value} is not supported")
        
        # Check format compatibility using ProcessingStrategy
        if not ProcessingStrategy.is_compatible(document.document_type, output_structure, output_format):
            available_formats = ProcessingStrategy.get_available_formats(document.document_type, output_structure)
            raise ValidationError(
                f"Format {output_format.value} not available for {document.document_type.value} "
                f"with {output_structure.value} structure. Available: {[f.value for f in available_formats]}"
            )
    
    def process(self, document: Document, 
                output_format: Optional[OutputFormat] = None,
                output_structure: Optional[OutputStructure] = None) -> ProcessingResult:
        """
        Process document to specified format and structure.
        
        Args:
            document: Document to process
            output_format: Target output format (uses document default if None)
            output_structure: Target output structure (uses document default if None)
            
        Returns:
            ProcessingResult with processed content and metadata
        """
        try:
            # Use document defaults if not specified
            if output_structure is None:
                output_structure = document.get_recommended_structure()
            if output_format is None:
                output_format = document.get_recommended_format()
            
            # Validate request
            self.validate_processing_request(document, output_format, output_structure)
            
            # Get processor and process
            processor = self.registry.get_processor(document.document_type)
            processed_content = processor.process(document, output_format, output_structure)
            
            # Create result with metadata
            metadata = {
                'document_type': document.document_type.value,
                'output_format': output_format.value,
                'output_structure': output_structure.value,
                'document_size': document.size_bytes,
                'is_large_file': document.is_large_file,
            }
            
            return ProcessingResult(
                content=processed_content,
                processor_used=processor.__class__.__name__,
                processing_metadata=metadata,
                success=True
            )
        
        except Exception as e:
            return ProcessingResult(
                content=ProcessedContent(),  # Empty content
                processor_used="",
                processing_metadata={},
                success=False,
                error_message=str(e)
            )
    
    def get_pipeline_info(self) -> Dict[str, Any]:
        """
        Get information about pipeline capabilities.
        
        Returns:
            Dictionary with supported types, processors, and capabilities
        """
        return {
            'supported_document_types': [dt.value for dt in self.registry.get_supported_types()],
            'available_processors': [p.get_supported_info() for p in self.registry.get_all_processors()],
            'total_processors': len(self.registry.get_all_processors()),
        }