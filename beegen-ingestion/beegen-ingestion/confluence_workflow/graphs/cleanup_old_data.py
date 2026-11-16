"""
Reusable cleanup graph for old Confluence derived data.

This graph deletes derived data linked to Mongo `documents` rows:
- Milvus vectors by chunk_id
- Mongo `chunk_data` by doc_id
- Milvus vectors by node_id
- Mongo `node` by document_id
- Mongo `document_data` by document_id
- S3 multimedia objects by Mongo `multimedia.path`
- Mongo `multimedia` rows after their S3 objects are deleted
"""

import os
from typing import Any

from beeflow.nodes import START, END, INPUT, OUTPUT, BranchNode, CodeNode, GraphNode, MilvusNode, MongoNode, S3Node
from beeflow.nodes.flow.for_loop_node import ForLoopNode

from beegen.configs.storage.mongo_config import MongoOperation
from beegen.configs.storage.s3_config import S3Operation
from beegen.configs.storage.vectordb.milvus_config import MilvusOperation

from confluence_workflow.functions.milvus_processor import (
    _build_milvus_delete_payload,
    _build_milvus_node_delete_payload,
)

"""
Logic xóa 
chunk_data.doc_id = documents._id
node.document_id = documents._id
document_data.document_id = documents._id
chunk_data.chunk_id dùng để xóa Milvus
node.node_id dùng để xóa Milvus
"""


