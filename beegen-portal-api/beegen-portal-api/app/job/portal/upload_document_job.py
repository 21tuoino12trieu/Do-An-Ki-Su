import json
import os
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

from beedoc_v3.engine import BeedocEngine
from beedoc_v3.models.document import Document as BeeDocument
from beeflow.workflow import WorkflowEngine

from beeflow.nodes.primitives.data.mongo_node import MongoNode
from beeflow.nodes.primitives.data.s3_node import S3Node
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beeflow.nodes.flow.for_loop_node import ForLoopNode
from beeflow.nodes.base_node import END, INPUT, START
from beegen.configs import S3Operation

from app.model.document import UploadJobRequest
from app.service.chunk import chunk
from app.service.portal.utils.prepare_document import (
    prepare_mongo_document_data_only,
)
from app.utils.db_validation import get_mongo_db
from app.utils.image_s3 import process_and_replace_s3_images_async


async def _process_document_s3_images(
    reconstructed: str,
    zones: list[dict[str, Any]],
    bot_id: str,
    doc_id: str,
    llm_resource_key: str = "gemini-3.1-flash-lite-chat",
) -> dict[str, Any]:
    clean_reconstructed = await process_and_replace_s3_images_async(
        content=reconstructed,
        bot_id=bot_id,
        document_id=doc_id,
        s3_resource_key="ai-nlp-text",
        mongo_resource_key="aicenter-chatbot",
        llm_resource_key=llm_resource_key,
    )
    clean_zones = []
    for zone in zones or []:
        z_copy = dict(zone)
        if z_copy.get("content"):
            z_copy["content"] = await process_and_replace_s3_images_async(
                content=z_copy["content"],
                bot_id=bot_id,
                document_id=doc_id,
                s3_resource_key="ai-nlp-text",
                mongo_resource_key="aicenter-chatbot",
                llm_resource_key=llm_resource_key,
            )
        clean_zones.append(z_copy)

    return {
        "out_reconstructed": clean_reconstructed,
        "out_zones": clean_zones,
    }


@lru_cache()
def get_beedoc_engine() -> BeedocEngine:
    return BeedocEngine()


async def extract_document_data(
    file_path: str,
    output_format: str = "markdown",
) -> Dict[str, Any]:
    """Pure extraction only — no S3 image upload.

    S3 image upload + src rewriting is a separate step owned by each caller, so
    it never runs twice: in UploadDocumentJob it is the ``code_process_s3_images``
    CodeNode; in the /ingest and /extract_file endpoints it is an explicit call
    to ``process_and_replace_s3_images_async`` right after this returns.
    """
    file_name = Path(file_path).name
    engine = get_beedoc_engine()
    document: BeeDocument = (
        await engine.process_html(file_path)
        if output_format == "html"
        else await engine.process(file_path)
    )
    reconstructed = (
        document.reconstructed_content or "").strip() if document else ""
    zones = []
    if not reconstructed and document:
        for page in document.pages or []:
            sheet_name = page.metadata.get(
                "sheet_name", "") if page.metadata else ""
            for zone in page.content or []:
                if zone and zone.content:
                    zones.append({"content": zone.content,
                                 "sheet_name": sheet_name})

    return {"reconstructed": reconstructed, "zones": zones, "file_name": file_name}


def _build_doc_query(item: str):
    return {"query": {"_id": item, "deleted": {"$ne": True}}}


def _mark_upload_error(doc_id: str):
    db = get_mongo_db()
    db["documents"].update_one(
        {"_id": doc_id},
        {"$set": {"status": "ERROR"}},
    )


