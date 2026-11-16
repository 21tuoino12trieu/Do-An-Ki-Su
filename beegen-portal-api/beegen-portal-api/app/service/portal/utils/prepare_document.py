import datetime
import os
from typing import Any, Dict, List, Optional
import uuid

from app.service.tree.process_tree import TreeService


def get_extension(doc_name: Optional[str]) -> Optional[str]:
    if not doc_name:
        return None
    _, ext = os.path.splitext(doc_name)
    if ext:
        return ext.lstrip(".").lower()
    return None


async def process_tree_if_applicable(
    extension: str,
    source: Optional[str],
    reconstructed: str
) -> Dict[str, Any]:
    if (extension or "").lower() in ["pdf", "docx"] or source == "confluence":
        service = TreeService()
        result = await service.run(markdown_content=reconstructed, extract_keywords=True)
        return {"tree_structure": result.get("final_structure", [])}
    return {"tree_structure": []}

def format_keywords(keywords: Any) -> str:
    if isinstance(keywords, list):
        return ", ".join([str(k) for k in keywords])
    if isinstance(keywords, str):
        return keywords
    return ""

def prepare_mongo_document_data_only(
    doc_id: str,
    bot_id: str,
    chunks: List[Dict[str, Any]]
) -> Dict[str, Any]:

    chunk_ids = [str(uuid.uuid4()) for _ in range(len(chunks))]

    mongo_document_data = [
        {
            "_id": cid,
            "document_id": doc_id,
            "content": c.get("content", ""),
            "index": i,
            "created_at": datetime.datetime.now(datetime.UTC),
            "bot_id": bot_id
        } for i, (cid, c) in enumerate(zip(chunk_ids, chunks))
    ]

    return {
        "mongo_document_data": mongo_document_data
    }

import unicodedata
import re

def normalize_topic_name(name: str) -> str:
    if not name:
        return ""
    name = name.replace('đ', 'd').replace('Đ', 'D')
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('utf-8')
    name = name.lower()
    name = re.sub(r'[^a-z0-9]', '_', name)
    name = re.sub(r'_+', '_', name)
    return name.strip('_')

def build_topic_tree(topic_id: str, all_topics: List[Dict[str, Any]]) -> Dict[str, str]:
    if not all_topics or not topic_id:
        return {"topic_path": ""}
    topic_map = {str(t["_id"]): t for t in all_topics}
    path = []
    curr = str(topic_id)
    while curr in topic_map:
        t = topic_map[curr]
        raw_name = t.get("name", "")
        norm_name = normalize_topic_name(raw_name)
        if norm_name:
            path.append(norm_name)
        parent = t.get("parent_id")
        if not parent:
            break
        curr = str(parent)
    path.reverse()
    return {"topic_path": "/".join(path) if path else ""}

def prepare_milvus_train_payload(
    topic_path: str,
    chunks: Optional[List[Dict[str, Any]]] = None,
    chunk_embeddings: Optional[List[List[float]]] = None,
    nodes: Optional[List[Dict[str, Any]]] = None,
    node_embeddings: Optional[List[List[float]]] = None,
) -> Dict[str, Any]:
    chunks = chunks or []
    chunk_embeddings = chunk_embeddings or []
    nodes = nodes or []
    node_embeddings = node_embeddings or []
    
    milvus_chunks = []
    for chunk, emb in zip(chunks, chunk_embeddings):
        milvus_chunks.append({
            "chunk_id": chunk.get("chunk_id"),
            "content": chunk.get("keywords", ""),
            "vector": emb,
            "topic": topic_path,
            "type": "document"
        })
        
    milvus_nodes = []
    for node, emb in zip(nodes, node_embeddings):
        milvus_nodes.append({
            "node_id": node.get("node_id"),
            "content": node.get("keywords", ""),
            "vector": emb,
            "topic": topic_path,
            "type": "document"
        })
        
    return {
        "milvus_chunks": milvus_chunks,
        "milvus_nodes": milvus_nodes
    }


# ─────────────────────────────────────────────────────────────
#  Clean workflow helpers
# ─────────────────────────────────────────────────────────────

def prepare_deleted_documents_query(bot_id: str) -> Dict[str, Any]:
    """Query to fetch all documents marked deleted=True for a given bot."""
    return {
        "query_deleted_docs": {
            "bot_id": bot_id,
            "deleted": True
        }
    }


