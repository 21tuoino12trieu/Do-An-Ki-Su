import asyncio
import io
import logging
import os
import tempfile
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Body, Form, HTTPException, status
from fastapi.responses import JSONResponse, Response
from google.api_core.exceptions import NotFound

from app.job.portal.upload_document_job import extract_document_data
from app.utils.db_validation import get_mongo_db
from app.utils.image_s3 import process_and_replace_s3_images_async
from app.utils.gcs_client import (
    delete_blob_from_gcs,
    parse_gcs_uri,
    upload_stream_to_gcs,
)
from app.utils.s3_client import delete_html, download_html, download_to_file, parse_s3_key, upload_html
from app.utils.vertex_search_client import (
    delete_document,
    get_chunked_document,
    poll_batch_import,
    read_batch_error_log,
    read_batch_error_log_raw,
    trigger_batch_index,
    trigger_document_index,
)

logger = logging.getLogger(__name__)

router = APIRouter()
SYSTEM_AUDIT_USER = "SYSTEM"


def _audit_set(fields: dict, actor: str) -> dict:
    return {
        **fields,
        "updated_at": datetime.now(timezone.utc),
        "updated_by": actor,
    }

# Caps how many files are extracted CONCURRENTLY in this process.
#
# Why: /ingest returns 202 immediately and extracts in the background, so the
# caller (beegen-portal-be) is never blocked — it keeps firing requests. Without
# a cap, hundreds of files would render pages -> images -> call the VLM at once,
# exhausting RAM until Beedoc returns empty HTML => the record is marked FAILED
# with "content unreadable" even though the input file was perfectly fine.
#
# The semaphore makes over-limit requests QUEUE for their turn instead of
# competing. Tunable via env DOCUMENT_EXTRACT_MAX_CONCURRENCY (default 2).
_EXTRACT_MAX_CONCURRENCY = int(os.getenv("DOCUMENT_EXTRACT_MAX_CONCURRENCY", "2"))
_extract_semaphore = asyncio.Semaphore(_EXTRACT_MAX_CONCURRENCY)


async def _extract_document_in_background(documentId: str, botId: str, s3Key: str, userId: str) -> None:
    """Runs after the HTTP response has already been sent — the caller (the
    BeegenPortalApiClient Feign client in beegen-portal-be) does not wait for
    this to finish, so there's no Feign readTimeout to blow through no matter
    how long the VLM-based extraction takes for a large file.

    The source file is NOT transferred over HTTP: the caller uploads it to S3
    (ai-text-raw) itself and only sends the object key. This task acquires
    ``_extract_semaphore`` FIRST and only then downloads the file to a temp
    path, so queued documents cost no RAM/disk while waiting for their turn.
    The source object under HTML/{stem}_{documentId}.{ext} is intentionally
    kept — beegen-portal-be references it via documentPath for re-extraction.
    """
    db = get_mongo_db()
    key = parse_s3_key(s3Key)
    temp_path = None
    try:
        async with _extract_semaphore:
            # Only now is the document actually being extracted (as opposed to
            # queued behind the semaphore) — flip to PROCESSING here so a
            # PROCESSING record always means "really running", never "just
            # waiting its turn". See ingest_document below for the queued state.
            db["document_ingestion"].update_one(
                {"_id": documentId},
                {"$set": _audit_set({"status": "PROCESSING"}, userId)},
            )
            suffix = Path(key).suffix or ".bin"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                temp_path = tmp_file.name
            await download_to_file(key, temp_path)
            result = await extract_document_data(
                temp_path,
                output_format="html",
            )
        html_content = result["reconstructed"]

        # extract_document_data already .strip()s the result (upload_document_job.py),
        # so an empty string means Beedoc read nothing from the file — some input
        # files are corrupt and cannot be parsed. This used to be set to EXTRACTED,
        # leaving the user with a blank page and no idea it had failed.
        if not html_content:
            db["document_ingestion"].update_one(
                {"_id": documentId},
                {"$set": _audit_set({
                    "status": "FAILED",
                    "error_message": "Không đọc được nội dung từ file (kết quả trích xuất rỗng)",
                }, userId)},
            )
            return

        # Separate S3 image-upload step (was previously fused inside
        # extract_document_data). /ingest always has botId + documentId, so it
        # always uploads — but gating on html_content avoids a pointless call on
        # an already-empty body.
        html_content = await process_and_replace_s3_images_async(
            content=html_content,
            bot_id=botId,
            document_id=documentId,
        )

        s3_uri = await upload_html(documentId, html_content)
        db["document_ingestion"].update_one(
            {"_id": documentId},
            {"$set": _audit_set({
                "status": "EXTRACTED",
                "html_s3_path": s3_uri,
            }, userId)},
        )
    except Exception as exc:
        logger.error(
            "ingest_document background extraction failed for documentId=%s botId=%s key=%s: %s\n%s",
            documentId, botId, key, exc, traceback.format_exc(),
        )
        db["document_ingestion"].update_one(
            {"_id": documentId},
            {"$set": _audit_set({
                "status": "FAILED",
                "error_message": f"Không thể tải/xử lý file từ S3: {exc}",
            }, userId)},
        )
    finally:
        # missing_ok: this runs in a background task, where an unhandled
        # exception is only visible as a stray traceback and would mask the
        # extraction outcome already recorded above. A temp file that is
        # already gone means the cleanup it exists for has happened anyway.
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)


