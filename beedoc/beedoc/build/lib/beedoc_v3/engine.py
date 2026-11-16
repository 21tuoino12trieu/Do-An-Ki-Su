import os
import time
from typing import Optional, Any

from beedoc_v3.models.document import Document
from beedoc_v3.core.constants import DocumentStatus, EXTENSION_CATEGORY_MAP, DocumentCategory
from beedoc_v3.core.exceptions import BeedocError, UnsupportedFormatError
from beedoc_v3.readers.factory import ReaderFactory
from beedoc_v3.renders.factory import RendererFactory
from beedoc_v3.readers.base import BaseReader
from beedoc_v3.renders.base import BaseRenderer


class BeedocEngine:
    """Main pipeline orchestrator for the beedoc SDK."""

    def __init__(self, config: Optional[Any] = None):
        self.config: Optional[Any] = config

    def _get_category(self, extension: str) -> DocumentCategory:
        ext: str = extension.lower().lstrip('.')
        if ext not in EXTENSION_CATEGORY_MAP:
            raise UnsupportedFormatError(f"Extension '{ext}' is not supported.")
        return EXTENSION_CATEGORY_MAP[ext]

    async def process(self, file_path: str) -> str:
        """
        Main pipeline: Ingestion (Reader) -> Reconstruction (Renderer) -> Output
        """
        start_time: float = time.time()

        # 1. Initialize model
        ext: str = os.path.splitext(file_path)[1]
        category: DocumentCategory = self._get_category(ext)
        doc: Document = Document(file_path=file_path, extension=ext, category=category)

        try:
            # 2. Ingestion phase (Reader)
            doc.update_status(DocumentStatus.READING)
            reader: BaseReader = ReaderFactory.get_reader(ext)
            await reader.read(doc)

            # 3. Reconstruction phase (Renderer)
            doc.update_status(DocumentStatus.RECONSTRUCTING)
            renderer: BaseRenderer = RendererFactory.get_renderer(ext)
            await renderer.render(doc)

            doc.update_status(DocumentStatus.COMPLETED)

        except BeedocError as e:
            doc.update_status(DocumentStatus.FAILED, error=str(e))
        except Exception as e:
            doc.update_status(DocumentStatus.FAILED, error=f"Unexpected error: {str(e)}")
        finally:
            doc.processing_time_ms = int((time.time() - start_time) * 1000)

        # 4. Output phase
        return doc
