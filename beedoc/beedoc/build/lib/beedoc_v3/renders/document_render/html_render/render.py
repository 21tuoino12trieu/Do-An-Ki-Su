import uuid
from typing import TYPE_CHECKING
from beeflow.nodes.base_node import END, INPUT, OUTPUT, START
from beeflow.nodes.flow.for_loop_node import ForLoopNode
from beeflow.nodes.primitives.ai.llm_node import LLMNode
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beeflow.workflow import WorkflowEngine
from beedoc_v3.core.exceptions import RendererError
from beedoc_v3.renders.base import BaseRenderer
from beedoc_v3.renders.document_render.html_render.utils.processor import (
    parse_html_to_structure,
    prepare_html_source,
    render_blocks_to_markdown,
)
from beedoc_v3.renders.document_render.html_render.utils.image_pipeline import (
    collect_image_gate_result,
    finalize_html_images,
    prepare_image_gate_prompt,
    resolve_html_images,
)

if TYPE_CHECKING:
    from beedoc_v3.models.document import Document


class HtmlRenderer(BaseRenderer):
    """Render HTML into structured blocks plus markdown output."""

    def _build_workflow(self) -> WorkflowEngine:
        with WorkflowEngine(
            name="html_renderer_workflow",
            description="Workflow for converting HTML to structured markdown",
            inputs=INPUT,
            langfuse="beegen-portal",
        ) as workflow:
            prepare_node = CodeNode(
                name="prepare_html_source",
                code_fn=prepare_html_source,
                inputs={"file_path": {INPUT: "file_path"},},
                return_keys=["normalized_raw_content: str"],
            )

            parse_node = CodeNode(
                name="parse_html_to_structure",
                code_fn=parse_html_to_structure,
                inputs={
                    "normalized_raw_content": {prepare_node: "normalized_raw_content"},
                },
                return_keys=["html_payload: Dict[str, Any]"],
            )

            resolve_images_node = CodeNode(
                name="resolve_html_images",
                code_fn=resolve_html_images,
                inputs={"parsed_html_payload": {parse_node: "html_payload"},},
                return_keys=[
                    "html_payload: Dict[str, Any]",
                    "image_batch_data: List[Dict[str, Any]]",
                ],
            )

            with ForLoopNode(
                name="html_image_gate_loop",
                description="Gate HTML images with VLM",
                max_concurrency=15,
                inputs={"batch_data": {resolve_images_node: "image_batch_data"},},
            ) as image_gate_loop:
                image_gate_prompt = CodeNode(
                    name="html_image_gate_prompt",
                    code_fn=prepare_image_gate_prompt,
                    inputs={
                        "image_id": {INPUT: "image_id"},
                        "image_format": {INPUT: "image_format"},
                        "image_base64": {INPUT: "image_base64"},
                    },
                    return_keys=[
                        "messages: List[Dict[str, Any]]",
                        "payload: Dict[str, Any]",
                    ],
                )

                image_gate_llm = LLMNode(
                    name="html_image_gate_llm",
                    resource_key="gemini-3.1-flash-lite-chat",
                    inputs={
                        "messages": {image_gate_prompt: "messages"},
                        "reasoning_effort": "none",
                    },
                )

                image_gate_collect = CodeNode(
                    name="html_image_gate_collect",
                    code_fn=collect_image_gate_result,
                    inputs={
                        "content": {image_gate_llm: "content"},
                        "payload": {image_gate_prompt: "payload"},
                    },
                    return_keys=["gate_result: Dict[str, Any]"],
                    outputs=OUTPUT,
                )

                START >> image_gate_prompt >> image_gate_llm >> image_gate_collect >> END

            finalize_images_node = CodeNode(
                name="finalize_html_images",
                code_fn=finalize_html_images,
                inputs={
                    "resolved_html_payload": {resolve_images_node: "html_payload"},
                    "gate_results": {image_gate_loop: "batch_result"},
                },
                return_keys=["html_payload: Dict[str, Any]"],
            )

            render_node = CodeNode(
                name="render_blocks_to_markdown",
                code_fn=render_blocks_to_markdown,
                inputs={
                    "finalized_html_payload": {finalize_images_node: "html_payload"},
                },
                return_keys=["reconstructed_content: str"],
                outputs=OUTPUT,
            )

            START >> prepare_node >> parse_node >> resolve_images_node >> image_gate_loop >> finalize_images_node >> render_node >> END

        workflow.compile()
        return workflow

    async def render(self, document: "Document") -> "Document":
        if not self.workflow:
            self.workflow = self._build_workflow()
        try:
            results = await self.workflow.run(
                inputs={"file_path": document.file_path,}, request_id=str(uuid.uuid4()),
            )
            document.reconstructed_content = (
                results.get("reconstructed_content", "") or ""
            ).strip()
            document.pages = []
            return document
        except Exception as e:
            raise RendererError(f"HtmlRenderer workflow failed: {str(e)}") from e