@router.post(
    "/document-ingestion/ingest",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Extract a document to HTML for user review (Phase 1)",
    description=(
        "Receives the S3 key of the already-uploaded source file and immediately "
        "returns 202, then extracts it to HTML via the Beedoc engine in the "
        "background — the caller does NOT wait for extraction to finish, so "
        "large/slow files never trip the Feign client's read timeout, and the "
        "file bytes themselves never cross this HTTP boundary. The "
        "document_ingestion record stays at its current status (queued state, "
        "set by the caller) until this process actually acquires the extraction "
        "semaphore, at which point it moves to PROCESSING, then to EXTRACTED (or "
        "FAILED) once the background extraction completes; an "
        "empty extraction result counts as FAILED, not EXTRACTED. The HTML "
        "itself is stored on S3 under HTML_EXTRACTED/, with only its s3:// URI "
        "kept in Mongo. Does NOT upload to GCS — the user reviews/edits the "
        "extracted HTML first (see the /html GET+PUT endpoints below), then "
        "explicitly triggers /upload-gcs when satisfied."
    ),
)
async def ingest_document(
    background_tasks: BackgroundTasks,
    botId: str = Form(...),
    documentId: str = Form(...),
    s3Key: str = Form(...),
    userId: str = Form(...),
) -> JSONResponse:
    s3Key = parse_s3_key(s3Key)
    if not s3Key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="s3Key must not be empty")

    db = get_mongo_db()
    # Do NOT flip to PROCESSING here: the task below still has to wait its turn
    # behind _extract_semaphore, so setting PROCESSING now would mark a merely
    # QUEUED record as "actually running" — indistinguishable from a document
    # genuinely mid-extraction if this process later dies (e.g. OOM), leaving
    # queued-only records stuck at PROCESSING forever. The record keeps
    # whatever status the caller (beegen-portal-be) set before calling this
    # endpoint; _extract_document_in_background flips it to PROCESSING itself,
    # right after acquiring the semaphore.
    db["document_ingestion"].update_one(
        {"_id": documentId},
        {"$set": _audit_set({
            # Keep the source key for debugging/retry.
            "source_s3_key": s3Key,
        }, userId)},
    )
    background_tasks.add_task(_extract_document_in_background, documentId, botId, s3Key, userId)

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={"documentId": documentId, "status": "PENDING"},
    )


@router.get(
    "/document-ingestion/{documentId}/html",
    summary="Get a document's extracted HTML content for review/editing",
)
async def get_extracted_html(documentId: str) -> dict:
    db = get_mongo_db()
    doc = db["document_ingestion"].find_one({"_id": documentId})
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Contract is unchanged (still returns htmlContent) — moving storage from
    # Mongo to S3 is internal; neither the FE nor beegen-portal-be needs changes.
    html_content = ""
    if doc.get("html_s3_path"):
        html_content = await download_html(documentId)

    return {
        "documentId": documentId,
        "status": doc.get("status"),
        "htmlContent": html_content,
    }


