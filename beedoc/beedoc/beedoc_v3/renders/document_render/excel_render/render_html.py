import uuid
import re
import html
from pathlib import Path
from typing import Any, Dict, List, TYPE_CHECKING

from beeflow.workflow import WorkflowEngine
from beeflow.nodes.base_node import START, END, INPUT, OUTPUT
from beeflow.nodes.flow.for_loop_node import ForLoopNode
from beeflow.nodes.primitives.transform.code_node import CodeNode

from beedoc_v3.renders.base import BaseRenderer
from beedoc_v3.core.exceptions import RendererError
from beedoc_v3.models.document import Page, Zone
from beedoc_v3.renders.document_render.excel_render.utils import processor
from beedoc_v3.utils.legacy_converter import convert_legacy_to_modern_async

if TYPE_CHECKING:
    from beedoc_v3.models.document import Document


class ExcelHtmlRenderer(BaseRenderer):
    """
    HTML output variant of ExcelRenderer:
    1. Converts legacy .xls to .xlsx if needed via legacy_convert_node.
    2. Extracts Excel sheet zones and reconstructs semantic HTML tables.
    3. High-performance direct structured rendering (no heavy VLM calls needed).
    """

    def _build_workflow(self) -> WorkflowEngine:
        with WorkflowEngine(
            name="excel_html_renderer_workflow",
            description="Workflow for direct structured HTML rendering of Excel spreadsheets",
            inputs=INPUT,
            langfuse="beegen-portal"
        ) as workflow:

            # Node 0: Convert legacy XLS to XLSX if needed
            legacy_convert_node = CodeNode(
                name="legacy_convert_node",
                code_fn=convert_legacy_to_modern_async,
                inputs={"file_path": {INPUT: "file_path"}},
                return_keys=["modern_file_path: str"]
            )

            # Node 1: Render Excel to Images
            render_node = CodeNode(
                name="render_node",
                code_fn=processor.render_excel_to_images,
                inputs={"file_path": {legacy_convert_node: "modern_file_path"}},
                return_keys=["pages_images: List[Dict[str, Any]]"]
            )

            # Node 2: Extract zone payloads per sheet
            zone_payloads_node = CodeNode(
                name="zone_payloads_node",
                code_fn=processor.extract_excel_zone_payloads,
                inputs={"file_path": {legacy_convert_node: "modern_file_path"}},
                return_keys=["sheet_payloads: List[Dict[str, Any]]"]
            )

            unwrap_sheet_payloads = CodeNode(
                name="unwrap_sheet_payloads",
                code_fn=self._unwrap_sheet_payloads,
                inputs={"payload": {zone_payloads_node: "sheet_payloads"}},
                return_keys=["batch_data: List[Dict[str, Any]]"]
            )

            with ForLoopNode(
                name="vlm_page_loop",
                description="Iterate through Excel sheets for HTML processing",
                inputs={
                    "batch_data": {unwrap_sheet_payloads: "batch_data"}
                }
            ) as vlm_page_loop:
                zone_messages_node = CodeNode(
                    name="zone_messages_node",
                    code_fn=self._prepare_zone_messages,
                    inputs={
                        "sheet_name": {INPUT: "sheet_name"},
                        "zones": {INPUT: "zones"}
                    },
                    return_keys=["zone_payloads: List[Dict[str, Any]]"]
                )

                with ForLoopNode(
                    name="zone_loop",
                    description="Iterate through sheet zones for HTML table generation",
                    inputs={
                        "batch_data": {zone_messages_node: "zone_payloads"}
                    }
                ) as zone_loop:
                    zone_collect_node = CodeNode(
                        name="zone_collect_node",
                        code_fn=self._collect_zone_result_html,
                        inputs={
                            "content": {INPUT: "zone_grid_text"},
                            "sheet_name": {INPUT: "zone_sheet_name"},
                            "zone": {INPUT: "zone"}
                        },
                        return_keys=["zone_result: Dict[str, Any]"],
                        outputs=OUTPUT
                    )

                    START >> zone_collect_node >> END

                sheet_collect_node = CodeNode(
                    name="sheet_collect_node",
                    code_fn=self._collect_sheet_result,
                    inputs={
                        "sheet_name": {INPUT: "sheet_name"},
                        "file_path": {INPUT: "file_path"},
                        "page_num": {INPUT: "page_num"},
                        "zones": {zone_loop: "batch_result"}
                    },
                    return_keys=["page_result: Dict[str, Any]"],
                    outputs=OUTPUT
                )

                START >> zone_messages_node >> zone_loop >> sheet_collect_node >> END

            finalize_node = CodeNode(
                name="finalize_node",
                code_fn=self._finalize_document_logic,
                inputs={
                    "vlm_results": {vlm_page_loop: "batch_result"},
                    "pages_images": {render_node: "pages_images"}
                },
                return_keys=["final_pages: List[Dict[str, Any]]", "reconstructed_content: str"],
                outputs=OUTPUT
            )

            START >> legacy_convert_node >> [render_node, zone_payloads_node] >> unwrap_sheet_payloads >> vlm_page_loop >> finalize_node >> END

        workflow.compile()
        return workflow

    def _unwrap_sheet_payloads(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return {"batch_data": []}

        zones = payload.get("zones")
        if isinstance(zones, list):
            zones_sorted = sorted(zones, key=lambda z: z.get("page_num", 0))
            return {"batch_data": zones_sorted}

        sheet_names = payload.get("sheet_name") or []
        file_paths = payload.get("file_path") or []
        zones_list = payload.get("zones") or []
        page_nums = payload.get("page_num") or []

        length = max(len(sheet_names), len(file_paths), len(zones_list), len(page_nums))
        batch_data = []
        for idx in range(length):
            batch_data.append(
                {
                    "sheet_name": sheet_names[idx] if idx < len(sheet_names) else "",
                    "file_path": file_paths[idx] if idx < len(file_paths) else "",
                    "page_num": page_nums[idx] if idx < len(page_nums) else 0,
                    "zones": zones_list[idx] if idx < len(zones_list) else [],
                }
            )

        return {"batch_data": batch_data}

    def _prepare_zone_messages(self, sheet_name: str, zones: List[Dict[str, Any]]) -> Dict[str, Any]:
        zone_payloads = [
            {
                "zone_sheet_name": sheet_name or "",
                "zone": zone_payload.get("zone"),
                "zone_grid_text": zone_payload.get("grid_text", ""),
            }
            for zone_payload in (zones or [])
        ]
        return {"zone_payloads": zone_payloads}

    def _collect_zone_result_html(self, content: str, sheet_name: str, zone: Dict[str, Any]) -> Dict[str, Any]:
        """Convert grid cell text directly to structured HTML tables/blocks."""
        text = content or ""
        cell_map: Dict[tuple, str] = {}
        last_key = None

        for line in text.splitlines():
            match = re.match(r"^\[R(\d+)C(\d+)\]\s*(.*)$", line)
            if match:
                r = int(match.group(1))
                c = int(match.group(2))
                value = match.group(3).strip()
                key = (r, c)
                cell_map[key] = value
                last_key = key
            elif last_key is not None:
                cell_map[last_key] = (cell_map.get(last_key, "") + "\n" + line).strip()

        if not cell_map:
            return {
                "zone_result": {
                    "sheet_name": sheet_name,
                    "zone": zone,
                    "content": "",
                }
            }

        rows = sorted({r for r, _ in cell_map.keys()})
        row_counts = {r: 0 for r in rows}
        for (r, _), value in cell_map.items():
            if value.strip():
                row_counts[r] += 1

        dense_rows = [r for r in rows if row_counts.get(r, 0) >= 2]
        if not dense_rows:
            html_paragraphs = [f"<p>{html.escape(cell_map[k])}</p>" for k in sorted(cell_map.keys()) if cell_map[k].strip()]
            return {
                "zone_result": {
                    "sheet_name": sheet_name,
                    "zone": zone,
                    "content": "\n".join(html_paragraphs),
                }
            }

        header_row = dense_rows[0]
        last_table_row = dense_rows[-1]

        text_lines = []
        for r in rows:
            if r >= header_row:
                break
            values = [v for (rr, _), v in cell_map.items() if rr == r and v.strip()]
            if len(values) == 1:
                text_lines.append(f"<p>{html.escape(values[0])}</p>")

        table_rows = [r for r in rows if header_row <= r <= last_table_row]
        table_cols = sorted({c for (r, c), v in cell_map.items() if r in table_rows and v.strip()})

        trailing_text_lines = []
        for r in rows:
            if r <= last_table_row:
                continue
            values = [v for (rr, _), v in cell_map.items() if rr == r and v.strip()]
            if len(values) == 1:
                trailing_text_lines.append(f"<p>{html.escape(values[0])}</p>")

        # Build HTML table
        table_html = ['<table border="1" class="excel-table">']

        # Header row
        table_html.append('  <thead>')
        table_html.append('    <tr>')
        for c in table_cols:
            val = html.escape(cell_map.get((header_row, c), "").strip()).replace("\n", "<br>")
            table_html.append(f'      <th>{val}</th>')
        table_html.append('    </tr>')
        table_html.append('  </thead>')

        # Body rows
        table_html.append('  <tbody>')
        for r in table_rows:
            if r == header_row:
                continue
            table_html.append('    <tr>')
            for c in table_cols:
                val = html.escape(cell_map.get((r, c), "").strip()).replace("\n", "<br>")
                table_html.append(f'      <td>{val}</td>')
            table_html.append('    </tr>')
        table_html.append('  </tbody>')
        table_html.append('</table>')

        content_parts = []
        if text_lines:
            content_parts.extend(text_lines)
        content_parts.append("\n".join(table_html))
        if trailing_text_lines:
            content_parts.extend(trailing_text_lines)

        return {
            "zone_result": {
                "sheet_name": sheet_name,
                "zone": zone,
                "content": "\n".join(content_parts),
            }
        }

    def _collect_sheet_result(self, sheet_name: str, file_path: str, zones: List[Dict[str, Any]], page_num: int = 0) -> Dict[str, Any]:
        zone_results = [z.get("zone_result", z) for z in zones if isinstance(z, dict)]
        zone_results = [z for z in zone_results if z.get("sheet_name") in (None, sheet_name)]
        zone_results.sort(key=lambda z: (z.get("zone", {}).get("min_row", 0), z.get("zone", {}).get("min_col", 0)))

        zone_contents = [z.get("content", "") for z in zone_results if z.get("content")]

        return {
            "page_result": {
                "page_num": page_num or 0,
                "sheet_name": sheet_name,
                "content": zone_contents
            }
        }

    def _finalize_document_logic(self, vlm_results: List[Dict[str, Any]], pages_images: List[Dict[str, Any]]) -> Dict[str, Any]:
        sorted_results = []
        if vlm_results:
            inner_results = [r["page_result"] for r in vlm_results if isinstance(r, dict) and "page_result" in r]
            sorted_results = sorted(inner_results, key=lambda x: x["page_num"])

        processed_pages = []
        for p in pages_images:
            page_data = {
                "page_number": p["page_number"],
                "image_data": p["image_data"],
                "metadata": p.get("metadata", {}),
                "content": "",
                "image_list": []
            }

            extracted = next((r for r in sorted_results if r["page_num"] == p["page_number"]), None)
            if extracted:
                sheet_name = extracted.get("sheet_name")
                if sheet_name is not None:
                    page_data["metadata"]["sheet_name"] = sheet_name
                content_list = extracted.get("content")
                if isinstance(content_list, list):
                    page_data["content"] = "\n\n".join([chunk for chunk in content_list if chunk])

            processed_pages.append(page_data)

        # Build full HTML output
        html_chunks = []
        for p in processed_pages:
            sheet = p["metadata"].get("sheet_name", f"Sheet {p['page_number']}")
            if p["content"]:
                html_chunks.append(f'<div class="excel-sheet" data-sheet="{html.escape(sheet)}">\n<h2>{html.escape(sheet)}</h2>\n{p["content"]}\n</div>')

        reconstructed_content = "\n\n".join(html_chunks)

        return {
            "final_pages": processed_pages,
            "reconstructed_content": reconstructed_content
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
            return document

        except Exception as e:
            raise RendererError(f"ExcelHtmlRenderer workflow failed: {str(e)}")
