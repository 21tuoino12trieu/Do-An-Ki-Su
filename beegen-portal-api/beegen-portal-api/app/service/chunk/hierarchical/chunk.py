import asyncio
import json
import re
import threading
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from app.model.chunk import Chunk
from app.service.chunk.base import BaseChunker
from app.service.chunk.hierarchical.utils.table import table_detector
from app.service.chunk.hierarchical.utils.table import table_processor
from app.service.utils.extract_keywords import KeywordExtractor
from beeflow.workflow import WorkflowEngine
from beedoc_v3.engine import BeedocEngine
from beeflow.nodes.base_node import START, END, INPUT, OUTPUT
from beeflow.nodes.flow.branch_node import BranchNode
from beeflow.nodes.flow.for_loop_node import ForLoopNode
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beeflow.nodes.templates.basic_chain_node import BasicChainNode
from langchain_text_splitters import MarkdownHeaderTextSplitter
from pathlib import Path

MAX_WORD_COUNT = 2048


def _metadata_to_path(metadata: Dict[str, str]) -> str:
    return " > ".join(
        metadata[key] for key in sorted(metadata) if key.startswith("H") and metadata[key]
    )


def _format_heading_chunks(docs: List[Any], max_word_count: int) -> List[str]:
    results: List[str] = []
    for doc in docs:
        path = _metadata_to_path(doc.metadata)
        content = doc.page_content.strip()
        if not content:
            continue
        chunk_text = path + "\n" + content if path else content
        # Use semantic split instead of hard word split
        if len(chunk_text.split()) > max_word_count:
            results.extend(_split_oversized_chunk(chunk_text, max_word_count))
        else:
            results.append(chunk_text)
    return results


def _split_markdown_by_headings(markdown_text: str, max_word_count: int) -> List[str]:
    splitter = MarkdownHeaderTextSplitter([
        ("#", "H1"), 
        ("##", "H2"),
        ("###", "H3"),
        ("####", "H4"),
        ("#####", "H5"),
        ("######", "H6")
    ])
    chunks = splitter.split_text(markdown_text)
    return _format_heading_chunks(chunks, max_word_count)


def _split_markdown_by_headings_final(markdown_text: str, max_word_count: int) -> List[str]:
    return _split_markdown_by_headings(markdown_text, max_word_count)


def _strip_heading_line(chunk: str) -> str:
    lines = chunk.splitlines()
    if not lines:
        return ""
    return "\n".join(lines[1:]).strip()


def _get_heading_line(chunk: str) -> str:
    lines = chunk.splitlines()
    return lines[0].strip() if lines else ""


# === Oversized Chunk Splitting ===

MAX_WORDS_OVERSIZE = 2048

BOUNDARY_SEPARATORS = [
    # P1: markdown heading (with optional whitespace)
    r"\n(?=\s*#{1,6}\s)",
    r"\n(?=\s*(?:PHẦN|CHƯƠNG|MỤC)\s)",         # P2: plain section heading
    # P3: numbered top-level "1. " (start or newline, with whitespace)
    r"(?:^|\n)(?=\s*\d+\.\s)",
    # P4: sub-numbered "1.1" or "1.1.1"
    r"(?:^|\n)(?=\s*\d+\.\d+(?:\.\d+)*\s)",
    # P5: table row (with whitespace)
    r"\n(?=\s*\|)",
    r"\n\s*\n",                                 # P6: paragraph break
    # P7: single newline (not followed by space - keeps indented lines)
    r"\n(?!\s)",
    r"(?<=[.;!?])\s+",                          # P8: sentence boundary
]


def _count_words(text: str) -> int:
    return len(text.split())


def _split_keep_sep(text: str, pattern: str) -> List[str]:
    parts = re.split(f"({pattern})", text)
    if len(parts) <= 1:
        return [text]

    segments = []
    current = parts[0] if parts[0] else ""
    i = 1
    while i < len(parts):
        sep = parts[i]
        content = parts[i + 1] if i + 1 < len(parts) else ""

        # Handle empty separator (e.g., when ^ matches at start of string)
        if not sep:
            current = current + content if current else content
        else:
            segments.append(current)
            current = sep + content
        i += 2
    if current:
        segments.append(current)

    return [s for s in segments if s.strip()]


