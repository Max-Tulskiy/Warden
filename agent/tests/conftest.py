"""Shared test configuration.

`tls_server` is a real HTTPS server on localhost, on a thread, whose
certificate comes from a throwaway `trustme` authority. The connection-window
tests run genuine TLS handshakes against it, so verification, refusal, and the
trust step are the real thing, never a stub of a certificate store.
"""

import json
import os
import socket
import ssl
import threading
from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
import trustme

# Qt has no display on a CI runner; the window tests run on its offscreen
# platform. Set before anything imports PySide6, and only when the environment
# has not chosen a platform itself.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@dataclass
class RecordedRequest:
    method: str
    path: str
    headers: dict[str, str]
    body: bytes


Route = Callable[[RecordedRequest], tuple[int, Any]]


@dataclass
class TlsTestServer:
    """Scripted answers, a record of every request, and a swappable authority."""

    url: str = ""
    requests: list[RecordedRequest] = field(default_factory=list)
    routes: dict[tuple[str, str], Route] = field(default_factory=dict)
    _authority: trustme.CA | None = None
    _context: ssl.SSLContext | None = None

    @property
    def authority_pem(self) -> str:
        assert self._authority is not None
        return self._authority.cert_pem.bytes().decode("ascii")

    def rotate_authority(self) -> None:
        """Serve from a brand-new authority, as a rebuilt server would."""
        self._authority = trustme.CA()
        self._context = _server_context(self._authority)

    def answer(self, method: str, path: str, status: int = 200, body: Any = None):
        """Always answer `method path` with `status` and a JSON `body`."""
        self.routes[(method, path)] = lambda _request: (status, body)

    def on(self, method: str, path: str, route: Route) -> None:
        self.routes[(method, path)] = route


def _server_context(authority: trustme.CA) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    authority.issue_cert("localhost", "127.0.0.1").configure_cert(context)
    return context


@pytest.fixture
def tls_server() -> Generator[TlsTestServer]:
    owner = TlsTestServer()
    owner.rotate_authority()

    class Handler(BaseHTTPRequestHandler):
        def _handle(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            request = RecordedRequest(
                method=self.command,
                path=self.path,
                headers={key.lower(): value for key, value in self.headers.items()},
                body=self.rfile.read(length) if length else b"",
            )
            owner.requests.append(request)
            route = owner.routes.get((request.method, request.path))
            status, body = route(request) if route else (404, {"detail": "no route"})
            payload = json.dumps(body).encode() if body is not None else b""
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        do_GET = do_POST = do_PUT = do_DELETE = _handle

        def log_message(self, *args: object) -> None:
            pass

    class Server(ThreadingHTTPServer):
        def get_request(self):
            connection, address = super().get_request()
            # The handshake happens in the handler thread on first read, so a
            # client that refuses the certificate cannot stall accepting.
            assert owner._context is not None
            wrapped = owner._context.wrap_socket(
                connection, server_side=True, do_handshake_on_connect=False
            )
            return wrapped, address

        def handle_error(self, request, client_address) -> None:
            pass  # a client rejecting the certificate is an expected outcome

    server = Server(("127.0.0.1", 0), Handler)
    owner.url = f"https://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
    )
    thread.start()
    try:
        yield owner
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def unreachable_url() -> str:
    """An address on which nothing listens."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    return f"https://127.0.0.1:{port}"
