class BeedocError(Exception):
    """Base exception for Beedoc SDK."""
    def __init__(self, message: str, doc_id: str = None):
        super().__init__(message)
        self.doc_id = doc_id

# --- Ingestion Errors ---
class ReaderError(BeedocError):
    """Raised when reading or validating a document fails."""

class StorageError(ReaderError):
    """Raised when uploading to or downloading from S3 fails."""

class UnsupportedFormatError(ReaderError):
    """Raised when a file extension is not supported."""

# --- Reconstruction Errors ---
class RendererError(BeedocError):
    """Raised when document reconstruction fails."""

class AIProviderError(RendererError):
    """Raised when external AI services (OpenAI, Claude) return an error."""

class WorkflowError(RendererError):
    """Raised when BeeFlow workflow execution fails."""

# --- Controller/View Errors ---
class ViewError(BeedocError):
    """Raised when formatting the output fails."""