def extract_document_ids(deleted_docs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract _id list from deleted document records."""
    doc_ids = [d.get("_id") for d in deleted_docs if d.get("_id")]
    return {"doc_ids": doc_ids}


def prepare_chunk_query_by_doc_ids(doc_ids: List[str]) -> Dict[str, Any]:
    """Build Mongo query to fetch chunk_data records by doc_id."""
    return {"query": {"doc_id": {"$in": doc_ids}}}


def prepare_node_query_by_doc_ids(doc_ids: List[str]) -> Dict[str, Any]:
    """Build Mongo query to fetch nodes by document_id."""
    return {"query": {"document_id": {"$in": doc_ids}}}


def collect_chunk_ids_by_doc(chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Collect chunk_id values from chunk records for Milvus delete expr."""
    chunk_ids = [c.get("chunk_id") or str(c.get("_id")) for c in (chunks or []) if c.get("chunk_id") or c.get("_id")]
    ids_str = ", ".join(f'"{i}"' for i in chunk_ids)
    return {
        "chunk_ids": chunk_ids,
        "milvus_expr": f"chunk_id in [{ids_str}]" if chunk_ids else "chunk_id in [\"__none__\"]"
    }


def collect_node_ids_by_doc(nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Collect node_id values from node records for Milvus delete expr."""
    node_ids = [n.get("node_id") or str(n.get("_id")) for n in (nodes or []) if n.get("node_id") or n.get("_id")]
    ids_str = ", ".join(f'"{i}"' for i in node_ids)
    return {
        "node_ids": node_ids,
        "milvus_expr": f"node_id in [{ids_str}]" if node_ids else "node_id in [\"__none__\"]"
    }


def prepare_mongo_delete_by_doc_ids(doc_ids: List[str]) -> Dict[str, Any]:
    """Build Mongo delete filter matching document_id in the deleted list."""
    return {"mongo_filter": {"document_id": {"$in": doc_ids}}}


def prepare_mongo_delete_chunks_by_doc_ids(doc_ids: List[str]) -> Dict[str, Any]:
    """Build Mongo delete filter for chunk_data using the new doc_id field."""
    return {"mongo_filter": {"doc_id": {"$in": doc_ids}}}


def prepare_mongo_delete_documents(doc_ids: List[str]) -> Dict[str, Any]:
    """Delete parent documents only when they were marked as deleted."""
    return {
        "mongo_filter": {
            "_id": {"$in": doc_ids},
            "deleted": True,
        }
    }


def get_milvus_collection_names_for_delete(bot_id: str) -> Dict[str, Any]:
    """Derive chunk/node Milvus collection names from bot_id (matches upload/train job convention)."""
    if not bot_id.startswith("bot"):
        bot_id = f"bot_{bot_id}"
    base = bot_id.replace("-", "_")
    return {
        "chunk_collection_name": f"{base}_chunk",
        "node_collection_name": f"{base}_node",
    }


# ─────────────────────────────────────────────────────────────
#  Train workflow helpers — reconstruct from document_data
# ─────────────────────────────────────────────────────────────

def _is_heading_line(line: str) -> bool:
    """Heuristic: a line is a heading if it is non-empty, not a markdown table row,
    not a code fence, and short enough to plausibly be a section title."""
    if not line or not line.strip():
        return False
    stripped = line.strip()
    # Table row: starts with |
    if stripped.startswith("|"):
        return False
    # Markdown code fence
    if stripped.startswith("```") or stripped.startswith("~~~"):
        return False
    # Numbered / lettered list items that span many words are body, not headings
    # Allow up to ~200 chars for a heading (generous for Vietnamese multi-word headings)
    if len(stripped) > 200:
        return False
    return True


def reconstruct_markdown_from_document_data(
    document_data: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Reconstruct full markdown from document_data records (sorted by index).

    Each record's ``content`` format::

        <filename>\\n\\n<heading_path>\\n<body>

    - ``<heading_path>`` is a ' > '-joined hierarchy string, e.g.
      ``"PHẦN 1. QUY ĐỊNH CHUNG > Điều 1. Mục đích"``
      OR a plain single-level heading with no ``>``.
    - Records sharing the same heading_path are length-split continuations
      and should be merged (heading emitted only once).
    - Emit only new / changed heading levels (not the whole path each time).
    """
    records = sorted(document_data, key=lambda r: r.get("index", 0))
    lines: List[str] = []
    prev_heading_parts: Optional[List[str]] = None

    for record in records:
        content = record.get("content", "")

        # ── Step 1: strip filename (everything up to first "\n\n") ──
        double_nl = content.find("\n\n")
        rest = content[double_nl + 2:] if double_nl != -1 else content

        # ── Step 2: detect heading path (first line) ──
        nl = rest.find("\n")
        if nl == -1:
            first_line = rest.strip()
            body = ""
        else:
            first_line = rest[:nl].strip()
            body = rest[nl + 1:]

        if ">" in first_line:
            # Multi-level heading path: "A > B > C"
            heading_path = first_line
        elif _is_heading_line(first_line):
            # Single-level heading (no ">"), e.g. "5. Tài khoản VietQR"
            heading_path = first_line
        else:
            heading_path = None
            body = rest  # no heading → whole rest is body

        # ── Step 3: emit headings for new / changed levels ──
        if heading_path is not None:
            curr_parts = [p.strip() for p in heading_path.split(">")]

            if curr_parts != prev_heading_parts:
                if prev_heading_parts is None:
                    diverge_idx = 0
                else:
                    # find first position where curr differs from prev
                    diverge_idx = min(len(curr_parts), len(prev_heading_parts))
                    for i in range(min(len(curr_parts), len(prev_heading_parts))):
                        if curr_parts[i] != prev_heading_parts[i]:
                            diverge_idx = i
                            break

                for i in range(diverge_idx, len(curr_parts)):
                    lines.append(f"{'#' * (i + 1)} {curr_parts[i]}")

                prev_heading_parts = curr_parts

        # ── Step 4: append body ──
        if body.strip():
            lines.append(body.strip())
            lines.append("")

    return {"markdown": "\n".join(lines).strip()}


def prepare_chunk_data_from_document_data(
    document_data: List[Dict[str, Any]],
    doc_id: str,
) -> Dict[str, Any]:
    """
    Bê nguyên content từ document_data sang chunk_data records (không chunk lại).
    Schema chunk_data mới:
      {_id, chunk_id, doc_id, chunk_index, llm_text, keywords}
    """
    records = sorted(document_data, key=lambda r: r.get("index", 0))
    chunk_data = []
    for record in records:
        raw_id = record.get("_id") or str(uuid.uuid4())
        cid = str(raw_id)
        chunk_data.append({
            "_id": raw_id,
            "chunk_id": cid,
            "doc_id": doc_id,
            "chunk_index": record.get("index", 0),
            "llm_text": record.get("content", ""),
            "keywords": ""
        })
    return {"chunk_data": chunk_data}


def prepare_node_data_from_tree(
    doc_id: str,
    tree_structure: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Build node_data records from tree_structure (output of process_tree_if_applicable).
    Schema khớp với prepare_mongo_upload_data's node_data.
    Returns empty list when tree_structure is empty (e.g. non-docx/pdf).
    """
    node_data: List[Dict[str, Any]] = []

    if tree_structure:
        def traverse(nodes: List[Dict], parent_id: Optional[str] = None, level: int = 0):
            for n in nodes:
                nid = str(uuid.uuid4())
                node_data.append({
                    "_id": nid,
                    "node_id": nid,
                    "document_id": doc_id,
                    "parent_id": parent_id,
                    "title": n.get("title", ""),
                    "content": n.get("text", ""),
                    "summary": n.get("summary", ""),
                    "level": level,
                    "keywords": format_keywords(n.get("keywords", ""))
                })
                traverse(n.get("nodes", []), nid, level + 1)

        traverse(tree_structure)

    return {"node_data": node_data}


def prepare_milvus_chunk_retrain_payload(
    chunk_data: List[Dict[str, Any]],
    embeddings: List[List[float]],
    topic_path: str,
) -> Dict[str, Any]:
    """
    Build Milvus insert payload for _chunk collection from document_data-based chunks.
    Milvus vẫn dùng field content; chunk_data Mongo dùng llm_text.
    """
    milvus_chunks = []
    for chunk, emb in zip(chunk_data, embeddings):
        milvus_chunks.append({
            "chunk_id": chunk.get("chunk_id"),
            "content": chunk.get("keywords", ""),
            "vector": emb,
            "topic": topic_path,
            "type": "document"
        })
    return {"milvus_chunks": milvus_chunks}


def prepare_milvus_node_retrain_payload(
    nodes: List[Dict[str, Any]],
    embeddings: List[List[float]],
    topic_path: str,
) -> Dict[str, Any]:
    """Build Milvus insert payload for _node collection (embed summary, store keywords as content)."""
    milvus_nodes = []
    for node, emb in zip(nodes, embeddings):
        milvus_nodes.append({
            "node_id": node.get("node_id"),
            "content": node.get("keywords", ""),
            "vector": emb,
            "topic": topic_path,
            "type": "document"
        })
    return {"milvus_nodes": milvus_nodes}

