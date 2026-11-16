from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from beedoc_v3.models.document import Document

class BaseInterface(ABC):
    """Base interface for all SDK components."""
    pass

class IReader(BaseInterface):
    @abstractmethod
    async def read(self, document: 'Document') -> 'Document':
        """Read document, upload to S3 and enrich the document model."""
        pass

class IRenderer(BaseInterface):
    @abstractmethod
    async def render(self, document: 'Document') -> 'Document':
        """Reconstruct document content using AI/Workflow."""
        pass
