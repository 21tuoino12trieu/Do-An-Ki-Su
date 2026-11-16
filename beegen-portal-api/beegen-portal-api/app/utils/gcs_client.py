"""GCS client routed through the internal F5 gateway (10.6.116.2:443).

The F5 gateway terminates TLS for `storage.googleapis.com` based on SNI only
and forwards to the real GCS backend — it is not a distinct API endpoint and
does not care about the TCP-level Host header being correct, but the GCS
backend behind it does care and returns a generic Google 404 page unless the
HTTP `Host` header is also `storage.googleapis.com`.

Verified manually against the real gateway:
- `curl --resolve storage.googleapis.com:443:10.6.116.2 https://storage.googleapis.com/storage/v1/b`
  returns a genuine storage.googleapis.com certificate (Google Trust Services)
  and a real GCS API JSON error body.
- A `requests` session whose connection pool connects to 10.6.116.2 with
  `server_hostname="storage.googleapis.com"` (for SNI/cert validation) and an
  explicit `Host: storage.googleapis.com` header returns the same kind of real
  GCS JSON response (e.g. `401 Anonymous caller does not have ... access`).

So the fix is at the connection-pool level: connect to the proxy IP, but keep
SNI and the Host header pinned to the real GCS hostname. This is NOT the same
as a `client_options={"api_endpoint": ...}` override (that would change what
host google-cloud-storage itself thinks it's talking to) and NOT the same as
HTTPS_PROXY (the gateway isn't a forward/CONNECT proxy).
"""

import os
from functools import lru_cache

import google.auth.transport.requests as google_requests
import requests
from google.cloud import storage

from app.utils.f5_proxy import mount_f5_proxy

GCS_PINNED_HOST = "storage.googleapis.com"
OAUTH_PINNED_HOST = "oauth2.googleapis.com"


def _build_proxied_authorized_session(credentials) -> google_requests.AuthorizedSession:
    proxy_host = os.environ["GCS_PROXY_HOST"]
    proxy_port = int(os.environ.get("GCS_PROXY_PORT", "443"))

    # The internal network has no direct route to Google's public endpoints —
    # only the F5 gateway is reachable. That gateway also serves
    # oauth2.googleapis.com by SNI (same as storage.googleapis.com), so the
    # OAuth token-refresh call AuthorizedSession makes internally (on its own
    # separate auth-request session, for `authorized_user`-type credentials)
    # needs the same proxy adapter mounted, or it tries to connect directly
    # and gets RemoteDisconnected.
    #
    # Corporate TLS-inspecting proxy presents a self-signed root CA for
    # oauth2.googleapis.com that Python's certifi bundle doesn't trust, even
    # though Windows' OS trust store does. TEMPORARY bypass for local testing
    # — replace with the corporate root CA bundle (REQUESTS_CA_BUNDLE /
    # verify=<path>) before shipping this.
    if os.environ.get("GCS_INSECURE_SKIP_OAUTH_TLS_VERIFY") == "1":
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        auth_request_session = requests.Session()
        auth_request_session.verify = False
    else:
        auth_request_session = requests.Session()

    auth_request_session.trust_env = False
    mount_f5_proxy(auth_request_session, proxy_host=proxy_host, proxy_port=proxy_port, pinned_host=OAUTH_PINNED_HOST)
    auth_request = google_requests.Request(session=auth_request_session)
    session = google_requests.AuthorizedSession(credentials, auth_request=auth_request)

    session.trust_env = False
    mount_f5_proxy(session, proxy_host=proxy_host, proxy_port=proxy_port, pinned_host=GCS_PINNED_HOST)
    return session


@lru_cache()
def get_gcs_client() -> storage.Client:
    """Returns a cached google-cloud-storage Client routed through the F5 gateway.

    Requires env vars: GCS_PROJECT_ID, GCS_BUCKET_NAME, GCS_PROXY_HOST,
    GCS_PROXY_PORT (default 443), and standard GOOGLE_APPLICATION_CREDENTIALS
    for service-account auth (read by google.auth.default()).
    """
    import google.auth

    project_id = os.environ["GCS_PROJECT_ID"]
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/devstorage.read_write"]
    )
    session = _build_proxied_authorized_session(credentials)
    return storage.Client(project=project_id, credentials=credentials, _http=session)


def get_gcs_bucket_name() -> str:
    return os.environ["GCS_BUCKET_NAME"]


def upload_bytes_to_gcs(*, blob_path: str, content: bytes, content_type: str | None) -> str:
    """Uploads bytes to GCS and returns the resulting gs:// URI."""
    client = get_gcs_client()
    bucket = client.bucket(get_gcs_bucket_name())
    blob = bucket.blob(blob_path)
    blob.upload_from_string(content, content_type=content_type)
    return f"gs://{get_gcs_bucket_name()}/{blob_path}"


def upload_stream_to_gcs(*, blob_path: str, stream, content_type: str | None) -> str:
    """Uploads a file-like object to GCS in a streaming fashion and returns the
    resulting gs:// URI.

    Unlike upload_bytes_to_gcs, this never holds the whole payload in memory as
    a single bytes object — blob.upload_from_file() reads from `stream` in
    chunks. That matters for the document-ingestion HTML, which can reach ~10MB
    per document.

    `stream` must be a binary file-like object (anything with .read()); an
    io.BytesIO wrapping already-loaded bytes works too, and is what the S3 read
    path currently provides.
    """
    client = get_gcs_client()
    bucket = client.bucket(get_gcs_bucket_name())
    blob = bucket.blob(blob_path)
    blob.upload_from_file(stream, content_type=content_type)
    return f"gs://{get_gcs_bucket_name()}/{blob_path}"


def parse_gcs_uri(gcs_uri: str) -> str:
    """Recovers the blob path from a stored gs://{bucket}/{blob_path} URI,
    the inverse of the path construction done in upload_bytes_to_gcs."""
    prefix = f"gs://{get_gcs_bucket_name()}/"
    if not gcs_uri.startswith(prefix):
        raise ValueError(f"gcs_uri '{gcs_uri}' does not start with expected prefix '{prefix}'")
    return gcs_uri[len(prefix):]


def read_blobs_by_prefix(*, prefix: str) -> list[bytes]:
    """Reads every blob under a GCS prefix, in whatever shard order the API
    lists them. Used for ImportErrorConfig.gcs_prefix output, which Discovery
    Engine may split across multiple shard files under the same prefix."""
    client = get_gcs_client()
    bucket = client.bucket(get_gcs_bucket_name())
    return [blob.download_as_bytes() for blob in client.list_blobs(bucket, prefix=prefix)]


def delete_blob_from_gcs(*, blob_path: str) -> None:
    """Deletes a blob from GCS. Raises google.api_core.exceptions.NotFound if
    it doesn't exist."""
    client = get_gcs_client()
    bucket = client.bucket(get_gcs_bucket_name())
    blob = bucket.blob(blob_path)
    blob.delete()
