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
        """Read local HTML and enrich document metadata."""
        pass

class IRenderer(BaseInterface):
    @abstractmethod
    async def render(self, document: 'Document') -> 'Document':
        """Convert HTML content to Markdown using a workflow."""
        pass
