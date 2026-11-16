from typing import Any, Dict, List

from beeflow.workflow import WorkflowEngine

from beeflow.nodes.primitives.data.mongo_node import MongoNode
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beeflow.nodes.primitives.data.milvus_node import MilvusNode
from beeflow.nodes.flow.for_loop_node import ForLoopNode
from beeflow.nodes.base_node import END, INPUT, START
from beegen.configs import MilvusOperation, MongoOperation

from app.model.document import CleanJobRequest
from app.service.portal.utils.prepare_document import (
    prepare_chunk_query_by_doc_ids,
    prepare_node_query_by_doc_ids,
    collect_chunk_ids_by_doc,
    collect_node_ids_by_doc,
    prepare_mongo_delete_by_doc_ids,
    prepare_mongo_delete_chunks_by_doc_ids,
    prepare_mongo_delete_documents,
    get_milvus_collection_names_for_delete,
)


def _wrap_single_doc_id(document_id: str) -> Dict[str, Any]:
    """Wrap a single document_id into a list for the batch delete helpers."""
    return {"doc_ids": [document_id]}


def _prepare_document_items(document_ids: list[str], bot_id: str):
    return {
        "batch_data": [
            {"document_id": document_id, "bot_id": bot_id}
            for document_id in document_ids
        ]
    }


