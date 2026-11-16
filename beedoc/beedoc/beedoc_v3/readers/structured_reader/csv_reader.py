import uuid
from typing import TYPE_CHECKING, Dict, Any
from beeflow.workflow import WorkflowEngine
from beeflow.nodes.base_node import START, END, INPUT
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beedoc_v3.readers.base import BaseReader
from beedoc_v3.core.exceptions import ReaderError

if TYPE_CHECKING:
    from beedoc_v3.models.document import Document

class CsvReader(BaseReader):
    """
    Csv Reader focused on Local Ingestion:
    Hashing -> Basic Metadata.
    """

    def _build_workflow(self) -> WorkflowEngine:
        """Builds the Beeflow workflow for CSV ingestion."""
        with WorkflowEngine(
            name="csv_reader_workflow",
            description="Workflow for ingesting CSV files",
            inputs=INPUT
        ) as workflow:

            # Node 1: Hashing & Metadata
            hashing_node = CodeNode(
                name="hashing_node",
                code_fn=self._hashing_logic,
                inputs={"file_path": INPUT},
                return_keys=["file_hash: str", "file_name: str", "file_size: int"]
            )

            START >> hashing_node >> END

        workflow.compile()
        return workflow

    async def read(self, document: 'Document') -> 'Document':
        """Executes the CSV ingestion workflow and updates the Document object."""
        if not self.workflow:
            self.workflow = self._build_workflow()

        try:
            results = await self.workflow.run(
                inputs={"file_path": document.file_path},
                request_id=str(uuid.uuid4())
            )

            # Update Document from results
            hashing_data: Dict[str, Any] = results.get("hashing_node", {})

            self._update_document_logic(document, hashing_data)

            return document
        except Exception as e:
            raise ReaderError(f"CsvReader workflow failed: {str(e)}")
