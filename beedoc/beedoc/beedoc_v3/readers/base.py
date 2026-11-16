import uuid
import os
from typing import Any, Dict, Optional, TYPE_CHECKING
from beeflow.workflow import WorkflowEngine
from beeflow.nodes.base_node import START, END, INPUT, OUTPUT
from beeflow.nodes.primitives.data.s3_node import S3Node
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beegen.configs.storage.s3_config import S3Operation
from beedoc_v3.core.interfaces import IReader
from beedoc_v3.core.exceptions import ReaderError
from beedoc_v3.utils.hashing import calculate_file_hash

if TYPE_CHECKING:
    from beedoc_v3.models.document import Document

class BaseReader(IReader):
    """
    Base Reader focused on Local Ingestion:
    Hashing and metadata extraction using Beeflow.
    """

    def __init__(self):
        # We don't initialize workflow in __init__ because subclasses might need
        # to customize it. We'll lazy-init it in read().
        self.workflow: Optional[WorkflowEngine] = None

    def _build_workflow(self) -> WorkflowEngine:
        """Builds a simple Beeflow workflow for ingestion."""
        with WorkflowEngine(
            name=f"{self.__class__.__name__}_workflow",
            description=f"Local ingestion workflow for {self.__class__.__name__}",
            inputs=INPUT
        ) as workflow:

            # Step 1: Calculate hash and basic metadata
            hashing_node = CodeNode(
                name="hashing_node",
                code_fn=self._hashing_logic,
                inputs={"file_path": INPUT},
                return_keys=["file_hash: str", "file_name: str", "file_size: int"]
            )

            START >> hashing_node >> END

        workflow.compile()
        return workflow

    @staticmethod
    def _hashing_logic(file_path: str) -> Dict[str, Any]:
        """Logic for hashing and basic file info."""
        if not os.path.exists(file_path):
            raise ReaderError(f"File not found: {file_path}")

        file_hash: str = calculate_file_hash(file_path)
        file_name: str = os.path.basename(file_path)
        file_size: int = os.path.getsize(file_path)

        return {
            "file_hash": file_hash,
            "file_name": file_name,
            "file_size": file_size
        }

    @staticmethod
    def _update_document_logic(document: 'Document', data: Dict[str, Any]) -> None:
        """Shared logic to update Document object from hashing/basic metadata."""
        import uuid
        if not document.document_id:
            document.document_id = str(uuid.uuid4())
        document.file_hash = data.get("file_hash")
        document.file_name = data.get("file_name", document.file_name or "")
        document.file_size_bytes = data.get("file_size", 0)

    async def read(self, document: 'Document') -> 'Document':
        """Executes the ingestion workflow and updates the Document object."""
        if not self.workflow:
            self.workflow = self._build_workflow()

        try:
            # Workflow now only takes primitive path and returns primitive data
            results = await self.workflow.run(
                inputs={"file_path": document.file_path},
                request_id=str(uuid.uuid4())
            )

            # Map workflow results back to the Document object
            data: Dict[str, Any] = results.get("hashing_node", {})
            self._update_document_logic(document, data)

            return document
        except Exception as e:
            raise ReaderError(f"Reader workflow failed: {str(e)}")