@router.put(
    "/document-ingestion/{documentId}/html",
    summary="Save the user-edited HTML content for a document",
)
async def update_extracted_html(documentId: str, htmlContent: str = Body(..., embed=True)) -> dict:
    db = get_mongo_db()
    doc = db["document_ingestion"].find_one({"_id": documentId}, {"_id": 1})
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Overwrite the S3 object; html_s3_path is re-set in case an old (migrated)
    # record doesn't have the field yet.
    s3_uri = await upload_html(documentId, htmlContent)
    db["document_ingestion"].update_one(
        {"_id": documentId},
        {"$set": _audit_set({"html_s3_path": s3_uri}, SYSTEM_AUDIT_USER)},
    )
    return {"documentId": documentId, "status": "EXTRACTED"}


@router.post(
    "/document-ingestion/{documentId}/upload-gcs",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a document's reviewed HTML content to GCS",
    description=(
        "Streams the document's reviewed/edited HTML from S3 (html_s3_path) up "
        "to GCS under {GCS_DOCUMENT_INGESTION_PREFIX}/{fileName}_{documentId}.html "
        "(prefix defaults to 'documents'), then records the "
        "resulting gs:// URI and moves the record to UPLOADED. Requires the "
        "document to already have extracted HTML on S3. Does NOT index into "
        "Vertex — /document-ingestion/sync-vertex does that for a whole batch."
    ),
)
async def upload_extracted_html_to_gcs(documentId: str) -> JSONResponse:
    db = get_mongo_db()
    doc = db["document_ingestion"].find_one({"_id": documentId})
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    if not doc.get("html_s3_path"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document has no extracted HTML content to upload",
        )

    file_stem = Path(doc.get("document_name") or documentId).stem
    try:
        html_content = await download_html(documentId)
        # Streaming: blob.upload_from_file() reads in chunks instead of holding
        # the whole payload (~10MB for large files) as one bytes object in RAM.
        gcs_uri = upload_stream_to_gcs(
            blob_path=f"{os.environ.get('GCS_DOCUMENT_INGESTION_PREFIX', 'documents')}/{file_stem}_{documentId}.html",
            stream=io.BytesIO(html_content.encode("utf-8")),
            content_type="text/html; charset=utf-8",
        )
        # Only mark it as uploaded to GCS and stop here — pushing into Vertex is
        # done by /sync-vertex, which handles the whole batch at once.
        db["document_ingestion"].update_one(
            {"_id": documentId},
            {"$set": _audit_set({"status": "UPLOADED", "gcs_uri": gcs_uri}, SYSTEM_AUDIT_USER)},
        )
    except Exception as exc:
        logger.error(
            "upload_extracted_html_to_gcs failed for documentId=%s: %s\n%s",
            documentId, exc, traceback.format_exc(),
        )
        db["document_ingestion"].update_one(
            {"_id": documentId},
            {"$set": _audit_set({
                "status": "FAILED",
                "error_message": f"Không thể upload HTML lên GCS: {exc}",
            }, SYSTEM_AUDIT_USER)},
        )
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"documentId": documentId, "gcs_uri": None, "status": "FAILED"},
        )

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={"documentId": documentId, "gcs_uri": gcs_uri, "status": "UPLOADED"},
    )