def _recursive_split(text: str, max_words: int, priority: int = 0) -> List[str]:
    if _count_words(text) <= max_words:
        return [text.strip()]

    if priority >= len(BOUNDARY_SEPARATORS):
        words = text.split()
        return [" ".join(words[i: i + max_words]) for i in range(0, len(words), max_words)]

    segments = _split_keep_sep(text, BOUNDARY_SEPARATORS[priority])

    if len(segments) <= 1:
        return _recursive_split(text, max_words, priority + 1)

    result = []
    current_parts: List[str] = []
    current_wc = 0

    for seg in segments:
        seg_wc = _count_words(seg)

        if seg_wc > max_words:
            if current_parts:
                result.append("\n".join(current_parts))
                current_parts, current_wc = [], 0
            result.extend(_recursive_split(seg, max_words, priority + 1))
        elif current_wc + seg_wc <= max_words:
            current_parts.append(seg)
            current_wc += seg_wc
        else:
            result.append("\n".join(current_parts))
            current_parts, current_wc = [seg], seg_wc

    if current_parts:
        result.append("\n".join(current_parts))

    return [c.strip() for c in result if c.strip()]


def _parse_chunk(chunk: str) -> Tuple[str, str]:
    parts = chunk.strip().split("\n", 1)
    if len(parts) != 2:
        return "", chunk.strip()

    first_line = parts[0].strip()
    body = parts[1].strip()

    is_heading = (
        not first_line.startswith("#")
        and not first_line.startswith("|")
        and len(first_line) < 500
        and bool(
            re.search(
                r"[A-ZĐÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂẮẶẲẴỀẾỆỂỄỈỊỌỐỔỖỢỚỜỞỠỤỨỪỰỮ]",
                first_line,
            )
        )
    )

    if is_heading:
        return first_line, body
    return "", chunk.strip()


def _split_oversized_chunk(chunk: str, max_words: int = MAX_WORDS_OVERSIZE) -> List[str]:
    if _count_words(chunk) <= max_words:
        return [chunk.strip()]

    heading_line, body = _parse_chunk(chunk)
    body_chunks = _recursive_split(body, max_words)

    if heading_line:
        return [f"{heading_line}\n\n{c}" for c in body_chunks]
    return body_chunks


def _extract_table_name(table_summary: str) -> str:
    """Extract table name from the ---TABLE_NAME--- section of table_summary."""
    if not table_summary:
        return ""
    match = re.search(
        r"---TABLE_NAME---\s*\n(.+?)(?:\n---|\Z)", table_summary, re.DOTALL
    )
    if match:
        return match.group(1).strip()
    return ""


def _build_table_placeholder_text(table_summary: str) -> str:
    """Build a plain text description from table_summary to replace {TABLE_PIVOT}.

    Format:
        Bảng: <TABLE_NAME>
        Nội dung: <TABLE_ABOUT>
        Kiến trúc: <TABLE_COLUMNS>
    """
    if not table_summary:
        return ""

    def _extract_section(section_name: str) -> str:
        pattern = rf"---{section_name}---\s*\n(.+?)(?:\n---|\Z)"
        m = re.search(pattern, table_summary, re.DOTALL)
        return m.group(1).strip() if m else ""

    table_name = _extract_section("TABLE_NAME")
    table_about = _extract_section("TABLE_ABOUT")
    table_columns = _extract_section("TABLE_COLUMNS")

    parts: List[str] = []
    if table_name:
        parts.append(f"Bảng: {table_name}")
    if table_about:
        parts.append(f"Nội dung: {table_about}")
    if table_columns:
        parts.append(f"Kiến trúc: {table_columns}")

    return "\n".join(parts) if parts else ""


