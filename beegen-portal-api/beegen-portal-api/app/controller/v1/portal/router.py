import tempfile
from pathlib import Path
# Only used by the /extract_file endpoint below.
from typing import Literal

from beedoc_v3.core.exceptions import UnsupportedFormatError
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.model.document import (
    CleanDataRequest,
    ConvertFormatRequest,
    RevertDataRequest,
    TrainRequest,
    UpdateChunkRequest,
    UploadRequest,
    CreateBotRequest,
    DeleteBotRequest,
)

# Document-ingestion (Vertex) admin screen only.
from app.job.portal.upload_document_job import extract_document_data
from app.utils.image_s3 import process_and_replace_s3_images_async
from app.service.portal import (
    process_document_service,
    process_qna_service,
    process_bot_service,
)
from app.service.converter import file_converter_service
from app.service.converter.file_converter import (
    ConvertDocumentNotFoundError,
    ConvertDocumentPathError,
    UnsupportedDocumentFormatError,
)
from app.exception.portal import success_response
from app.utils.enums import DocumentType

router = APIRouter()


@router.post(
    "/upload",
    summary="Upload data for training",
    description="Trigger an Airflow DAG to download raw files from S3, extract layout/text/images, and prepare Mongo documents for the given bot.",
)
async def upload_document(
    body: UploadRequest
) -> dict:
    if body.type == DocumentType.DOCUMENT:
        result = await process_document_service.upload(body)
        message = "Upload completed"
    elif body.type == DocumentType.QA:
        result = await process_qna_service.upload(body)
        message = "Upload request accepted"
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid document type",
        )
    return success_response(result, message)


# Document-ingestion (Vertex) admin screen only.
@router.post(
    "/extract_file",
    summary="Extract a document file",
    description=(
        "Upload a PDF, DOCX, or Excel file and synchronously extract its layout/text/images "
        "into reconstructed Markdown (default) or HTML using the Beedoc engine. When "
        "output_format=html and both botId and documentId are given, images found in the "
        "extracted HTML are also uploaded to S3 and their <img> src rewritten to the resulting "
        "portal URL (same image pipeline as /document-ingestion/ingest)."
    ),
)
async def extract_file(
    file: UploadFile = File(...),
    output_format: Literal["markdown", "html"] = "markdown",
    botId: str | None = Form(default=None),
    documentId: str | None = Form(default=None),
) -> dict:
    suffix = Path(file.filename or "").suffix
    tmp_dir = Path(tempfile.gettempdir())
    with tempfile.NamedTemporaryFile(delete=False, dir=tmp_dir, suffix=suffix) as tmp_file:
        content = await file.read()
        tmp_file.write(content)
        temp_path = tmp_file.name

    try:
        result = await extract_document_data(
            temp_path,
            output_format=output_format,
        )
        # Separate S3 image-upload step (was previously fused inside
        # extract_document_data). Only run for HTML output when both botId and
        # documentId are supplied — same condition as the old process_images flag.
        if output_format == "html" and botId and documentId and result.get("reconstructed"):
            result["reconstructed"] = await process_and_replace_s3_images_async(
                content=result["reconstructed"],
                bot_id=botId,
                document_id=documentId,
            )
        result["file_name"] = Path(file.filename or "").name
    except UnsupportedFormatError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file format: {exc}",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Extract file failed: {exc}",
        ) from exc
    finally:
        # missing_ok: a raise in `finally` would replace whatever exception the
        # body was already propagating, turning a real extraction error into a
        # misleading FileNotFoundError.
        Path(temp_path).unlink(missing_ok=True)

    return success_response(result, "Extract completed")


@router.post(
    "/train",
    summary="Train and embed data",
    description="Trigger an Airflow DAG to chunk document data, embed it, build hierarchical trees (for documents), and push to Milvus collections for the given bot.",
)
async def update_document(
    body: TrainRequest
) -> dict:
    if body.type == DocumentType.DOCUMENT:
        result = await process_document_service.train(body)
        message = "Train completed"
    elif body.type == DocumentType.QA:
        result = await process_qna_service.train(body)
        message = "Train request accepted"
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid document type",
        )
    return success_response(result, message)


@router.post(
    "/update_chunk",
    summary="Update a specific chunk",
    description="Manually update the content of a chunk. (Not implemented)",
)
async def update_chunk(
    request: UpdateChunkRequest
):
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Update chunk is not implemented",
    )


@router.post(
    "/revert",
    summary="Revert data version",
    description="Revert a document or bot data to a previous state. (Not implemented)",
)
async def revert(
    request: RevertDataRequest
):
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Revert data is not implemented",
    )


@router.post(
    "/convert",
    summary="Convert file format",
    description="Convert a DOC, DOCX, XLSM, or XLSX document to PDF.",
)
async def convert(
    request: ConvertFormatRequest
) -> dict:
    try:
        result = await file_converter_service.process(request.doc_id)
        return success_response(result, "Convert completed")
    except ConvertDocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except (ConvertDocumentPathError, UnsupportedDocumentFormatError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Convert document failed: {exc}",
        ) from exc


@router.post(
    "/clean",
    summary="Clean deleted data",
    description="Hard delete all chunks, nodes, and parent data for a document or QnA dialogue that has been marked as deleted.",
)
async def clean(
    body: CleanDataRequest
) -> dict:
    if body.type == DocumentType.DOCUMENT:
        result = await process_document_service.clean(body)
    elif body.type == DocumentType.QA:
        result = await process_qna_service.clean(body)
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid document type",
        )
    return success_response(result, "Clean request accepted")


@router.post(
    "/create_bot",
    summary="Create a new bot",
    description="Initialize Milvus collections (chunk and node) for a newly created bot.",
)
async def create_bot(
    body: CreateBotRequest
) -> dict:
    result = await process_bot_service.create_bot(bot_id=body.bot_id)
    return success_response(result, "Create bot request accepted")


@router.post(
    "/delete_bot",
    summary="Delete bot data completely",
    description="Delete all Mongo document and dialogue data for a bot, and clear its Milvus collections.",
)
async def delete_bot(
    body: DeleteBotRequest
) -> dict:
    result = await process_bot_service.delete_bot(bot_id=body.bot_id)
    return success_response(result, "Delete bot request accepted")

