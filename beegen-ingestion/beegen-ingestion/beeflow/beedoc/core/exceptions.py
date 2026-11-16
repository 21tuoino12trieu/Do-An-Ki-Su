class DocumentProcessingError(Exception):
    """Base exception for document processing errors."""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.details = details or {}


class DocumentValidationError(DocumentProcessingError):
    """Raised when document validation fails."""
    pass


class DocumentReadError(DocumentProcessingError):
    """Raised when document reading fails."""
    pass


class DocumentRenderError(DocumentProcessingError):
    """Raised when document rendering fails."""
    pass


class UnsupportedDocumentTypeError(DocumentProcessingError):
    """Raised when document type is not supported."""
    pass


class ConfigurationError(DocumentProcessingError):
    """Raised when configuration is invalid."""
    pass


class ProcessorNotFoundError(DocumentProcessingError):
    """Raised when required processor is not available."""
    pass