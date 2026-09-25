"""The operations behind the connection window and its command line.

Nothing here touches an operating system: the folder the files live in and the
service that reads them are handed in, so all of it runs, and is tested, on any
platform. The window and the installer's helper are thin callers of this module.
"""

import hashlib
import json
import logging
import re
import socket
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

import httpx

from warden_agent.collectors.registry import current_platform
from warden_agent.configurator.backend import ServiceState
from warden_agent.configurator.config_file import (
    UnsupportedConfigError,
    check_writable,
    read_config,
    write_config,
)
from warden_agent.configurator.paths import AgentPaths
from warden_agent.core.transport import (
    EnrollmentError,
    FailureKind,
    ServerClient,
    build_ssl_context,
    classify_failure,
)
from warden_agent.errors import NotConfiguredError
from warden_agent.fileio import write_atomically
from warden_agent.state import AgentState, same_server
from warden_agent.status import AgentStatus, StatusStore

logger = logging.getLogger(__name__)

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


def normalize_fingerprint(text: str) -> str | None:
    """A SHA-256 typed or pasted by a person, as 64 lowercase hex characters.

    Colons, spaces, dashes and case do not matter; anything that is not exactly
    a SHA-256 gives `None`.
    """
    cleaned = re.sub(r"[\s:\-]", "", text).lower()
    return cleaned if re.fullmatch(r"[0-9a-f]{64}", cleaned) else None


class RefusalReason(StrEnum):
    """Why a station was not connected. Nothing is stored for any of them."""

    INVALID_ADDRESS = "invalid_address"
    INVALID_FINGERPRINT = "invalid_fingerprint"
    NOT_ENROLLED = "not_enrolled"
    # The two TOKEN_* members are reason codes, not tokens: the password
    # checks read the name (S105, B105) and are silenced on those lines.
    TOKEN_MISSING = "token_missing"  # noqa: S105  # nosec B105
    UNREACHABLE = "unreachable"
    UNEXPECTED_REPLY = "unexpected_reply"
    NO_AUTHORITY = "no_authority"
    AUTHORITY_INVALID = "authority_invalid"
    FINGERPRINT_MISMATCH = "fingerprint_mismatch"
    CERTIFICATE_NOT_TRUSTED = "certificate_not_trusted"
    TOKEN_REFUSED = "token_refused"  # noqa: S105  # nosec B105
    SERVER_ERROR = "server_error"
    NEEDS_REPLACE = "needs_replace"
    CONFIG_UNSUPPORTED = "config_unsupported"
    WRITE_FAILED = "write_failed"


@dataclass(frozen=True)
class Connected:
    server_url: str
    agent_id: str
    #: True when the station was enrolled with this server already and nothing
    #: was done.
    already: bool = False


@dataclass(frozen=True)
class TrustNeeded:
    """The server's certificate is not trusted, and this authority is on offer.

    Nothing has been stored. The caller asks an administrator to compare
    `offer.fingerprint` and, once confirmed, calls `connect` again with `trust`.
    """

    offer: TrustOffer


@dataclass(frozen=True)
class Refused:
    reason: RefusalReason
    detail: str | None = None
    expected: str | None = None
    actual: str | None = None
    current_server: str | None = None


Outcome = Connected | TrustNeeded | Refused


class ConfiguratorLog:
    """The record of what the window and the installer's helper decided (R-18).

    One line per event, English, never holding a token. A write that fails is
    logged and dropped: keeping the record must not stop a connection.
    """

    def __init__(
        self, path: Path, *, now: Callable[[], datetime] = lambda: datetime.now(UTC)
    ) -> None:
        self._path = path
        self._now = now

    def write(self, event: str, **fields: str | int | None) -> None:
        parts = [self._now().isoformat(), event]
        for key, value in fields.items():
            if value is not None:
                text = str(value)
                parts.append(f"{key}={json.dumps(text) if ' ' in text else text}")
        try:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(" ".join(parts) + "\n")
        except OSError:
            logger.warning("could not write the configurator log %s", self._path)


def _valid_address(address: str) -> bool:
    try:
        url = httpx.URL(address)
    except httpx.InvalidURL:
        return False
    return url.scheme in ("http", "https") and bool(url.host)


def _refuse(log: ConfiguratorLog, refused: Refused) -> Refused:
    log.write(
        "refused",
        reason=refused.reason.value,
        detail=refused.detail,
        expected=refused.expected,
        actual=refused.actual,
    )
    return refused


@dataclass(frozen=True)
class _Request:
    server_url: str
    token: str
    trust: TrustOffer | None
    expected_sha256: str | None
    replace: bool


