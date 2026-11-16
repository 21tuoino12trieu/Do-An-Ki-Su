import uuid
from typing import TYPE_CHECKING, Dict, Any
from beeflow.workflow import WorkflowEngine
from beeflow.nodes.base_node import START, END, INPUT, OUTPUT
from beeflow.nodes.primitives.transform.code_node import CodeNode

from beedoc_v3.models.document import Page, Zone
from beedoc_v3.renders.base import BaseRenderer
from beedoc_v3.core.exceptions import RendererError
from beedoc_v3.renders.document_render.docx_render.utils.converter import convert_docx_to_pdf
from beedoc_v3.renders.document_render.pdf_render.render import PdfRenderer

if TYPE_CHECKING:
    from beedoc_v3.models.document import Document

class DocxRenderer(BaseRenderer):
    """
    Docx Renderer that handles:
    1. Converting DOCX to PDF.
    2. Delegating the rendering and reconstruction to PdfRenderer.
    """

    def _build_workflow(self) -> WorkflowEngine:
        """Builds the Beeflow workflow for DOCX rendering by delegation to PDF."""
        with WorkflowEngine(
            name="docx_renderer_workflow",
            description="Workflow for converting DOCX to PDF and delegating to PdfRenderer",
            inputs=INPUT,
            langfuse="beegen-portal"
        ) as workflow:

            # Node 1: Convert DOCX to PDF
            convert_node = CodeNode(
                name="convert_docx_to_pdf_node",
                code_fn=convert_docx_to_pdf,
                inputs={"docx_path": INPUT["file_path"]},
                return_keys=["pdf_path: str"]
            )

            # Node 2: Delegate to PdfRenderer and get results
            delegate_node = CodeNode(
                name="delegate_to_pdf_renderer_node",
                code_fn=self._delegate_to_pdf_logic,
                inputs={
                    "pdf_path": {convert_node: "pdf_path"}
                },
                return_keys=[
                    "final_pages: List[Dict[str, Any]]",
                    "reconstructed_content: str",
                    "document_metadata: Dict[str, Any]"
                ],
                outputs=OUTPUT
            )

            START >> convert_node >> delegate_node >> END

        workflow.compile()
        return workflow

    async def _delegate_to_pdf_logic(self, pdf_path: str) -> Dict[str, Any]:
        """Logic for delegating to the PdfRenderer with the newly created PDF path."""
        # Note: We need to use a real document object for PdfRenderer,
        # but since we are within a workflow node, we should be careful.
        # We need the ACTUAL document object here to modify it.

        from beedoc_v3.models.document import Document
        temp_doc = Document(file_path=pdf_path)

        pdf_renderer = PdfRenderer()
        await pdf_renderer.render(temp_doc)

        # We return the extracted data to be applied
        return {
            "final_pages": [
                {
                    "page_number": p.page_number,
                    "image_data": p.image_data,
                    "metadata": p.metadata,
                    "content": [
                        {"content": z.content, "metadata": z.metadata}
                        for z in (p.content or [])
                        if z and z.content
                    ],
                    "image_list": p.image_list
                } for p in temp_doc.pages
            ],
            "reconstructed_content": temp_doc.reconstructed_content,
            "document_metadata": temp_doc.metadata
        }

    async def render(self, document: 'Document') -> 'Document':
        if not self.workflow:
            self.workflow = self._build_workflow()

        try:
            results = await self.workflow.run(
                inputs={
                    "file_path": document.file_path
                },
                request_id=str(uuid.uuid4())
            )
            
            final_pages_data = results.get("final_pages", [])
            reconstructed_content = results.get("reconstructed_content", "")
            document_metadata = results.get("document_metadata", {})

            # Apply to document object
            document.pages = []
            for p_data in final_pages_data:
                page = Page(
                    page_number=p_data["page_number"],
                    image_data=p_data["image_data"],
                    metadata=p_data["metadata"],
                    content=p_data["content"],
                    image_list=p_data["image_list"]
                )
                document.add_page(page)

            document.reconstructed_content = reconstructed_content
            document.metadata.update(document_metadata or {})
            return document

        except Exception as e:
            raise RendererError(f"PdfRenderer workflow failed: {str(e)}")
