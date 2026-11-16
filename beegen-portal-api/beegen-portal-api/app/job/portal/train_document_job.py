import asyncio
import datetime
import json
import os
import threading
from typing import Any, Dict

from beeflow.workflow import WorkflowEngine

from beeflow.nodes.primitives.data.mongo_node import MongoNode
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beeflow.nodes.flow.branch_node import BranchNode
from beeflow.nodes import EmbeddingNode
from beeflow.nodes.flow.for_loop_node import ForLoopNode
from beeflow.nodes.primitives.data.milvus_node import MilvusNode
from beeflow.nodes.base_node import END, INPUT, OUTPUT, START
from beegen.configs import MilvusOperation, MongoOperation

from app.model.document import TrainJobRequest
from app.service.utils.extract_keywords import KeywordExtractor
from app.utils.db_validation import get_mongo_db
from app.service.portal.utils.prepare_document import (
    build_topic_tree,
    collect_chunk_ids_by_doc,
    collect_node_ids_by_doc,
    get_extension,
    prepare_chunk_data_from_document_data,
    prepare_milvus_chunk_retrain_payload,
    prepare_milvus_node_retrain_payload,
    prepare_node_data_from_tree,
    process_tree_if_applicable,
    reconstruct_markdown_from_document_data,
)


# ─────────────────────────────────────────────────────────────
#  Pure helper functions (must be named — no lambdas)
# ─────────────────────────────────────────────────────────────

def _pass_through(**kwargs):
    return kwargs


def _get_list_length(items: list):
    return {"count": len(items or [])}


def _empty_embeddings():
    return {"embeddings": []}


def _select_embeddings(model_embeddings: list | None, empty_embeddings: list | None):
    embeddings = (
        model_embeddings
        if isinstance(model_embeddings, list)
        else empty_embeddings
    )
    return {"embeddings": embeddings}


def _get_milvus_collection_names(bot_id: str):
    if not bot_id.startswith("bot"):
        bot_id = f"bot_{bot_id}"
    base = bot_id.replace('-', '_')
    return {
        "chunk_collection_name": f"{base}_chunk",
        "node_collection_name": f"{base}_node"
    }


def _build_doc_query(item: str):
    return {"query": {"_id": item, "deleted": {"$ne": True}}}


def _build_doc_id_query(item: str):
    return {"query": {"document_id": item, "deleted": {"$ne": True}}}


def _build_chunk_doc_id_query(item: str):
    return {"query": {"doc_id": item, "deleted": {"$ne": True}}}


def _build_doc_id_filter(item: str):
    """Build Mongo DELETE_MANY filter by document_id."""
    return {"filter": {"document_id": item}}


def _build_chunk_doc_id_filter(item: str):
    """Build Mongo DELETE_MANY filter for chunk_data by doc_id."""
    return {"filter": {"doc_id": item}}


def _build_topic_query(bot_id: str):
    return {"query": {"bot_id": bot_id}}


def _capture_all_topics(topics: list):
    return {"all_topics": topics}


def _prepare_document_items(document_ids: list[str], bot_id: str):
    # Khi pod retry sẽ không chạy lại các tài liệu xử lí thành công
    completed_ids = {
        document["_id"]
        for document in get_mongo_db()["documents"].find(
            {
                "_id": {"$in": document_ids},
                "bot_id": bot_id,
                "is_trained": True,
                "training_status": "DONE",
            },
            {"_id": 1},
        )
    }
    return {
        "batch_data": [
            {"document_id": document_id, "bot_id": bot_id} for document_id in document_ids if document_id not in completed_ids
        ]
    }


def _build_training_status_update(document_id: str, is_trained: bool, training_status: str):
    update_fields = {
        "is_trained": is_trained,
        "training_status": training_status,
    }
    if is_trained and training_status == "DONE":
        update_fields["trained_at"] = datetime.datetime.now(datetime.UTC)
    return {
        "filter": {"_id": document_id},
        "update": {"$set": update_fields},
    }


def _mark_training_error(document_id: str) -> None:
    get_mongo_db()["documents"].update_one(
        {"_id": document_id},
        {"$set": {"is_trained": False, "training_status": "ERROR"}},
    )


def _get_training_status(document_id: str) -> tuple[bool, str | None]:
    document = get_mongo_db()["documents"].find_one(
        {"_id": document_id},
        {"is_trained": 1, "training_status": 1},
    )
    if not document:
        return False, None
    return document.get("is_trained") is True, document.get("training_status")