@dataclass(frozen=True)
class _Plan:
    """What a connection attempt has settled before it touches the network."""

    server_url: str
    expected: str | None
    config: dict[str, Any]
    values: dict[str, Any]
    server_changed: bool
    ca_file: Path | None


@dataclass(frozen=True)
class _Trusted:
    """The authority to trust for this enrollment, if the system's own is not enough."""

    candidate: TrustOffer | None


def _plan(  # noqa: PLR0911
    paths: AgentPaths, log: ConfiguratorLog, request: _Request
) -> _Plan | Connected | Refused:
    server_url, token = request.server_url, request.token
    expected_sha256, replace = request.expected_sha256, request.replace
    if not _valid_address(server_url):
        return _refuse(log, Refused(RefusalReason.INVALID_ADDRESS))
    expected = None
    if expected_sha256 is not None:
        expected = normalize_fingerprint(expected_sha256)
        if expected is None:
            return _refuse(log, Refused(RefusalReason.INVALID_FINGERPRINT))

    config = read_config(paths.config)
    state = AgentState.load(paths.state)
    server_changed = False
    if state.is_enrolled:
        current = state.server_url or config.get("server_url")
        if current is not None and same_server(str(current), server_url):
            log.write("already connected", server=server_url)
            return Connected(server_url, str(state.agent_id), already=True)
        if not replace:
            return _refuse(
                log, Refused(RefusalReason.NEEDS_REPLACE, current_server=current)
            )
        server_changed = True
        log.write("server changed", old=current, new=server_url)

    if not token.strip():
        return _refuse(log, Refused(RefusalReason.TOKEN_MISSING))

    values = {**config, "server_url": server_url}
    values.pop("enrollment_token", None)
    try:
        check_writable(values)
    except UnsupportedConfigError as exc:
        return _refuse(log, Refused(RefusalReason.CONFIG_UNSUPPORTED, detail=str(exc)))

    return _Plan(
        server_url=server_url,
        expected=expected,
        config=config,
        values=values,
        server_changed=server_changed,
        ca_file=_usable_authority(config, server_changed=server_changed),
    )


def _usable_authority(config: dict[str, Any], *, server_changed: bool) -> Path | None:
    """The configured authority, unless it belongs to another server or is unusable."""
    if server_changed or not config.get("ca_file"):
        return None
    ca_file = Path(str(config["ca_file"]))
    try:
        build_ssl_context(ca_file)
    except NotConfiguredError:
        return None
    return ca_file


def _refusal_for(probed: ProbeResult) -> Refused | None:
    if probed.kind is ProbeKind.UNREACHABLE:
        return Refused(RefusalReason.UNREACHABLE)
    if probed.kind is ProbeKind.UNEXPECTED:
        return Refused(RefusalReason.UNEXPECTED_REPLY, detail=str(probed.status_code))
    return None


async def _fetch_offer(plan: _Plan, log: ConfiguratorLog) -> TrustOffer | Refused:
    try:
        offer = await fetch_authority(plan.server_url)
    except NoAuthorityError:
        return _refuse(log, Refused(RefusalReason.NO_AUTHORITY))
    except InvalidAuthorityError:
        return _refuse(log, Refused(RefusalReason.AUTHORITY_INVALID))
    except httpx.HTTPError:
        return _refuse(log, Refused(RefusalReason.UNREACHABLE))
    log.write("trust offered", sha256=offer.sha256, subject=offer.subject)
    return offer


async def _accept(
    plan: _Plan, log: ConfiguratorLog, offer: TrustOffer
) -> _Trusted | Refused:
    """Take `offer` as the authority to trust, once it matches and really verifies."""
    if plan.expected is not None and offer.sha256 != plan.expected:
        return _refuse(
            log,
            Refused(
                RefusalReason.FINGERPRINT_MISMATCH,
                expected=plan.expected,
                actual=offer.sha256,
            ),
        )
    verified = await probe(
        plan.server_url, ca_file=plan.ca_file, extra_ca_pem=offer.pem
    )
    if verified.kind is not ProbeKind.TRUSTED:
        return _refuse(log, Refused(RefusalReason.CERTIFICATE_NOT_TRUSTED))
    log.write(
        "trust accepted",
        sha256=offer.sha256,
        by="expected fingerprint" if plan.expected is not None else "confirmation",
    )
    return _Trusted(offer)


