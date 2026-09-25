"""HTTP client for talking to the server (constitution D-1, D-2).

Every method here is something the agent initiates; nothing in this module
listens for or accepts an incoming connection. Retries use exponential
backoff and only kick in for transport failures and 5xx responses -- a 4xx
(bad token, unknown task) means retrying the same request would just fail
again, so it is raised immediately instead.
"""

import asyncio
import logging
import ssl
from collections.abc import Awaitable, Callable
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import certifi
import httpx

from warden_agent.core.models import OutgoingEvent, TaskDTO
from warden_agent.errors import NotConfiguredError

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = {500, 502, 503, 504}


class EnrollmentError(RuntimeError):
    """Raised when the server rejects an enrollment token."""


class FailureKind(StrEnum):
    """What went wrong in a request to the server, in the terms a person acts on.

    The values are the codes the status file stores; the connection window turns
    them into Russian sentences, so no raw library text is ever stored or shown.
    """

    UNREACHABLE = "unreachable"
    CERTIFICATE_NOT_TRUSTED = "certificate_not_trusted"
    CREDENTIAL_REFUSED = "credential_refused"
    SERVER_ERROR = "server_error"
    OTHER = "other"


def _cause_chain(exc: BaseException) -> list[BaseException]:
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        chain.append(current)
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return chain


def _status_kind(code: int) -> FailureKind:
    if code in (httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN):
        return FailureKind.CREDENTIAL_REFUSED
    if code >= httpx.codes.INTERNAL_SERVER_ERROR:
        return FailureKind.SERVER_ERROR
    return FailureKind.OTHER


def classify_failure(exc: BaseException) -> FailureKind:
    """Sort a failed request into a `FailureKind`, walking the cause chain once."""
    chain = _cause_chain(exc)
    status_errors = [i for i in chain if isinstance(i, httpx.HTTPStatusError)]
    if any(isinstance(item, ssl.SSLCertVerificationError) for item in chain):
        return FailureKind.CERTIFICATE_NOT_TRUSTED
    if any(isinstance(item, EnrollmentError) for item in chain):
        return FailureKind.CREDENTIAL_REFUSED
    if status_errors:
        return _status_kind(status_errors[0].response.status_code)
    if any(isinstance(item, httpx.TransportError) for item in chain):
        return FailureKind.UNREACHABLE
    return FailureKind.OTHER


def build_ssl_context(ca_file: Path | None = None) -> ssl.SSLContext:
    """The context every agent request is verified with.

    The system's own store (which the `ssl` module loads by itself on Windows,
    so a certificate an organization distributes to its workstations works),
    the bundle shipped with `certifi` (httpx's own default, kept so trust the
    agent has today is not lost), and `ca_file` when one is configured. Nothing
    here turns checking off.
    """
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=certifi.where())
    if ca_file is not None:
        try:
            context.load_verify_locations(cafile=str(ca_file))
        except (OSError, ssl.SSLError) as exc:
            raise NotConfiguredError(
                f"the trusted authority {ca_file} cannot be used",
                reason="ca_unreadable",
            ) from exc
    return context


class ServerClient:
    # Every parameter after `base_url` is a keyword-only knob a caller or a test
    # injects on its own (timeouts, the transport, the sleep, the trust context).
    def __init__(  # noqa: PLR0913
        self,
        base_url: str,
        *,
        timeout: float = 10.0,
        max_attempts: int = 5,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        verify: ssl.SSLContext | None = None,
    ) -> None:
        # `verify` is an SSL context built by `build_ssl_context`; without one
        # httpx keeps its own default (the `certifi` bundle).
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            transport=transport,
            verify=True if verify is None else verify,
        )
        self._max_attempts = max_attempts
        self._sleep = sleep

    async def aclose(self) -> None:
        await self._client.aclose()

    async def enroll(
        self, *, token: str, hostname: str, os_name: str
    ) -> tuple[str, str]:
        response = await self._client.post(
            "/api/v1/enroll",
            json={"token": token, "hostname": hostname, "os": os_name},
        )
        if response.status_code == httpx.codes.BAD_REQUEST:
            detail = response.json().get("detail", "enrollment rejected")
            raise EnrollmentError(detail)
        response.raise_for_status()
        body = response.json()
        return body["agent_id"], body["agent_key"]

    async def poll_tasks(self, *, agent_id: str, agent_key: str) -> list[TaskDTO]:
        response = await self._request(
            "GET", f"/api/v1/agents/{agent_id}/tasks", agent_key=agent_key
        )
        return [
            TaskDTO(
                id=item["id"],
                kind=item["kind"],
                window_start=datetime.fromisoformat(item["window_start"]),
                window_end=datetime.fromisoformat(item["window_end"]),
                status=item["status"],
            )
            for item in response.json()
        ]

    async def push_report(
        self,
        *,
        agent_id: str,
        agent_key: str,
        task_id: str,
        events: list[OutgoingEvent],
    ) -> None:
        await self._request(
            "POST",
            f"/api/v1/agents/{agent_id}/reports",
            agent_key=agent_key,
            json={
                "task_id": task_id,
                "events": [
                    {
                        "category": event.category,
                        "occurred_at": event.occurred_at.isoformat(),
                        "payload": event.payload,
                    }
                    for event in events
                ],
            },
        )

    async def push_inventory(
        self,
        *,
        agent_id: str,
        agent_key: str,
        hardware: dict[str, Any],
        software: dict[str, Any],
    ) -> None:
        await self._request(
            "POST",
            f"/api/v1/agents/{agent_id}/inventory",
            agent_key=agent_key,
            json={"hardware": hardware, "software": software},
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        agent_key: str,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        headers = {"X-Agent-Key": agent_key}
        last_error: Exception | None = None

        for attempt in range(1, self._max_attempts + 1):
            try:
                response = await self._client.request(
                    method, path, headers=headers, json=json
                )
            except httpx.TransportError as exc:
                last_error = exc
            else:
                if response.status_code not in _RETRYABLE_STATUS:
                    response.raise_for_status()
                    return response
                last_error = httpx.HTTPStatusError(
                    f"server returned {response.status_code}",
                    request=response.request,
                    response=response,
                )

            if attempt < self._max_attempts:
                delay = min(2 ** (attempt - 1), 30)
                logger.warning(
                    "request to %s failed (attempt %d/%d), retrying in %ds",
                    path,
                    attempt,
                    self._max_attempts,
                    delay,
                )
                await self._sleep(delay)

        if last_error is None:  # pragma: no cover -- defensive, unreachable in practice
            raise RuntimeError("retry loop exited without a recorded error")
        raise last_error
