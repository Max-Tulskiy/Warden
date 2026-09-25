"""The operations behind the connection window and its command line.

Nothing here touches an operating system: the folder the files live in and the
service that reads them are handed in, so all of it runs, and is tested, on any
platform. The window and the installer's helper are thin callers of this module.
"""

import hashlib
import re
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

import httpx

from warden_agent.core.transport import (
    FailureKind,
    build_ssl_context,
    classify_failure,
)

#: How long the window waits for a server before calling it unreachable.
CHECK_TIMEOUT_SECONDS = 10.0

#: What a server may send as its authority; a certificate is far smaller.
MAX_OFFER_BYTES = 64 * 1024

_CERTIFICATE_BLOCK = re.compile(
    r"-----BEGIN CERTIFICATE-----\r?\n[A-Za-z0-9+/=\r\n]+?-----END CERTIFICATE-----"
)

_NAME_SHORT = {
    "commonName": "CN",
    "organizationName": "O",
    "organizationalUnitName": "OU",
    "countryName": "C",
}


class NoAuthorityError(Exception):
    """The server does not publish an authority of its own."""


class InvalidAuthorityError(ValueError):
    """What the server offered as its authority is not a certificate."""


@dataclass(frozen=True)
class TrustOffer:
    """A certificate authority the server offers, described by what was computed here.

    Every field comes from the certificate itself: the fingerprint is the SHA-256
    of its DER form, worked out on this machine, never a value the server
    reported, so an administrator compares what the certificate really is.
    """

    pem: str
    sha256: str
    subject: str
    not_before: datetime
    not_after: datetime

    @property
    def fingerprint(self) -> str:
        """The SHA-256 as people compare it: upper case, in pairs joined by colons."""
        return ":".join(
            self.sha256[i : i + 2].upper() for i in range(0, len(self.sha256), 2)
        )


_Name = tuple[tuple[tuple[str, str], ...], ...]


def _format_name(name: _Name) -> str:
    parts = [
        f"{_NAME_SHORT.get(key, key)}={value}"
        for relative in name
        for key, value in relative
    ]
    return ", ".join(parts)


def _seconds_to_datetime(text: str) -> datetime:
    return datetime.fromtimestamp(ssl.cert_time_to_seconds(text), UTC)


def offer_from_reply(body: Any) -> TrustOffer:
    """Turn the server's reply into an offer, trusting only the certificate in it.

    Only the first certificate block of `pem` is kept, so what is later saved is
    exactly what was fingerprinted. The reply's own `sha256` is ignored.
    """
    pem = body.get("pem") if isinstance(body, dict) else None
    block = _CERTIFICATE_BLOCK.search(pem) if isinstance(pem, str) else None
    if block is None:
        raise InvalidAuthorityError("the reply holds no certificate")
    single = block.group(0).replace("\r", "") + "\n"

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    try:
        context.load_verify_locations(cadata=single)
        der = ssl.PEM_cert_to_DER_cert(single)
    except (ssl.SSLError, ValueError) as exc:
        raise InvalidAuthorityError("the reply's certificate cannot be read") from exc
    loaded = context.get_ca_certs()
    if len(loaded) != 1:
        raise InvalidAuthorityError("the reply's certificate cannot be read")

    info = loaded[0]
    return TrustOffer(
        pem=single,
        sha256=hashlib.sha256(der).hexdigest(),
        subject=_format_name(cast("_Name", info["subject"])),
        not_before=_seconds_to_datetime(cast("str", info["notBefore"])),
        not_after=_seconds_to_datetime(cast("str", info["notAfter"])),
    )


async def fetch_authority(server_url: str) -> TrustOffer:
    """Ask a server for its own certificate authority, before it is trusted.

    This is the one request the agent makes without checking the server's
    certificate, and it has to be: the authority that would let it check is
    exactly what is being asked for. It sends nothing but the request itself, no
    token and no key, and its answer is used only after an administrator has
    compared the fingerprint (or a fingerprint given in advance matches).

    Raises `NoAuthorityError` for a server with no authority of its own,
    `InvalidAuthorityError` for a reply that is not a certificate, and the
    `httpx` errors for a server that cannot be reached.
    """
    async with httpx.AsyncClient(
        base_url=server_url,
        # The one deliberately unverified request; see the docstring above.
        verify=False,  # noqa: S501  # nosec B501
        timeout=CHECK_TIMEOUT_SECONDS,
    ) as client:
        response = await client.get("/api/v1/tls/ca")
    if response.status_code == httpx.codes.NOT_FOUND:
        raise NoAuthorityError(server_url)
    response.raise_for_status()
    if len(response.content) > MAX_OFFER_BYTES:
        raise InvalidAuthorityError("the reply is too large to be a certificate")
    try:
        body = response.json()
    except ValueError as exc:
        raise InvalidAuthorityError("the reply is not JSON") from exc
    return offer_from_reply(body)


class ProbeKind(StrEnum):
    TRUSTED = "trusted"
    NOT_TRUSTED = "not_trusted"
    UNREACHABLE = "unreachable"
    UNEXPECTED = "unexpected"


@dataclass(frozen=True)
class ProbeResult:
    kind: ProbeKind
    status_code: int | None = None


async def probe(
    server_url: str, *, ca_file: Path | None = None, extra_ca_pem: str | None = None
) -> ProbeResult:
    """Reach the server's health check with certificate checking on.

    `ca_file` is the authority already configured, `extra_ca_pem` one being
    considered but not yet saved. Raises `NotConfiguredError` when `ca_file`
    cannot be used.
    """
    context = build_ssl_context(ca_file)
    if extra_ca_pem is not None:
        context.load_verify_locations(cadata=extra_ca_pem)
    try:
        async with httpx.AsyncClient(
            base_url=server_url, verify=context, timeout=CHECK_TIMEOUT_SECONDS
        ) as client:
            response = await client.get("/health")
    except httpx.HTTPError as exc:
        if classify_failure(exc) is FailureKind.CERTIFICATE_NOT_TRUSTED:
            return ProbeResult(ProbeKind.NOT_TRUSTED)
        return ProbeResult(ProbeKind.UNREACHABLE)
    if _is_health_reply(response):
        return ProbeResult(ProbeKind.TRUSTED)
    return ProbeResult(ProbeKind.UNEXPECTED, response.status_code)


def _is_health_reply(response: httpx.Response) -> bool:
    if response.status_code != httpx.codes.OK:
        return False
    try:
        body = response.json()
    except ValueError:
        return False
    return isinstance(body, dict) and body.get("status") == "ok"