async def _establish_trust(
    plan: _Plan, log: ConfiguratorLog, trust: TrustOffer | None
) -> _Trusted | TrustNeeded | Refused:
    probed = await probe(plan.server_url, ca_file=plan.ca_file)
    refusal = _refusal_for(probed)
    if refusal is not None:
        return _refuse(log, refusal)
    if probed.kind is ProbeKind.TRUSTED:
        return _Trusted(None)

    offer = trust
    if offer is None:
        fetched = await _fetch_offer(plan, log)
        if isinstance(fetched, Refused):
            return fetched
        if plan.expected is None:
            return TrustNeeded(fetched)
        offer = fetched
    return await _accept(plan, log, offer)


async def _enroll(
    plan: _Plan, log: ConfiguratorLog, candidate: TrustOffer | None, token: str
) -> AgentState | Refused:
    context = build_ssl_context(plan.ca_file)
    if candidate is not None:
        context.load_verify_locations(cadata=candidate.pem)
    client = ServerClient(plan.server_url, verify=context)
    try:
        agent_id, agent_key = await client.enroll(
            token=token.strip(),
            hostname=str(plan.config.get("hostname") or socket.gethostname()),
            os_name=current_platform(),
        )
    except EnrollmentError as exc:
        return _refuse(log, Refused(RefusalReason.TOKEN_REFUSED, detail=str(exc)))
    except httpx.HTTPStatusError as exc:
        return _refuse(
            log,
            Refused(RefusalReason.SERVER_ERROR, detail=str(exc.response.status_code)),
        )
    except httpx.HTTPError as exc:
        untrusted = classify_failure(exc) is FailureKind.CERTIFICATE_NOT_TRUSTED
        return _refuse(
            log,
            Refused(
                RefusalReason.CERTIFICATE_NOT_TRUSTED
                if untrusted
                else RefusalReason.UNREACHABLE
            ),
        )
    finally:
        await client.aclose()
    return AgentState(
        agent_id=agent_id, agent_key=agent_key, server_url=plan.server_url
    )


async def connect(  # noqa: PLR0913 -- each is an independent option of the flow
    paths: AgentPaths,
    *,
    server_url: str,
    token: str,
    trust: TrustOffer | None = None,
    expected_sha256: str | None = None,
    replace: bool = False,
) -> Outcome:
    """Connect this station to a server, or say why it was not.

    The whole flow: check the address, see whether the server's certificate is
    trusted, and if not fetch its authority and either return it for a person
    to confirm or accept it against a fingerprint given in advance; then enroll
    over a connection that trusts it. Only after the enrollment has succeeded is
    anything written, and the state file goes last, so a station is either
    enrolled or exactly as it was. The token is used once and never stored.

    `trust` is an offer a person has confirmed; `expected_sha256` a fingerprint
    given in advance (a silent install), which makes the authority acceptable
    without a prompt only if it matches. `replace` confirms moving an enrolled
    station to another server.
    """
    paths = paths.following_config()
    log = ConfiguratorLog(paths.log)
    server_url = server_url.strip().rstrip("/")
    log.write("connect", server=server_url)

    plan = _plan(
        paths, log, _Request(server_url, token, trust, expected_sha256, replace)
    )
    if isinstance(plan, Connected | Refused):
        return plan
    trusted = await _establish_trust(plan, log, trust)
    if isinstance(trusted, TrustNeeded | Refused):
        return trusted
    enrolled = await _enroll(plan, log, trusted.candidate, token)
    if isinstance(enrolled, Refused):
        return enrolled
    refused = _commit(paths, plan, trusted.candidate, enrolled, log)
    if refused is not None:
        return refused
    log.write("enrolled", server=server_url, agent=enrolled.agent_id)
    return Connected(server_url, str(enrolled.agent_id))


def _restore(path: Path, previous: bytes | None) -> None:
    try:
        if previous is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(previous)
    except OSError:
        logger.warning("could not restore %s", path)


def _commit(
    paths: AgentPaths,
    plan: _Plan,
    candidate: TrustOffer | None,
    state: AgentState,
    log: ConfiguratorLog,
) -> Refused | None:
    """Save the authority, the configuration, and last the state, or none of them."""
    previous_config = paths.config.read_bytes() if paths.config.exists() else None
    previous_authority = (
        paths.authority.read_bytes() if paths.authority.exists() else None
    )
    values = dict(plan.values)
    try:
        if candidate is not None:
            write_atomically(paths.authority, candidate.pem)
            values["ca_file"] = paths.authority
        elif plan.server_changed:
            values.pop("ca_file", None)
            paths.authority.unlink(missing_ok=True)
        write_config(paths.config, values)
        # The state file is the commit point: an agent with a key and no
        # matching configuration is merely not connected yet.
        state.save(paths.state)
    except OSError as exc:
        _restore(paths.config, previous_config)
        _restore(paths.authority, previous_authority)
        return _refuse(
            log, Refused(RefusalReason.WRITE_FAILED, detail=type(exc).__name__)
        )
    return None


