"""Tests for the agent's HTTP transport: requests, retries, and backoff.

Every test runs against `httpx.MockTransport` -- no real network, and no
real `asyncio.sleep` either (a fake `sleep` records delays instead of
waiting), so a retry test that would otherwise take real seconds runs
instantly.
"""

import json
from datetime import UTC, datetime

import httpx
import pytest

from warden_agent.core.models import OutgoingEvent
from warden_agent.core.transport import EnrollmentError, ServerClient


class _RecordingSleep:
    def __init__(self):
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


def _client(handler, *, max_attempts: int = 3) -> tuple[ServerClient, _RecordingSleep]:
    sleep = _RecordingSleep()
    transport = httpx.MockTransport(handler)
    client = ServerClient(
        "https://server.example",
        transport=transport,
        sleep=sleep,
        max_attempts=max_attempts,
    )
    return client, sleep


async def test_enroll_returns_the_agent_id_and_key():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/enroll"
        return httpx.Response(201, json={"agent_id": "a1", "agent_key": "k1"})

    client, _ = _client(handler)

    agent_id, agent_key = await client.enroll(
        token="tok", hostname="H", os_name="linux"
    )

    assert (agent_id, agent_key) == ("a1", "k1")


async def test_enroll_with_a_rejected_token_raises_enrollment_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"detail": "Invalid or used token"})

    client, _ = _client(handler)

    with pytest.raises(EnrollmentError, match="Invalid or used token"):
        await client.enroll(token="bad", hostname="H", os_name="linux")


async def test_poll_tasks_parses_the_task_list():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Agent-Key"] == "k1"
        return httpx.Response(
            200,
            json=[
                {
                    "id": "t1",
                    "kind": "window_request",
                    "window_start": "2026-01-01T10:00:00+00:00",
                    "window_end": "2026-01-01T12:00:00+00:00",
                    "status": "dispatched",
                }
            ],
        )

    client, _ = _client(handler)

    tasks = await client.poll_tasks(agent_id="a1", agent_key="k1")

    assert len(tasks) == 1
    assert tasks[0].id == "t1"
    assert tasks[0].window_end.hour == 12


async def test_push_report_sends_events_as_json():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read()
        return httpx.Response(204)

    client, _ = _client(handler)

    await client.push_report(
        agent_id="a1",
        agent_key="k1",
        task_id="t1",
        events=[
            OutgoingEvent(
                category="processes",
                occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
                payload={"name": "explorer.exe"},
            )
        ],
    )

    body = json.loads(captured["body"])
    assert body["task_id"] == "t1"
    assert body["events"][0]["payload"]["name"] == "explorer.exe"


async def test_a_5xx_response_is_retried_and_then_succeeds():
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 2:
            return httpx.Response(503)
        return httpx.Response(200, json=[])

    client, sleep = _client(handler)

    tasks = await client.poll_tasks(agent_id="a1", agent_key="k1")

    assert tasks == []
    assert attempts["count"] == 2
    assert sleep.delays == [1]


async def test_retries_are_exhausted_and_the_last_error_is_raised():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client, sleep = _client(handler, max_attempts=3)

    with pytest.raises(httpx.HTTPStatusError):
        await client.poll_tasks(agent_id="a1", agent_key="k1")

    assert sleep.delays == [1, 2]


async def test_a_4xx_response_is_not_retried():
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(404)

    client, sleep = _client(handler)

    with pytest.raises(httpx.HTTPStatusError):
        await client.poll_tasks(agent_id="a1", agent_key="k1")

    assert attempts["count"] == 1
    assert sleep.delays == []
