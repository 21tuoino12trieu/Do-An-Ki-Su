import uuid
from typing import Dict, List, TYPE_CHECKING

import pandas as pd
from beeflow.workflow import WorkflowEngine
from beeflow.nodes.base_node import START, END, INPUT, OUTPUT
from beeflow.nodes.primitives.transform.code_node import CodeNode

from beedoc_v3.renders.base import BaseRenderer
from beedoc_v3.core.exceptions import RendererError
from beedoc_v3.models.document import Page, Zone

if TYPE_CHECKING:
    from beedoc_v3.models.document import Document


class CsvRenderer(BaseRenderer):
    """CSV renderer that reconstructs CSV into markdown table."""

    def _build_workflow(self) -> WorkflowEngine:
        with WorkflowEngine(
            name="csv_renderer_workflow",
            description="Workflow for converting CSV to markdown table",
            inputs=INPUT,
            langfuse="beegen-portal"
        ) as workflow:
            read_node = CodeNode(
                name="read_csv_to_markdown",
                code_fn=self._read_csv_markdown,
                inputs={"file_path": {INPUT: "file_path"}},
                return_keys=["content: str"],
                outputs=OUTPUT
            )

            START >> read_node >> END

        workflow.compile()
        return workflow

    @staticmethod
    def _escape_cell(value: str) -> str:
        text = "" if value is None else str(value)
        text = text.replace("\n", "<br>")
        text = text.replace("|", "\\|")
        return text

    @classmethod
    def _read_csv_markdown(cls, file_path: str) -> Dict[str, str]:
        df = pd.read_csv(file_path, dtype=str, keep_default_na=False)

        columns: List[str] = [cls._escape_cell(col) for col in df.columns.tolist()]
        if not columns:
            return {"content": ""}

        header = "| " + " | ".join(columns) + " |"
        separator = "| " + " | ".join([":---" for _ in columns]) + " |"

        rows = []
        for _, row in df.iterrows():
            values = [cls._escape_cell(row[col]) for col in df.columns.tolist()]
            rows.append("| " + " | ".join(values) + " |")

        content = "\n".join([header, separator] + rows)
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
            raise RendererError(f"CsvRenderer workflow failed: {str(e)}")