def _apply_import_result(
    result, document_ids: list[str], operation_name: str, error_log_prefix: str = "",
) -> dict:
    """Settles the records covered by an ImportDocuments operation into their
    final status, based on a SINGLE poll result.

    Used by the manual /check-sync endpoint. Does NOT loop — if the operation
    is still running, the records stay INDEXING and the caller is expected to
    check again later.

    Returns a summary dict for the caller to return to the UI.
    """
    db = get_mongo_db()

    if not result.done:
        logger.info(
            "check_sync: operation=%s still running, %d document(s) remain INDEXING",
            operation_name, len(document_ids),
        )
        return {
            "done": False,
            "successCount": 0,
            "failureCount": 0,
            "errorMessage": "",
            "errorLogPrefix": "",
            "errorDetails": [],
            "affectedDocumentIds": [],
        }

    if result.failure_count:
        # Import is per-document, so a partial failure leaves some documents
        # genuinely indexed. error_samples on the operation response is only a
        # PARTIAL sample, so the whole batch is marked FAILED and re-synced
        # rather than trusting an incomplete list and leaving some document
        # silently unsearchable under an INDEXED status. Re-importing an
        # already-indexed document is harmless (INCREMENTAL reconciliation
        # overwrites by id).
        #
        # error_log_prefix (ImportErrorConfig.gcs_prefix, set at submit time —
        # see trigger_batch_index) holds the FULL per-document failure list, one
        # google.rpc.Status per line, which is what an operator actually needs
        # to tell true failures from collateral ones before calling
        # /resolve-batch-failure. Reading it here is best-effort: a failure to
        # fetch it must not block settling the batch to FAILED, since the
        # counts/records themselves are already known from `result`.
        error_details: list[str] = []
        if error_log_prefix:
            try:
                error_details = read_batch_error_log(error_log_prefix)
            except Exception as exc:
                logger.error(
                    "check_sync: failed to read error log at %s: %s\n%s",
                    error_log_prefix, exc, traceback.format_exc(),
                )

        logger.error(
            "check_sync: operation=%s imported %d document(s), %d failed. "
            "Error samples: %s. Full error log: %s. Error log prefix: %s. Batch document ids: %s",
            operation_name, result.success_count, result.failure_count,
            result.error_message or "(none reported)", error_details or "(unavailable)",
            error_log_prefix or "(none)", document_ids,
        )
        error_message = (
            f"Lô đồng bộ Vertex có {result.failure_count}/"
            f"{result.failure_count + result.success_count} tài liệu bị từ chối, "
            f"cần đồng bộ lại cả lô. Chi tiết: "
            f"{result.error_message or 'không có thông tin lỗi chi tiết'}"
        )
        db["document_ingestion"].update_many(
            {"_id": {"$in": document_ids}},
            {"$set": _audit_set({"status": "FAILED", "error_message": error_message}, SYSTEM_AUDIT_USER)},
        )
        return {
            "done": True,
            "successCount": result.success_count,
            "failureCount": result.failure_count,
            "errorMessage": error_message,
            "errorLogPrefix": error_log_prefix,
            "errorDetails": error_details,
            "affectedDocumentIds": document_ids,
        }

    logger.info(
        "check_sync: operation=%s indexed %d document(s)",
        operation_name, result.success_count,
    )
    db["document_ingestion"].update_many(
        {"_id": {"$in": document_ids}},
        {"$set": _audit_set({"status": "INDEXED"}, SYSTEM_AUDIT_USER), "$unset": {"error_message": ""}},
    )
    return {
        "done": True,
        "successCount": result.success_count,
        "failureCount": 0,
        "errorMessage": "",
        "errorLogPrefix": "",
        "errorDetails": [],
        "affectedDocumentIds": document_ids,
    }


