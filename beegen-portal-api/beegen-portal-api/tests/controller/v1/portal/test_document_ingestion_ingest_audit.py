from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.controller.v1.portal.document_ingestion_router import router


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/portal")
    return app


@patch("app.controller.v1.portal.document_ingestion_router.process_and_replace_s3_images_async", new_callable=AsyncMock)
@patch("app.controller.v1.portal.document_ingestion_router.upload_html", new_callable=AsyncMock)
@patch("app.controller.v1.portal.document_ingestion_router.extract_document_data", new_callable=AsyncMock)
@patch("app.controller.v1.portal.document_ingestion_router.get_mongo_db")
def test_ingest_document_stamps_status_processing_with_real_caller_userId(
    mock_get_mongo_db, mock_extract_document_data, mock_upload_html, mock_process_s3_images
):
    # extract_document_data/upload_html are patched (not just get_mongo_db) because
    # Starlette's TestClient runs BackgroundTasks synchronously as part of the
    # request/response cycle (see BackgroundTasks.__call__ in starlette.background),
    # so client.post(...) below also executes _extract_document_in_background before
    # returning. Without mocking these, that background call would hit real S3/Beedoc
    # dependencies and call update_one a second time, breaking assert_called_once()
    # below in a way that has nothing to do with what this test is verifying (the
    # PROCESSING stamp written by ingest_document itself).
    mock_collection = MagicMock()
    mock_db = MagicMock()
    mock_db.__getitem__.return_value = mock_collection
    mock_get_mongo_db.return_value = mock_db
    mock_extract_document_data.return_value = {"reconstructed": "<p>hello</p>"}
    mock_upload_html.return_value = "s3://bucket/HTML_EXTRACTED/doc-1.html"
    # process_and_replace_s3_images_async is now a separate step in the background
    # task; stub it to pass content through so the test exercises the full path.
    mock_process_s3_images.side_effect = lambda **kw: kw["content"]

    client = TestClient(_build_app())
    response = client.post(
        "/portal/document-ingestion/ingest",
        data={"botId": "bot-1", "documentId": "doc-1", "userId": "user-42"},
        files={"file": ("doc.pdf", BytesIO(b"%PDF-1.4 fake content"), "application/pdf")},
    )

    assert response.status_code == 202
    # Two update_one calls happen: PROCESSING (from ingest_document) then EXTRACTED
    # (from the background task, which TestClient also runs before returning here).
    # This test only asserts on the first one — the PROCESSING stamp under test.
    assert mock_collection.update_one.call_count == 2
    call_args = mock_collection.update_one.call_args_list[0]
    assert call_args[0][0] == {"_id": "doc-1"}
    assert call_args[0][1]["$set"]["status"] == "PROCESSING"
    assert call_args[0][1]["$set"]["updated_by"] == "user-42"


@pytest.mark.asyncio
@patch("app.controller.v1.portal.document_ingestion_router.process_and_replace_s3_images_async", new_callable=AsyncMock)
@patch("app.controller.v1.portal.document_ingestion_router.upload_html", new_callable=AsyncMock)
@patch("app.controller.v1.portal.document_ingestion_router.extract_document_data", new_callable=AsyncMock)
@patch("app.controller.v1.portal.document_ingestion_router.get_mongo_db")
async def test_extract_document_in_background_stamps_extracted_with_caller_userId(
    mock_get_mongo_db, mock_extract_document_data, mock_upload_html, mock_process_s3_images, tmp_path
):
    from app.controller.v1.portal.document_ingestion_router import _extract_document_in_background

    mock_collection = MagicMock()
    mock_db = MagicMock()
    mock_db.__getitem__.return_value = mock_collection
    mock_get_mongo_db.return_value = mock_db
    mock_extract_document_data.return_value = {"reconstructed": "<p>hello</p>"}
    mock_upload_html.return_value = "s3://bucket/HTML_EXTRACTED/doc-1.html"
    mock_process_s3_images.side_effect = lambda **kw: kw["content"]

    temp_file = tmp_path / "doc-1.pdf"
    temp_file.write_bytes(b"%PDF-1.4 fake content")

    await _extract_document_in_background("doc-1", "bot-1", str(temp_file), "user-42")

    mock_collection.update_one.assert_called_once()
    call_args = mock_collection.update_one.call_args
    assert call_args[0][1]["$set"]["status"] == "EXTRACTED"
    assert call_args[0][1]["$set"]["updated_by"] == "user-42"
