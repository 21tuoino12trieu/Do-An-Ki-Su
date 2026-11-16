from unittest.mock import MagicMock, patch

import pytest
from google.api_core.exceptions import NotFound

from app.utils.vertex_search_client import delete_document


@patch("app.utils.vertex_search_client._document_resource_name")
@patch("app.utils.vertex_search_client.compute_vertex_document_id")
@patch("app.utils.vertex_search_client._get_document_service_client")
def test_delete_document_calls_client_with_computed_resource_name(
    mock_get_client, mock_compute_id, mock_resource_name
):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_compute_id.return_value = "abc123"
    mock_resource_name.return_value = (
        "projects/p/locations/global/collections/default_collection/"
        "dataStores/ds/branches/default_branch/documents/abc123"
    )

    delete_document("gs://test-bucket/bot-1/doc-1/content.html")

    mock_compute_id.assert_called_once_with("gs://test-bucket/bot-1/doc-1/content.html")
    mock_resource_name.assert_called_once_with("abc123")
    mock_client.delete_document.assert_called_once()
    request = mock_client.delete_document.call_args.kwargs["request"]
    assert request.name == (
        "projects/p/locations/global/collections/default_collection/"
        "dataStores/ds/branches/default_branch/documents/abc123"
    )


@patch("app.utils.vertex_search_client._document_resource_name")
@patch("app.utils.vertex_search_client.compute_vertex_document_id")
@patch("app.utils.vertex_search_client._get_document_service_client")
def test_delete_document_propagates_not_found(mock_get_client, mock_compute_id, mock_resource_name):
    mock_client = MagicMock()
    mock_client.delete_document.side_effect = NotFound("document missing")
    mock_get_client.return_value = mock_client
    mock_compute_id.return_value = "abc123"
    mock_resource_name.return_value = "projects/p/.../documents/abc123"

    with pytest.raises(NotFound):
        delete_document("gs://test-bucket/bot-1/doc-1/content.html")