class HierarchicalChunker(BaseChunker):
    def __init__(self) -> None:
        self._workflow: Optional[WorkflowEngine] = None
        self._keyword_extractor: Optional[KeywordExtractor] = None
        self._table_processor: Optional[table_processor.TableProcessor] = None

    def _classify_reconstructed(self, reconstructed: str) -> Dict[str, Any]:
        return {"has_reconstructed": bool(reconstructed and reconstructed.strip())}

    def _chunk_reconstructed(self, reconstructed: str, file_name: str) -> Dict[str, Any]:
        chunks = _split_markdown_by_headings_final(
            reconstructed, MAX_WORD_COUNT)
        prefix = f"{file_name}" if file_name else ""
        if prefix:
            chunks = [f"{prefix}\n\n{c}" for c in chunks]
        return {"chunks": chunks}

    def _prepare_zone_batch(self, zones: List[Dict[str, Any]], file_name: str) -> Dict[str, Any]:
        batch_data = []
        if not zones:
            zones = []
        for z in zones:
            if z and isinstance(z, dict) and z.get("content", "").strip():
                batch_data.append({
                    "zone_text": z["content"],
                    "sheet_name": z.get("sheet_name", ""),
                    "file_name": file_name,
                })
        return {"batch_data": batch_data}

    def _detect_tables(self, zone_text: str) -> Dict[str, Any]:
        tables = table_detector.detect_tables(zone_text)
        return {"tables": tables, "has_tables": bool(tables)}

    def _prepare_table_batch(self, tables: List[str], zone_text: str) -> Dict[str, Any]:
        batch_data = []
        for t in tables:
            idx = zone_text.find(t)
            if idx != -1:
                before_text = zone_text[:idx]
                after_text = zone_text[idx + len(t):]
                before_lines = before_text.splitlines()[-15:] if before_text else []
                after_lines = after_text.splitlines()[:15] if after_text else []
                context_before = "\n".join(before_lines).strip()
                context_after = "\n".join(after_lines).strip()
            else:
                context_before = ""
                context_after = ""
            batch_data.append({
                "table_text": t,
                "context_before": context_before,
                "context_after": context_after,
            })
        return {"batch_data": batch_data}

    def _process_table_node(self, table_text: str, context_before: str = "", context_after: str = "") -> Dict[str, Any]:
        if self._table_processor is None:
            self._table_processor = table_processor.TableProcessor(
                max_word_count=MAX_WORD_COUNT)

        async def runner() -> tuple:
            return await self._table_processor.run_with_summary(
                table_text,
                parent_heading=[],
                context_before=context_before,
                context_after=context_after,
            )

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            chunks, summary = asyncio.run(runner())
            return {
                "table_chunks": chunks if isinstance(chunks, list) else [],
                "table_summary": summary if isinstance(summary, str) else "",
            }

        result_container: Dict[str, Any] = {}

        def thread_runner() -> None:
            chunks, summary = asyncio.run(runner())
            result_container["table_chunks"] = chunks
            result_container["table_summary"] = summary

        thread = threading.Thread(target=thread_runner)
        thread.start()
        thread.join()
        table_chunks = result_container.get("table_chunks", [])
        table_summary = result_container.get("table_summary", "")
        return {
            "table_chunks": table_chunks if isinstance(table_chunks, list) else [],
            "table_summary": table_summary if isinstance(table_summary, str) else "",
        }

    def _flatten_table_chunks(self, batches: List[Dict[str, Any]]) -> Dict[str, Any]:
        table_chunks_list: List[List[str]] = []
        table_summaries: List[str] = []
        for item in batches or []:
            if not isinstance(item, dict):
                continue
            chunks = item.get("table_chunks")
            if isinstance(chunks, list):
                table_chunks_list.append(chunks)
            summary = item.get("table_summary", "")
            table_summaries.append(summary if isinstance(summary, str) else "")
        return {"table_chunks_list": table_chunks_list, "table_summaries": table_summaries}

    def _build_pivot_text(self, zone_text: str, tables: List[str]) -> Dict[str, Any]:
        pivot_text = zone_text or ""
        for table in tables or []:
            replaced = False
            if table in pivot_text:
                pivot_text = pivot_text.replace(table, "{TABLE_PIVOT}", 1)
                replaced = True
            if not replaced:
                stripped = table.strip()
                if stripped and stripped in pivot_text:
                    pivot_text = pivot_text.replace(
                        stripped, "{TABLE_PIVOT}", 1)
                    replaced = True
            if not replaced:
                dedented = "\n".join(line.lstrip()
                                     for line in table.splitlines()).strip()
                if dedented and dedented in pivot_text:
                    pivot_text = pivot_text.replace(
                        dedented, "{TABLE_PIVOT}", 1)
        return {"pivot_text": pivot_text}

    def _split_pivot_text(self, pivot_text: str) -> Dict[str, Any]:
        if not pivot_text:
            return {"text_chunks": []}
        return {"text_chunks": _split_markdown_by_headings(pivot_text, MAX_WORD_COUNT)}

    def _merge_and_split_pivot(
        self,
        text_chunks: List[str],
        table_chunks_list: List[List[str]],
        table_summaries: List[str],
    ) -> Dict[str, Any]:
        """Merge text chunks with table summary + table chunks.

        Output: n text chunks (with table summary replacing {TABLE_PIVOT}) followed
        by m table chunks (each prefixed with '# BẢNG: <table_name>').
        """
        text_result: List[str] = []
        table_result: List[str] = []
        chunk_iter = iter(table_chunks_list or [])
        summary_iter = iter(table_summaries or [])

        for chunk in text_chunks or []:
            if "{TABLE_PIVOT}" in chunk:
                table_chunks = next(chunk_iter, [])
                table_summary = next(summary_iter, "")
                table_name = _extract_table_name(table_summary)
                placeholder_text = _build_table_placeholder_text(table_summary)

                # Replace {TABLE_PIVOT} with summary plain text
                text_with_summary = chunk.replace("{TABLE_PIVOT}", placeholder_text)

                # Split text if oversized
                if len(text_with_summary.split()) > MAX_WORD_COUNT:
                    text_result.extend(
                        _split_oversized_chunk(text_with_summary, MAX_WORD_COUNT))
                else:
                    text_result.append(text_with_summary)

                # Prefix each table chunk with table name header
                for tc in table_chunks:
                    if isinstance(tc, str) and tc.strip():
                        prefixed = f"# BẢNG: {table_name}\n{tc.strip()}" if table_name else tc.strip()
                        table_result.append(prefixed)
            else:
                # Non-pivot text chunk: split if oversized
                if len(chunk.split()) > MAX_WORD_COUNT:
                    text_result.extend(
                        _split_oversized_chunk(chunk, MAX_WORD_COUNT))
                else:
                    text_result.append(chunk)

        # Drain remaining table chunks/summaries not consumed by {TABLE_PIVOT}
        for remaining_chunks in chunk_iter:
            remaining_summary = next(summary_iter, "")
            table_name = _extract_table_name(remaining_summary)
            for tc in remaining_chunks:
                if isinstance(tc, str) and tc.strip():
                    prefixed = f"# BẢNG: {table_name}\n{tc.strip()}" if table_name else tc.strip()
                    table_result.append(prefixed)

        # Final output: n text chunks then m table chunks
        merged_chunks = [c for c in text_result if c.strip()] + [c for c in table_result if c.strip()]
        return {"merged_chunks": merged_chunks}

    def _split_zone_no_tables(self, zone_text: str) -> Dict[str, Any]:
        return {"no_table_chunks": _split_markdown_by_headings(zone_text, MAX_WORD_COUNT)}

    def _finalize_zone_output(self, chunks_in: List[str], file_name: str, sheet_name: str) -> Dict[str, Any]:
        prefix = f"{file_name}" if file_name else ""
        if sheet_name:
            prefix += f" > Sheet: {sheet_name}"
            
        out = []
        for c in chunks_in:
            if prefix:
                out.append(f"{prefix}\n\n{c}")
            else:
                out.append(c)
        return {"chunks": out}

    def _flatten_zone_chunks(self, batches: List[Dict[str, Any]]) -> Dict[str, Any]:
        all_chunks: List[str] = []
        for item in batches or []:
            if not isinstance(item, dict):
                continue
            chunks = item.get("chunks")
            if isinstance(chunks, list):
                all_chunks.extend(chunks)
        return {"chunks": all_chunks}

    def _finalize_chunks(self, chunks_in: List[str]) -> Dict[str, Any]:
        result_chunks = [Chunk(content=c, keywords=None).model_dump()
                         for c in chunks_in if c.strip()]
        return {"out_chunks": result_chunks}

    def _prepare_keyword_batches(self, chunks_in: List[Dict[str, Any]]) -> Dict[str, Any]:
        batch_data = []
        for chunk in chunks_in or []:
            if not isinstance(chunk, dict):
                continue
            content = chunk.get("content", "")
            if content:
                batch_data.append({"chunk": content})
        return {"batch_data": batch_data}

    def _extract_keywords_node(self, chunk: str) -> Dict[str, Any]:
        if self._keyword_extractor is None:
            self._keyword_extractor = KeywordExtractor()

        async def runner() -> Dict[str, Any]:
            return await self._keyword_extractor.extract(chunk)

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            result = asyncio.run(runner())
            return {
                "keywords": result.get("keywords") if isinstance(result, dict) else None,
                "keywords_text": result.get("keywords_text", "") if isinstance(result, dict) else ""
            }

        result_container: Dict[str, Any] = {}

        def thread_runner() -> None:
            result_container.update(asyncio.run(runner()))

        thread = threading.Thread(target=thread_runner)
        thread.start()
        thread.join()
        return {
            "keywords": result_container.get("keywords"),
            "keywords_text": result_container.get("keywords_text", "")
        }

    def _merge_keywords(self, chunks: List[Dict[str, Any]], batches: List[Dict[str, Any]]) -> Dict[str, Any]:
        merged = []
        keyword_results = list(batches or [])
        for idx, chunk in enumerate(chunks or []):
            if not isinstance(chunk, dict):
                continue
            keywords = None
            if idx < len(keyword_results):
                keywords = keyword_results[idx].get("keywords")
            if keywords:
                chunk = {**chunk, "keywords": keywords}
            merged.append(chunk)
        return {"out_chunks": merged}

    def _select_chunks(
        self,
        reconstructed_chunks: List[Dict[str, Any]],
        zones_chunks: List[Dict[str, Any]],
        has_reconstructed: bool,
    ) -> Dict[str, Any]:
        return {"chunks": reconstructed_chunks if has_reconstructed else zones_chunks}

    def _pass_chunks(self, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {"out_chunks": chunks}

    def _build_workflow(self) -> WorkflowEngine:
        with WorkflowEngine(
            name="hierarchical_chunk_workflow",
            description="Hierarchical chunking with table handling",
            langfuse="beegen-portal",
            inputs=INPUT,
        ) as workflow:
            classify = CodeNode(
                name="classify_reconstructed",
                code_fn=self._classify_reconstructed,
                inputs={"reconstructed": {INPUT: "reconstructed"}},
                return_keys=["has_reconstructed: bool"],
            )

            chunk_reconstructed = CodeNode(
                name="chunk_reconstructed",
                code_fn=self._chunk_reconstructed,
                inputs={
                    "reconstructed": {INPUT: "reconstructed"},
                    "file_name": {INPUT: "file_name"},
                },
                return_keys=["chunks: List[str]"],
            )

            prepare_zones = CodeNode(
                name="prepare_zones",
                code_fn=self._prepare_zone_batch,
                inputs={
                    "zones": {INPUT: "zones"},
                    "file_name": {INPUT: "file_name"},
                },
                return_keys=["batch_data: List[Any]"],
            )

            with ForLoopNode(
                name="zones_loop",
                description="Chunk each zone",
                inputs={"batch_data": {prepare_zones: "batch_data"}},
            ) as zones_loop:
                detect_tables = CodeNode(
                    name="detect_tables",
                    code_fn=self._detect_tables,
                    inputs={"zone_text": {INPUT: "zone_text"}},
                    return_keys=["tables: List[str]", "has_tables: bool"],
                )

                build_pivot_text = CodeNode(
                    name="build_pivot_text",
                    code_fn=self._build_pivot_text,
                    inputs={
                        "zone_text": {INPUT: "zone_text"},
                        "tables": {detect_tables: "tables"},
                    },
                    return_keys=["pivot_text: str"],
                )

                split_no_tables = CodeNode(
                    name="split_zone_no_tables",
                    code_fn=self._split_zone_no_tables,
                    inputs={"zone_text": {INPUT: "zone_text"}},
                    return_keys=["no_table_chunks: List[str]"],
                    outputs=OUTPUT,
                )

                prepare_table_batch = CodeNode(
                    name="prepare_table_batch",
                    code_fn=self._prepare_table_batch,
                    inputs={
                        "tables": {detect_tables: "tables"},
                        "zone_text": {INPUT: "zone_text"},
                    },
                    return_keys=["batch_data: List[Any]"],
                )

                with ForLoopNode(
                    name="table_process_loop",
                    description="Process each detected table",
                    inputs={"batch_data": {prepare_table_batch: "batch_data"}},
                ) as table_process_loop:
                    process_table = CodeNode(
                        name="process_table",
                        code_fn=self._process_table_node,
                        inputs={
                            "table_text": {INPUT: "table_text"},
                            "context_before": {INPUT: "context_before"},
                            "context_after": {INPUT: "context_after"},
                        },
                        return_keys=["table_chunks: List[str]", "table_summary: str"],
                        outputs=OUTPUT,
                    )

                    START >> process_table >> END

                flatten_table_chunks = CodeNode(
                    name="flatten_table_chunks",
                    code_fn=self._flatten_table_chunks,
                    inputs={"batches": {table_process_loop: "batch_result"}},
                    return_keys=["table_chunks_list: List[Any]", "table_summaries: List[str]"],
                )

                split_pivot_text = CodeNode(
                    name="split_pivot_text",
                    code_fn=self._split_pivot_text,
                    inputs={"pivot_text": {build_pivot_text: "pivot_text"}},
                    return_keys=["text_chunks: List[str]"],
                )

                merge_and_split = CodeNode(
                    name="merge_and_split_pivot",
                    code_fn=self._merge_and_split_pivot,
                    inputs={
                        "text_chunks": {split_pivot_text: "text_chunks"},
                        "table_chunks_list": {flatten_table_chunks: "table_chunks_list"},
                        "table_summaries": {flatten_table_chunks: "table_summaries"},
                    },
                    return_keys=["merged_chunks: List[str]"],
                )

                finalize_tables = CodeNode(
                    name="finalize_tables",
                    code_fn=self._finalize_zone_output,
                    inputs={
                        "chunks_in": {merge_and_split: "merged_chunks"},
                        "file_name": {INPUT: "file_name"},
                        "sheet_name": {INPUT: "sheet_name"},
                    },
                    return_keys=["chunks: List[str]"],
                    outputs=OUTPUT,
                )

                finalize_no_tables = CodeNode(
                    name="finalize_no_tables",
                    code_fn=self._finalize_zone_output,
                    inputs={
                        "chunks_in": {split_no_tables: "no_table_chunks"},
                        "file_name": {INPUT: "file_name"},
                        "sheet_name": {INPUT: "sheet_name"},
                    },
                    return_keys=["chunks: List[str]"],
                    outputs=OUTPUT,
                )

                branch_tables = BranchNode(
                    name="branch_tables",
                    cases={"has_tables == True": prepare_table_batch},
                    default=split_no_tables,
                    inputs={"has_tables": {detect_tables: "has_tables"}},
                )

                START >> detect_tables >> build_pivot_text >> branch_tables >> [
                    prepare_table_batch, split_no_tables]

                prepare_table_batch >> table_process_loop >> flatten_table_chunks >> split_pivot_text >> merge_and_split >> finalize_tables >> END
                split_no_tables >> finalize_no_tables >> END

            flatten_zones = CodeNode(
                name="flatten_zone_chunks",
                code_fn=self._flatten_zone_chunks,
                inputs={"batches": {zones_loop: "batch_result"}},
                return_keys=["chunks: List[str]"],
            )

            finalize_reconstructed = CodeNode(
                name="finalize_reconstructed",
                code_fn=self._finalize_chunks,
                inputs={"chunks_in": {chunk_reconstructed: "chunks"}},
                return_keys=["out_chunks: List[Dict[str, Any]]"],
            )

            finalize_zones = CodeNode(
                name="finalize_zones",
                code_fn=self._finalize_chunks,
                inputs={"chunks_in": {flatten_zones: "chunks"}},
                return_keys=["out_chunks: List[Dict[str, Any]]"],
            )

            select_chunks = CodeNode(
                name="select_chunks",
                code_fn=self._select_chunks,
                inputs={
                    "reconstructed_chunks": {finalize_reconstructed: "out_chunks"},
                    "zones_chunks": {finalize_zones: "out_chunks"},
                    "has_reconstructed": {classify: "has_reconstructed"},
                },
                return_keys=["chunks: List[Dict[str, Any]]"],
            )

            prepare_keyword_batches = CodeNode(
                name="prepare_keyword_batches",
                code_fn=self._prepare_keyword_batches,
                inputs={"chunks_in": {select_chunks: "chunks"}},
                return_keys=["batch_data: List[Any]"],
            )

            pass_chunks = CodeNode(
                name="pass_chunks",
                code_fn=self._pass_chunks,
                inputs={"chunks": {select_chunks: "chunks"}},
                return_keys=["out_chunks: List[Dict[str, Any]]"],
                outputs={"out_chunks": OUTPUT},
            )

            branch_keywords = BranchNode(
                name="branch_keywords",
                cases={"extract_keywords == True": prepare_keyword_batches},
                default=pass_chunks,
                inputs={"extract_keywords": {INPUT: "extract_keywords"}},
            )

            with ForLoopNode(
                name="extract_keywords_loop",
                description="Extract keywords for each chunk",
                inputs={"batch_data": {prepare_keyword_batches: "batch_data"}},
            ) as extract_keywords_loop:
                extract_keywords = CodeNode(
                    name="extract_keywords",
                    code_fn=self._extract_keywords_node,
                    inputs={"chunk": {INPUT: "chunk"}},
                    return_keys=[
                        "keywords: List[str]",
                        "keywords_text: str"
                    ],
                    outputs=OUTPUT,
                )

                START >> extract_keywords >> END

            merge_keywords = CodeNode(
                name="merge_keywords",
                code_fn=self._merge_keywords,
                inputs={
                    "chunks": {select_chunks: "chunks"},
                    "batches": {extract_keywords_loop: "batch_result"},
                },
                return_keys=["out_chunks: List[Dict[str, Any]]"],
                outputs={"out_chunks": OUTPUT},
            )

            START >> classify >> [chunk_reconstructed, prepare_zones]
            chunk_reconstructed >> finalize_reconstructed
            prepare_zones >> zones_loop >> flatten_zones >> finalize_zones

            [finalize_reconstructed, finalize_zones] >> select_chunks >> branch_keywords >> [prepare_keyword_batches, pass_chunks]
            prepare_keyword_batches >> extract_keywords_loop >> merge_keywords >> END
            pass_chunks >> END

        workflow.compile()
        return workflow

    async def chunk(
        self,
        reconstructed: str,
        zones: List[Dict[str, Any]],
        file_name: str,
        extract_keywords: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        if self._workflow is None:
            self._workflow = self._build_workflow()

        result = await self._workflow.run(
            inputs={
                "reconstructed": reconstructed,
                "zones": zones,
                "file_name": file_name,
                "extract_keywords": extract_keywords,
            }
        )
        return {"chunks": result.get("out_chunks", []) if isinstance(result, dict) else []}


async def main() -> None:
    file_path = "assets/BIM.PL 02. Giai thich tu ngu va cac tu viet tat - 9439.QC-HS HL 20.08.2025  Ver 6.0.pdf"
    beedoc = BeedocEngine()
    document = await beedoc.process(file_path)
    reconstructed = (document.reconstructed_content or "").strip() if document else ""
    zones = []
    if not reconstructed and document:
        for page in document.pages or []:
            sheet_name = page.metadata.get("sheet_name", "") if page.metadata else ""
            for zone in page.content or []:
                if zone and zone.content:
                    zones.append({"content": zone.content, "sheet_name": sheet_name})

    chunker = HierarchicalChunker()
    result = await chunker.chunk(
        reconstructed=reconstructed,
        zones=zones,
        file_name=Path(file_path).name,
        extract_keywords=False
    )
    chunks = result.get("chunks", []) if isinstance(result, dict) else []

    output_path = Path(file_path).with_suffix(Path(file_path).suffix + ".txt")
    with open(output_path, "w", encoding="utf-8") as f:
        for i, chunk in enumerate(chunks, start=1):
            content = chunk.get("content") if isinstance(chunk, dict) else str(chunk)
            f.write(f"==> Chunk {i}:\n{content}\n\n")

    print(f"Chunks: {len(chunks)}")
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