@router.post(
    "/document-ingestion/sync-vertex",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Batch-import uploaded documents into Vertex AI Search",
    description=(
        "Collects document_ingestion records that are UPLOADED (i.e. their "
        "HTML is on GCS) but not yet indexed, builds ONE metadata JSONL "
        "containing a line per document, and imports the whole batch with a "
        "single ImportDocuments call — instead of one JSONL file plus one "
        "long-running operation per document. Scope is every UPLOADED record "
        "of the bot by default, or exactly the records named in documentIds "
        "when that body field is given.\n\n"
        "Claimed records move to INDEXING immediately, which both reserves them "
        "against a concurrent sync and reflects that Discovery Engine has only "
        "ACCEPTED the import at this point. This endpoint does NOT poll for the "
        "operation result — use POST /document-ingestion/check-sync to settle "
        "INDEXING records to INDEXED/FAILED on demand. Returns 200 with an empty "
        "list when there is nothing waiting."
    ),
)
async def sync_documents_to_vertex(
    botId: str | None = None,
    documentIds: list[str] | None = Body(default=None, embed=True),
) -> JSONResponse:
    db = get_mongo_db()
    # FAILED is retryable here, not just UPLOADED: a batch whose import was
    # rejected is marked FAILED as a whole (see _apply_import_result), so without
    # this those records could never be re-synced — nothing else moves them back
    # to UPLOADED. Requiring a gcs_uri keeps that from picking up documents that
    # failed earlier in the flow, before they ever reached GCS.
    query: dict = {"status": {"$in": ["UPLOADED", "FAILED"]}, "gcs_uri": {"$nin": [None, ""]}}
    if botId:
        query["bot_id"] = botId
    # Take only the records the user ticked; still keep the UPLOADED + has-gcs_uri
    # conditions so records that aren't ready never reach the Data Store.
    if documentIds:
        query["_id"] = {"$in": documentIds}

    # Remember each record's status before claiming it, so a failed submit can
    # put it back exactly as it was instead of promoting a FAILED record to
    # UPLOADED (or vice versa).
    previous_status = {
        doc["_id"]: doc["status"]
        for doc in db["document_ingestion"].find(query, {"status": 1})
    }
    if not previous_status:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"batchSize": 0, "documentIds": [], "metadataUri": None},
        )

    # Claim the batch by flipping the eligible records to INDEXING before
    # reading them back. Doing it in this order means two concurrent syncs
    # cannot pick up the same records: the second one's update matches nothing,
    # because the filter still requires UPLOADED/FAILED.
    claim_id = str(uuid.uuid4())
    claimed = db["document_ingestion"].update_many(
        query,
        {"$set": _audit_set({"status": "INDEXING", "vertex_index_claim": claim_id}, SYSTEM_AUDIT_USER)},
    )
    if not claimed.modified_count:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"batchSize": 0, "documentIds": [], "metadataUri": None},
        )

    pending = list(db["document_ingestion"].find({"vertex_index_claim": claim_id}))

    def _release(document_ids: list[str]) -> None:
        """Hands claimed records back to the status they had before the claim,
        so a later sync can pick them up again."""
        for document_id in document_ids:
            db["document_ingestion"].update_one(
                {"_id": document_id},
                {
                    "$set": _audit_set({"status": previous_status.get(document_id, "UPLOADED")}, SYSTEM_AUDIT_USER),
                    "$unset": {"vertex_index_claim": ""},
                },
            )

    try:
        submission = trigger_batch_index(pending)
    except Exception as exc:
        logger.error(
            "sync_documents_to_vertex failed for %d document(s): %s\n%s",
            len(pending), exc, traceback.format_exc(),
        )
        _release([doc["_id"] for doc in pending])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Không thể đồng bộ lô tài liệu lên Vertex: {exc}",
        ) from exc

    # Records whose gcs_uri vanished between the claim and the build were
    # skipped by trigger_batch_index — hand those back rather than leaving them
    # stuck in INDEXING under an operation that never covered them.
    skipped = [doc["_id"] for doc in pending if doc["_id"] not in set(submission.document_ids)]
    if skipped:
        logger.warning(
            "sync_documents_to_vertex: %d claimed document(s) had no gcs_uri and "
            "were not imported", len(skipped),
        )
        _release(skipped)

    db["document_ingestion"].update_many(
        {"_id": {"$in": submission.document_ids}},
        {
            "$set": _audit_set({
                "vertex_operation_name": submission.operation_name,
                "vertex_error_log_prefix": submission.error_log_prefix,
            }, SYSTEM_AUDIT_USER),
            "$unset": {"vertex_index_claim": ""},
        },
    )

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "batchSize": len(submission.document_ids),
            "documentIds": submission.document_ids,
            "metadataUri": submission.metadata_uri,
            "errorLogPrefix": submission.error_log_prefix,
        },
    )