def _replace_document_data(
    doc_id: str,
    mongo_document_data: list[dict[str, Any]],
    markdown_content: str = "",
) -> dict[str, str]:
    db = get_mongo_db()
    db["document_data"].delete_many({"document_id": doc_id})
    if mongo_document_data:
        db["document_data"].insert_many(mongo_document_data)

    update_fields = {
        "status": "DONE",
        "is_trained": False,
        "training_status": "NOT_TRAINING",
    }
    if markdown_content:
        update_fields["markdown_content"] = markdown_content

    result = db["documents"].update_one(
        {"_id": doc_id},
        {"$set": update_fields},
    )
    if result.matched_count != 1:
        raise RuntimeError(f"Document not found while completing upload: {doc_id}")
    return {"status": "DONE"}


def _get_upload_status(doc_id: str) -> str | None:
    document = get_mongo_db()["documents"].find_one(
        {"_id": doc_id},
        {"status": 1},
    )
    return document.get("status") if document else None


def _prepare_document_items(document_ids: list[str], bot_id: str):
    return {
        "batch_data": [
            {"document_id": document_id, "bot_id": bot_id}
            for document_id in document_ids
        ]
    }

def _extract_doc_info(data: dict):
    """Unwrap MongoNode find_one result (which wraps in {data: {...}})"""
    doc = data or {}
    return {
        "doc_id": doc.get("_id"),
        "s3_path": doc.get("path"),
    }


