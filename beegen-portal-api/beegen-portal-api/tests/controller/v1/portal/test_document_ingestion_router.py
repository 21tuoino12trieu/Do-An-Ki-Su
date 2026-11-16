from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.api_core.exceptions import NotFound

from app.controller.v1.portal.document_ingestion_router import router


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/portal")
    return app


@patch("app.controller.v1.portal.document_ingestion_router.upload_bytes_to_gcs")
@patch("app.controller.v1.portal.document_ingestion_router.extract_document_data", new_callable=AsyncMock)
@patch("app.controller.v1.portal.document_ingestion_router.get_mongo_db")
def test_ingest_document_sets_status_uploaded(
    mock_get_mongo_db, mock_extract_document_data, mock_upload_bytes_to_gcs
):
    mock_collection = MagicMock()
    mock_db = MagicMock()
    mock_db.__getitem__.return_value = mock_collection
    mock_get_mongo_db.return_value = mock_db
    mock_extract_document_data.return_value = {"reconstructed": "<p>hello</p>", "zones": [], "file_name": "doc.pdf"}
    mock_upload_bytes_to_gcs.return_value = "gs://test-bucket/bot-1/doc-1/content.html"

    client = TestClient(_build_app())
    response = client.post(
        "/portal/document-ingestion/ingest",
        data={"botId": "bot-1", "documentId": "doc-1"},
        files={"file": ("doc.pdf", BytesIO(b"%PDF-1.4 fake content"), "application/pdf")},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["documentId"] == "doc-1"
    assert body["gcs_uri"] == "gs://test-bucket/bot-1/doc-1/content.html"
    assert body["status"] == "UPLOADED"

    mock_upload_bytes_to_gcs.assert_called_once()
    upload_kwargs = mock_upload_bytes_to_gcs.call_args.kwargs
    assert upload_kwargs["blob_path"] == "bot-1/doc-1/content.html"
    assert upload_kwargs["content"] == b"<p>hello</p>"
    assert upload_kwargs["content_type"] == "text/html"

    mock_collection.update_one.assert_called_once()
    call_args = mock_collection.update_one.call_args
    assert call_args[0][0] == {"_id": "doc-1"}
    assert call_args[0][1]["$set"]["status"] == "UPLOADED"
    assert call_args[0][1]["$set"]["extracted_html_content"] == "<p>hello</p>"
    assert call_args[0][1]["$set"]["gcs_uri"] == "gs://test-bucket/bot-1/doc-1/content.html"


@patch("app.controller.v1.portal.document_ingestion_router.upload_bytes_to_gcs")
@patch("app.controller.v1.portal.document_ingestion_router.extract_document_data", new_callable=AsyncMock)
@patch("app.controller.v1.portal.document_ingestion_router.get_mongo_db")
def test_ingest_document_sets_status_failed_when_gcs_upload_fails(
    mock_get_mongo_db, mock_extract_document_data, mock_upload_bytes_to_gcs
):
    mock_collection = MagicMock()
    mock_db = MagicMock()
    mock_db.__getitem__.return_value = mock_collection
    mock_get_mongo_db.return_value = mock_db
    mock_extract_document_data.return_value = {"reconstructed": "<p>hello</p>", "zones": [], "file_name": "doc.pdf"}
    mock_upload_bytes_to_gcs.side_effect = RuntimeError("gateway unreachable")

    client = TestClient(_build_app())
    response = client.post(
        "/portal/document-ingestion/ingest",
        data={"botId": "bot-1", "documentId": "doc-1"},
        files={"file": ("doc.pdf", BytesIO(b"%PDF-1.4 fake content"), "application/pdf")},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["documentId"] == "doc-1"
    assert body["status"] == "FAILED"

    mock_collection.update_one.assert_called_once()
    call_args = mock_collection.update_one.call_args
    assert call_args[0][0] == {"_id": "doc-1"}
    assert call_args[0][1]["$set"]["status"] == "FAILED"
    assert "gateway unreachable" in call_args[0][1]["$set"]["error_message"]


@patch("app.controller.v1.portal.document_ingestion_router.delete_document")
@patch("app.controller.v1.portal.document_ingestion_router.delete_blob_from_gcs")
@patch("app.controller.v1.portal.document_ingestion_router.parse_gcs_uri")
@patch("app.controller.v1.portal.document_ingestion_router.get_mongo_db")
def test_delete_document_with_gcs_uri_deletes_gcs_vertex_and_mongo(
    mock_get_mongo_db, mock_parse_gcs_uri, mock_delete_blob, mock_delete_document
):
    mock_collection = MagicMock()
    mock_collection.find_one.return_value = {
        "_id": "doc-1",
        "bot_id": "bot-1",
        "gcs_uri": "gs://test-bucket/bot-1/doc-1/content.html",
    }
    mock_db = MagicMock()
    mock_db.__getitem__.return_value = mock_collection
    mock_get_mongo_db.return_value = mock_db
    mock_parse_gcs_uri.return_value = "bot-1/doc-1/content.html"

    client = TestClient(_build_app())
    response = client.delete("/portal/document-ingestion/doc-1")

    assert response.status_code == 200
    assert response.json() == {"documentId": "doc-1"}

    mock_delete_blob.assert_called_once_with(blob_path="bot-1/doc-1/content.html")
    mock_delete_document.assert_called_once_with("gs://test-bucket/bot-1/doc-1/content.html")
    mock_collection.delete_one.assert_called_once_with({"_id": "doc-1"})


@patch("app.controller.v1.portal.document_ingestion_router.delete_document")
@patch("app.controller.v1.portal.document_ingestion_router.delete_blob_from_gcs")
@patch("app.controller.v1.portal.document_ingestion_router.get_mongo_db")
def test_delete_document_without_gcs_uri_skips_gcs_and_vertex(
    mock_get_mongo_db, mock_delete_blob, mock_delete_document
):
    mock_collection = MagicMock()
    mock_collection.find_one.return_value = {"_id": "doc-1", "bot_id": "bot-1"}
    mock_db = MagicMock()
    mock_db.__getitem__.return_value = mock_collection
    mock_get_mongo_db.return_value = mock_db

    client = TestClient(_build_app())
    response = client.delete("/portal/document-ingestion/doc-1")

    assert response.status_code == 200
    assert response.json() == {"documentId": "doc-1"}

    mock_delete_blob.assert_not_called()
    mock_delete_document.assert_not_called()
    mock_collection.delete_one.assert_called_once_with({"_id": "doc-1"})


@patch("app.controller.v1.portal.document_ingestion_router.get_mongo_db")
def test_delete_document_returns_404_when_record_missing(mock_get_mongo_db):
    mock_collection = MagicMock()
    mock_collection.find_one.return_value = None
    mock_db = MagicMock()
    mock_db.__getitem__.return_value = mock_collection
    mock_get_mongo_db.return_value = mock_db

    client = TestClient(_build_app())
    response = client.delete("/portal/document-ingestion/doc-missing")

    assert response.status_code == 404
    mock_collection.delete_one.assert_not_called()


@patch("app.controller.v1.portal.document_ingestion_router.delete_document")
@patch("app.controller.v1.portal.document_ingestion_router.delete_blob_from_gcs")
@patch("app.controller.v1.portal.document_ingestion_router.parse_gcs_uri")
@patch("app.controller.v1.portal.document_ingestion_router.get_mongo_db")
def test_delete_document_continues_when_gcs_delete_raises_not_found(
    mock_get_mongo_db, mock_parse_gcs_uri, mock_delete_blob, mock_delete_document
):
    mock_collection = MagicMock()
    mock_collection.find_one.return_value = {
        "_id": "doc-1",
        "bot_id": "bot-1",
        "gcs_uri": "gs://test-bucket/bot-1/doc-1/content.html",
    }
    mock_db = MagicMock()
    mock_db.__getitem__.return_value = mock_collection
    mock_get_mongo_db.return_value = mock_db
    mock_parse_gcs_uri.return_value = "bot-1/doc-1/content.html"
    mock_delete_blob.side_effect = NotFound("blob missing")

    client = TestClient(_build_app())
    response = client.delete("/portal/document-ingestion/doc-1")

    assert response.status_code == 200
    mock_delete_blob.assert_called_once_with(blob_path="bot-1/doc-1/content.html")
    mock_delete_document.assert_called_once()
    mock_collection.delete_one.assert_called_once_with({"_id": "doc-1"})


@patch("app.controller.v1.portal.document_ingestion_router.delete_document")
@patch("app.controller.v1.portal.document_ingestion_router.delete_blob_from_gcs")
@patch("app.controller.v1.portal.document_ingestion_router.parse_gcs_uri")
@patch("app.controller.v1.portal.document_ingestion_router.get_mongo_db")
def test_delete_document_continues_when_vertex_delete_raises_not_found(
    mock_get_mongo_db, mock_parse_gcs_uri, mock_delete_blob, mock_delete_document
):
    mock_collection = MagicMock()
    mock_collection.find_one.return_value = {
        "_id": "doc-1",
        "bot_id": "bot-1",
        "gcs_uri": "gs://test-bucket/bot-1/doc-1/content.html",
    }
    mock_db = MagicMock()
    mock_db.__getitem__.return_value = mock_collection
    mock_get_mongo_db.return_value = mock_db
    mock_parse_gcs_uri.return_value = "bot-1/doc-1/content.html"
    mock_delete_document.side_effect = NotFound("document missing")

    client = TestClient(_build_app())
    response = client.delete("/portal/document-ingestion/doc-1")

    assert response.status_code == 200
    mock_delete_blob.assert_called_once_with(blob_path="bot-1/doc-1/content.html")
    mock_collection.delete_one.assert_called_once_with({"_id": "doc-1"})


@patch("app.controller.v1.portal.document_ingestion_router.delete_document")
@patch("app.controller.v1.portal.document_ingestion_router.delete_blob_from_gcs")
@patch("app.controller.v1.portal.document_ingestion_router.parse_gcs_uri")
@patch("app.controller.v1.portal.document_ingestion_router.get_mongo_db")
def test_delete_document_continues_when_gcs_delete_raises_other_error(
    mock_get_mongo_db, mock_parse_gcs_uri, mock_delete_blob, mock_delete_document
):
    mock_collection = MagicMock()
    mock_collection.find_one.return_value = {
        "_id": "doc-1",
        "bot_id": "bot-1",
        "gcs_uri": "gs://test-bucket/bot-1/doc-1/content.html",
    }
    mock_db = MagicMock()
    mock_db.__getitem__.return_value = mock_collection
    mock_get_mongo_db.return_value = mock_db
    mock_parse_gcs_uri.return_value = "bot-1/doc-1/content.html"
    mock_delete_blob.side_effect = RuntimeError("gateway unreachable")

    client = TestClient(_build_app())
    response = client.delete("/portal/document-ingestion/doc-1")

    assert response.status_code == 200
    mock_delete_document.assert_called_once()
    mock_collection.delete_one.assert_called_once_with({"_id": "doc-1"})