def _enrolled_server(paths: AgentPaths) -> tuple[AgentState, str] | None:
    """The state and the server of an enrolled station; `None` if it is not one."""
    state = AgentState.load(paths.state)
    if not state.is_enrolled:
        return None
    server = state.server_url or read_config(paths.config).get("server_url")
    return (state, str(server)) if server else None


async def begin_retrust(paths: AgentPaths) -> TrustNeeded | Refused:
    """Ask an enrolled station's server for the authority it now uses.

    For a server that was rebuilt and so issues certificates from a new authority
    the station has never seen. Nothing is stored; the caller has the
    fingerprint compared and then calls `retrust`.
    """
    paths = paths.following_config()
    log = ConfiguratorLog(paths.log)
    enrolled = _enrolled_server(paths)
    if enrolled is None:
        return _refuse(log, Refused(RefusalReason.NOT_ENROLLED))
    _, server = enrolled
    try:
        offer = await fetch_authority(server)
    except NoAuthorityError:
        return _refuse(log, Refused(RefusalReason.NO_AUTHORITY))
    except InvalidAuthorityError:
        return _refuse(log, Refused(RefusalReason.AUTHORITY_INVALID))
    except httpx.HTTPError:
        return _refuse(log, Refused(RefusalReason.UNREACHABLE))
    log.write(
        "trust offered", server=server, sha256=offer.sha256, subject=offer.subject
    )
    return TrustNeeded(offer)


async def retrust(
    paths: AgentPaths, *, offer: TrustOffer, expected_sha256: str | None = None
) -> Connected | Refused:
    """Trust `offer` for a station that is already enrolled, without enrolling again.

    The offer must match `expected_sha256` when one is given and must really
    verify the server, or nothing is changed. The station's id and key are left
    alone: only the authority it trusts is replaced.
    """
    paths = paths.following_config()
    log = ConfiguratorLog(paths.log)
    enrolled = _enrolled_server(paths)
    if enrolled is None:
        return _refuse(log, Refused(RefusalReason.NOT_ENROLLED))
    state, server = enrolled
    if expected_sha256 is not None:
        expected = normalize_fingerprint(expected_sha256)
        if expected is None:
            return _refuse(log, Refused(RefusalReason.INVALID_FINGERPRINT))
        if offer.sha256 != expected:
            return _refuse(
                log,
                Refused(
                    RefusalReason.FINGERPRINT_MISMATCH,
                    expected=expected,
                    actual=offer.sha256,
                ),
            )
    verified = await probe(server, extra_ca_pem=offer.pem)
    if verified.kind is not ProbeKind.TRUSTED:
        return _refuse(log, Refused(RefusalReason.CERTIFICATE_NOT_TRUSTED))

    config = read_config(paths.config)
    values = {**config, "server_url": config.get("server_url", server)}
    previous_config = paths.config.read_bytes() if paths.config.exists() else None
    previous_authority = (
        paths.authority.read_bytes() if paths.authority.exists() else None
    )
    try:
        check_writable(values)
        write_atomically(paths.authority, offer.pem)
        write_config(paths.config, {**values, "ca_file": paths.authority})
    except (OSError, UnsupportedConfigError) as exc:
        _restore(paths.config, previous_config)
        _restore(paths.authority, previous_authority)
        return _refuse(
            log, Refused(RefusalReason.WRITE_FAILED, detail=type(exc).__name__)
        )
    log.write("trust accepted", server=server, sha256=offer.sha256, by="re-trust")
    return Connected(server, str(state.agent_id), already=True)


@dataclass(frozen=True)
class StationStatus:
    """What the window shows about the station (R-2)."""

    service: ServiceState
    enrolled: bool
    #: The server the station's key was issued by, when it is enrolled.
    enrolled_server: str | None
    #: The address in the configuration, to fill the window's field with.
    configured_server: str | None
    #: Whether the configuration names an authority the station trusts.
    trusts_authority: bool
    agent: AgentStatus


def read_status(paths: AgentPaths, service: ServiceState) -> StationStatus:
    paths = paths.following_config()
    config = read_config(paths.config)
    enrolled = _enrolled_server(paths)
    configured = config.get("server_url")
    return StationStatus(
        service=service,
        enrolled=enrolled is not None,
        enrolled_server=None if enrolled is None else enrolled[1],
        configured_server=None if configured is None else str(configured),
        trusts_authority=bool(config.get("ca_file")),
        agent=StatusStore(paths.status).read(),
    )
