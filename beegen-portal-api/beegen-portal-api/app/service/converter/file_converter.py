import asyncio
import posixpath
import tempfile
import uuid

from beeflow.nodes.base_node import END, INPUT, OUTPUT, START
from beeflow.nodes.flow.branch_node import BranchNode
from beeflow.nodes.primitives.data.mongo_node import MongoNode
from beeflow.nodes.primitives.data.s3_node import S3Node
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beeflow.workflow import WorkflowEngine
from beegen.configs import MongoOperation, S3Operation

from app.service.converter.utils.converter import LibreOfficePdfConverter
from app.utils.db_validation import get_mongo_db


SUPPORTED_EXTENSIONS = {".doc", ".docx", ".xlsm", ".xlsx"}


class ConvertDocumentNotFoundError(Exception):
    pass


class ConvertDocumentPathError(Exception):
    pass


class UnsupportedDocumentFormatError(Exception):
    pass


def validate_document_for_conversion(doc_id: str) -> None:
    document = get_mongo_db()["documents"].find_one(
        {"_id": doc_id, "deleted": {"$ne": True}},
        {"path": 1},
    )
    if not document:
        raise ConvertDocumentNotFoundError("Document not found")

    path = document.get("path")
    if not path:
        raise ConvertDocumentPathError("Document does not have an S3 path")

    extension = posixpath.splitext(str(path))[1].lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise UnsupportedDocumentFormatError(
            f"Unsupported document format: {extension or 'unknown'}"
        )


def convert_document_to_pdf(file_path: str) -> dict:
    try:
        converter = LibreOfficePdfConverter()
        pdf_path = converter.convert_to_pdf(file_path)
        if not pdf_path:
            raise RuntimeError("PDF conversion did not create an output file")

        return {
            "conversion_success": True,
            "converted_pdf_path": str(pdf_path),
            "conversion_error": "",
        }
    except Exception as exc:
        return {
            "conversion_success": False,
            "converted_pdf_path": "",
            "conversion_error": str(exc),
        }


def check_upload_result(status: str | None, message: str | None) -> dict:
    upload_success = str(status).lower() == "success"
    return {
        "upload_success": upload_success,
        "upload_error": "" if upload_success else (message or "PDF upload failed"),
    }


def check_mongo_update_result(
    status: str | None,
    matched_count: int | None,
    message: str | None,
) -> dict:
    persistence_success = (
        str(status).lower() == "success" and matched_count == 1
    )
    return {
        "persistence_success": persistence_success,
        "persistence_error": (
            ""
            if persistence_success
            else (message or "Failed to update documents.pdf_path")
        ),
    }


def build_failure_result(stage: str, error: str) -> dict[str, object]:
    return {
        "conversion_completed": False,
        "failed_stage": stage,
        "failure_message": error or f"{stage} failed",
    }


def build_doc_query(doc_id: str) -> dict:
    return {
        "query": {
            "_id": doc_id,
            "deleted": {"$ne": True},
        }
    }


def extract_doc_info(data: dict) -> dict[str, str]:
    document = data or {}
    doc_id = document.get("_id")
    path = document.get("path")

    if not doc_id:
        raise RuntimeError("Document not found")
    if not path:
        raise RuntimeError(f"Document does not have an S3 path: {doc_id}")

    return {
        "doc_id": str(doc_id),
        "path": str(path),
    }


def build_pdf_s3_key(path: str) -> dict[str, str]:
    directory, file_name = posixpath.split(path)
    base_name, _ = posixpath.splitext(file_name)
    pdf_s3_key = posixpath.join(directory,"pdf_reference", f"{base_name}.pdf")
    return {"pdf_s3_key": pdf_s3_key}


def build_document_pdf_path_update(doc_id: str,pdf_s3_key: str) -> dict:
    return {
        "filter": {"_id": doc_id},
        "update": {"$set": {"pdf_path": pdf_s3_key}},
    }