class UploadDocumentJob:
    def __init__(self):
        with WorkflowEngine(
            name="wf_upload_document_job",
            description="process document in airflow",
            langfuse="beegen-portal"
        ) as wf_upload_document_job:

            code_build_doc_query = CodeNode(
                name="code_build_doc_query",
                code_fn=_build_doc_query,
                inputs={"item": {INPUT: "id"}},
                return_keys=["query: dict"]
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

            code_extract_doc_info = CodeNode(
                name="code_extract_doc_info",
                code_fn=_extract_doc_info,
                inputs={"data": {get_document_info: "data"}},
                return_keys=[
                    "doc_id: str",
                    "s3_path: str",
                ]
            )

            s3_download_document = S3Node(
                name="s3_download",
                resource_key="ai-nlp-text",
                operation=S3Operation.DOWNLOAD_FILE,
                inputs={
                    "key": {code_extract_doc_info: "s3_path"},
                    "local_dir": tempfile.gettempdir(),
                    "bucket": "ai-text-raw"
                },
            )

            code_extract_document_data = CodeNode(
                name="code_extract_document_data",
                code_fn=extract_document_data,
                inputs={
                    "file_path": {s3_download_document: "local_file_path"},
                },
                return_keys=[
                    "reconstructed: str",
                    "zones: List[Dict[str, Any]]",
                    "file_name: str",
                ],
            )

            code_process_s3_images = CodeNode(
                name="code_process_s3_images",
                code_fn=_process_document_s3_images,
                inputs={
                    "reconstructed": {code_extract_document_data: "reconstructed"},
                    "zones": {code_extract_document_data: "zones"},
                    "bot_id": {INPUT: "bot_id"},
                    "doc_id": {code_extract_doc_info: "doc_id"},
                },
                return_keys=[
                    "out_reconstructed: str",
                    "out_zones: list",
                ],
            )

            code_chunking = CodeNode(
                name="code_chunking",
                code_fn=chunk,
                inputs={
                    "reconstructed": {code_process_s3_images: "out_reconstructed"},
                    "zones": {code_process_s3_images: "out_zones"},
                    "file_name": {code_extract_document_data: "file_name"},
                    "chunk_type": "hierarchical",
                    "extract_keywords": False,
                },
                return_keys=[
                    "chunks: list"
                ]
            )

            code_prepare_mongo_data = CodeNode(
                name="code_prepare_mongo_data",
                code_fn=prepare_mongo_document_data_only,
                inputs={
                    "doc_id": {code_extract_doc_info: "doc_id"},
                    "bot_id": {INPUT: "bot_id"},
                    "chunks": {code_chunking: "chunks"}
                },
                return_keys=[
                    "mongo_document_data: list"
                ]
            )

            code_replace_document_data = CodeNode(
                name="code_replace_document_data",
                code_fn=_replace_document_data,
                inputs={
                    "doc_id": {code_extract_doc_info: "doc_id"},
                    "mongo_document_data": {
                        code_prepare_mongo_data: "mongo_document_data"
                    },
                    "markdown_content": {code_process_s3_images: "out_reconstructed"},
                },
                return_keys=["status: str"],
            )

            START >> code_build_doc_query >> get_document_info >> code_extract_doc_info
            code_extract_doc_info >> s3_download_document
            s3_download_document >> code_extract_document_data >> code_process_s3_images >> code_chunking >> code_prepare_mongo_data
            [code_extract_doc_info, code_prepare_mongo_data] >> code_replace_document_data >> END

        wf_upload_document_job.compile()
        self.wf_upload_document_job = wf_upload_document_job
        self._build_documents_workflow()

    def _build_documents_workflow(self) -> None:
        with WorkflowEngine(
            name="wf_upload_documents_job",
            description="process upload documents concurrently in one pod",
            langfuse="beegen-portal",
        ) as workflow:
            prepare_documents = CodeNode(
                name="code_prepare_upload_documents",
                code_fn=_prepare_document_items,
                inputs={"document_ids": {INPUT: "document_ids"}, "bot_id": {INPUT: "bot_id"}},
                return_keys=["batch_data: list"],
            )

            with ForLoopNode(
                name="loop_upload_documents",
                max_concurrency=8,
                inputs={"batch_data": {prepare_documents: "batch_data"}},
            ) as loop_documents:
                process_document = CodeNode(
                    name="code_process_upload_document",
                    code_fn=self._process_document_item,
                    inputs={"document_id": {INPUT: "document_id"}, "bot_id": {INPUT: "bot_id"}},
                    return_keys=[
                        "processed_document_id: str",
                        "status: str",
                        "error: str",
                    ],
                )
                START >> process_document >> END

            START >> prepare_documents >> loop_documents >> END

        workflow.compile()
        self.wf_upload_documents_job = workflow

    async def _process_document_item(self,document_id: str,bot_id: str) -> dict:
        try:
            await self.process(UploadJobRequest(bot_id=bot_id,type="document",id=document_id))
            return {
                "processed_document_id": document_id,
                "status": "DONE",
                "error": "",
            }
        except Exception as exc:
            try:
                _mark_upload_error(document_id)
            except Exception:
                pass
            return {
                "processed_document_id": document_id,
                "status": "ERROR",
                "error": str(exc),
            }

    async def process(
        self, document: UploadJobRequest, **kwargs
    ):
        try:
            import uuid
            request_id = str(uuid.uuid4())
            result = await self.wf_upload_document_job.run(
                request_id=request_id,
                inputs={
                    "bot_id": document.bot_id,
                    "id": document.id
                }
            )
            if _get_upload_status(document.id) != "DONE":
                raise RuntimeError("Document upload workflow did not complete")
            return result
        except Exception as e:
            try:
                _mark_upload_error(document.id)
            except Exception:
                pass
            raise RuntimeError(f"Process document failed: {str(e)}") from e

    async def process_documents(
        self,
        bot_id: str,
        document_ids: list[str],
    ) -> dict:
        import uuid

        return await self.wf_upload_documents_job.run(
            request_id=str(uuid.uuid4()),
            inputs={"bot_id": bot_id, "document_ids": document_ids},
        )

if __name__ == "__main__":
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Test UploadDocumentJob")
    parser.add_argument("--bot_id", type=str, required=True, help="Bot ID")
    parser.add_argument("--document_ids", type=str, required=True, help="Array of document IDS")
    args = parser.parse_args()
    async def _run():
        job = UploadDocumentJob()
        document_ids = json.loads(args.document_ids)
        await job.process_documents(
            bot_id=args.bot_id,
            document_ids=document_ids
        )
        await asyncio.sleep(3)

    asyncio.run(_run())
