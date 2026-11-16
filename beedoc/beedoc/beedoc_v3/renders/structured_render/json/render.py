import json
import uuid
from typing import Any, Dict, List, TYPE_CHECKING

from beeflow.workflow import WorkflowEngine
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beeflow.nodes.base_node import START, END, INPUT, OUTPUT

from beedoc_v3.renders.base import BaseRenderer
from beedoc_v3.core.exceptions import RendererError
from beedoc_v3.models.document import Page, Zone

if TYPE_CHECKING:
    from beedoc_v3.models.document import Document


class JsonRenderer(BaseRenderer):
    """JSON renderer that reconstructs JSON into heading-based markdown."""

    def _build_workflow(self) -> WorkflowEngine:
        with WorkflowEngine(
            name="json_renderer_workflow",
            description="Workflow for converting JSON to heading-based markdown",
            inputs=INPUT,
            langfuse="beegen-portal"
        ) as workflow:
            read_node = CodeNode(
                name="read_json_to_markdown",
                code_fn=self._read_json_markdown,
                inputs={"file_path": {INPUT: "file_path"}},
                return_keys=["content: str"],
                outputs=OUTPUT
            )

            START >> read_node >> END

        workflow.compile()
        return workflow

    @staticmethod
    def _format_scalar(value: Any) -> str:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    @classmethod
    def _to_markdown(cls, data: Any, level: int = 1, key: str = "") -> List[str]:
        lines: List[str] = []

        if isinstance(data, dict):
            if key:
                lines.append(f"{'#' * min(level, 6)} {key}")
                lines.append("")

            for child_key, child_value in data.items():
                lines.extend(cls._to_markdown(child_value, level + 1 if key else level, str(child_key)))

        elif isinstance(data, list):
            if key:
                lines.append(f"{'#' * min(level, 6)} {key}")
                lines.append("")

            for item in data:
                if isinstance(item, (dict, list)):
                    lines.extend(cls._to_markdown(item, level + 1, ""))
                else:
                    lines.append(f"- {cls._format_scalar(item)}")
            lines.append("")

        else:
            if key:
                lines.append(f"- **{key}**: {cls._format_scalar(data)}")
            else:
                lines.append(cls._format_scalar(data))
            lines.append("")

        return lines

    @classmethod
    def _read_json_markdown(cls, file_path: str) -> Dict[str, str]:
        with open(file_path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        markdown_lines = cls._to_markdown(payload)
        content = "\n".join(markdown_lines).strip()
        return {"content": content}

    async def render(self, document: 'Document') -> 'Document':
        if not self.workflow:
            self.workflow = self._build_workflow()

        try:
            results = await self.workflow.run(
                inputs={"file_path": document.file_path},
                request_id=str(uuid.uuid4())
            )

            content = (results.get("content", "") or "").strip()
            document.pages = []

            if content:
                page = Page(page_number=1, content=[Zone(content=content)])
                document.add_page(page)

            document.reconstructed_content = document.get_full_markdown()
            return document
        except Exception as e:
            raise RendererError(f"JsonRenderer workflow failed: {str(e)}")
