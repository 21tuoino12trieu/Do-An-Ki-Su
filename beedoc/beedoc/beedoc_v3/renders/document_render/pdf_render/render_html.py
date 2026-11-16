"""
HTML output variant of PdfRenderer. Uses parallel ForLoopNode constructs for
VLM page extraction and boundary merge verification, achieving maximum speed
by executing Gemini LLM calls in parallel with configurable max_concurrency.
"""
import time
import uuid
import re
from typing import Any, Dict, List, TYPE_CHECKING
from beeflow.workflow import WorkflowEngine
from beeflow.nodes.base_node import START, END, INPUT, OUTPUT
from beeflow.nodes.flow.for_loop_node import ForLoopNode
from beeflow.nodes.primitives.ai.llm_node import LLMNode
from beeflow.nodes.primitives.transform.code_node import CodeNode

from beedoc_v3.renders.base import BaseRenderer
from beedoc_v3.core.exceptions import RendererError
from beedoc_v3.models.document import Page, Zone
from beedoc_v3.renders.document_render.pdf_render.utils.extractor import PDFExtractor
from beedoc_v3.renders.document_render.pdf_render.utils import logic_html as logic
from beedoc_v3.renders.utils.vlm_image_gate import build_image_gate_messages, parse_image_gate_response

MERGE_VERIFY_THRESHOLD = 20000

if TYPE_CHECKING:
    from beedoc_v3.models.document import Document