def _check_embedding_outputs(
    chunks: list,
    chunk_embeddings: list,
    nodes: list,
    node_embeddings: list,
):
    chunks = chunks or []
    nodes = nodes or []
    chunk_success = (isinstance(chunk_embeddings, list) and len(chunk_embeddings) == len(chunks))
    node_success = (
        not nodes
        or (isinstance(node_embeddings, list) and len(node_embeddings) == len(nodes))
    )
    return {"embed_success": chunk_success and node_success}


def _check_milvus_insert_outputs(
    embed_success: bool,
    chunk_count: int,
    node_count: int,
    milvus_insert_chunk_status: str | None,
    milvus_insert_node_status: str | None,
):
    # Check trạng thái insert vào Milvus thành công hay không 
    statuses = {}
    if chunk_count > 0:
        statuses["milvus_insert_chunks"] = milvus_insert_chunk_status
    if node_count > 0:
        statuses["milvus_insert_nodes"] = milvus_insert_node_status
    failed_operations = [
        name for name, status in statuses.items() if status != "success"
    ]
    return {
        "training_success": bool(embed_success) and not failed_operations,
        "failed_operations": failed_operations,
    }


def _extract_doc_info(data: dict):
    """Unwrap MongoNode find_one result → doc fields."""
    doc = data or {}
    doc_name = doc.get("doc_name")
    return {
        "doc_id": doc.get("_id"),
        "extension": get_extension(doc_name),
        "file_name": doc_name,
        "topic": doc.get("category_id"),
        "source": doc.get("source")
    }


def _extract_chunk_texts(chunk_data: list):
    """Extract llm_text strings for embedding from chunk_data records."""
    return {"chunk_texts": [c.get("llm_text", "") for c in chunk_data]}


def _extract_node_texts(nodes: list):
    """Extract summary strings for embedding from node_data records."""
    return {"node_texts": [n.get("summary", "") for n in (nodes or [])]}


def _prepare_keyword_batches(chunk_data: list):
    batch_data = []
    for chunk in chunk_data or []:
        content = chunk.get("llm_text", "")
        batch_data.append({"chunk": content})
    return {"batch_data": batch_data}


def _extract_keywords_node(chunk: str) -> Dict[str, Any]:
    if not chunk or not str(chunk).strip():
        return {"keywords": None}

    extractor = KeywordExtractor()

    async def runner() -> Dict[str, Any]:
        return await extractor.extract(chunk)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        result = asyncio.run(runner())
        return {
            "keywords": result.get("keywords") if isinstance(result, dict) else None,
        }

    result_container: Dict[str, Any] = {}

    def thread_runner() -> None:
        result_container.update(asyncio.run(runner()))

    thread = threading.Thread(target=thread_runner)
    thread.start()
    thread.join()
    return {
        "keywords": result_container.get("keywords"),
    }


def _merge_keywords_to_chunk_data(chunk_data: list, batches: list):
    merged = []
    keyword_results = list(batches or [])
    for idx, chunk in enumerate(chunk_data or []):
        keywords = None
        if idx < len(keyword_results):
            keywords_list = keyword_results[idx].get("keywords")
            if isinstance(keywords_list, list):
                keywords = ", ".join([str(k) for k in keywords_list])
            elif isinstance(keywords_list, str):
                keywords = keywords_list
        
        chunk["keywords"] = keywords or ""
        merged.append(chunk)
    return {"merged_chunk_data": merged}

# ─────────────────────────────────────────────────────────────
#  TrainDocumentJob
# ─────────────────────────────────────────────────────────────

