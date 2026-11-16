"""Shared SNI-pinning proxy adapter for routing Google API traffic through the
internal F5 gateway.

The F5 gateway terminates TLS for `*.googleapis.com` hosts based on SNI only
and forwards to the real Google backend — it is not a distinct API endpoint
and does not care about the TCP-level Host header being correct, but the
backend behind it does care and returns a generic Google 404 page unless the
HTTP `Host` header is also the real hostname (e.g. `storage.googleapis.com`).

Verified manually against the real gateway:
- `curl --resolve storage.googleapis.com:443:10.6.116.2 https://storage.googleapis.com/storage/v1/b`
  returns a genuine storage.googleapis.com certificate (Google Trust Services)
  and a real GCS API JSON error body.
- A `requests` session whose connection pool connects to 10.6.116.2 with
  `server_hostname="storage.googleapis.com"` (for SNI/cert validation) and an
  explicit `Host: storage.googleapis.com` header returns the same kind of real
  GCS JSON response (e.g. `401 Anonymous caller does not have ... access`).
- The gateway's cert SAN list includes `*.googleapis.com`, so any Google API
  hostname (e.g. `discoveryengine.googleapis.com`) can be pinned the same way.

So the fix is at the connection-pool level: connect to the proxy IP, but keep
SNI and the Host header pinned to the real hostname. This is NOT the same as
a `client_options={"api_endpoint": ...}` override (that would change what
host the client library itself thinks it's talking to) and NOT the same as
HTTPS_PROXY (the gateway isn't a forward/CONNECT proxy).
"""

import requests
import requests.adapters
from urllib3.connectionpool import HTTPSConnectionPool


class _SniPinnedHTTPSConnectionPool(HTTPSConnectionPool):
    """Connects to a fixed proxy IP/port while keeping SNI on a pinned hostname."""

    def __init__(self, *args, proxy_host: str, proxy_port: int, pinned_host: str, **kwargs):
        self._proxy_host = proxy_host
        self._proxy_port = proxy_port
        self._pinned_host = pinned_host
        super().__init__(*args, **kwargs)

    def _new_conn(self):
        self.num_connections += 1
        return self.ConnectionCls(
            host=self._proxy_host,
            port=self._proxy_port,
            timeout=self.timeout.connect_timeout,
            server_hostname=self._pinned_host,
            **self.conn_kw,
        )


class GoogleApiF5ProxyAdapter(requests.adapters.HTTPAdapter):
    """Routes requests to a pinned Google hostname through the internal F5 gateway.

    Only affects connections whose pool host matches the pinned hostname (this
    adapter is mounted solely on that host's `https://` prefix), so it cannot
    accidentally redirect unrelated traffic.
    """

    def __init__(self, proxy_host: str, proxy_port: int, pinned_host: str, *args, **kwargs):
        self._proxy_host = proxy_host
        self._proxy_port = proxy_port
        self._pinned_host = pinned_host
        super().__init__(*args, **kwargs)

    def get_connection_with_tls_context(self, request, verify, proxies=None, cert=None):
        pool = super().get_connection_with_tls_context(request, verify, proxies=proxies, cert=cert)
        if pool.host == self._pinned_host and not isinstance(pool, _SniPinnedHTTPSConnectionPool):
            pool.__class__ = _SniPinnedHTTPSConnectionPool
            pool._proxy_host = self._proxy_host
            pool._proxy_port = self._proxy_port
            pool._pinned_host = self._pinned_host
        return pool

    def send(self, request, **kwargs):
        request.headers.setdefault("Host", self._pinned_host)
        return super().send(request, **kwargs)


def mount_f5_proxy(session: requests.Session, *, proxy_host: str, proxy_port: int, pinned_host: str) -> None:
    """Mounts the F5 proxy adapter onto `session` for the given pinned hostname."""
    session.mount(
        f"https://{pinned_host}",
        GoogleApiF5ProxyAdapter(proxy_host=proxy_host, proxy_port=proxy_port, pinned_host=pinned_host),
    )