class PdfHtmlRenderer(BaseRenderer):
    """
    HTML variant of PdfRenderer:
    1. Rendering PDF pages to Images (Base64)
    2. Parallel VLM Page extraction using ForLoopNode (max_concurrency=10)
    3. Parallel Boundary Merge verification using ForLoopNode (max_concurrency=10)
    """

    def _build_workflow(self) -> WorkflowEngine:
        """Builds the Beeflow workflow for parallel PDF rendering and HTML reconstruction."""
        with WorkflowEngine(
            name="pdf_html_renderer_workflow",
            description="Parallel workflow for rendering PDF to images and reconstructing HTML using VLM and boundary merging",
            inputs=INPUT,
            langfuse="beegen-portal"
        ) as workflow:

            # Node 0: Strip images from PDF before rendering
            strip_images_node = CodeNode(
                name="strip_images_node",
                code_fn=logic.strip_images_from_pdf,
                inputs={"input_file_path": INPUT["file_path"]},
                return_keys=["processed_file_path: str", "removed_images: int"]
            )

            # Node 1: Render PDF to Images and count pages
            render_node = CodeNode(
                name="render_node",
                code_fn=self._render_pdf_with_total_pages,
                inputs={"file_path": {strip_images_node: "processed_file_path"}},
                return_keys=["pages: List[Dict[str, Any]]", "total_pages: int"]
            )

            # Node 1b: Extract document identifiers from the first 3 rendered pages
            doc_metadata_prompt = CodeNode(
                name="doc_metadata_prompt",
                code_fn=self._prepare_doc_metadata_prompt,
                inputs={
                    "pages": {render_node: "pages"},
                    "total_pages": {render_node: "total_pages"}
                },
                return_keys=["doc_metadata_messages: List[Dict[str, Any]]"]
            )

            doc_metadata_llm = LLMNode(
                name="doc_metadata_llm",
                resource_key="gemini-3.1-flash-lite-chat",
                inputs={
                    "messages": {doc_metadata_prompt: "doc_metadata_messages"},
                    "reasoning_effort": "none",
                    "max_tokens": 65535
                }
            )

            doc_metadata_collect = CodeNode(
                name="doc_metadata_collect",
                code_fn=self._collect_doc_metadata,
                inputs={"content": {doc_metadata_llm: "content"}},
                return_keys=["extracted_document_metadata: Dict[str, Any]"]
            )

            # Node 3: Extract Image References
            image_references = CodeNode(
                name="get_image_references",
                code_fn=self._extract_images_references_logic,
                inputs={"file_path": INPUT["file_path"]},
                return_keys=["image_references: Dict[int, Any]"]
            )

            image_gate_batch = CodeNode(
                name="image_gate_batch",
                code_fn=self._prepare_image_gate_batch,
                inputs={
                    "image_references": {image_references: "image_references"}
                },
                return_keys=["batch_data: List[Dict[str, Any]]"]
            )

            with ForLoopNode(
                name="image_gate_loop",
                description="Gate PDF images with VLM",
                inputs={
                    "batch_data": {image_gate_batch: "batch_data"}
                },
                max_concurrency=15
            ) as image_gate_loop:
                image_gate_prompt = CodeNode(
                    name="image_gate_prompt",
                    code_fn=self._prepare_image_gate_prompt,
                    inputs={
                        "image_item": {INPUT: "image_item"},
                        "text_context": {INPUT: "text_context"},
                        "page_num": {INPUT: "page_num"},
                        "image_bytes": {INPUT: "image_bytes"}
                    },
                    return_keys=["messages: List[Dict[str, Any]]", "payload: Dict[str, Any]"]
                )

                image_gate_llm = LLMNode(
                    name="image_gate_llm",
                    resource_key="gemini-3.1-flash-lite-chat",
                    inputs={
                        "messages": {image_gate_prompt: "messages"},
                        "reasoning_effort": "none",
                        "max_tokens": 65535
                    }
                )

                image_gate_collect = CodeNode(
                    name="image_gate_collect",
                    code_fn=self._collect_image_gate_result,
                    inputs={
                        "content": {image_gate_llm: "content"},
                        "payload": {image_gate_prompt: "payload"}
                    },
                    return_keys=["gate_result: Dict[str, Any]"],
                    outputs=OUTPUT
                )

                START >> image_gate_prompt >> image_gate_llm >> image_gate_collect >> END

            image_gate_finalize = CodeNode(
                name="image_gate_finalize",
                code_fn=self._finalize_image_gate_results,
                inputs={
                    "gate_results": {image_gate_loop: "batch_result"}
                },
                return_keys=["image_references: Dict[int, Any]"]
            )

            # ── Parallel Phase 1: VLM Page Extraction ──
            vlm_batch_prep = CodeNode(
                name="vlm_batch_prep",
                code_fn=self._prepare_vlm_batch,
                inputs={
                    "pages": {render_node: "pages"},
                    "total_pages": {render_node: "total_pages"},
                    "image_references": {image_gate_finalize: "image_references"}
                },
                return_keys=["vlm_batch: List[Dict[str, Any]]"]
            )

            with ForLoopNode(
                name="vlm_extract_loop",
                description="Extract VLM HTML for all PDF pages in parallel",
                inputs={
                    "batch_data": {vlm_batch_prep: "vlm_batch"}
                },
                max_concurrency=15
            ) as vlm_extract_loop:
                vlm_prep_node = CodeNode(
                    name="vlm_prep_node",
                    code_fn=self._prepare_vlm_input_item,
                    inputs={
                        "page_item": {INPUT: "page_item"},
                        "total_pages": {INPUT: "total_pages"}
                    },
                    return_keys=["messages: List[Dict[str, Any]]", "page_number: int"]
                )

                extract_node = LLMNode(
                    name="vlm_extract_node",
                    resource_key="gemini-3.1-flash-lite-chat",
                    inputs={
                        "messages": {vlm_prep_node: "messages"},
                        "reasoning_effort": "none",
                        "max_tokens": 65535
                    }
                )

                insert_image_node = CodeNode(
                    name="insert_image_node",
                    code_fn=logic.insert_images_into_text,
                    inputs={
                        "page_content": {extract_node: "content"},
                        "page_num": {vlm_prep_node: "page_number"},
                        "image_references": {INPUT: "image_references"}
                    },
                    return_keys=["final_content: str"]
                )

                vlm_page_collect = CodeNode(
                    name="vlm_page_collect",
                    code_fn=self._collect_vlm_page_result,
                    inputs={
                        "page_number": {vlm_prep_node: "page_number"},
                        "content": {insert_image_node: "final_content"}
                    },
                    return_keys=["page_result: Dict[str, Any]"],
                    outputs=OUTPUT
                )

                START >> vlm_prep_node >> extract_node >> insert_image_node >> vlm_page_collect >> END

            # ── Parallel Phase 2: Boundary Merge Verification ──
            merge_batch_prep = CodeNode(
                name="merge_batch_prep",
                code_fn=self._prepare_merge_batch,
                inputs={
                    "vlm_batch_result": {vlm_extract_loop: "batch_result"}
                },
                return_keys=["merge_batch: List[Dict[str, Any]]", "sorted_page_results: List[Dict[str, Any]]"]
            )

            with ForLoopNode(
                name="merge_verify_loop",
                description="Verify boundary continuation merges in parallel",
                inputs={
                    "batch_data": {merge_batch_prep: "merge_batch"}
                },
                max_concurrency=10
            ) as merge_verify_loop:
                merge_verify_prompt = CodeNode(
                    name="merge_verify_prompt",
                    code_fn=self._prepare_merge_verify_prompt,
                    inputs={
                        "prev_block": {INPUT: "prev_block"},
                        "current_block": {INPUT: "current_block"},
                        "pair_index": {INPUT: "pair_index"}
                    },
                    return_keys=["merge_messages: List[Dict[str, Any]]", "merge_payload: Dict[str, Any]"]
                )

                merge_verify_llm = LLMNode(
                    name="html_merge_verify_llm",
                    resource_key="gemini-3.1-flash-lite-chat",
                    inputs={
                        "messages": {merge_verify_prompt: "merge_messages"},
                        "reasoning_effort": "none",
                        "max_tokens": 65535
                    }
                )

                merge_verify_collect = CodeNode(
                    name="merge_verify_collect",
                    code_fn=self._collect_merge_verify_result,
                    inputs={
                        "content": {merge_verify_llm: "content"},
                        "payload": {merge_verify_prompt: "merge_payload"}
                    },
                    return_keys=["merge_result: Dict[str, Any]"],
                    outputs=OUTPUT
                )

                START >> merge_verify_prompt >> merge_verify_llm >> merge_verify_collect >> END

            # ── Finalization ──
            finalize_pdf_node = CodeNode(
                name="finalize_pdf_node",
                code_fn=self._finalize_pdf_logic,
                inputs={
                    "sorted_page_results": {merge_batch_prep: "sorted_page_results"},
                    "pages": {render_node: "pages"},
                    "merge_batch_results": {merge_verify_loop: "batch_result"},
                    "in_document_metadata": {doc_metadata_collect: "extracted_document_metadata"},
                    "image_references": {image_gate_finalize: "image_references"}
                },
                return_keys=[
                    "final_pages: List[Dict[str, Any]]",
                    "reconstructed_content: str",
                    "document_metadata: Dict[str, Any]"
                ],
                outputs=OUTPUT
            )

            START >> strip_images_node
            START >> image_references
            strip_images_node >> render_node
            render_node >> doc_metadata_prompt >> doc_metadata_llm >> doc_metadata_collect
            image_references >> image_gate_batch >> image_gate_loop >> image_gate_finalize
            render_node >> vlm_batch_prep
            image_gate_finalize >> vlm_batch_prep
            vlm_batch_prep >> vlm_extract_loop
            image_gate_finalize >> vlm_extract_loop
            vlm_extract_loop >> merge_batch_prep >> merge_verify_loop
            merge_batch_prep >> finalize_pdf_node
            merge_verify_loop >> finalize_pdf_node
            doc_metadata_collect >> finalize_pdf_node
            finalize_pdf_node >> END

        workflow.compile()
        return workflow

    def _prepare_vlm_batch(self, pages: List[Dict[str, Any]], total_pages: int, image_references: Dict[int, Any]) -> Dict[str, Any]:
        batch = [
            {"page_item": page, "total_pages": total_pages, "image_references": image_references}
            for page in (pages or [])
        ]
        return {"vlm_batch": batch}

    def _prepare_vlm_input_item(self, page_item: Dict[str, Any], total_pages: int) -> Dict[str, Any]:
        page_number = page_item["page_number"]
        image_data = page_item["image_data"]
        system_prompt = logic.get_pdf_html_system_prompt()
        user_prompt = logic.get_pdf_html_user_prompt(context_summary="", heading_tree="")
        messages = [
            {
                "role": "system",
                "content": [{"type": "text", "text": system_prompt}]
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}
                    }
                ]
            }
        ]
        return {"messages": messages, "page_number": page_number}

    def _collect_vlm_page_result(self, page_number: int, content: str) -> Dict[str, Any]:
        return {
            "page_result": {
                "page_number": page_number,
                "text": content or ""
            }
        }

    def _prepare_merge_batch(self, vlm_batch_result: List[Dict[str, Any]]) -> Dict[str, Any]:
        page_results = []
        for item in (vlm_batch_result or []):
            res = item.get("page_result", item) if isinstance(item, dict) else None
            if isinstance(res, dict) and res.get("page_number"):
                page_results.append(res)

        page_results.sort(key=lambda x: x["page_number"])

        merge_batch = []
        pair_index = 0
        for i in range(len(page_results) - 1):
            prev_text = (page_results[i].get("text") or "").strip()
            match = re.match(r"^\[CONTINUES\](True|False)\[/CONTINUES\]", prev_text, flags=re.IGNORECASE)
            if match and match.group(1).lower() == "true":
                merge_batch.append({
                    "pair_index": pair_index,
                    "prev_block": page_results[i]["text"],
                    "current_block": page_results[i+1]["text"],
                })
                pair_index += 1

        return {
            "merge_batch": merge_batch,
            "sorted_page_results": page_results
        }

    def _prepare_doc_metadata_prompt(self, pages: List[Dict[str, Any]], total_pages: int) -> Dict[str, Any]:
        selected_pages = list(pages or [])[:3]
        page_numbers = [p.get("page_number") for p in selected_pages if p.get("page_number")]
        user_content = [
            {
                "type": "text",
                "text": logic.get_doc_metadata_user_prompt(total_pages, page_numbers)
            }
        ]

        for page in selected_pages:
            image_data = page.get("image_data")
            if not image_data:
                continue
            page_number = page.get("page_number")
            user_content.extend([
                {"type": "text", "text": f"Trang {page_number}:"},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}
                },
            ])

        return {
            "doc_metadata_messages": [
                {
                    "role": "system",
                    "content": [{"type": "text", "text": logic.get_doc_metadata_system_prompt()}]
                },
                {
                    "role": "user",
                    "content": user_content,
                },
            ]
        }

    def _collect_doc_metadata(self, content: str) -> Dict[str, Any]:
        return {"extracted_document_metadata": logic.parse_doc_metadata_response(content or "")}

    def _extract_images_references_logic(self, file_path: str) -> Dict[str, Any]:
        extractor = PDFExtractor()
        image_references = extractor.get_pdf_images_reference(file_path, "tmp_doc", "tmp_bot")
        image_references = logic.filter_repetitive_layout_images(image_references)
        return {"image_references": image_references}

    def _prepare_merge_verify_prompt(self, prev_block: str, current_block: str, pair_index: int) -> Dict[str, Any]:
        prev_block = logic.strip_continues_tag_html(prev_block)
        current_block = logic.strip_continues_tag_html(current_block)

        prev_prefix, prev_tail, current_head, current_suffix = logic.extract_html_boundary_blocks(prev_block, current_block)

        system_prompt = logic.get_merge_verify_html_system_prompt()
        user_prompt = logic.get_merge_verify_html_user_prompt(prev_tail, current_head)
        return {
            "merge_messages": [
                {"role": "system", "content": [{"type": "text", "text": system_prompt}]},
                {"role": "user", "content": [{"type": "text", "text": user_prompt}]},
            ],
            "merge_payload": {
                "pair_index": pair_index,
                "prev_prefix": prev_prefix,
                "current_suffix": current_suffix,
            }
        }

    def _collect_merge_verify_result(self, content: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        cleaned_content = logic.strip_continues_tag_html((content or "").strip())
        cleaned_content = cleaned_content.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")

        prev_prefix = payload.get("prev_prefix", "")
        current_suffix = payload.get("current_suffix", "")

        full_merged = logic.reconstruct_merged_boundary(prev_prefix, cleaned_content, current_suffix)
        return {
            "merge_result": {
                "pair_index": payload.get("pair_index"),
                "content": full_merged
            }
        }

    def _finalize_pdf_logic(
        self,
        sorted_page_results: List[Dict[str, Any]],
        pages: List[Dict[str, Any]],
        merge_batch_results: List[Dict[str, Any]],
        in_document_metadata: Dict[str, Any],
        image_references: Dict[int, Any] = None
    ) -> Dict[str, Any]:
        processed_pages = []
        for p in pages:
            page_data = {
                "page_number": p["page_number"],
                "image_data": p["image_data"],
                "metadata": {"width": p.get("width"), "height": p.get("height")},
                "content": [],
                "image_list": None
            }

            extracted = next((item for item in (sorted_page_results or []) if item["page_number"] == p["page_number"]), None)
            if extracted:
                text = extracted.get("text") or ""
                page_data["content"] = [{"content": text, "metadata": {}}] if text else []
                page_data["image_list"] = extracted.get("image_list")

            processed_pages.append(page_data)

        verified_list = []
        for item in (merge_batch_results or []):
            res = item.get("merge_result", item) if isinstance(item, dict) else None
            if isinstance(res, dict):
                verified_list.append({
                    "pair_index": res.get("pair_index"),
                    "content": (res.get("content") or "").strip(),
                })
        verified_list.sort(key=lambda x: x.get("pair_index") if x.get("pair_index") is not None else -1)

        pages_sorted = [r for r in sorted((sorted_page_results or []), key=lambda x: x["page_number"]) if r.get("text")]
        combined_text = "\n".join([r["text"] for r in pages_sorted])

        pair_counter = [0]
        def verify_fn(prev_block: str, current_block: str):
            idx = pair_counter[0]
            pair_counter[0] += 1
            candidate = verified_list[idx]["content"] if idx < len(verified_list) else None
            if candidate and len(candidate) < MERGE_VERIFY_THRESHOLD:
                return candidate
            return "".join([b for b in [prev_block, current_block] if b])

        reconstructed_content = logic.merge_continues_blocks_html(combined_text, verify_fn=verify_fn)

        # Document-level image matching & replacement post-processing to fix cross-page layout issues
        if image_references:
            # 1. Clean up any existing image tags and placeholder empty paragraphs
            # We first extract all embedded image details from the existing content to preserve dimensions
            existing_images = {}
            img_pattern = re.compile(
                r"<img[^>]*?src=['\"](?P<src>[^'\"]*?)['\"][^>]*?width=['\"](?P<w>\d+)['\"][^>]*?height=['\"](?P<h>\d+)['\"][^>]*?>"
            )
            for m in img_pattern.finditer(reconstructed_content):
                src = m.group("src")
                w = m.group("w")
                h = m.group("h")
                existing_images[src] = (w, h)

            # Strip all image tags from the content
            clean_content = img_pattern.sub("", reconstructed_content)
            # Strip empty paragraph wrappers left over from image removals
            clean_content = re.sub(r"<p>\s*</p>", "", clean_content)

            # 2. Merge all page references
            flat_references = []
            for page_num, refs in image_references.items():
                for image_item, ref_text in refs:
                    img = image_item["image"]
                    img_path = img["path"]
                    # Retain dimensions from existing images if available
                    if img_path in existing_images:
                        img["width"], img["height"] = existing_images[img_path]
                    flat_references.append((image_item, ref_text))

            # 3. Re-insert images on the entire clean content at document-level
            if flat_references:
                flat_image_refs = {0: flat_references}
                reconstructed_content = logic.insert_images_into_text(
                    page_content=clean_content,
                    page_num=0,
                    image_references=flat_image_refs
                )["final_content"]

        started_at = getattr(self, "_post_strip_images_started_at", None)
        if started_at is not None:
            elapsed_seconds = time.monotonic() - started_at
            print(
                f"[beedoc_v3 TIMING] PdfHtmlRenderer (PARALLEL): {elapsed_seconds:.2f}s from after "
                f"image-stripping to end of parallel workflow for {len(pages)} page(s)",
                flush=True,
            )

        return {
            "final_pages": processed_pages,
            "reconstructed_content": reconstructed_content,
            "document_metadata": in_document_metadata or {}
        }

    def _render_pdf_with_total_pages(self, file_path: str) -> Dict[str, Any]:
        self._post_strip_images_started_at = time.monotonic()
        result = logic.render_pdf_to_images(file_path)
        pages = result.get("pages", [])
        return {"pages": pages, "total_pages": len(pages)}

    def _prepare_image_gate_batch(self, image_references: Dict[int, Any]) -> Dict[str, Any]:
        batch = []
        for page_num, refs in (image_references or {}).items():
            for image_item, ref_text in refs:
                if logic.should_skip_image(image_item):
                    continue
                img = (image_item or {}).get("image", {})
                w = img.get("width", 0)
                h = img.get("height", 0)
                if (0 < w < 50) and (0 < h < 50):
                    continue
                path = img.get("path")
                if not path:
                    continue
                try:
                    with open(path, "rb") as f:
                        data = f.read()
                except Exception:
                    data = None
                if not data or len(data) < 500:
                    continue
                batch.append({
                    "page_num": page_num,
                    "image_item": image_item,
                    "text_context": ref_text or "",
                    "image_bytes": data,
                })
        return {"batch_data": batch}

    def _prepare_image_gate_prompt(self, image_item: Dict[str, Any], text_context: str, page_num: int, image_bytes: bytes) -> Dict[str, Any]:
        img = (image_item or {}).get("image", {})
        messages = build_image_gate_messages(text_context or "", image_bytes, img.get("ext") or "jpeg")
        return {"messages": messages, "payload": {"page_num": page_num, "image_item": image_item, "text_context": text_context}}

    def _collect_image_gate_result(self, content: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        extracted = parse_image_gate_response(content or "")
        return {
            "gate_result": {
                "page_num": payload.get("page_num"),
                "image_item": payload.get("image_item"),
                "text_context": payload.get("text_context"),
                "extracted": extracted,
            }
        }

    def _finalize_image_gate_results(self, gate_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        gated: Dict[int, Any] = {}
        for item in gate_results or []:
            result = item.get("gate_result", item) if isinstance(item, dict) else None
            if not isinstance(result, dict):
                continue
            if not result.get("extracted"):
                continue
            page_num = result.get("page_num")
            if not page_num:
                continue
            gated.setdefault(page_num, []).append((result.get("image_item"), result.get("text_context")))
        return {"image_references": gated}

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
                zones = [
                    Zone(content=z.get("content", ""), metadata=z.get("metadata", {}))
                    for z in (p_data.get("content") or [])
                    if isinstance(z, dict) and z.get("content")
                ]
                page = Page(
                    page_number=p_data["page_number"],
                    image_data=p_data["image_data"],
                    metadata=p_data["metadata"],
                    content=zones,
                    image_list=p_data["image_list"]
                )
                document.add_page(page)

            document.reconstructed_content = reconstructed_content
            document.metadata.update(document_metadata or {})
            return document

        except Exception as e:
            raise RendererError(f"PdfHtmlRenderer workflow failed: {str(e)}")
