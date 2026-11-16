"""
HTML output variant of DocxRenderer. Same DOCX->PDF conversion, but delegates
reconstruction to PdfHtmlRenderer instead of PdfRenderer so the result is HTML.
"""
import uuid
from typing import TYPE_CHECKING, Dict, Any
from beeflow.workflow import WorkflowEngine
from beeflow.nodes.base_node import START, END, INPUT, OUTPUT
from beeflow.nodes.primitives.transform.code_node import CodeNode

from beedoc_v3.models.document import Page, Zone
from beedoc_v3.renders.base import BaseRenderer
from beedoc_v3.core.exceptions import RendererError
from beedoc_v3.renders.document_render.docx_render.utils.converter import convert_docx_to_pdf
from beedoc_v3.renders.document_render.pdf_render.render_html import PdfHtmlRenderer
from beedoc_v3.utils.legacy_converter import convert_legacy_to_modern_async

if TYPE_CHECKING:
    from beedoc_v3.models.document import Document

class DocxHtmlRenderer(BaseRenderer):
    """
    HTML variant of DocxRenderer:
    1. Converting DOC/DOCX to PDF.
    2. Delegating the rendering and reconstruction to PdfHtmlRenderer.
    """

    def _build_workflow(self) -> WorkflowEngine:
        """Builds the Beeflow workflow for DOCX rendering by delegation to PdfHtmlRenderer."""
        with WorkflowEngine(
            name="docx_html_renderer_workflow",
            description="Workflow for converting DOC/DOCX to PDF and delegating to PdfHtmlRenderer",
            inputs=INPUT,
            langfuse="beegen-portal"
        ) as workflow:

            # Node 0: Convert legacy DOC to DOCX if needed
            legacy_convert_node = CodeNode(
                name="legacy_convert_node",
                code_fn=convert_legacy_to_modern_async,
                inputs={"file_path": INPUT["file_path"]},
                return_keys=["modern_file_path: str"]
            )

            # Node 1: Convert DOCX to PDF
            convert_node = CodeNode(
                name="convert_docx_to_pdf_node",
                code_fn=convert_docx_to_pdf,
                inputs={"docx_path": {legacy_convert_node: "modern_file_path"}},
                return_keys=["pdf_path: str"]
            )

            # Node 2: Delegate to PdfHtmlRenderer and get results
            delegate_node = CodeNode(
                name="delegate_to_pdf_html_renderer_node",
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

            START >> legacy_convert_node >> convert_node >> delegate_node >> END

        workflow.compile()
        return workflow

    async def _delegate_to_pdf_logic(self, pdf_path: str) -> Dict[str, Any]:
        """Logic for delegating to the PdfHtmlRenderer with the newly created PDF path."""
        from beedoc_v3.models.document import Document
        temp_doc = Document(file_path=pdf_path)

        pdf_html_renderer = PdfHtmlRenderer()
        await pdf_html_renderer.render(temp_doc)

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
            raise RendererError(f"DocxHtmlRenderer workflow failed: {str(e)}")