class TrainDocumentJob:
    """
    Retrain workflow:

    1. Fetch topics, document info, document_data, old chunk_data, old node records (parallel).
    2. Reconstruct full markdown from document_data; build node tree (docx/pdf only).
    3. Prepare new chunk_data (bê nguyên content) + new node_data (from tree).
    4. Embed new chunks (content) and new nodes (summary).
    5. Delete old Milvus _chunk / _node (using collected IDs) and old Mongo chunk_data / node.
    6. Insert new data into Mongo and Milvus (chained after respective deletes).
    7. Update documents.training_status = DONE | ERROR.
    """

    def __init__(self):
        with WorkflowEngine(
            name="wf_train_document_job",
            description="train document in airflow",
            langfuse="beegen-portal"
        ) as wf_train_document_job:

            # ── 1a. Build query / filter helpers ──────────────────────────
            code_build_topic_query = CodeNode(
                name="code_build_topic_query",
                code_fn=_build_topic_query,
                inputs={"bot_id": {INPUT: "bot_id"}},
                return_keys=["query: dict"]
            )

            code_get_collection_names = CodeNode(
                name="code_get_collection_names",
                code_fn=_get_milvus_collection_names,
                inputs={"bot_id": {INPUT: "bot_id"}},
                return_keys=["chunk_collection_name: str", "node_collection_name: str"]
            )

            code_build_doc_query = CodeNode(
                name="code_build_doc_query",
                code_fn=_build_doc_query,
                inputs={"item": {INPUT: "document_id"}},
                return_keys=["query: dict"]
            )

            code_build_doc_id_query = CodeNode(
                name="code_build_doc_id_query",
                code_fn=_build_doc_id_query,
                inputs={"item": {INPUT: "document_id"}},
                return_keys=["query: dict"]
            )

            code_build_chunk_doc_id_query = CodeNode(
                name="code_build_chunk_doc_id_query",
                code_fn=_build_chunk_doc_id_query,
                inputs={"item": {INPUT: "document_id"}},
                return_keys=["query: dict"]
            )

            code_build_doc_id_filter = CodeNode(
                name="code_build_doc_id_filter",
                code_fn=_build_doc_id_filter,
                inputs={"item": {INPUT: "document_id"}},
                return_keys=["filter: dict"]
            )

            code_build_chunk_doc_id_filter = CodeNode(
                name="code_build_chunk_doc_id_filter",
                code_fn=_build_chunk_doc_id_filter,
                inputs={"item": {INPUT: "document_id"}},
                return_keys=["filter: dict"]
            )

            # ── 1b. Fetch ──────────────────────────────────────────────────
            get_all_topics = MongoNode(
                name="get_all_topics",
                resource_key="aicenter-chatbot",
                operation="find",
                inputs={
                    "collection_name": "category",
                    "query": {code_build_topic_query: "query"}
                }
            )

            get_document_info = MongoNode(
                name="get_document_info",
                resource_key="aicenter-chatbot",
                operation="find_one",
                inputs={
                    "collection_name": "documents",
                    "query": {code_build_doc_query: "query"},
                    "limit": 10000
                }
            )

            get_document_data = MongoNode(
                name="get_document_data",
                resource_key="aicenter-chatbot",
                operation="find",
                inputs={
                    "collection_name": "document_data",
                    "query": {code_build_doc_id_query: "query"},
                    "limit": 100000
                }
            )

            get_old_chunks = MongoNode(
                name="get_old_chunks",
                resource_key="aicenter-chatbot",
                operation="find",
                inputs={
                    "collection_name": "chunk_data",
                    "query": {code_build_chunk_doc_id_query: "query"},
                    "limit": 100000
                }
            )

            get_old_nodes = MongoNode(
                name="get_old_nodes",
                resource_key="aicenter-chatbot",
                operation="find",
                inputs={
                    "collection_name": "node",
                    "query": {code_build_doc_id_query: "query"},
                    "limit": 100000
                }
            )

            # ── 2. Process fetched data ────────────────────────────────────
            code_capture_all_topics = CodeNode(
                name="code_capture_all_topics",
                code_fn=_capture_all_topics,
                inputs={"topics": {get_all_topics: "data"}},
                return_keys=["all_topics: list"]
            )

            code_extract_doc_info = CodeNode(
                name="code_extract_doc_info",
                code_fn=_extract_doc_info,
                inputs={"data": {get_document_info: "data"}},
                return_keys=["doc_id: str", "extension: str", "file_name: str", "topic: str", "source: str"]
            )

            code_build_topic_path = CodeNode(
                name="code_build_topic_path",
                code_fn=build_topic_tree,
                inputs={
                    "topic_id": {code_extract_doc_info: "topic"},
                    "all_topics": {code_capture_all_topics: "all_topics"}
                },
                return_keys=["topic_path: str"]
            )

            # ── 3. Prepare new data from document_data ─────────────────────
            # 3a. chunk_data: bê nguyên content
            code_prepare_chunk_data = CodeNode(
                name="code_prepare_chunk_data",
                code_fn=prepare_chunk_data_from_document_data,
                inputs={
                    "document_data": {get_document_data: "data"},
                    "doc_id": {code_extract_doc_info: "doc_id"},
                },
                return_keys=["chunk_data: list"]
            )

            # 3c. Extract keywords for chunks
            code_prepare_keyword_batches = CodeNode(
                name="code_prepare_keyword_batches",
                code_fn=_prepare_keyword_batches,
                inputs={"chunk_data": {code_prepare_chunk_data: "chunk_data"}},
                return_keys=["batch_data: list"]
            )

            with ForLoopNode(
                name="loop_extract_chunk_keywords",
                description="Extract keywords for each chunk",
                inputs={"batch_data": {code_prepare_keyword_batches: "batch_data"}}
            ) as loop_extract_chunk_keywords:
                extract_keywords_node = CodeNode(
                    name="extract_keywords",
                    code_fn=_extract_keywords_node,
                    inputs={"chunk": {INPUT: "chunk"}},
                    return_keys=["keywords: list"],
                    outputs=OUTPUT
                )
                START >> extract_keywords_node >> END

            code_merge_chunk_keywords = CodeNode(
                name="code_merge_chunk_keywords",
                code_fn=_merge_keywords_to_chunk_data,
                inputs={
                    "chunk_data": {code_prepare_chunk_data: "chunk_data"},
                    "batches": {loop_extract_chunk_keywords: "batch_result"}
                },
                return_keys=["merged_chunk_data: list"]
            )

            # 3b. node_data: reconstruct markdown → tree (docx/pdf only) → node records
            code_reconstruct_markdown = CodeNode(
                name="code_reconstruct_markdown",
                code_fn=reconstruct_markdown_from_document_data,
                inputs={"document_data": {get_document_data: "data"}},
                return_keys=["markdown: str"]
            )

            code_build_tree = CodeNode(
                name="code_build_tree",
                code_fn=process_tree_if_applicable,
                inputs={
                    "extension": {code_extract_doc_info: "extension"},
                    "source": {code_extract_doc_info: "source"},
                    "reconstructed": {code_reconstruct_markdown: "markdown"},
                },
                return_keys=["tree_structure: list"]
            )

            code_prepare_node_data = CodeNode(
                name="code_prepare_node_data",
                code_fn=prepare_node_data_from_tree,
                inputs={
                    "doc_id": {code_extract_doc_info: "doc_id"},
                    "tree_structure": {code_build_tree: "tree_structure"},
                },
                return_keys=["node_data: list"]
            )

            # ── 4. Embed ───────────────────────────────────────────────────
            code_extract_chunk_texts = CodeNode(
                name="code_extract_chunk_texts",
                code_fn=_extract_chunk_texts,
                inputs={"chunk_data": {code_merge_chunk_keywords: "merged_chunk_data"}},
                return_keys=["chunk_texts: list"]
            )

            code_extract_node_texts = CodeNode(
                name="code_extract_node_texts",
                code_fn=_extract_node_texts,
                inputs={"nodes": {code_prepare_node_data: "node_data"}},
                return_keys=["node_texts: list"]
            )

            embedding_chunk = EmbeddingNode(
                name="embedding_chunk",
                resource_key="qwen-embedding-chat",
                inputs={"texts": {code_extract_chunk_texts: "chunk_texts"}}
            )

            code_count_chunk_texts = CodeNode(
                name="code_count_chunk_texts",
                code_fn=_get_list_length,
                inputs={"items": {code_extract_chunk_texts: "chunk_texts"}},
                return_keys=["count: int"],
            )

            code_empty_chunk_embeddings = CodeNode(
                name="code_empty_chunk_embeddings",
                code_fn=_empty_embeddings,
                inputs={},
                return_keys=["embeddings: list"],
            )

            branch_embed_chunks = BranchNode(
                name="branch_embed_chunks",
                cases={"count > 0": embedding_chunk},
                default=code_empty_chunk_embeddings,
                inputs={"count": {code_count_chunk_texts: "count"}},
            )

            code_select_chunk_embeddings = CodeNode(
                name="code_select_chunk_embeddings",
                code_fn=_select_embeddings,
                inputs={
                    "model_embeddings": {embedding_chunk: "embeddings"},
                    "empty_embeddings": {code_empty_chunk_embeddings: "embeddings"},
                },
                return_keys=["embeddings: list"],
            )

            embedding_node = EmbeddingNode(
                name="embedding_node",
                resource_key="qwen-embedding-chat",
                inputs={"texts": {code_extract_node_texts: "node_texts"}}
            )

            code_count_node_texts = CodeNode(
                name="code_count_node_texts",
                code_fn=_get_list_length,
                inputs={"items": {code_extract_node_texts: "node_texts"}},
                return_keys=["count: int"],
            )

            code_empty_node_embeddings = CodeNode(
                name="code_empty_node_embeddings",
                code_fn=_empty_embeddings,
                inputs={},
                return_keys=["embeddings: list"],
            )

            branch_embed_nodes = BranchNode(
                name="branch_embed_nodes",
                cases={"count > 0": embedding_node},
                default=code_empty_node_embeddings,
                inputs={"count": {code_count_node_texts: "count"}},
            )

            code_select_node_embeddings = CodeNode(
                name="code_select_node_embeddings",
                code_fn=_select_embeddings,
                inputs={
                    "model_embeddings": {embedding_node: "embeddings"},
                    "empty_embeddings": {code_empty_node_embeddings: "embeddings"},
                },
                return_keys=["embeddings: list"],
            )

            # ── 5. Embedding success check ──────────────────────────────────
            code_check_embedding_outputs = CodeNode(
                name="code_check_embedding_outputs",
                code_fn=_check_embedding_outputs,
                inputs={
                    "chunks": {code_merge_chunk_keywords: "merged_chunk_data"},
                    "chunk_embeddings": {code_select_chunk_embeddings: "embeddings"},
                    "nodes": {code_prepare_node_data: "node_data"},
                    "node_embeddings": {code_select_node_embeddings: "embeddings"},
                },
                return_keys=["embed_success: bool"]
            )

            code_build_done_training_status_update = CodeNode(
                name="code_build_done_training_status_update",
                code_fn=_build_training_status_update,
                inputs={
                    "document_id": {INPUT: "document_id"},
                    "is_trained": True,
                    "training_status": "DONE",
                },
                return_keys=["filter: dict", "update: dict"]
            )

            mongo_update_done_training_status = MongoNode(
                name="mongo_update_done_training_status",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.UPDATE_ONE,
                inputs={
                    "collection_name": "documents",
                    "filter": {code_build_done_training_status_update: "filter"},
                    "update": {code_build_done_training_status_update: "update"},
                }
            )

            code_build_error_training_status_update = CodeNode(
                name="code_build_error_training_status_update",
                code_fn=_build_training_status_update,
                inputs={
                    "document_id": {INPUT: "document_id"},
                    "is_trained": False,
                    "training_status": "ERROR",
                },
                return_keys=["filter: dict", "update: dict"]
            )

            mongo_update_error_training_status = MongoNode(
                name="mongo_update_error_training_status",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.UPDATE_ONE,
                inputs={
                    "collection_name": "documents",
                    "filter": {code_build_error_training_status_update: "filter"},
                    "update": {code_build_error_training_status_update: "update"},
                }
            )

            # ── 6. Prepare Milvus payloads ─────────────────────────────────
            code_prepare_milvus_chunks = CodeNode(
                name="code_prepare_milvus_chunks",
                code_fn=prepare_milvus_chunk_retrain_payload,
                inputs={
                    "chunk_data": {code_merge_chunk_keywords: "merged_chunk_data"},
                    "embeddings": {code_select_chunk_embeddings: "embeddings"},
                    "topic_path": {code_build_topic_path: "topic_path"},
                },
                return_keys=["milvus_chunks: list"]
            )

            code_prepare_milvus_nodes = CodeNode(
                name="code_prepare_milvus_nodes",
                code_fn=prepare_milvus_node_retrain_payload,
                inputs={
                    "nodes": {code_prepare_node_data: "node_data"},
                    "embeddings": {code_select_node_embeddings: "embeddings"},
                    "topic_path": {code_build_topic_path: "topic_path"},
                },
                return_keys=["milvus_nodes: list"]
            )

            # ── 7. Collect old IDs → Milvus delete expressions ────────────
            code_collect_old_chunk_ids = CodeNode(
                name="code_collect_old_chunk_ids",
                code_fn=collect_chunk_ids_by_doc,
                inputs={"chunks": {get_old_chunks: "data"}},
                return_keys=["chunk_ids: list", "milvus_expr: str"]
            )

            code_collect_old_node_ids = CodeNode(
                name="code_collect_old_node_ids",
                code_fn=collect_node_ids_by_doc,
                inputs={"nodes": {get_old_nodes: "data"}},
                return_keys=["node_ids: list", "milvus_expr: str"]
            )

            # ── 8a. Delete old Milvus ──────────────────────────────────────
            milvus_delete_old_chunks = MilvusNode(
                name="milvus_delete_old_chunks",
                resource_key="chatbot-libra",
                operation=MilvusOperation.DELETE,
                inputs={
                    "collection_name": {code_get_collection_names: "chunk_collection_name"},
                    "expr": {code_collect_old_chunk_ids: "milvus_expr"}
                }
            )

            milvus_delete_old_nodes = MilvusNode(
                name="milvus_delete_old_nodes",
                resource_key="chatbot-libra",
                operation=MilvusOperation.DELETE,
                inputs={
                    "collection_name": {code_get_collection_names: "node_collection_name"},
                    "expr": {code_collect_old_node_ids: "milvus_expr"}
                }
            )

            # ── 8b. Delete old Mongo ───────────────────────────────────────
            mongo_delete_old_chunks = MongoNode(
                name="mongo_delete_old_chunks",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.DELETE_MANY,
                inputs={
                    "collection_name": "chunk_data",
                    "filter": {code_build_chunk_doc_id_filter: "filter"},
                }
            )

            mongo_delete_old_nodes = MongoNode(
                name="mongo_delete_old_nodes",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.DELETE_MANY,
                inputs={
                    "collection_name": "node",
                    "filter": {code_build_doc_id_filter: "filter"},
                }
            )

            # ── 9. Insert new data (chained after respective deletes) ──────
            # Pass-through nodes for empty-list branches
            code_pass_through_mongo_chunk_data = CodeNode(
                name="code_pass_through_mongo_chunk_data",
                code_fn=_pass_through,
                inputs={},
            )
            code_pass_through_mongo_node = CodeNode(
                name="code_pass_through_mongo_node",
                code_fn=_pass_through,
                inputs={},
            )
            code_pass_through_milvus_chunk = CodeNode(
                name="code_pass_through_milvus_chunk",
                code_fn=_pass_through,
                inputs={},
            )
            code_pass_through_milvus_node = CodeNode(
                name="code_pass_through_milvus_node",
                code_fn=_pass_through,
                inputs={},
            )

            # 9a. Mongo chunk_data insert (conditional on count > 0)
            mongo_insert_chunk_data = MongoNode(
                name="mongo_insert_chunk_data",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.INSERT_MANY,
                inputs={
                    "collection_name": "chunk_data",
                    "documents": {code_merge_chunk_keywords: "merged_chunk_data"}
                }
            )

            code_count_mongo_chunk_data = CodeNode(
                name="code_count_mongo_chunk_data",
                code_fn=_get_list_length,
                inputs={"items": {code_merge_chunk_keywords: "merged_chunk_data"}},
                return_keys=["count: int"]
            )

            branch_mongo_insert_chunk_data = BranchNode(
                name="branch_mongo_insert_chunk_data",
                cases={"count > 0": mongo_insert_chunk_data},
                default=code_pass_through_mongo_chunk_data,
                inputs={"count": {code_count_mongo_chunk_data: "count"}}
            )

            # 9b. Mongo node insert (conditional on count > 0)
            mongo_insert_node = MongoNode(
                name="mongo_insert_node",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.INSERT_MANY,
                inputs={
                    "collection_name": "node",
                    "documents": {code_prepare_node_data: "node_data"}
                }
            )

            code_count_mongo_nodes = CodeNode(
                name="code_count_mongo_nodes",
                code_fn=_get_list_length,
                inputs={"items": {code_prepare_node_data: "node_data"}},
                return_keys=["count: int"]
            )

            branch_mongo_insert_node = BranchNode(
                name="branch_mongo_insert_node",
                cases={"count > 0": mongo_insert_node},
                default=code_pass_through_mongo_node,
                inputs={"count": {code_count_mongo_nodes: "count"}}
            )

            # 9c. Milvus _chunk insert (always has chunks; chain after delete)
            milvus_insert_chunk = MilvusNode(
                name="milvus_insert_chunk",
                resource_key="chatbot-libra",
                operation=MilvusOperation.INSERT,
                inputs={
                    "data": {code_prepare_milvus_chunks: "milvus_chunks"},
                    "collection_name": {code_get_collection_names: "chunk_collection_name"}
                }
            )

            code_count_milvus_chunks = CodeNode(
                name="code_count_milvus_chunks",
                code_fn=_get_list_length,
                inputs={"items": {code_prepare_milvus_chunks: "milvus_chunks"}},
                return_keys=["count: int"]
            )

            branch_milvus_insert_chunk = BranchNode(
                name="branch_milvus_insert_chunk",
                cases={"count > 0": milvus_insert_chunk},
                default=code_pass_through_milvus_chunk,
                inputs={"count": {code_count_milvus_chunks: "count"}}
            )

            # 9d. Milvus _node insert (conditional on count > 0)
            milvus_insert_node = MilvusNode(
                name="milvus_insert_node",
                resource_key="chatbot-libra",
                operation=MilvusOperation.INSERT,
                inputs={
                    "data": {code_prepare_milvus_nodes: "milvus_nodes"},
                    "collection_name": {code_get_collection_names: "node_collection_name"}
                }
            )

            code_count_milvus_nodes = CodeNode(
                name="code_count_milvus_nodes",
                code_fn=_get_list_length,
                inputs={"items": {code_prepare_milvus_nodes: "milvus_nodes"}},
                return_keys=["count: int"]
            )

            branch_milvus_insert_node = BranchNode(
                name="branch_milvus_insert_node",
                cases={"count > 0": milvus_insert_node},
                default=code_pass_through_milvus_node,
                inputs={"count": {code_count_milvus_nodes: "count"}}
            )

            code_check_milvus_insert_outputs = CodeNode(
                name="code_check_milvus_insert_outputs",
                code_fn=_check_milvus_insert_outputs,
                inputs={
                    "embed_success": {code_check_embedding_outputs: "embed_success"},
                    "chunk_count": {code_count_milvus_chunks: "count"},
                    "node_count": {code_count_milvus_nodes: "count"},
                    "milvus_insert_chunk_status": {milvus_insert_chunk: "status"},
                    "milvus_insert_node_status": {milvus_insert_node: "status"},
                },
                return_keys=["training_success: bool", "failed_operations: list"],
            )

            branch_update_training_status = BranchNode(
                name="branch_update_training_status",
                cases={"training_success == True": code_build_done_training_status_update},
                default=code_build_error_training_status_update,
                inputs={
                    "training_success": {
                        code_check_milvus_insert_outputs: "training_success"
                    }
                },
            )

            # ── Workflow graph ─────────────────────────────────────────────
            START >> [
                code_build_topic_query,
                code_get_collection_names,
                code_build_doc_query,
                code_build_doc_id_query,
                code_build_chunk_doc_id_query,
                code_build_doc_id_filter,
                code_build_chunk_doc_id_filter,
            ]

            # Fetch
            code_build_topic_query >> get_all_topics >> code_capture_all_topics
            code_build_doc_query >> get_document_info >> code_extract_doc_info
            code_build_doc_id_query >> [get_document_data, get_old_nodes]
            code_build_chunk_doc_id_query >> get_old_chunks

            # Topic path
            [code_extract_doc_info, code_capture_all_topics] >> code_build_topic_path

            # Prepare new chunk_data (from document_data)
            [get_document_data, code_extract_doc_info] >> code_prepare_chunk_data

            # Extract keywords for chunk_data
            code_prepare_chunk_data >> code_prepare_keyword_batches >> loop_extract_chunk_keywords >> code_merge_chunk_keywords
            code_prepare_chunk_data >> code_merge_chunk_keywords

            # Prepare new node_data (reconstruct markdown → tree → nodes)
            get_document_data >> code_reconstruct_markdown
            [code_reconstruct_markdown, code_extract_doc_info] >> code_build_tree
            [code_build_tree, code_extract_doc_info] >> code_prepare_node_data

            # Embed
            code_merge_chunk_keywords >> code_extract_chunk_texts >> code_count_chunk_texts
            code_count_chunk_texts >> branch_embed_chunks >> [embedding_chunk, code_empty_chunk_embeddings] >> code_select_chunk_embeddings
            code_prepare_node_data >> code_extract_node_texts >> code_count_node_texts
            code_count_node_texts >> branch_embed_nodes >> [embedding_node, code_empty_node_embeddings] >> code_select_node_embeddings

            # Check embeddings. Final status is decided after persistence.
            [code_select_chunk_embeddings, code_select_node_embeddings, code_merge_chunk_keywords, code_prepare_node_data] >> code_check_embedding_outputs

            # Milvus payloads
            [code_prepare_chunk_data, code_select_chunk_embeddings, code_build_topic_path] >> code_prepare_milvus_chunks >> code_count_milvus_chunks
            [code_prepare_node_data, code_select_node_embeddings, code_build_topic_path] >> code_prepare_milvus_nodes >> code_count_milvus_nodes
            code_prepare_node_data >> code_count_mongo_nodes
            code_merge_chunk_keywords >> code_count_mongo_chunk_data

            # Collect old IDs
            get_old_chunks >> code_collect_old_chunk_ids
            get_old_nodes >> code_collect_old_node_ids

            # Delete old Milvus
            [code_collect_old_chunk_ids, code_get_collection_names] >> milvus_delete_old_chunks
            [code_collect_old_node_ids, code_get_collection_names] >> milvus_delete_old_nodes

            # Delete old Mongo
            code_build_chunk_doc_id_filter >> mongo_delete_old_chunks
            code_build_doc_id_filter >> mongo_delete_old_nodes

            # Insert new Mongo chunk_data (conditional; chain: delete first)
            code_count_mongo_chunk_data >> branch_mongo_insert_chunk_data
            mongo_delete_old_chunks >> branch_mongo_insert_chunk_data
            branch_mongo_insert_chunk_data >> [mongo_insert_chunk_data, code_pass_through_mongo_chunk_data]

            # Insert new Mongo node (conditional; chain: delete first)
            code_count_mongo_nodes >> branch_mongo_insert_node
            mongo_delete_old_nodes >> branch_mongo_insert_node
            branch_mongo_insert_node >> [mongo_insert_node, code_pass_through_mongo_node]

            # Insert new Milvus _chunk (conditional; chain: delete first)
            code_count_milvus_chunks >> branch_milvus_insert_chunk
            milvus_delete_old_chunks >> branch_milvus_insert_chunk
            branch_milvus_insert_chunk >> [milvus_insert_chunk, code_pass_through_milvus_chunk]

            # Insert new Milvus _node (conditional; chain: delete first)
            code_count_milvus_nodes >> branch_milvus_insert_node
            milvus_delete_old_nodes >> branch_milvus_insert_node
            branch_milvus_insert_node >> [milvus_insert_node, code_pass_through_milvus_node]

            # A failed Milvus insert must never be treated as DONE.
            [
                code_check_embedding_outputs,
                code_count_milvus_chunks,
                code_count_milvus_nodes,
                mongo_insert_chunk_data,
                code_pass_through_mongo_chunk_data,
                mongo_insert_node,
                code_pass_through_mongo_node,
                milvus_insert_chunk,
                code_pass_through_milvus_chunk,
                milvus_insert_node,
                code_pass_through_milvus_node,
            ] >> code_check_milvus_insert_outputs  >> branch_update_training_status >> [
                code_build_done_training_status_update,
                code_build_error_training_status_update,
            ]
            code_build_done_training_status_update >> mongo_update_done_training_status >> END
            code_build_error_training_status_update >> mongo_update_error_training_status >> END

        wf_train_document_job.compile()
        self.wf_train_document_job = wf_train_document_job
        self._build_documents_workflow()

    def _build_documents_workflow(self) -> None:
        with WorkflowEngine(
            name="wf_train_documents_job",
            description="train documents concurrently in one pod",
            langfuse="beegen-portal",
        ) as workflow:
            prepare_documents = CodeNode(
                name="code_prepare_train_documents",
                code_fn=_prepare_document_items,
                inputs={"document_ids": INPUT, "bot_id": INPUT},
                return_keys=["batch_data: list"],
            )

            with ForLoopNode(
                name="loop_train_documents",
                max_concurrency=8,
                inputs={"batch_data": {prepare_documents: "batch_data"}},
            ) as loop_documents:
                process_document = CodeNode(
                    name="code_process_train_document",
                    code_fn=self._process_document_item,
                    inputs={"document_id": INPUT, "bot_id": INPUT},
                    return_keys=[
                        "processed_document_id: str",
                        "is_trained: bool",
                        "training_status: str",
                        "error: str",
                    ],
                )
                START >> process_document >> END

            START >> prepare_documents >> loop_documents >> END

        workflow.compile()
        self.wf_train_documents_job = workflow

    async def _process_document_item(self,document_id: str,bot_id: str) -> dict:
        is_trained, training_status = _get_training_status(document_id)
        if is_trained and training_status == "DONE":
            return {
                "processed_document_id": document_id,
                "is_trained": True,
                "training_status": "DONE",
                "error": "",
            }

        try:
            await self.process(TrainJobRequest(bot_id=bot_id, id=document_id))
            return {
                "processed_document_id": document_id,
                "is_trained": True,
                "training_status": "DONE",
                "error": "",
            }
        except Exception as exc:
            try:
                _mark_training_error(document_id)
            except Exception:
                pass
            return {
                "processed_document_id": document_id,
                "is_trained": False,
                "training_status": "ERROR",
                "error": str(exc),
            }

    async def process(
        self, document: TrainJobRequest, **kwargs
    ):
        try:
            import uuid
            request_id = str(uuid.uuid4())
            result = await self.wf_train_document_job.run(
                request_id=request_id,
                inputs={
                    "bot_id": document.bot_id,
                    "document_id": document.id
                }
            )
            is_trained, training_status = _get_training_status(document.id)
            if not is_trained or training_status != "DONE":
                raise RuntimeError(
                    "Document training workflow did not complete "
                )
            return result
        except Exception as e:
            try:
                _mark_training_error(document.id)
            except Exception:
                pass
            raise RuntimeError(f"Train document failed: {str(e)}") from e

    async def process_documents(
        self,
        bot_id: str,
        document_ids: list[str],
    ) -> dict:
        import uuid

        return await self.wf_train_documents_job.run(
            request_id=str(uuid.uuid4()),
            inputs={"bot_id": bot_id, "document_ids": document_ids},
        )


if __name__ == "__main__":
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Test TrainDocumentJob")
    parser.add_argument("--bot_id", type=str, required=True, help="Bot ID")
    parser.add_argument("--document_ids", type=str, required=True, help="JSON array of document IDS")
    args = parser.parse_args()

    async def _run():
        job = TrainDocumentJob()
        document_ids = json.loads(args.document_ids)
        await job.process_documents(
            bot_id=args.bot_id,
            document_ids=document_ids
        )
        await asyncio.sleep(3)

    asyncio.run(_run())