@router.post(
    "/document-ingestion/check-sync",
    summary="Manually check and settle the latest Vertex sync operation for a bot",
    description=(
        "Finds the most recent ImportDocuments operation submitted for this bot "
        "(by reading vertex_operation_name off its INDEXING records), polls it "
        "ONCE, and settles those records to INDEXED (all good), FAILED (batch "
        "rejected), or leaves them INDEXING (operation still running). Returns a "
        "summary the UI can show. Does not loop — call again later if not done. "
        "Returns 200 with batchSize=0 when there is nothing INDEXING to check."
    ),
)
async def check_sync(botId: str = Body(..., embed=True)) -> JSONResponse:
    db = get_mongo_db()

    # The most recent operation submitted for this bot is the one its still-
    # INDEXING records point at. A bot can only have one outstanding sync at a
    # time because /sync-vertex claims records by flipping them to INDEXING, so
    # no later sync can pick them up until they settle — but the operation_name
    # is read off the records rather than tracked separately, which stays
    # correct even if an older operation is still around from a previous batch.
    pending = list(db["document_ingestion"].find(
        {"bot_id": botId, "status": "INDEXING", "vertex_operation_name": {"$nin": [None, ""]}},
        {"vertex_operation_name": 1, "vertex_error_log_prefix": 1},
    ))
    if not pending:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "operationName": None,
                "done": True,
                "batchSize": 0,
                "successCount": 0,
                "failureCount": 0,
                "errorMessage": "",
                "errorLogPrefix": "",
                "errorDetails": [],
                "affectedDocumentIds": [],
            },
        )

    # All INDEXING records of one sync share the same operation_name (see
    # /sync-vertex); group them so a single poll covers the whole batch and the
    # settlement write touches exactly the records this operation owns.
    operation_name = pending[0]["vertex_operation_name"]
    error_log_prefix = pending[0].get("vertex_error_log_prefix") or ""
    document_ids = [
        doc["_id"]
        for doc in pending
        if doc["vertex_operation_name"] == operation_name
    ]

    try:
        result = await asyncio.to_thread(poll_batch_import, operation_name)
    except Exception as exc:
        # A poll failure (transient network, operation gone) does NOT settle the
        # records: the import itself may well have succeeded, and the operation
        # name stays on the record to retry later.
        logger.error(
            "check_sync: polling operation=%s failed: %s\n%s",
            operation_name, exc, traceback.format_exc(),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Không thể kiểm tra trạng thái operation Vertex: {exc}",
        ) from exc

    summary = _apply_import_result(result, document_ids, operation_name, error_log_prefix)
    summary["operationName"] = operation_name
    summary["batchSize"] = len(document_ids)
    return JSONResponse(status_code=status.HTTP_200_OK, content=summary)


