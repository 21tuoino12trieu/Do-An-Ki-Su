import asyncio
from typing import Optional, Callable, List
import time

from beedoc.core.interfaces import DocumentProcessor
from beedoc.core.entities import DocumentMetadata, ProcessingResult, ProcessingConfig, OutputFormat, DocumentType, ProcessedPage
from beedoc.core.factories import DocumentReaderFactory, DocumentRendererFactory
from beedoc.core.exceptions import DocumentProcessingError


class DefaultDocumentProcessor(DocumentProcessor):
    """Default implementation of document processor."""
    
    def __init__(self):
        self.reader_factory = DocumentReaderFactory()
        self.renderer_factory = DocumentRendererFactory()
    
    async def process_document(
        self,
        metadata: DocumentMetadata,
        config: Optional[ProcessingConfig] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> ProcessingResult:
        """
        Process a single document with the given configuration.
        
        Args:
            metadata: Document metadata
            config: Processing configuration (uses defaults if None)
            progress_callback: Optional callback for progress updates
            
        Returns:
            ProcessingResult containing processed pages
            
        Raises:
            DocumentProcessingError: If processing fails
        """
        if config is None:
            config = ProcessingConfig()
        
        try:
            # Validate output format compatibility with document type
            if (config.output_format == OutputFormat.TEXT and 
                metadata.document_type != DocumentType.PDF):
                raise DocumentProcessingError(
                    f"TEXT output format is only supported for PDF documents, got: {metadata.document_type.value}"
                )
            
            # Create reader and renderer
            reader = self.reader_factory.create(metadata.document_type)
            renderer = self.renderer_factory.create(config.output_format)
            
            # Configure renderer
            await renderer.configure(config)
            
            # Validate input
            is_valid = await reader.validate_input(metadata)
            if not is_valid:
                raise DocumentProcessingError(f"Document validation failed for: {metadata.name}")
            
            # Read metadata (enriches the metadata object)
            enriched_metadata = await reader.read_metadata(metadata)
            
            # Read content
            content = await reader.read_content(enriched_metadata)
            
            # Render document
            result = await renderer.render_document(
                enriched_metadata, 
                content, 
                progress_callback
            )
            
            return result
            
        except Exception as e:
            if isinstance(e, DocumentProcessingError):
                raise
            raise DocumentProcessingError(f"Unexpected error processing document: {e}")
    
    async def process_batch(
        self,
        documents: List[DocumentMetadata],
        config: Optional[ProcessingConfig] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> List[ProcessingResult]:
        """
        Process multiple documents in parallel.
        
        Args:
            documents: List of document metadata
            config: Processing configuration (uses defaults if None)
            progress_callback: Optional callback for overall progress
            
        Returns:
            List of ProcessingResult objects
            
        Raises:
            DocumentProcessingError: If any processing fails
        """
        if not documents:
            return []
        
        if config is None:
            config = ProcessingConfig()
        
        total_docs = len(documents)
        results = []
        
        async def process_single_with_progress(idx: int, metadata: DocumentMetadata) -> ProcessingResult:
            """Process single document and update progress."""
            try:
                result = await self.process_document(metadata, config)
                if progress_callback:
                    progress_callback(idx + 1, total_docs)
                return result
            except Exception as e:
                # Include document info in error
                raise DocumentProcessingError(
                    f"Failed to process document '{metadata.name}': {e}"
                )
        
        # Process documents concurrently
        tasks = [
            process_single_with_progress(idx, doc) 
            for idx, doc in enumerate(documents)
        ]
        
        try:
            results = await asyncio.gather(*tasks)
            return results
        except Exception as e:
            raise DocumentProcessingError(f"Batch processing failed: {e}")
    
    async def process_document_page(
        self,
        metadata: DocumentMetadata,
        page_number: int,
        config: Optional[ProcessingConfig] = None
    ) -> 'ProcessedPage':
        """
        Process a single page from a document.
        
        Args:
            metadata: Document metadata
            page_number: Page number to process (1-based)
            config: Processing configuration
            
        Returns:
            ProcessedPage object
        """
        if config is None:
            config = ProcessingConfig()
        
        try:
            # Create reader and renderer
            reader = self.reader_factory.create(metadata.document_type)
            renderer = self.renderer_factory.create(config.output_format)
            
            # Configure renderer
            await renderer.configure(config)
            
            # Validate and read
            await reader.validate_input(metadata)
            enriched_metadata = await reader.read_metadata(metadata)
            content = await reader.read_content(enriched_metadata)
            
            # Render single page
            page = await renderer.render_page(content, page_number, enriched_metadata)
            
            return page
            
        except Exception as e:
            if isinstance(e, DocumentProcessingError):
                raise
            raise DocumentProcessingError(f"Failed to process page {page_number}: {e}")


class DocumentProcessingPipeline:
    """Higher-level pipeline for document processing with additional features."""
    
    def __init__(self, 
                 processor: Optional[DocumentProcessor] = None, 
                 config: Optional[ProcessingConfig] = None):
        self.processor = processor or DefaultDocumentProcessor()
        if config:
            config.validate()
        
        self.default_config = config or ProcessingConfig()
    
    async def process_from_path(
        self,
        file_path: str,
        config: Optional[ProcessingConfig] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> ProcessingResult:
        """
        Process a document from file path.
        
        Args:
            file_path: Path to the document file
            config: Processing configuration
            progress_callback: Progress callback
            
        Returns:
            ProcessingResult
        """
        metadata = DocumentMetadata.from_path(file_path)
        effective_config = config or self.default_config
        
        return await self.processor.process_document(
            metadata, 
            effective_config, 
            progress_callback
        )
    
    async def process_from_bytes(
        self,
        name: str,
        content: bytes,
        document_type: 'DocumentType',
        config: Optional[ProcessingConfig] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> ProcessingResult:
        """
        Process a document from bytes.
        
        Args:
            name: Document name
            content: Document content as bytes
            document_type: Type of document
            config: Processing configuration
            progress_callback: Progress callback
            
        Returns:
            ProcessingResult
        """
        metadata = DocumentMetadata.from_content(name, content, document_type)
        effective_config = config or self.default_config
        
        return await self.processor.process_document(
            metadata, 
            effective_config, 
            progress_callback
        )
    
    async def process_batch_from_paths(
        self,
        file_paths: List[str],
        config: Optional[ProcessingConfig] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> List[ProcessingResult]:
        """
        Process multiple documents from file paths.
        
        Args:
            file_paths: List of file paths
            config: Processing configuration
            progress_callback: Progress callback
            
        Returns:
            List of ProcessingResult
        """
        documents = [DocumentMetadata.from_path(path) for path in file_paths]
        effective_config = config or self.default_config
        
        return await self.processor.process_batch(
            documents, 
            effective_config, 
            progress_callback
        )