async def _extract_cleanup_doc_ids(documents: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Extract Mongo document ids and build cleanup queries."""
    doc_ids = [doc["_id"] for doc in (documents or []) if isinstance(doc, dict) and "_id" in doc]
    return {
        "doc_ids": doc_ids,
        "has_doc_ids": bool(doc_ids),
        "chunk_doc_query": {"doc_id": {"$in": doc_ids}},
        "node_document_query": {"document_id": {"$in": doc_ids}},
        "document_data_query": {"document_id": {"$in": doc_ids}},
    }


async def _build_cleanup_result(cleanup_doc_ids: list | None = None) -> dict[str, Any]:
    """Expose a small stable output for callers that need to inspect cleanup."""
    return {
        "doc_ids": cleanup_doc_ids or [],
        "has_doc_ids": bool(cleanup_doc_ids),
        "cleaned_count": len(cleanup_doc_ids or []),
    }


async def _build_multimedia_cleanup_query(
    doc_ids: list,
    bot_id: str,
    protected_multimedia_ids: list,
) -> dict[str, Any]:
    """Find old multimedia by its owning document without selecting new uploads."""
    return {
        "multimedia_query": {
            "bot_id": str(bot_id),
            "document_id": {"$in": [str(doc_id) for doc_id in doc_ids]},
            "_id": {"$nin": protected_multimedia_ids},
        }
    }


async def _prepare_multimedia_cleanup(multimedia_documents: list) -> dict[str, Any]:
    """Prepare the exact old S3 objects and Mongo multimedia rows to delete."""
    return {
        "multimedia_delete_batch": [
            {"key": document["path"]}
            for document in multimedia_documents
        ],
        "multimedia_delete_filter": {
            "_id": {"$in": [document["_id"] for document in multimedia_documents]}
        },
    }


async def _validate_multimedia_s3_cleanup(
    multimedia_delete_results: list,
    multimedia_delete_filter: dict,
) -> dict[str, Any]:
    """Allow Mongo deletion only after every old multimedia object was deleted from S3."""
    if any(result.get("status") != "success" for result in multimedia_delete_results):
        raise RuntimeError("Could not delete all old Confluence multimedia files from S3")
    return {"validated_multimedia_delete_filter": multimedia_delete_filter}


def build_cleanup_old_confluence_data_graph(
    name: str = "graph_cleanup_old_confluence_data",
    inputs: dict[str, Any] | None = None,
):
    """Build a graph that cleans derived data for documents matching `document_query`."""
    with GraphNode(
        name=name,
        description="Cleanup Confluence chunk, node, document and multimedia data",
        inputs=inputs or {
            "bot_id": INPUT,
            "document_query": INPUT,
            "protected_multimedia_ids": INPUT,
        },
    ) as graph_cleanup_old_confluence_data:
        
        # Vào bảng documents lấy ra _id
        mongo_find_documents = MongoNode(
            name="mongo_find_documents_for_cleanup",
            resource_key="aicenter-chatbot",
            operation=MongoOperation.FIND,
            inputs={
                "collection_name": "documents",
                "query": {INPUT: "document_query"},
                "projection": {"_id": 1},
                "limit": 0,
            },
        )

        # Dùng kết quả MongoNode trả về để lấy ra list _id
        code_extract_doc_ids = CodeNode(
            name="code_extract_cleanup_doc_ids",
            code_fn=_extract_cleanup_doc_ids,
            inputs={"documents": {mongo_find_documents: "data"}},
            return_keys=[
                "doc_ids: list",
                "has_doc_ids: bool",
                "chunk_doc_query: dict",
                "node_document_query: dict",
                "document_data_query: dict",
            ],
        )

        # Vào bảng chunk_data lấy ra chunk_id dựa _id của documents
        mongo_find_chunks = MongoNode(
            name="mongo_find_cleanup_chunks",
            resource_key="aicenter-chatbot",
            operation=MongoOperation.FIND,
            inputs={
                "collection_name": "chunk_data",
                "query": {code_extract_doc_ids: "chunk_doc_query"},
                "projection": {"chunk_id": 1, "_id": 0},
                "limit": 0,
            },
        )

        # Code để xóa trên Milvus dựa vào chunk_id
        code_build_milvus_delete_payload = CodeNode(
            name="code_build_cleanup_milvus_delete_payload",
            code_fn=_build_milvus_delete_payload,
            return_keys=["collection_name: str", "expr: str", "has_chunk_ids: bool"],
            inputs={
                "chunk_docs": {mongo_find_chunks: "data"},
                "bot_id": {INPUT: "bot_id"},
            },
        )

        branch_has_milvus_chunks = BranchNode(
            name="branch_has_cleanup_milvus_chunks",
            cases={"has_chunk_ids == True": "milvus_delete_cleanup_vectors"},
            inputs={"has_chunk_ids": {code_build_milvus_delete_payload: "has_chunk_ids"}},
            default="mongo_delete_cleanup_chunk_data",
        )

        # Xóa data trên Milvus
        milvus_delete_vectors = MilvusNode(
            name="milvus_delete_cleanup_vectors",
            resource_key="chatbot-libra",
            operation=MilvusOperation.DELETE,
            inputs={
                "collection_name": {code_build_milvus_delete_payload: "collection_name"},
                "expr": {code_build_milvus_delete_payload: "expr"},
            },
        )

        # Xóa data trong bảng chunk_data
        mongo_delete_chunk_data = MongoNode(
            name="mongo_delete_cleanup_chunk_data",
            resource_key="aicenter-chatbot",
            operation=MongoOperation.DELETE_MANY,
            inputs={
                "collection_name": "chunk_data",
                "filter": {code_extract_doc_ids: "chunk_doc_query"},
            },
        )

        mongo_find_nodes = MongoNode(
            name="mongo_find_cleanup_nodes",
            resource_key="aicenter-chatbot",
            operation=MongoOperation.FIND,
            inputs={
                "collection_name": "node",
                "query": {code_extract_doc_ids: "node_document_query"},
                "projection": {"node_id": 1, "_id": 0},
                "limit": 0,
            },
        )

        code_build_milvus_node_delete_payload = CodeNode(
            name="code_build_cleanup_milvus_node_delete_payload",
            code_fn=_build_milvus_node_delete_payload,
            return_keys=["collection_name: str", "expr: str", "has_node_ids: bool"],
            inputs={
                "node_docs": {mongo_find_nodes: "data"},
                "bot_id": {INPUT: "bot_id"},
            },
        )

        branch_has_milvus_nodes = BranchNode(
            name="branch_has_cleanup_milvus_nodes",
            cases={"has_node_ids == True": "milvus_delete_cleanup_node_vectors"},
            inputs={
                "has_node_ids": {
                    code_build_milvus_node_delete_payload: "has_node_ids"
                }
            },
            default="mongo_delete_cleanup_nodes",
        )

        milvus_delete_node_vectors = MilvusNode(
            name="milvus_delete_cleanup_node_vectors",
            resource_key="chatbot-libra",
            operation=MilvusOperation.DELETE,
            inputs={
                "collection_name": {
                    code_build_milvus_node_delete_payload: "collection_name"
                },
                "expr": {code_build_milvus_node_delete_payload: "expr"},
            },
        )

        mongo_delete_nodes = MongoNode(
            name="mongo_delete_cleanup_nodes",
            resource_key="aicenter-chatbot",
            operation=MongoOperation.DELETE_MANY,
            inputs={
                "collection_name": "node",
                "filter": {code_extract_doc_ids: "node_document_query"},
            },
        )

        # Xóa data trong bảng document_data
        mongo_delete_document_data = MongoNode(
            name="mongo_delete_cleanup_document_data",
            resource_key="aicenter-chatbot",
            operation=MongoOperation.DELETE_MANY,
            inputs={
                "collection_name": "document_data",
                "filter": {code_extract_doc_ids: "document_data_query"},
            },
        )

        code_build_multimedia_cleanup_query = CodeNode(
            name="code_build_multimedia_cleanup_query",
            code_fn=_build_multimedia_cleanup_query,
            inputs={
                "doc_ids": {code_extract_doc_ids: "doc_ids"},
                "bot_id": {INPUT: "bot_id"},
                "protected_multimedia_ids": {INPUT: "protected_multimedia_ids"},
            },
            return_keys=["multimedia_query: dict"],
        )

        mongo_find_cleanup_multimedia = MongoNode(
            name="mongo_find_cleanup_multimedia",
            resource_key="aicenter-chatbot",
            operation=MongoOperation.FIND,
            inputs={
                "collection_name": "multimedia",
                "query": {code_build_multimedia_cleanup_query: "multimedia_query"},
                "projection": {"_id": 1, "path": 1},
                "limit": 0,
            },
        )

        code_prepare_multimedia_cleanup = CodeNode(
            name="code_prepare_multimedia_cleanup",
            code_fn=_prepare_multimedia_cleanup,
            inputs={"multimedia_documents": {mongo_find_cleanup_multimedia: "data"}},
            return_keys=[
                "multimedia_delete_batch: list",
                "multimedia_delete_filter: dict",
            ],
        )

        with ForLoopNode(
            name="multimedia_delete_loop",
            description="Delete old Confluence multimedia files from S3",
            inputs={
                "batch_data": {code_prepare_multimedia_cleanup: "multimedia_delete_batch"},
            },
            max_concurrency=8,
        ) as multimedia_delete_loop:
            s3_delete_multimedia = S3Node(
                name="s3_delete_multimedia",
                resource_key="ai-nlp-text",
                operation=S3Operation.DELETE,
                inputs={
                    "bucket":"ai-text-raw",
                    "key": {INPUT: "key"},
                },
                outputs={"status": OUTPUT["status"]},
            )

            START >> s3_delete_multimedia >> END

        multimedia_delete_loop.build()

        code_validate_multimedia_s3_cleanup = CodeNode(
            name="code_validate_multimedia_s3_cleanup",
            code_fn=_validate_multimedia_s3_cleanup,
            inputs={
                "multimedia_delete_results": {multimedia_delete_loop: "batch_result"},
                "multimedia_delete_filter": {
                    code_prepare_multimedia_cleanup: "multimedia_delete_filter",
                },
            },
            return_keys=["validated_multimedia_delete_filter: dict"],
        )

        mongo_delete_cleanup_multimedia = MongoNode(
            name="mongo_delete_cleanup_multimedia",
            resource_key="aicenter-chatbot",
            operation=MongoOperation.DELETE_MANY,
            inputs={
                "collection_name": "multimedia",
                "filter": {
                    code_validate_multimedia_s3_cleanup: "validated_multimedia_delete_filter",
                },
            },
        )

        code_build_cleanup_result = CodeNode(
            name="code_build_cleanup_result",
            code_fn=_build_cleanup_result,
            inputs={"cleanup_doc_ids": {code_extract_doc_ids: "doc_ids"}},
            outputs={
                "doc_ids": OUTPUT,
                "has_doc_ids": OUTPUT,
                "cleaned_count": OUTPUT,
            },
            return_keys=["doc_ids: list", "has_doc_ids: bool", "cleaned_count: int"],
        )

        START >> mongo_find_documents >> code_extract_doc_ids
        code_extract_doc_ids >> [
            mongo_find_chunks,
            mongo_find_nodes,
            mongo_delete_document_data,
            code_build_multimedia_cleanup_query,
        ]

        mongo_find_chunks >> code_build_milvus_delete_payload >> branch_has_milvus_chunks
        branch_has_milvus_chunks >> [milvus_delete_vectors, mongo_delete_chunk_data]
        milvus_delete_vectors >> mongo_delete_chunk_data

        mongo_find_nodes >> code_build_milvus_node_delete_payload >> branch_has_milvus_nodes
        branch_has_milvus_nodes >> [milvus_delete_node_vectors, mongo_delete_nodes]
        milvus_delete_node_vectors >> mongo_delete_nodes

        code_build_multimedia_cleanup_query >> mongo_find_cleanup_multimedia
        mongo_find_cleanup_multimedia >> code_prepare_multimedia_cleanup
        code_prepare_multimedia_cleanup >> multimedia_delete_loop
        multimedia_delete_loop >> code_validate_multimedia_s3_cleanup
        code_validate_multimedia_s3_cleanup >> mongo_delete_cleanup_multimedia

        [
            mongo_delete_chunk_data,
            mongo_delete_nodes,
            mongo_delete_document_data,
            mongo_delete_cleanup_multimedia,
        ] >> code_build_cleanup_result
        code_build_cleanup_result >> END

    graph_cleanup_old_confluence_data.build()
    return graph_cleanup_old_confluence_data
