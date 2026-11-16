import uuid
from typing import TYPE_CHECKING, Any, Dict

from beeflow.nodes.base_node import END, INPUT, START
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beeflow.workflow import WorkflowEngine

from beedoc_v3.core.exceptions import ReaderError
from beedoc_v3.readers.base import BaseReader

if TYPE_CHECKING:
    from beedoc_v3.models.document import Document


class HtmlReader(BaseReader):
    """
    Local HTML reader.

    The renderer owns HTML decoding, parsing, image resolution, table
    normalization, and markdown reconstruction. The reader only validates the
    local file and extracts basic file metadata.
    """

    def _build_workflow(self) -> WorkflowEngine:
        with WorkflowEngine(
            name="html_reader_workflow",
            description="Workflow for ingesting local HTML files",
            inputs=INPUT,
        ) as workflow:
            hashing_node = CodeNode(
                name="hashing_node",
                code_fn=self._hashing_logic,
                inputs={"file_path": INPUT},
                return_keys=["file_hash: str", "file_name: str", "file_size: int"],
            )

            START >> hashing_node >> END

        workflow.compile()
        return workflow

    async def read(self, document: "Document") -> "Document":
        if not self.workflow:
            self.workflow = self._build_workflow()

        try:
            results = await self.workflow.run(
                inputs={"file_path": document.file_path},
                request_id=str(uuid.uuid4()),
            )

            hashing_data: Dict[str, Any] = results.get("hashing_node") or results
            self._update_document_logic(document, hashing_data)
            document.extension = "html"
            return document
        except Exception as e:
            raise ReaderError(f"HtmlReader workflow failed: {str(e)}")