def build_conversion_result(
    input_doc_id: str,
    input_pdf_s3_key: str,
) -> dict[str, str]:
    return {
        "conversion_completed": True,
        "processed_doc_id": input_doc_id,
        "pdf_s3_key": input_pdf_s3_key,
    }


class FileConverter:
    def __init__(self):
        with WorkflowEngine(
            name="wf_file_converter",
            description="convert a document to PDF and store its PDF S3 path",
            langfuse="beegen-portal",
        ) as wf_file_converter:
            code_build_doc_query = CodeNode(
                name="code_build_doc_query",
                code_fn=build_doc_query,
                inputs={"doc_id": {INPUT: "doc_id"}},
                return_keys=["query: dict"],
            )

            get_document_info = MongoNode(
                name="get_document_info",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.FIND_ONE,
                inputs={
                    "collection_name": "documents",
                    "query": {code_build_doc_query: "query"},
                },
            )

            code_extract_document_info = CodeNode(
                name="code_extract_document_info",
                code_fn=extract_doc_info,
                inputs={"data": {get_document_info: "data"}},
                return_keys=["doc_id: str", "path: str"],
            )

            code_build_pdf_s3_key = CodeNode(
                name="code_build_pdf_s3_key",
                code_fn=build_pdf_s3_key,
                inputs={"path": {code_extract_document_info: "path"}},
                return_keys=["pdf_s3_key: str"],
            )

            download_s3_file = S3Node(
                name="download_s3_file",
                resource_key="ai-nlp-text",
                operation=S3Operation.DOWNLOAD_FILE,
                inputs={
                    "key": {code_extract_document_info: "path"},
                    "local_dir": {INPUT: "temp_dir"},
                    "bucket": "ai-text-raw",
                },
            )

            code_convert_file = CodeNode(
                name="code_convert_file",
                code_fn=convert_document_to_pdf,
                inputs={
                    "file_path": {download_s3_file: "local_file_path"},
                },
                return_keys=[
                    "conversion_success: bool",
                    "converted_pdf_path: str",
                    "conversion_error: str",
                ],
            )

            code_build_conversion_failure = CodeNode(
                name="code_build_conversion_failure",
                code_fn=build_failure_result,
                inputs={
                    "stage": "conversion",
                    "error": {code_convert_file: "conversion_error"},
                },
                return_keys=[
                    "conversion_completed: bool",
                    "failed_stage: str",
                    "failure_message: str",
                ],
                outputs=OUTPUT,
            )

            branch_conversion_success = BranchNode(
                name="branch_conversion_success",
                cases={"conversion_success == True": code_build_pdf_s3_key},
                default=code_build_conversion_failure,
                inputs={"conversion_success": {code_convert_file: "conversion_success"}},
            )

            upload_s3_file = S3Node(
                name="upload_s3_file",
                resource_key="ai-nlp-text",
                operation=S3Operation.UPLOAD_FILE,
                inputs={
                    "key": {code_build_pdf_s3_key: "pdf_s3_key"},
                    "local_file_path": {code_convert_file: "converted_pdf_path"},
                    "bucket": "ai-text-raw",
                    "content_type": "application/pdf",
                },
            )

            code_check_upload_result = CodeNode(
                name="code_check_upload_result",
                code_fn=check_upload_result,
                inputs={
                    "status": {upload_s3_file: "status"},
                    "message": {upload_s3_file: "message"},
                },
                return_keys=["upload_success: bool", "upload_error: str"],
            )

            code_build_upload_failure = CodeNode(
                name="code_build_upload_failure",
                code_fn=build_failure_result,
                inputs={
                    "stage": "upload",
                    "error": {code_check_upload_result: "upload_error"},
                },
                return_keys=[
                    "conversion_completed: bool",
                    "failed_stage: str",
                    "failure_message: str",
                ],
                outputs=OUTPUT,
            )

            code_build_document_pdf_path_update = CodeNode(
                name="code_build_document_pdf_path_update",
                code_fn=build_document_pdf_path_update,
                inputs={
                    "doc_id": {code_extract_document_info: "doc_id"},
                    "pdf_s3_key": {code_build_pdf_s3_key: "pdf_s3_key"},
                },
                return_keys=["filter: dict", "update: dict"],
            )

            update_mongo_pdf_path = MongoNode(
                name="update_mongo_pdf_path",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.UPDATE_ONE,
                inputs={
                    "collection_name": "documents",
                    "filter": {code_build_document_pdf_path_update: "filter"},
                    "update": {code_build_document_pdf_path_update: "update"},
                },
            )

            code_check_mongo_update_result = CodeNode(
                name="code_check_mongo_update_result",
                code_fn=check_mongo_update_result,
                inputs={
                    "status": {update_mongo_pdf_path: "status"},
                    "matched_count": {update_mongo_pdf_path: "matched_count"},
                    "message": {update_mongo_pdf_path: "message"},
                },
                return_keys=[
                    "persistence_success: bool",
                    "persistence_error: str",
                ],
            )

            code_build_persistence_failure = CodeNode(
                name="code_build_persistence_failure",
                code_fn=build_failure_result,
                inputs={
                    "stage": "mongo_update",
                    "error": {code_check_mongo_update_result: "persistence_error"},
                },
                return_keys=[
                    "conversion_completed: bool",
                    "failed_stage: str",
                    "failure_message: str",
                ],
                outputs=OUTPUT,
            )

            code_build_conversion_result = CodeNode(
                name="code_build_conversion_result",
                code_fn=build_conversion_result,
                inputs={
                    "input_doc_id": {code_extract_document_info: "doc_id"},
                    "input_pdf_s3_key": {code_build_pdf_s3_key: "pdf_s3_key"},
                },
                return_keys=[
                    "conversion_completed: bool",
                    "processed_doc_id: str",
                    "pdf_s3_key: str",
                ],
                outputs=OUTPUT,
            )

            branch_upload_success = BranchNode(
                name="branch_upload_success",
                cases={"upload_success == True": code_build_document_pdf_path_update},
                default=code_build_upload_failure,
                inputs={"upload_success": {code_check_upload_result: "upload_success"}},
            )

            branch_persistence_success = BranchNode(
                name="branch_persistence_success",
                cases={
                    "persistence_success == True": code_build_conversion_result
                },
                default=code_build_persistence_failure,
                inputs={"persistence_success": {code_check_mongo_update_result: "persistence_success"}},
            )

            START >> code_build_doc_query >> get_document_info >> code_extract_document_info >> download_s3_file
            download_s3_file >> code_convert_file >> branch_conversion_success >> [
                code_build_pdf_s3_key,
                code_build_conversion_failure,
            ]
            code_build_conversion_failure >> END

            code_build_pdf_s3_key >> upload_s3_file >> code_check_upload_result
            code_check_upload_result >> branch_upload_success >> [
                code_build_document_pdf_path_update,
                code_build_upload_failure,
            ]
            code_build_upload_failure >> END

            code_build_document_pdf_path_update >> update_mongo_pdf_path
            update_mongo_pdf_path >> code_check_mongo_update_result
            code_check_mongo_update_result >> branch_persistence_success >> [
                code_build_conversion_result,
                code_build_persistence_failure,
            ]
            code_build_persistence_failure >> END
            code_build_conversion_result >> END

        wf_file_converter.compile()
        self.file_converter_workflow = wf_file_converter

    async def process(self, doc_id: str) -> dict:
        await asyncio.to_thread(validate_document_for_conversion, doc_id)
        with tempfile.TemporaryDirectory(prefix="file_converter_") as temp_dir:
            result = await self.file_converter_workflow.run(
                request_id=str(uuid.uuid4()),
                inputs={"doc_id": doc_id, "temp_dir": temp_dir},
            )
        if not result.get("conversion_completed"):
            stage = result.get("failed_stage", "workflow")
            message = result.get("failure_message", "Unknown conversion error")
            raise RuntimeError(f"File conversion failed at {stage}: {message}")
        return result