@router.get(
    "/document-ingestion/check-sync/error-log",
    summary="Download a batch's full per-document error log from GCS",
    description=(
        "Fetches the ImportErrorConfig.gcs_prefix output for the given "
        "operationName (recorded on the batch's records as "
        "vertex_error_log_prefix — see /sync-vertex and /check-sync) and "
        "streams it back exactly as Discovery Engine wrote it: every shard "
        "concatenated, one JSON-encoded google.rpc.Status object per line. "
        "For a caller to identify which documents actually failed (the code/"
        "message describing each) before calling /resolve-batch-failure, "
        "since the check-sync response's error_message is a summary, not the "
        "full per-document list. Returns 404 if no error log was ever "
        "recorded for this operationName (e.g. the batch had 0 failures)."
    ),
)
async def download_batch_error_log(operationName: str) -> Response:
    db = get_mongo_db()
    doc = db["document_ingestion"].find_one(
        {"vertex_operation_name": operationName, "vertex_error_log_prefix": {"$nin": [None, ""]}},
        {"vertex_error_log_prefix": 1},
    )
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No error log recorded for this operationName",
        )

    error_log_prefix = doc["vertex_error_log_prefix"]
    try:
        content = await asyncio.to_thread(read_batch_error_log_raw, error_log_prefix)
    except Exception as exc:
        logger.error(
            "download_batch_error_log: failed to read %s: %s\n%s",
            error_log_prefix, exc, traceback.format_exc(),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Không thể đọc log lỗi từ GCS: {exc}",
        ) from exc

    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Error log is empty — the batch may have had 0 failures or isn't done yet",
        )

    file_name = operationName.rsplit("/", 1)[-1] + "-errors.jsonl"
    return Response(
        content=content,
        media_type="application/jsonl",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.post(
    "/document-ingestion/resolve-batch-failure",
    summary="Split a batch that check-sync marked FAILED, after confirming the real failures from the GCS error log",
    description=(
        "check-sync marks an ENTIRE batch FAILED whenever Discovery Engine "
        "reports any failure_count, because error_samples is only a partial "
        "sample and there's no reliable way to tell which documents actually "
        "failed from the API response alone — see _apply_import_result. That "
        "protects against silently leaving a genuinely-failed document as "
        "INDEXED, but it also means e.g. 990 documents that really did index "
        "sit under FAILED alongside the 10 that didn't.\n\n"
        "This endpoint lets an admin correct that once they've confirmed the "
        "true failures by reading the detailed per-document error log (see "
        "ImportErrorConfig.gcs_prefix) instead of trusting error_samples: pass "
        "the operationName plus the documentIds CONFIRMED to have actually "
        "failed. Every other document that shares that operationName and is "
        "currently FAILED is moved to INDEXED; the confirmed ones stay/become "
        "FAILED with the given reason. Only touches records still on this "
        "operationName, so a document already re-synced under a newer "
        "operation is left alone."
    ),
)
async def resolve_batch_failure(
    operationName: str = Body(..., embed=True),
    failedDocumentIds: list[str] = Body(..., embed=True),
    failureReason: str = Body(default="", embed=True),
) -> JSONResponse:
    db = get_mongo_db()

    batch_docs = list(db["document_ingestion"].find(
        {"vertex_operation_name": operationName, "status": "FAILED"},
        {"_id": 1},
    ))
    if not batch_docs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No FAILED document found for this operationName",
        )

    batch_ids = {doc["_id"] for doc in batch_docs}
    confirmed_failed = batch_ids & set(failedDocumentIds)
    # documentIds outside this batch are silently ignored rather than erroring:
    # the admin is reading ids off a GCS error log, not off this batch's exact
    # id list, so an id that no longer matches (already re-synced elsewhere,
    # typo) should not block resolving the ones that do.
    to_recover = batch_ids - confirmed_failed

    if to_recover:
        db["document_ingestion"].update_many(
            {"_id": {"$in": list(to_recover)}},
            {"$set": _audit_set({"status": "INDEXED"}, SYSTEM_AUDIT_USER), "$unset": {"error_message": ""}},
        )
    if confirmed_failed:
        db["document_ingestion"].update_many(
            {"_id": {"$in": list(confirmed_failed)}},
            {"$set": _audit_set({
                "status": "FAILED",
                "error_message": failureReason or "Xác nhận lỗi thật qua log chi tiết trên GCS",
            }, SYSTEM_AUDIT_USER)},
        )

    logger.info(
        "resolve_batch_failure: operation=%s recovered=%d confirmed_failed=%d",
        operationName, len(to_recover), len(confirmed_failed),
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "operationName": operationName,
            "recoveredDocumentIds": sorted(to_recover),
            "confirmedFailedDocumentIds": sorted(confirmed_failed),
        },
    )