class CleanDocumentJob:
    def __init__(self):
        with WorkflowEngine(
            name="wf_clean_document_job",
            description="delete the documents record only when deleted=True",
            langfuse="beegen-portal"
        ) as wf_clean_document_job:

            # ── Step 1: Wrap single document_id → [doc_ids] ──
            code_wrap_doc_id = CodeNode(
                name="code_wrap_doc_id",
                code_fn=_wrap_single_doc_id,
                inputs={"document_id": {INPUT: "document_id"}},
                return_keys=["doc_ids: List[str]"]
            )

            # ── Step 2: Derive Milvus collection names ──
            code_get_milvus_names = CodeNode(
                name="code_get_milvus_names",
                code_fn=get_milvus_collection_names_for_delete,
                inputs={"bot_id": {INPUT: "bot_id"}},
                return_keys=["chunk_collection_name: str", "node_collection_name: str"]
            )

            # ── Step 3: Build queries for chunk and node lookup ──
            code_chunk_query = CodeNode(
                name="code_chunk_query",
                code_fn=prepare_chunk_query_by_doc_ids,
                inputs={"doc_ids": {code_wrap_doc_id: "doc_ids"}},
                return_keys=["query: Dict[str, Any]"]
            )

            code_node_query = CodeNode(
                name="code_node_query",
                code_fn=prepare_node_query_by_doc_ids,
                inputs={"doc_ids": {code_wrap_doc_id: "doc_ids"}},
                return_keys=["query: Dict[str, Any]"]
            )

            # ── Step 4: Fetch chunks + nodes from Mongo ──
            get_chunks = MongoNode(
                name="get_chunks_for_delete",
                resource_key="aicenter-chatbot",
                operation="find",
                inputs={
                    "collection_name": "chunk_data",
                    "query": {code_chunk_query: "query"},
                    "limit": 100000
                }
            )

            get_nodes = MongoNode(
                name="get_nodes_for_delete",
                resource_key="aicenter-chatbot",
                operation="find",
                inputs={
                    "collection_name": "node",
                    "query": {code_node_query: "query"},
                    "limit": 100000
                }
            )

            # ── Step 5: Collect IDs → Milvus delete expressions ──
            code_collect_chunk_ids = CodeNode(
                name="code_collect_chunk_ids",
                code_fn=collect_chunk_ids_by_doc,
                inputs={"chunks": {get_chunks: "data"}},
                return_keys=["chunk_ids: List[str]", "milvus_expr: str"]
            )

            code_collect_node_ids = CodeNode(
                name="code_collect_node_ids",
                code_fn=collect_node_ids_by_doc,
                inputs={"nodes": {get_nodes: "data"}},
                return_keys=["node_ids: List[str]", "milvus_expr: str"]
            )

            # ── Step 6: Milvus deletes ──
            milvus_delete_chunks = MilvusNode(
                name="milvus_delete_chunks",
                resource_key="chatbot-libra",
                operation=MilvusOperation.DELETE,
                inputs={
                    "collection_name": {code_get_milvus_names: "chunk_collection_name"},
                    "expr": {code_collect_chunk_ids: "milvus_expr"}
                }
            )

            milvus_delete_nodes = MilvusNode(
                name="milvus_delete_nodes",
                resource_key="chatbot-libra",
                operation=MilvusOperation.DELETE,
                inputs={
                    "collection_name": {code_get_milvus_names: "node_collection_name"},
                    "expr": {code_collect_node_ids: "milvus_expr"}
                }
            )

            # ── Step 7: Mongo deletes ──
            # Build chunk_data filter: {doc_id: {$in: [doc_id]}}
            code_chunk_doc_id_filter = CodeNode(
                name="code_chunk_doc_id_filter",
                code_fn=prepare_mongo_delete_chunks_by_doc_ids,
                inputs={"doc_ids": {code_wrap_doc_id: "doc_ids"}},
                return_keys=["mongo_filter: Dict[str, Any]"]
            )

            # Build shared filter for node/document_data: {document_id: {$in: [doc_id]}}
            code_doc_id_filter = CodeNode(
                name="code_doc_id_filter",
                code_fn=prepare_mongo_delete_by_doc_ids,
                inputs={"doc_ids": {code_wrap_doc_id: "doc_ids"}},
                return_keys=["mongo_filter: Dict[str, Any]"]
            )

            # 7a: chunk_data
            mongo_delete_chunks = MongoNode(
                name="mongo_delete_chunks",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.DELETE_MANY,
                inputs={
                    "collection_name": "chunk_data",
                    "filter": {code_chunk_doc_id_filter: "mongo_filter"},
                }
            )

            # 7b: node
            mongo_delete_nodes = MongoNode(
                name="mongo_delete_nodes",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.DELETE_MANY,
                inputs={
                    "collection_name": "node",
                    "filter": {code_doc_id_filter: "mongo_filter"},
                }
            )

            # 7c: document_data
            mongo_delete_document_data = MongoNode(
                name="mongo_delete_document_data",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.DELETE_MANY,
                inputs={
                    "collection_name": "document_data",
                    "filter": {code_doc_id_filter: "mongo_filter"},
                }
            )

            # 7d: documents (delete the parent only when deleted=True)
            code_parent_doc_filter = CodeNode(
                name="code_parent_doc_filter",
                code_fn=prepare_mongo_delete_documents,
                inputs={"doc_ids": {code_wrap_doc_id: "doc_ids"}},
                return_keys=["mongo_filter: Dict[str, Any]"]
            )

            mongo_delete_document = MongoNode(
                name="mongo_delete_document",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.DELETE_MANY,
                inputs={
                    "collection_name": "documents",
                    "filter": {code_parent_doc_filter: "mongo_filter"},
                }
            )

            # ── Workflow graph ──
            START >> [code_wrap_doc_id, code_get_milvus_names]
            code_wrap_doc_id >> [
                code_chunk_query,
                code_node_query,
                code_chunk_doc_id_filter,
                code_doc_id_filter,
                code_parent_doc_filter,
            ]

            # Step 1: READ chunk/node IDs from Mongo FIRST (must complete before any delete)
            code_chunk_query >> get_chunks >> code_collect_chunk_ids
            code_node_query >> get_nodes >> code_collect_node_ids

            # Step 2: After IDs collected → delete from Milvus + Mongo in parallel
            # (Milvus delete uses the collected IDs; Mongo delete is safe since READ already done)
            [code_collect_chunk_ids, code_get_milvus_names] >> milvus_delete_chunks
            [code_collect_node_ids, code_get_milvus_names] >> milvus_delete_nodes

            [code_chunk_doc_id_filter, code_collect_chunk_ids] >> mongo_delete_chunks
            [code_doc_id_filter, code_collect_node_ids] >> mongo_delete_nodes
            code_doc_id_filter >> mongo_delete_document_data  # no IDs needed for Milvus → can run freely

            # Step 3: Delete the parent only if deleted=True, after all child cleanup completes.
            [
                mongo_delete_chunks,
                mongo_delete_nodes,
                mongo_delete_document_data,
                milvus_delete_chunks,
                milvus_delete_nodes,
                code_parent_doc_filter,
            ] >> mongo_delete_document >> END

        wf_clean_document_job.compile()
        self.wf_clean_document_job = wf_clean_document_job
        self._build_documents_workflow()

    async def process(
        self, document: CleanJobRequest, **kwargs
    ):
        try:
            import uuid
            request_id = str(uuid.uuid4())
            result = await self.wf_clean_document_job.run(
                request_id=request_id,
                inputs={
                    "document_id": document.id,
                    "bot_id": document.bot_id,
                }
            )
            return result
        except Exception as e:
            raise RuntimeError(f"Clean document job failed: {str(e)}") from e

    def _build_documents_workflow(self) -> None:
        with WorkflowEngine(
            name="wf_clean_documents_job",
            description="clean documents concurrently in one pod",
            langfuse="beegen-portal",
        ) as workflow:
            prepare_documents = CodeNode(
                name="code_prepare_clean_documents",
                code_fn=_prepare_document_items,
                inputs={"document_ids": INPUT, "bot_id": INPUT},
                return_keys=["batch_data: list"],
            )

            with ForLoopNode(
                name="loop_clean_documents",
                max_concurrency=8,
                inputs={"batch_data": {prepare_documents: "batch_data"}},
            ) as loop_documents:
                process_document = CodeNode(
                    name="code_process_clean_document",
                    code_fn=self._process_document_item,
                    inputs={"document_id": INPUT, "bot_id": INPUT},
                    return_keys=[
                        "processed_document_id: str",
                        "status: str",
                        "error: str",
                    ],
                )
                START >> process_document >> END

            START >> prepare_documents >> loop_documents >> END

        workflow.compile()
        self.wf_clean_documents_job = workflow

    async def _process_document_item(self,document_id: str, bot_id: str) -> dict:
        try:
            await self.process(CleanJobRequest(bot_id=bot_id,type="document",id=document_id))
            return {
                "processed_document_id": document_id,
                "status": "DONE",
                "error": "",
            }
        except Exception as exc:
            return {
                "processed_document_id": document_id,
                "status": "ERROR",
                "error": str(exc),
            }

    async def process_documents(
        self,
        bot_id: str,
        document_ids: list[str],
    ) -> dict:
        import uuid

        return await self.wf_clean_documents_job.run(
            request_id=str(uuid.uuid4()),
            inputs={"bot_id": bot_id, "document_ids": document_ids},
        )


if __name__ == "__main__":
    import argparse
    import asyncio
    import json

    parser = argparse.ArgumentParser(description=("Clean dependent document data and delete the parent only when deleted=True"))
    parser.add_argument("--bot_id", type=str, required=True, help="Bot ID")
    parser.add_argument("--document_ids", type=str, required=True, help="JSON array of document IDS")
    args = parser.parse_args()

    async def _run():
        job = CleanDocumentJob()
        document_ids = json.loads(args.document_ids)
        await job.process_documents(
            bot_id=args.bot_id,
            document_ids=document_ids
        )
        await asyncio.sleep(3)

    asyncio.run(_run())
