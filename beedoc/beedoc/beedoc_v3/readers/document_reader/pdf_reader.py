import uuid
import fitz # PyMuPDF
from typing import Any, Dict, TYPE_CHECKING
from beeflow.workflow import WorkflowEngine
from beeflow.nodes.base_node import START, END, INPUT
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beedoc_v3.readers.base import BaseReader
from beedoc_v3.core.exceptions import ReaderError

if TYPE_CHECKING:
    from beedoc_v3.models.document import Document

class PdfReader(BaseReader):
    """
    Pdf Reader focused on Local Ingestion:
    Hashing -> Metadata Extraction (Page Count).
    """

    def _build_workflow(self) -> WorkflowEngine:
        """Builds the Beeflow workflow for PDF ingestion."""
        with WorkflowEngine(
            name="pdf_reader_workflow",
            description="Workflow for ingesting PDF documents and extracting metadata",
            inputs=INPUT
        ) as workflow:

            # Node 1: Hashing & Basic info
            hashing_node = CodeNode(
                name="hashing_node",
                code_fn=self._hashing_logic,
                inputs={"file_path": INPUT},
                return_keys=["file_hash: str", "file_name: str", "file_size: int"]
            )

            # Node 2: Extract PDF specific metadata (like page count)
            metadata_node = CodeNode(
                name="metadata_node",
                code_fn=self._extract_pdf_metadata,
                inputs={"file_path": INPUT},
                return_keys=["total_pages: int"]
            )

            START >> hashing_node >> metadata_node >> END

        workflow.compile()
        return workflow

    @staticmethod
    def _extract_pdf_metadata(file_path: str) -> Dict[str, Any]:
        """Uses fitz to extract basic metadata without full rendering."""
        try:
            doc = fitz.open(file_path)
            page_count = len(doc)
            doc.close()
            return {"total_pages": page_count}
        except Exception as e:
            return {"total_pages": 0, "error": str(e)}

    async def read(self, document: 'Document') -> 'Document':
        """Executes the PDF ingestion workflow and updates the Document object."""
        if not self.workflow:
            self.workflow = self._build_workflow()

        try:
            results = await self.workflow.run(  
                inputs={"file_path": document.file_path},
                request_id=str(uuid.uuid4())
            )

            # Update Document from results
            hashing_data: Dict[str, Any] = results.get("hashing_node", {})
            pdf_metadata: Dict[str, Any] = results.get("metadata_node", {})

            # Use base logic for shared fields
            self._update_document_logic(document, hashing_data)

            # Update PDF specific metadata
            document.ai_metadata.update(pdf_metadata)

            return document
        except Exception as e:
            raise ReaderError(f"PdfReader workflow failed: {str(e)}")
