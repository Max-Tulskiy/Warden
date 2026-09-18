"""HTTP client for talking to the server (constitution D-1, D-2).

Every method here is something the agent initiates; nothing in this module
listens for or accepts an incoming connection. Retries use exponential
backoff and only kick in for transport failures and 5xx responses -- a 4xx
(bad token, unknown task) means retrying the same request would just fail
again, so it is raised immediately instead.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

import httpx

from warden_agent.core.models import OutgoingEvent, TaskDTO

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = {500, 502, 503, 504}


class EnrollmentError(RuntimeError):
    """Raised when the server rejects an enrollment token."""


class ServerClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 10.0,
        max_attempts: int = 5,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url, timeout=timeout, transport=transport
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
