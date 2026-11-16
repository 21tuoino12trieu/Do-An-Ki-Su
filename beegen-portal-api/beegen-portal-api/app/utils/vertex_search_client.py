"""Client for reading back a document's chunked content from a Vertex AI
Search (Discovery Engine) Data Store, once it has been synced there from GCS.

The Data Store is configured as a plain "Documents" (unstructured, no
metadata) source pointed at the same GCS bucket the document-ingestion HTML
files are uploaded to, with Streaming sync and chunking enabled. For that
source type, Discovery Engine assigns each document's ID deterministically:
the first 128 bits of SHA256(gcs_uri), hex-encoded — see
https://docs.cloud.google.com/generative-ai-app-builder/docs/reference/rest/v1/GcsSource
("content" data schema). That means the ID can be computed locally from the
gcs_uri already stored in Mongo, with no need to list/search the Data Store
to find a document.

Uses the REST transport (not the default gRPC one): this internal network
only routes to Google's public endpoints through the F5 gateway (see
app/utils/f5_proxy.py), which works at the HTTP connection-pool level and
has no gRPC equivalent here.

DocumentServiceRestTransport.__init__ has no constructor parameter to inject
a pre-built session (unlike google-cloud-storage's `storage.Client(_http=...)`
— see app/utils/gcs_client.py). It always builds its own
`self._session = AuthorizedSession(credentials, default_host=...)` internally
(google/cloud/discoveryengine_v1alpha/.../transports/rest.py), then
immediately calls `self._prep_wrapped_messages(client_info)`, which snapshots
`transport._session` as part of the dict keys in `transport._wrapped_methods`
(each entry is keyed by a `_GetProcessedDocument(session, host, interceptor)`
wrapper object built from that exact session instance). Every RPC method
(e.g. `transport.get_processed_document`) is a `@property` that re-builds that
wrapper from `self._session` on every access, so if `_session` is ever
*reassigned* to a different object after construction, the freshly-built
wrapper no longer matches any key in `_wrapped_methods` and the client raises
`KeyError` (see google/cloud/discoveryengine_v1alpha/.../document_service/client.py,
`rpc = self._transport._wrapped_methods[self._transport.get_processed_document]`).

The fix that is actually compatible with this library: let the transport
construct its own `AuthorizedSession` as normal (so `_wrapped_methods` is
built against the real, final session object), then mutate that SAME session
object in place — mount the F5 proxy adapter onto it for
discoveryengine.googleapis.com, and separately mount it onto the session's
own internal `_auth_request_session` (which `AuthorizedSession.__init__`
creates itself for oauth2 token-refresh calls whenever no `auth_request` is
passed in — google/auth/transport/requests.py, `AuthorizedSession.__init__`)
for oauth2.googleapis.com. Never assign `transport._session = <new object>`.
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Mapping

from google.cloud import discoveryengine_v1alpha
from google.oauth2 import service_account

from app.utils.f5_proxy import mount_f5_proxy
from app.utils.gcs_client import get_gcs_bucket_name, parse_gcs_uri, read_blobs_by_prefix, upload_bytes_to_gcs

logger = logging.getLogger(__name__)

DISCOVERYENGINE_PINNED_HOST = "discoveryengine.googleapis.com"
OAUTH2_PINNED_HOST = "oauth2.googleapis.com"


@dataclass(frozen=True)
class BatchImportSubmission:
    """What a submitted (not yet finished) ImportDocuments batch consists of.

    ``operation_name`` is the long-running operation's resource name. Import is
    asynchronous: acceptance of the request says nothing about whether the
    documents were actually indexed, so this name is the only handle callers
    have to find out later — keep it on the record (see poll_batch_import).

    ``error_log_prefix`` is where Discovery Engine writes ONE JSON-encoded
    google.rpc.Status per failed document, one per line, sharded across
    multiple files under this GCS prefix — see ImportErrorConfig.gcs_prefix.
    This is the ONLY way to find out which specific document(s) in the batch
    failed: the operation's response only carries error_samples, a partial
    sample, which is why _apply_import_result marks the WHOLE batch FAILED
    instead of trying to guess from that. An operator reads this prefix to
    confirm the real failures before calling /resolve-batch-failure.
    """

    metadata_uri: str
    operation_name: str
    document_ids: list[str]
    error_log_prefix: str


@dataclass(frozen=True)
class BatchImportResult:
    """Outcome of an ImportDocuments operation once Discovery Engine finished it.

    ``done=False`` means still running: counts are not final and callers should
    leave the records alone and poll again later.
    """

    done: bool
    success_count: int = 0
    failure_count: int = 0
    error_message: str = ""


def compute_vertex_document_id(gcs_uri: str) -> str:
    """Discovery Engine's deterministic document ID for a GCS "content"-schema
    source: first 128 bits (16 bytes) of SHA256(gcs_uri), as hex."""
    digest = hashlib.sha256(gcs_uri.encode("utf-8")).digest()
    return digest[:16].hex()


@lru_cache()
def _get_document_service_client() -> discoveryengine_v1alpha.DocumentServiceClient:
    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

    if credentials_path:
        # cloud-platform is required to call Discovery Engine; there is no
        # narrower "discoveryengine"-only OAuth scope.
        credentials = service_account.Credentials.from_service_account_file(
            credentials_path,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
    else:
        import google.auth
        credentials, _ = google.auth.default()

    # Let the transport build its own AuthorizedSession exactly as it always
    # does — this is what _prep_wrapped_messages snapshots into
    # _wrapped_methods, so this object must stay identical for the lifetime
    # of the transport.
    transport = discoveryengine_v1alpha.services.document_service.transports.DocumentServiceRestTransport(
        credentials=credentials
    )

    proxy_host = os.environ.get("GCS_PROXY_HOST")
    if proxy_host:
        proxy_port = int(os.environ.get("GCS_PROXY_PORT", "443"))

        # Mutate the transport's session in place for Discovery Engine API calls.
        transport._session.trust_env = False
        mount_f5_proxy(
            transport._session,
            proxy_host=proxy_host,
            proxy_port=proxy_port,
            pinned_host=DISCOVERYENGINE_PINNED_HOST,
        )

        # AuthorizedSession refreshes tokens via its own internal
        # _auth_request_session (created because DocumentServiceRestTransport
        # never passes `auth_request=` to AuthorizedSession) — mutate that
        # same sub-session in place too, for oauth2.googleapis.com.
        auth_request_session = transport._session._auth_request_session
        auth_request_session.trust_env = False
        mount_f5_proxy(
            auth_request_session,
            proxy_host=proxy_host,
            proxy_port=proxy_port,
            pinned_host=OAUTH2_PINNED_HOST,
        )

    client = discoveryengine_v1alpha.DocumentServiceClient(transport=transport)

    if proxy_host:
        proxy_port = int(os.environ.get("GCS_PROXY_PORT", "443"))

        # operations_client builds its OWN OperationsRestTransport with its OWN
        # AuthorizedSession on first access (see DocumentServiceRestTransport
        # .operations_client property) — the F5 proxy mount on transport
        # ._session above does NOT cover it, so get_operation calls (used by
        # poll_batch_import) bypass the gateway and time out. Force-create it
        # and mount the same adapter onto its session in place, following the
        # same mutate-in-place rule as above.
        ops_transport = client.transport.operations_client._transport
        ops_transport._session.trust_env = False
        mount_f5_proxy(
            ops_transport._session,
            proxy_host=proxy_host,
            proxy_port=proxy_port,
            pinned_host=DISCOVERYENGINE_PINNED_HOST,
        )

        ops_auth_session = ops_transport._session._auth_request_session
        ops_auth_session.trust_env = False
        mount_f5_proxy(
            ops_auth_session,
            proxy_host=proxy_host,
            proxy_port=proxy_port,
            pinned_host=OAUTH2_PINNED_HOST,
        )

    return client


def _branch_resource_name() -> str:
    project_id = os.environ["GCS_PROJECT_ID"]
    data_store_id = os.environ["DATA_STORE_ID"]
    location = os.environ.get("DATA_STORE_LOCATION", "global")
    return (
        f"projects/{project_id}/locations/{location}/collections/default_collection/"
        f"dataStores/{data_store_id}/branches/default_branch"
    )


def _document_resource_name(document_id: str) -> str:
    return f"{_branch_resource_name()}/documents/{document_id}"


def _build_struct_data(doc: Mapping[str, Any]) -> dict:
    """Builds the structData for a Document import line, conforming to the
    Data Store's registered Schema (confirmed via the Console's Schema tab):
    collection_code, confidentiality, created_at, description,
    doc_effective_date, doc_expiry_date, document_bussiness_type,
    document_collection, document_hash, document_id, document_name, domain,
    id, ingestion_type, is_active, issuing_unit, role_ids, source_system,
    title. Document.struct_data must conform to this Schema or Discovery
    Engine raises INVALID_ARGUMENT (see google/cloud/discoveryengine_v1alpha/
    types/document.py, Document.struct_data docstring).

    System-derived fields (document_id, document_hash, created_at,
    ingestion_type, is_active, source_system, title) are always set here.
    User-entered fields (document_collection, document_bussiness_type,
    issuing_unit, confidentiality, doc_effective_date, doc_expiry_date,
    description, domain) come from the document_ingestion Mongo record
    (populated at upload time — see beegen-portal-be's
    DocumentIngestionService.persistPending) and are only included when
    present, since none of them are required by the Schema itself.
    collection_code and role_ids are intentionally omitted: there is no
    per-document access-control/grouping concept yet.
    """
    document_id = doc["_id"]
    struct_data: dict[str, Any] = {
        "document_id": document_id,
        "document_name": doc.get("document_name") or document_id,
        "title": doc.get("document_name") or document_id,
        "source_system": "BEEGEN_PORTAL",
        "ingestion_type": "API",
        "is_active": True,
    }
    if doc.get("created_at") is not None:
        struct_data["created_at"] = doc["created_at"].isoformat()

    # NOTE: key = ten field trong Mongo (da rename), value = key trong Vertex
    # Discovery Engine Schema (GIU NGUYEN, vi Schema ben Google chua doi).
    optional_fields = {
        "collection_name": "document_collection",
        "document_business_type": "document_bussiness_type",
        "issuing_unit": "issuing_unit",
        "confidentiality_level": "confidentiality",
        "description": "description",
        "domain": "domain",
    }
    for mongo_field, struct_field in optional_fields.items():
        value = doc.get(mongo_field)
        if value:
            struct_data[struct_field] = value

    for mongo_field, struct_field in (
        ("effective_date", "doc_effective_date"),
        ("expiry_date", "doc_expiry_date"),
    ):
        value = doc.get(mongo_field)
        if value:
            struct_data[struct_field] = value.isoformat()

    return struct_data


def trigger_document_index(gcs_uri: str, doc: Mapping[str, Any]) -> None:
    """Triggers Discovery Engine to (re-)import a single GCS file into the Data
    Store, instead of waiting for the Data Store's own sync (streaming or
    scheduled) to pick it up. Fire-and-forget: returns as soon as the
    long-running ImportDocuments operation is accepted, without waiting for it
    to finish indexing.

    Uses data_schema="document" (one JSON Document per JSONL line) instead of
    data_schema="content" (Discovery Engine auto-derives a bare Document with
    no structData from the file itself). "content" is what earlier versions
    of this function used, and it's why documents ingested through this path
    had no "View document" link in the Console: only Documents with
    structData + an explicit content.uri/mimeType get one, same as documents
    from the other (VBNB) ingestion pipeline already in this Data Store.

    Document.id keeps using the same SHA256(gcs_uri)-derived value as before
    (see compute_vertex_document_id) — that scheme happens to already satisfy
    the RFC-1034 / 63-char constraint on Document.id, so get_chunked_document
    keeps working unchanged; the only difference is that this id is now
    assigned explicitly in the JSONL line instead of being auto-derived by
    Discovery Engine from data_schema="content".

    Temporary: it's not yet decided whether the Data Store will be configured
    for Streaming or periodic/one-time Import Document sync, so this call is
    made explicitly right after each successful GCS upload to guarantee the
    document gets indexed either way.
    """
    document_id = compute_vertex_document_id(gcs_uri)
    mime_type = "text/html" if gcs_uri.endswith(".html") else "application/pdf"
    metadata_line = {
        "id": document_id,
        "structData": _build_struct_data(doc),
        "content": {"mimeType": mime_type, "uri": gcs_uri},
    }
    metadata_blob_path = f"{doc.get('bot_id')}/{doc['_id']}/metadata.jsonl"
    metadata_uri = upload_bytes_to_gcs(
        blob_path=metadata_blob_path,
        content=(json.dumps(metadata_line, ensure_ascii=False) + "\n").encode("utf-8"),
        content_type="application/jsonl",
    )

    client = _get_document_service_client()
    request = discoveryengine_v1alpha.ImportDocumentsRequest(
        parent=_branch_resource_name(),
        gcs_source=discoveryengine_v1alpha.GcsSource(
            input_uris=[metadata_uri],
            data_schema="document",
        ),
        reconciliation_mode=discoveryengine_v1alpha.ImportDocumentsRequest.ReconciliationMode.INCREMENTAL,
    )
    client.import_documents(request=request)


def trigger_batch_index(docs: list[Mapping[str, Any]]) -> BatchImportSubmission:
    """Imports a whole batch of already-uploaded documents into the Data Store
    with a SINGLE ImportDocuments call, and returns the submission handle.

    trigger_document_index does one JSONL file plus one long-running operation
    per document, which is the expensive way to use this API: GcsSource
    .input_uris takes a *list*, and data_schema="document" is a JSONL format
    that holds one Document per *line*. Ingesting N documents one-by-one
    therefore leaves N single-line JSONL files behind on GCS and starts N
    LROs, where one file of N lines and one LRO would do.

    Each doc must already have a gcs_uri (i.e. be in status UPLOADED); docs
    without one are skipped rather than failing the whole batch, since a
    missing gcs_uri means that document never finished its GCS upload.

    Document.id keeps using compute_vertex_document_id(gcs_uri), identical to
    the single-document path, so get_chunked_document and delete_document keep
    working unchanged for batch-imported documents.

    Returns once the operation is ACCEPTED, without waiting for indexing to
    finish — an accepted request can still fail per-document afterwards (bad
    structData, unreadable GCS object). The returned operation_name is what
    poll_batch_import needs to establish whether that happened.
    """
    lines = []
    imported_ids = []
    for doc in docs:
        gcs_uri = doc.get("gcs_uri")
        if not gcs_uri:
            continue
        mime_type = "text/html" if gcs_uri.endswith(".html") else "application/pdf"
        lines.append(json.dumps({
            "id": compute_vertex_document_id(gcs_uri),
            "structData": _build_struct_data(doc),
            "content": {"mimeType": mime_type, "uri": gcs_uri},
        }, ensure_ascii=False))
        imported_ids.append(doc["_id"])

    if not lines:
        raise ValueError("No document has a gcs_uri to import")

    # One JSONL file per batch, named by timestamp so successive syncs don't
    # overwrite each other (kept around for investigating an older batch).
    batch_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    metadata_uri = upload_bytes_to_gcs(
        blob_path=f"_batch_metadata/{batch_stamp}.jsonl",
        content=("\n".join(lines) + "\n").encode("utf-8"),
        content_type="application/jsonl",
    )

    # error_config.gcs_prefix must be an empty, existing GCS directory —
    # reusing batch_stamp keeps it unique per batch, so it is guaranteed empty
    # (nothing has ever been written under this prefix before). GCS has no
    # real directories, so no placeholder object needs to be created first:
    # the prefix "exists" the moment Discovery Engine writes the first shard
    # under it.
    error_log_prefix = f"gs://{get_gcs_bucket_name()}/_batch_errors/{batch_stamp}/"

    client = _get_document_service_client()
    request = discoveryengine_v1alpha.ImportDocumentsRequest(
        parent=_branch_resource_name(),
        gcs_source=discoveryengine_v1alpha.GcsSource(
            input_uris=[metadata_uri],
            data_schema="document",
        ),
        reconciliation_mode=discoveryengine_v1alpha.ImportDocumentsRequest.ReconciliationMode.INCREMENTAL,
        error_config=discoveryengine_v1alpha.ImportErrorConfig(gcs_prefix=error_log_prefix),
    )
    operation = client.import_documents(request=request)
    operation_name = operation.operation.name
    logger.info(
        "ImportDocuments submitted: operation=%s documents=%d metadata_uri=%s error_log_prefix=%s",
        operation_name, len(imported_ids), metadata_uri, error_log_prefix,
    )
    return BatchImportSubmission(
        metadata_uri=metadata_uri,
        operation_name=operation_name,
        document_ids=imported_ids,
        error_log_prefix=error_log_prefix,
    )


def poll_batch_import(operation_name: str) -> BatchImportResult:
    """Checks a previously submitted ImportDocuments operation without blocking.

    Deliberately does NOT use operation.result(), which polls until the import
    finishes — that would block a request handler for as long as indexing takes.
    This reads the operation's current state once and returns immediately.

    Discovery Engine reports per-document failures in the operation's *metadata*
    (success_count / failure_count) rather than by failing the operation itself,
    so an operation can be done AND have failures. error_samples is only a
    sample of those failures, which is enough to tell an operator what went
    wrong without fetching the full error export.
    """
    client = _get_document_service_client()
    operation = client.transport.operations_client.get_operation(operation_name)

    if not operation.done:
        return BatchImportResult(done=False)

    metadata = discoveryengine_v1alpha.ImportDocumentsMetadata.deserialize(
        operation.metadata.value
    )

    # An operation that failed outright (as opposed to per-document failures)
    # carries an error instead of a response.
    if operation.HasField("error"):
        return BatchImportResult(
            done=True,
            success_count=metadata.success_count,
            failure_count=metadata.failure_count or metadata.total_count,
            error_message=operation.error.message,
        )

    response = discoveryengine_v1alpha.ImportDocumentsResponse.deserialize(
        operation.response.value
    )
    error_message = "; ".join(sample.message for sample in response.error_samples)
    return BatchImportResult(
        done=True,
        success_count=metadata.success_count,
        failure_count=metadata.failure_count,
        error_message=error_message,
    )


def read_batch_error_log(error_log_prefix: str) -> list[str]:
    """Reads the FULL per-document failure list for a batch from the
    ImportErrorConfig.gcs_prefix path recorded at submit time (see
    trigger_batch_index), instead of the partial error_samples the operation
    response carries.

    Each line under that prefix is a JSON-encoded google.rpc.Status message —
    one per failed document. The Status itself carries no document_id field
    (see google.rpc.Status: code, message, details only); Discovery Engine
    embeds the offending document's identifying info as free text inside
    `message`, so an operator has to read these strings to work out which
    document(s) genuinely failed before calling /resolve-batch-failure.

    Returns an empty list if nothing was ever written there (either the batch
    still has 0 failures, or the operation isn't done yet).
    """
    from google.protobuf.json_format import Parse
    from google.rpc import status_pb2

    prefix = parse_gcs_uri(error_log_prefix)
    messages = []
    for blob_bytes in read_blobs_by_prefix(prefix=prefix):
        for line in blob_bytes.decode("utf-8").splitlines():
            if not line.strip():
                continue
            error_status = Parse(line, status_pb2.Status())
            messages.append(error_status.message)
    return messages


def read_batch_error_log_raw(error_log_prefix: str) -> bytes:
    """Returns the batch's error log exactly as Discovery Engine wrote it —
    every shard under error_log_prefix concatenated, one google.rpc.Status
    JSON object per line — for an operator to download and inspect directly,
    without going through read_batch_error_log's message-only extraction."""
    prefix = parse_gcs_uri(error_log_prefix)
    shards = read_blobs_by_prefix(prefix=prefix)
    return b"\n".join(shard.rstrip(b"\n") for shard in shards) + b"\n" if shards else b""


def get_chunked_document(gcs_uri: str) -> str:
    """Returns the raw JSON string of the chunked document content for the
    document backed by gcs_uri, as processed by the Data Store's chunking
    config. Raises google.api_core.exceptions.NotFound if the document hasn't
    been synced into the Data Store yet."""
    client = _get_document_service_client()
    document_id = compute_vertex_document_id(gcs_uri)
    request = discoveryengine_v1alpha.GetProcessedDocumentRequest(
        name=_document_resource_name(document_id),
        processed_document_type=(
            discoveryengine_v1alpha.GetProcessedDocumentRequest.ProcessedDocumentType.CHUNKED_DOCUMENT
        ),
    )
    response = client.get_processed_document(request=request)
    return response.json_data


def delete_document(gcs_uri: str) -> None:
    """Deletes the Discovery Engine document backed by gcs_uri from the Data
    Store. Raises google.api_core.exceptions.NotFound if the document was
    never synced into the Data Store (e.g. the GCS upload's own
    trigger_document_index call failed, or streaming sync hadn't picked it up
    yet) — callers should treat that as "already gone", not an error."""
    client = _get_document_service_client()
    document_id = compute_vertex_document_id(gcs_uri)
    request = discoveryengine_v1alpha.DeleteDocumentRequest(
        name=_document_resource_name(document_id),
    )
    client.delete_document(request=request)
