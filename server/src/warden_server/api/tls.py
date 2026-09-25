"""Publication of the server's own certificate authority (decision D-13).

In the default deployment the reverse proxy issues the server's certificate
from an authority of its own, which no workstation knows. A station that has
not enrolled yet cannot be authenticated, so this is readable without a
credential: it is a public certificate, and it is only ever trusted by an
agent after an administrator has compared its fingerprint.
"""

import hashlib
import re
import ssl
from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from warden_server.config import get_settings
from warden_server.schemas.tls import TlsAuthorityOut

router = APIRouter(prefix="/api/v1/tls", tags=["tls"])

#: The setting points at a certificate; a file larger than this is not one.
MAX_FILE_BYTES = 1024 * 1024

# Only a CERTIFICATE block is ever matched, so a file that also holds a
# private key can never hand the key out.
_CERTIFICATE_BLOCK = re.compile(
    r"-----BEGIN CERTIFICATE-----\r?\n[A-Za-z0-9+/=\r\n]+?-----END CERTIFICATE-----"
)

_NO_AUTHORITY = "The server has no certificate authority of its own"


def _first_certificate(path: Path) -> str | None:
    try:
        with path.open(encoding="ascii") as handle:
            text = handle.read(MAX_FILE_BYTES)
    except (OSError, UnicodeDecodeError):
        return None
    match = _CERTIFICATE_BLOCK.search(text)
    return None if match is None else match.group(0).replace("\r", "") + "\n"


@router.get(
    "/ca",
    response_model=TlsAuthorityOut,
    responses={404: {"description": "The server has no authority of its own"}},
)
def certificate_authority() -> TlsAuthorityOut:
    """The certificate authority behind the server's own certificate.

    Read from the configured file at every request, since the proxy creates
    its authority after the server may already be running. Only the first
    certificate of the file is returned. A deployment whose certificate comes
    from a public authority has no file, and the answer is 404: a station then
    relies on its system's own trust. This request is not written to the audit
    log: it is unauthenticated, public, and anyone could otherwise grow the log.
    """
    path = get_settings().tls_ca_path
    pem = None if path is None else _first_certificate(path)
    if pem is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NO_AUTHORITY)
    try:
        der = ssl.PEM_cert_to_DER_cert(pem)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NO_AUTHORITY) from None
    return TlsAuthorityOut(pem=pem, sha256=hashlib.sha256(der).hexdigest())
