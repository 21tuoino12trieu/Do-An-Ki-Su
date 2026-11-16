import uuid
from typing import Any, Dict, TYPE_CHECKING
from beeflow.workflow import WorkflowEngine
from beeflow.nodes.base_node import START, END, INPUT, OUTPUT
from beeflow.nodes.primitives.ai.llm_node import LLMNode
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beedoc_v3.renders.base import BaseRenderer
from beedoc_v3.core.exceptions import RendererError
from beedoc_v3.models.document import Page, Zone

if TYPE_CHECKING:
    from beedoc_v3.models.document import Document

class ImageRenderer(BaseRenderer):
    """
    Image Renderer focused on VLM Reconstruction for single images.
    """

    def _build_workflow(self) -> WorkflowEngine:
        """Builds the Beeflow workflow for Image reconstruction."""
        with WorkflowEngine(
            name="image_renderer_workflow",
            description="Workflow for reconstructing content from a single image using VLM",
            inputs=INPUT,
            langfuse="beegen-portal"
        ) as workflow:

            # Node 1: Prepare VLM message (Reads from local file_path)
            prep_node = CodeNode(
                name="prep_node",
                code_fn=self._prepare_image_logic,
                inputs={"file_path": {INPUT: "file_path"}},
                return_keys=["messages: List[Dict[str, Any]]"]
            )

            # Node 2: VLM Call using LLMNode for correct multimodal support
            vlm_node = LLMNode(
                name="vlm_node",
                resource_key="gemini-3.1-flash-lite-chat",
                inputs={
                    "messages": {prep_node: "messages"}
                },
                outputs={"content": OUTPUT}
            )

            START >> prep_node >> vlm_node >> END

        workflow.compile()
        return workflow

    @staticmethod
    def _prepare_image_logic(file_path: str) -> Dict[str, Any]:
        """Reads image from local path and prepares VLM message."""
        import base64
        with open(file_path, "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode("utf-8")

        return {
            "messages": [
                {
                    "role": "system",
                    "content": [
                        {"type": "text", "text": "Hãy trích xuất nội dung của hình ảnh này sang Markdown chuẩn."}
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Nội dung ảnh dưới đây:"},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}
                        },
                    ],
                },
            ]
        }

    async def render(self, document: 'Document') -> 'Document':
        """Executes the workflow and updates the Document content."""
        if not self.workflow:
            self.workflow = self._build_workflow()

        try:
            results = await self.workflow.run(
                inputs={"file_path": document.file_path},
                request_id=str(uuid.uuid4())
            )

            # Update Document content from AI result
            content = results.get("vlm_node", {}).get("content", "")
            document.reconstructed_content = content

            # Clear existing pages to avoid duplicates
            document.pages = []

            # Read image for storage if needed, or just use the path
            import base64
            with open(document.file_path, "rb") as f:
                img_data = base64.b64encode(f.read()).decode("utf-8")

            # Create a single page for the image
            page = Page(
                page_number=1,
                image_data=img_data,
                content=[Zone(content=content)] if content else []
            )
            document.add_page(page)

            return document
        except Exception as e:
            raise RendererError(f"ImageRenderer workflow failed: {str(e)}")
