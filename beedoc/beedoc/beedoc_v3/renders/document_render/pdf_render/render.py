import uuid
import re
from typing import Any, Dict, List, TYPE_CHECKING
from beeflow.workflow import WorkflowEngine
from beeflow.nodes.base_node import START, END, INPUT, OUTPUT, CONTINUE
from beeflow.nodes.flow.while_loop_node import WhileLoopNode
from beeflow.nodes.flow.for_loop_node import ForLoopNode
from beeflow.nodes.primitives.ai.llm_node import LLMNode
from beeflow.nodes.templates.basic_chain_node import BasicChainNode
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beeflow.nodes.flow.branch_node import BranchNode

from beedoc_v3.renders.base import BaseRenderer
from beedoc_v3.core.exceptions import RendererError
from beedoc_v3.models.document import Page, Zone
from beedoc_v3.renders.document_render.pdf_render.utils.extractor import PDFExtractor
from beedoc_v3.renders.document_render.pdf_render.utils import logic
from beedoc_v3.renders.utils.vlm_image_gate import build_image_gate_messages, parse_image_gate_response

MERGE_VERIFY_THRESHOLD = 20000

if TYPE_CHECKING:
    from beedoc_v3.models.document import Document

class PdfRenderer(BaseRenderer):
    """
    Pdf Renderer that handles:
    1. Rendering PDF pages to Images (Base64)
    2. Reconstructing content using BasicChainNode in a Loop with context tracking.
    """

    def _build_workflow(self) -> WorkflowEngine:
        """Builds the Beeflow workflow for PDF rendering and reconstruction."""
        with WorkflowEngine(
            name="pdf_renderer_workflow",
            description="Workflow for rendering PDF to images and reconstructing using VLM with context",
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

            # Node 2: Initialize Context
            init_page_context = CodeNode(
                name="init_page_context",
                code_fn=self._init_context_logic,
                return_keys=["page_context: str", "heading_tree: str"]
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
                        "reasoning_effort":"none",
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

            # Main Loop
            with WhileLoopNode(
                name="page_loop",
                description="Iterate through PDF pages for VLM processing and merge verification",
                inputs={
                    "loop_pages": {render_node: "pages"},
                    "total_pages": {render_node: "total_pages"},
                    "page_context": {init_page_context: "page_context"},
                    "heading_tree": {init_page_context: "heading_tree"},
                    "image_references": {image_gate_finalize: "image_references"},
                    "current_page_idx": 0,
                    "loop_page_outputs": [],
                    "merge_flag": False,
                    "prev_page_content": "",
                    "prev_prev_page_content": "",
                    "merge_pair_index": 0,
                    "verify_results": []
                }
            ) as page_loop:
                check_ending = CodeNode(
                    name="check_ending",
                    code_fn=self._check_ending_logic,
                    inputs={
                        "current_page_idx": INPUT["current_page_idx"],
                        "total_pages": INPUT["total_pages"],
                        "merge_flag": INPUT["merge_flag"]
                    },
                    return_keys=["continue_loop: bool", "has_pages: bool"]
                )

                prep_output_node = CodeNode(
                    name="prep_output_node",
                    code_fn=self._prepare_loop_output,
                    inputs={
                        "in_page_outputs": INPUT["loop_page_outputs"],
                        "in_pages": INPUT["loop_pages"],
                        "verify_results": INPUT["verify_results"]
                    },
                    return_keys=["page_outputs: List[Dict[str, Any]]", "pages: List[Dict[str, Any]]", "out_verify_results: List[Dict[str, Any]]"],
                    outputs=OUTPUT
                )

                loop_dispatch = CodeNode(
                    name="loop_dispatch",
                    code_fn=lambda: {},
                    return_keys=[]
                )

                # ── VLM Extract Branch ──
                vlm_prep_node = CodeNode(
                    name="vlm_prep_node",
                    code_fn=self._prepare_vlm_input,
                    inputs={
                        "pages": INPUT["loop_pages"],
                        "current_page_idx": INPUT["current_page_idx"],
                        "page_context": INPUT["page_context"],
                        "heading_tree": INPUT["heading_tree"]
                    },
                    return_keys=["messages: List[Dict[str, Any]]"]
                )

                extract_node = LLMNode(
                    name="vlm_extract_node",
                    resource_key="gemini-3.1-flash-lite-chat",
                    inputs={
                        "messages": {vlm_prep_node: "messages"},
                        "reasoning_effort":"none",
                        "max_tokens": 65535
                    }
                )

                page_num_node = CodeNode(
                    name="calc_page_num",
                    code_fn=self._calc_page_num,
                    inputs={"it": INPUT["current_page_idx"]},
                    return_keys=["page_num: int"]
                )

                insert_image_node = CodeNode(
                    name="insert_image_node",
                    code_fn=logic.insert_images_into_text,
                    inputs={
                        "page_content": {extract_node: "content"},
                        "page_num": {page_num_node: "page_num"},
                        "image_references": INPUT["image_references"]
                    },
                    return_keys=["final_content: str"]
                )

                summary_prompt_node = CodeNode(
                    name="prepare_summary_prompt",
                    code_fn=self._prepare_summary_prompt,
                    inputs={
                        "summary": INPUT["page_context"],
                        "heading_tree": INPUT["heading_tree"],
                        "content": {extract_node: "content"}
                    },
                    return_keys=["summary_prompt: str"]
                )

                summary_node = BasicChainNode(
                    name="summary_context_node",
                    resource_key="gemini-3.1-flash-lite-chat",
                    system_prompt=logic.get_summary_system_prompt(),
                    user_prompt="{prompt}",
                    inputs={"prompt": {summary_prompt_node: "summary_prompt"}},
                    llm_configs= {
                        "reasoning_effort": "none",
                        "max_tokens": 65535
                    }
                )

                # Capture at end of VLM extract path → unique output keys
                vlm_extract_capture = CodeNode(
                    name="vlm_extract_capture",
                    code_fn=self._capture_vlm_extract,
                    inputs={
                        "final_content": {insert_image_node: "final_content"},
                        "new_context": {summary_node: "content"}
                    },
                    return_keys=["vlm_content: str", "vlm_context: str"]
                )

                # Capture for VLM skip path → same output keys, None values
                vlm_skip_capture = CodeNode(
                    name="vlm_skip_capture",
                    code_fn=lambda: {"vlm_content": None, "vlm_context": None},
                    return_keys=["vlm_content: str", "vlm_context: str"]
                )

                vlm_prep_branch = BranchNode(
                    name="vlm_prep_branch",
                    cases={"has_pages == True": vlm_prep_node},
                    default=vlm_skip_capture,
                    inputs={"has_pages": {check_ending: "has_pages"}}
                )

                # ── Merge Verify Branch ──
                merge_verify_prompt = CodeNode(
                    name="merge_verify_prompt",
                    code_fn=self._prepare_merge_verify_prompt,
                    inputs={
                        "prev_block": INPUT["prev_prev_page_content"],
                        "current_block": INPUT["prev_page_content"],
                        "pair_index": INPUT["merge_pair_index"]
                    },
                    return_keys=["merge_messages: List[Dict[str, Any]]", "merge_payload: Dict[str, Any]"]
                )

                merge_verify_llm = LLMNode(
                    name="merge_verify_llm",
                    resource_key="gemini-3.1-flash-lite-chat",
                    inputs={
                        "messages": {merge_verify_prompt: "merge_messages"},
                        "reasoning_effort": "none",
                        "max_tokens": 65535
                    }
                )

                # Capture at end of merge verify path → unique output key
                merge_verify_capture = CodeNode(
                    name="merge_verify_capture",
                    code_fn=self._collect_merge_verify_result,
                    inputs={
                        "content": {merge_verify_llm: "content"},
                        "payload": {merge_verify_prompt: "merge_payload"}
                    },
                    return_keys=["merge_result: Dict[str, Any]"]
                )

                # Capture for merge skip path → same output key, None value
                merge_skip_capture = CodeNode(
                    name="merge_skip_capture",
                    code_fn=lambda: {"merge_result": None},
                    return_keys=["merge_result: Dict[str, Any]"]
                )

                merge_branch = BranchNode(
                    name="merge_branch",
                    cases={"merge_flag == True": merge_verify_prompt},
                    default=merge_skip_capture,
                    inputs={"merge_flag": INPUT["merge_flag"]}
                )

                # ── Join Nodes (resolve each 2-path diamond join) ──
                vlm_join = CodeNode(
                    name="vlm_join",
                    code_fn=self._join_vlm_result,
                    inputs={
                        "vlm_content": {vlm_extract_capture: "vlm_content"},
                        "vlm_skip_content": {vlm_skip_capture: "vlm_content"},
                        "vlm_context": {vlm_extract_capture: "vlm_context"},
                        "vlm_skip_context": {vlm_skip_capture: "vlm_context"},
                        "has_pages": {check_ending: "has_pages"}
                    },
                    return_keys=["resolved_vlm_content: str", "resolved_vlm_context: str"]
                )

                merge_join = CodeNode(
                    name="merge_join",
                    code_fn=self._join_merge_result,
                    inputs={
                        "merge_result": {merge_verify_capture: "merge_result"},
                        "merge_skip_result": {merge_skip_capture: "merge_result"}
                    },
                    return_keys=["resolved_merge_result: Dict[str, Any]"]
                )

                # ── Update Loop State (no diamond join — only 2 guaranteed inputs) ──
                update_while = CodeNode(
                    name="update_context",
                    code_fn=self._update_loop_state,
                    inputs={
                        "in_current_page_idx": INPUT["current_page_idx"],
                        "in_image_references": INPUT["image_references"],
                        "in_page_outputs": INPUT["loop_page_outputs"],
                        "in_heading_tree": INPUT["heading_tree"],
                        "in_page_context": INPUT["page_context"],
                        "in_total_pages": INPUT["total_pages"],
                        "in_pages": INPUT["loop_pages"],
                        "in_verify_results": INPUT["verify_results"],
                        "in_merge_pair_index": INPUT["merge_pair_index"],
                        "in_prev_page_content": INPUT["prev_page_content"],
                        "has_pages": {check_ending: "has_pages"},
                        "vlm_content": {vlm_join: "resolved_vlm_content"},
                        "vlm_context": {vlm_join: "resolved_vlm_context"},
                        "merge_result": {merge_join: "resolved_merge_result"}
                    },
                    return_keys=[
                        "current_page_idx: int",
                        "loop_page_outputs: List[Dict[str, Any]]",
                        "page_context: str",
                        "heading_tree: str",
                        "total_pages: int",
                        "loop_pages: List[Dict[str, Any]]",
                        "merge_flag: bool",
                        "prev_page_content: str",
                        "prev_prev_page_content: str",
                        "merge_pair_index: int",
                        "verify_results: List[Dict[str, Any]]",
                        "image_references: Dict[int, Any]"
                    ],
                    outputs={
                        "current_page_idx": INPUT,
                        "loop_page_outputs": INPUT,
                        "page_context": INPUT,
                        "heading_tree": INPUT,
                        "total_pages": INPUT,
                        "loop_pages": INPUT,
                        "merge_flag": INPUT,
                        "prev_page_content": INPUT,
                        "prev_prev_page_content": INPUT,
                        "merge_pair_index": INPUT,
                        "verify_results": INPUT,
                        "image_references": INPUT
                    }
                )

                verify_loop = BranchNode(
                    name="verify_loop_branch",
                    cases={"continue_loop == True": loop_dispatch},
                    default=prep_output_node,
                    inputs={
                        "continue_loop": {check_ending: "continue_loop"}
                    }
                )

                # ── Flow Connections ──
                START >> check_ending >> verify_loop >> [loop_dispatch, prep_output_node]
                
                # Parallel fork: VLM extract ‖ Merge verify
                loop_dispatch >> [vlm_prep_branch, merge_branch]
                
                # VLM branch → vlm_join (2-path diamond, KI §21 confirmed)
                vlm_prep_branch >> [vlm_prep_node, vlm_skip_capture]
                vlm_prep_node >> extract_node >> page_num_node >> insert_image_node >> summary_prompt_node >> summary_node >> vlm_extract_capture
                vlm_extract_capture >> vlm_join
                vlm_skip_capture >> vlm_join
                
                # Merge branch → merge_join (2-path diamond, KI §21 confirmed)
                merge_branch >> [merge_verify_prompt, merge_skip_capture]
                merge_verify_prompt >> merge_verify_llm >> merge_verify_capture
                merge_verify_capture >> merge_join
                merge_skip_capture >> merge_join
                
                # Final join: 2 guaranteed-to-run nodes → no diamond
                [vlm_join, merge_join] >> update_while >> CONTINUE
                prep_output_node >> END

            finalize_pdf_node = CodeNode(
                name="finalize_pdf_node",
                code_fn=self._finalize_pdf_logic,
                inputs={
                    "page_outputs": page_loop,
                    "pages": page_loop,
                    "verify_results": page_loop,
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

            START >> [strip_images_node, image_references, init_page_context]
            strip_images_node >> render_node
            render_node >> doc_metadata_prompt >> doc_metadata_llm >> doc_metadata_collect
            image_references >> image_gate_batch >> image_gate_loop >> image_gate_finalize
            [render_node, init_page_context, image_gate_finalize] >> page_loop
            [page_loop, doc_metadata_collect] >> finalize_pdf_node >> END

        workflow.compile()
        return workflow

    def _prepare_loop_output(self, in_page_outputs: List[Dict[str, Any]], in_pages: List[Dict[str, Any]], verify_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Prepares the final output of the while loop."""
        return {
            "page_outputs": in_page_outputs,
            "pages": in_pages,
            "out_verify_results": verify_results
        }

    def _finalize_pdf_logic(
        self,
        page_outputs: List[Dict[str, Any]],
        pages: List[Dict[str, Any]],
        verify_results: List[Dict[str, Any]],
        in_document_metadata: Dict[str, Any],
        image_references: Dict[int, Any] = None
    ) -> Dict[str, Any]:
        """Finalizes the document data with the results from the page loop."""
        processed_pages = []
        for p in pages:
            page_data = {
                "page_number": p["page_number"],
                "image_data": p["image_data"],
                "metadata": {"width": p.get("width"), "height": p.get("height")},
                "content": [],
                "image_list": None
            }

            # Check if we have extracted text for this page
            extracted = next((item for item in page_outputs if item["page_number"] == p["page_number"]), None)
            if extracted:
                text = extracted.get("text") or ""
                page_data["content"] = [{"content": text, "metadata": {}}] if text else []
                page_data["image_list"] = extracted.get("image_list")

            processed_pages.append(page_data)

        verified_list = []
        for item in (verify_results or []):
            if not isinstance(item, dict):
                continue
            result = item.get("verify_result") or {}
            verified_list.append({
                "pair_index": result.get("pair_index"),
                "content": (result.get("content") or "").strip(),
            })
        verified_list.sort(key=lambda x: x.get("pair_index") if x.get("pair_index") is not None else -1)

        # Reconstruct combined text
        pages_sorted = [r for r in sorted(page_outputs, key=lambda x: x["page_number"]) if r.get("text")]
        combined_text = "\n\n".join([r["text"] for r in pages_sorted])

        pair_counter = [0]
        def verify_fn(prev_block: str, current_block: str):
            idx = pair_counter[0]
            pair_counter[0] += 1
            candidate = verified_list[idx]["content"] if idx < len(verified_list) else None
            if candidate and len(candidate) < MERGE_VERIFY_THRESHOLD:
                return candidate
            return "\n".join([b for b in [prev_block, current_block] if b])

        reconstructed_content = logic.merge_continues_blocks(combined_text, verify_fn=verify_fn)

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

        return {
            "final_pages": processed_pages,
            "reconstructed_content": reconstructed_content,
            "document_metadata": in_document_metadata or {}
        }

    def _render_pdf_with_total_pages(self, file_path: str) -> Dict[str, Any]:
        result = logic.render_pdf_to_images(file_path)
        pages = result.get("pages", [])
        return {"pages": pages, "total_pages": len(pages)}

    def _check_ending_logic(self, current_page_idx: int, total_pages: int, merge_flag: bool) -> Dict[str, Any]:
        has_pages = current_page_idx < total_pages
        return {
            "continue_loop": has_pages or merge_flag,
            "has_pages": has_pages
        }

    def _init_context_logic(self) -> Dict[str, Any]:
        return {"page_context": "Bắt đầu tài liệu", "heading_tree": ""}

    def _prepare_vlm_input(self, pages: List, current_page_idx: int, page_context: str, heading_tree: str) -> Dict[str, Any]:
        image_data = pages[current_page_idx]["image_data"]
        system_prompt = logic.get_pdf_system_prompt()
        user_prompt = logic.get_pdf_user_prompt(page_context, heading_tree)
        return {
            "messages": [
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
                        },
                    ],
                },
            ]
        }

    def _calc_page_num(self, it: int) -> Dict[str, Any]:
        return {"page_num": it + 1}

    def _prepare_summary_prompt(self, summary: str, heading_tree: str, content: str) -> Dict[str, Any]:
        return {"summary_prompt": logic.get_summary_user_prompt(summary, heading_tree, content)}

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

    def _capture_vlm_extract(self, final_content: str, new_context: str) -> Dict[str, Any]:
        return {"vlm_content": final_content, "vlm_context": new_context}

    def _prepare_merge_verify_prompt(self, prev_block: str, current_block: str, pair_index: int) -> Dict[str, Any]:
        system_prompt = logic.get_merge_verify_system_prompt()
        user_prompt = logic.get_merge_verify_user_prompt(prev_block, current_block)
        return {
            "merge_messages": [
                {"role": "system", "content": [{"type": "text", "text": system_prompt}]},
                {"role": "user", "content": [{"type": "text", "text": user_prompt}]},
            ],
            "merge_payload": {"pair_index": pair_index}
        }

    def _collect_merge_verify_result(self, content: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "merge_result": {
                "pair_index": payload.get("pair_index"),
                "content": (content or "").strip()
            }
        }

    def _join_vlm_result(self, vlm_content=None, vlm_skip_content=None,
                         vlm_context=None, vlm_skip_context=None,
                         has_pages: bool = False) -> Dict[str, Any]:
        return {
            "resolved_vlm_content": vlm_content if has_pages else vlm_skip_content,
            "resolved_vlm_context": vlm_context if has_pages else vlm_skip_context
        }

    def _join_merge_result(self, merge_result=None, merge_skip_result=None) -> Dict[str, Any]:
        return {
            "resolved_merge_result": merge_result if merge_result else merge_skip_result
        }

    def _update_loop_state(
        self,
        in_current_page_idx: int,
        in_image_references: Dict,
        in_page_outputs: List,
        in_heading_tree: str,
        in_page_context: str,
        in_total_pages: int,
        in_pages: List,
        in_verify_results: List,
        in_merge_pair_index: int,
        in_prev_page_content: str,
        has_pages: bool,
        vlm_content: str = None,
        vlm_context: str = None,
        merge_result: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        
        results = list(in_verify_results or [])
        next_merge_pair_index = in_merge_pair_index
        if merge_result:
            results.append({"verify_result": merge_result})
            next_merge_pair_index += 1

        current_extracted = vlm_content
        current_context = vlm_context

        next_current_page_idx = in_current_page_idx
        next_heading_tree = in_heading_tree
        next_page_context = in_page_context
        page_outputs = list(in_page_outputs or [])

        if has_pages:
            page_num = in_current_page_idx + 1
            page_refs = (in_image_references or {}).get(page_num, [])
            page_outputs.append({
                'page_number': page_num,
                'image_list': [img["image"]["path"] for img, text in page_refs],
                "text": current_extracted,
                "metadata": None,
            })

            parsed = logic.parse_summary_sections(current_context)
            next_page_context = parsed.get("page_context") or (current_context or "")
            next_heading_tree = parsed.get("heading_tree") or in_heading_tree
            next_current_page_idx += 1

        next_merge_flag = False
        if has_pages:
            match = re.match(
                r"^\[CONTINUES\](True|False)\[/CONTINUES\]",
                (current_extracted or "").strip(),
                flags=re.IGNORECASE,
            )
            next_merge_flag = match.group(1).lower() == "true" if match else False

        return {
            "current_page_idx": next_current_page_idx,
            "loop_page_outputs": page_outputs,
            "page_context": next_page_context,
            "heading_tree": next_heading_tree,
            "total_pages": in_total_pages,
            "loop_pages": in_pages,
            "merge_flag": next_merge_flag,
            "prev_page_content": current_extracted if has_pages else "",
            "prev_prev_page_content": in_prev_page_content,
            "merge_pair_index": next_merge_pair_index,
            "verify_results": results,
            "image_references": in_image_references or {}
        }

    def _prepare_image_gate_batch(self, image_references: Dict[int, Any]) -> Dict[str, Any]:
        batch = []
        for page_num, refs in (image_references or {}).items():
            for image_item, ref_text in refs:
                if logic.should_skip_image(image_item):
                    continue
                img = (image_item or {}).get("image", {})
                path = img.get("path")
                if not path:
                    continue
                try:
                    with open(path, "rb") as f:
                        data = f.read()
                except Exception:
                    data = None
                if not data:
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

            # # Apply to document object
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
            raise RendererError(f"PdfRenderer workflow failed: {str(e)}")
