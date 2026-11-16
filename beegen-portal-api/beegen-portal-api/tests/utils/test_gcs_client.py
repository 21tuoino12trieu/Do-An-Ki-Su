from unittest.mock import MagicMock, patch

import pytest

from app.utils.gcs_client import delete_blob_from_gcs, parse_gcs_uri


def test_parse_gcs_uri_strips_bucket_prefix():
    with patch("app.utils.gcs_client.get_gcs_bucket_name", return_value="test-bucket"):
        blob_path = parse_gcs_uri("gs://test-bucket/bot-1/doc-1/content.html")

    assert blob_path == "bot-1/doc-1/content.html"


@patch("app.utils.gcs_client.get_gcs_bucket_name", return_value="test-bucket")
@patch("app.utils.gcs_client.get_gcs_client")
def test_delete_blob_from_gcs_calls_blob_delete(mock_get_gcs_client, mock_get_bucket_name):
    mock_blob = MagicMock()
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket
    mock_get_gcs_client.return_value = mock_client

    delete_blob_from_gcs(blob_path="bot-1/doc-1/content.html")

    mock_client.bucket.assert_called_once_with("test-bucket")
    mock_bucket.blob.assert_called_once_with("bot-1/doc-1/content.html")
    mock_blob.delete.assert_called_once()


@patch("app.utils.gcs_client.get_gcs_bucket_name", return_value="test-bucket")
@patch("app.utils.gcs_client.get_gcs_client")
def test_delete_blob_from_gcs_propagates_not_found(mock_get_gcs_client, mock_get_bucket_name):
    from google.api_core.exceptions import NotFound

    mock_blob = MagicMock()
    mock_blob.delete.side_effect = NotFound("blob missing")
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket
    mock_get_gcs_client.return_value = mock_client

    with pytest.raises(NotFound):
        delete_blob_from_gcs(blob_path="bot-1/doc-1/content.html")
