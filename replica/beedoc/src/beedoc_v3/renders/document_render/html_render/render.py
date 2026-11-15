import uuid
from typing import TYPE_CHECKING

from beedoc_v3.core.exceptions import RendererError
from beedoc_v3.renders.base import BaseRenderer
from .utils.pipeline import prepare_html_source, render_html_source
from .utils.processor import parse_html_to_structure

if TYPE_CHECKING:
    from beedoc_v3.models.document import Document
    from beeflow.workflow import WorkflowEngine


class HtmlRenderer(BaseRenderer):
    """Giữ graph HTML của bản gốc, bỏ toàn bộ nhánh image gate/model."""

    def _build_workflow(self) -> "WorkflowEngine":
        from beeflow.nodes.base_node import END, INPUT, OUTPUT, START
        from beeflow.nodes.primitives.transform.code_node import CodeNode
        from beeflow.workflow import WorkflowEngine

        with WorkflowEngine(
            name="html_renderer_workflow",
            description="HTML to Markdown",
            inputs=INPUT,
        ) as workflow:
            prepare_node = CodeNode(
                name="prepare_html_source",
                code_fn=prepare_html_source,
                inputs={"file_path": {INPUT: "file_path"}},
                return_keys=["normalized_raw_content: str", "image_tags: Dict[str, str]"],
            )
            parse_node = CodeNode(
                name="parse_html_to_structure",
                code_fn=parse_html_to_structure,
                inputs={"normalized_raw_content": {prepare_node: "normalized_raw_content"}},
                return_keys=["html_payload: Dict[str, Any]"],
            )
            render_node = CodeNode(
                name="render_blocks_to_markdown",
                code_fn=render_html_source,
                inputs={
                    "html_payload": {parse_node: "html_payload"},
                    "image_tags": {prepare_node: "image_tags"},
                },
                return_keys=["reconstructed_content: str"],
                outputs=OUTPUT,
            )
            START >> prepare_node >> parse_node >> render_node >> END
        workflow.compile()
        return workflow

    async def render(self, document: "Document") -> "Document":
        if not self.workflow:
            self.workflow = self._build_workflow()
        try:
            results = await self.workflow.run(
                inputs={"file_path": document.file_path}, request_id=str(uuid.uuid4()),
            )
            # Đầu ra rỗng là hợp lệ; thiếu key là lỗi thực thi, không coi là rỗng.
            content = results["reconstructed_content"]
            if not isinstance(content, str):
                raise TypeError("Workflow phải trả reconstructed_content dạng chuỗi.")
            document.reconstructed_content = content
            document.pages = []
            return document
        except Exception as exc:
            raise RendererError(f"HtmlRenderer workflow thất bại: {exc}") from exc