@router.get(
    "/document-ingestion/{documentId}/processed",
    summary="Get a document's chunked content from the Vertex AI Search Data Store",
    description=(
        "Requires the document to already be UPLOADED (synced to GCS). Reads "
        "the chunked document content back from the Vertex AI Search Data "
        "Store the GCS bucket streams into. Returns 409 if the document isn't "
        "UPLOADED yet, and 404 if it hasn't finished syncing into the Data "
        "Store yet (streaming sync isn't instantaneous)."
    ),
)
async def get_processed_document(documentId: str) -> dict:
    db = get_mongo_db()
    doc = db["document_ingestion"].find_one({"_id": documentId})
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # INDEXED is valid too: it's an UPLOADED record that /sync-vertex has already
    # pushed into the Data Store, i.e. even "readier" than UPLOADED.
    if doc.get("status") not in ("UPLOADED", "INDEXED"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document has not been uploaded to Vertex yet",
        )

    gcs_uri = doc.get("gcs_uri")
    if not gcs_uri:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document has no gcs_uri recorded",
        )

    try:
        chunked_json_data = get_chunked_document(gcs_uri)
    except NotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document has not finished syncing into the Vertex AI Search Data Store yet",
        ) from exc
    except Exception as exc:
        logger.error(
            "get_processed_document failed for documentId=%s: %s\n%s",
            documentId, exc, traceback.format_exc(),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Không thể lấy dữ liệu đã chunk từ Vertex: {exc}",
        ) from exc

    return {"documentId": documentId, "chunkedJsonData": chunked_json_data}


@router.post(
    "/document-ingestion/{documentId}/reindex",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Re-trigger Vertex AI Search indexing with the document's current metadata",
    description=(
        "Re-reads the document_ingestion record's current structData fields "
        "(document_collection, issuing_unit, etc. — possibly just edited by "
        "the user) and re-imports the document into the Data Store, so its "
        "structData there gets refreshed to match. Requires the document to "
        "already be UPLOADED/DONE (i.e. it has a gcs_uri to re-import)."
    ),
)
async def reindex_document(documentId: str) -> JSONResponse:
    db = get_mongo_db()
    doc = db["document_ingestion"].find_one({"_id": documentId})
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    gcs_uri = doc.get("gcs_uri")
    if not gcs_uri:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document has no gcs_uri recorded — upload to Vertex first",
        )

    try:
        trigger_document_index(gcs_uri, doc)
    except Exception as exc:
        logger.error(
            "reindex_document failed for documentId=%s gcs_uri=%s: %s\n%s",
            documentId, gcs_uri, exc, traceback.format_exc(),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Không thể đẩy lại metadata lên Vertex: {exc}",
        ) from exc

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={"documentId": documentId, "status": doc.get("status")},
    )


@router.delete(
    "/document-ingestion/{documentId}",
    summary="Hard delete a document-ingestion record",
    description=(
        "Deletes the GCS blob and Vertex AI Search Data Store document behind "
        "this record (best-effort — failures, including NotFound, are logged "
        "but do not block the Mongo delete), then hard-deletes the "
        "document_ingestion Mongo record. Skips the GCS/Vertex step entirely "
        "if the record has no gcs_uri yet."
    ),
)
async def delete_document_ingestion(documentId: str) -> dict:
    db = get_mongo_db()
    doc = db["document_ingestion"].find_one({"_id": documentId})
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    gcs_uri = doc.get("gcs_uri")
    if gcs_uri:
        try:
            delete_blob_from_gcs(blob_path=parse_gcs_uri(gcs_uri))
        except NotFound:
            logger.info("delete_document_ingestion: GCS blob already gone for documentId=%s gcs_uri=%s", documentId, gcs_uri)
        except Exception as exc:
            logger.error(
                "delete_document_ingestion: GCS delete failed for documentId=%s gcs_uri=%s: %s\n%s",
                documentId, gcs_uri, exc, traceback.format_exc(),
            )

        try:
            delete_document(gcs_uri)
        except NotFound:
            logger.info("delete_document_ingestion: Vertex document already gone for documentId=%s gcs_uri=%s", documentId, gcs_uri)
        except Exception as exc:
            logger.error(
                "delete_document_ingestion: Vertex delete failed for documentId=%s gcs_uri=%s: %s\n%s",
                documentId, gcs_uri, exc, traceback.format_exc(),
            )

    if doc.get("html_s3_path"):
        try:
            await delete_html(documentId)
        except Exception as exc:
            logger.error(
                "delete_document_ingestion: S3 delete failed for documentId=%s: %s\n%s",
                documentId, exc, traceback.format_exc(),
            )

    db["document_ingestion"].delete_one({"_id": documentId})
    return {"documentId": documentId}
