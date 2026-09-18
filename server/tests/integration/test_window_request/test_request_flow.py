"""Integration: place a request, agent polls it, agent reports, operator reads it back.

Exercises the full flow from `specs/001-agent-server-complex/plan.md`
(section 1) end to end against the real HTTP endpoints and the in-memory
test database (constitution principle 7).
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from warden_server.models.audit import AuditLogEntry
from warden_server.schemas.event import MAX_REPORT_EVENTS


def test_full_window_request_cycle(client, auth_headers, enrolled_agent, agent_headers):
    agent_id = enrolled_agent["agent_id"]
    window_start = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    window_end = window_start + timedelta(hours=2)

    placed = client.post(
        f"/api/v1/agents/{agent_id}/requests",
        headers=auth_headers,
        json={
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
        },
    )
    assert placed.status_code == 201
    task_id = placed.json()["id"]

    polled = client.get(f"/api/v1/agents/{agent_id}/tasks", headers=agent_headers)
    assert polled.status_code == 200
    tasks = polled.json()
    assert len(tasks) == 1
    assert tasks[0]["id"] == task_id
    assert tasks[0]["status"] == "dispatched"

    reported = client.post(
        f"/api/v1/agents/{agent_id}/reports",
        headers=agent_headers,
        json={
            "task_id": task_id,
            "events": [
                {
                    "category": "processes",
                    "occurred_at": (window_start + timedelta(minutes=30)).isoformat(),
                    "payload": {"name": "explorer.exe", "pid": 1234},
                }
            ],
        },
    )
    assert reported.status_code == 204

    report_date = window_start.date().isoformat()
    events = client.get(
        f"/api/v1/agents/{agent_id}/events",
        headers=auth_headers,
        params={"report_date": report_date},
    )
    assert events.status_code == 200
    assert len(events.json()) == 1
    assert events.json()[0]["payload"]["name"] == "explorer.exe"


def test_a_window_over_four_hours_is_rejected_when_placing_a_request(
    client, auth_headers, enrolled_agent
):
    agent_id = enrolled_agent["agent_id"]
    window_start = datetime(2026, 1, 1, tzinfo=UTC)

    response = client.post(
        f"/api/v1/agents/{agent_id}/requests",
        headers=auth_headers,
        json={
            "window_start": window_start.isoformat(),
            "window_end": (window_start + timedelta(hours=5)).isoformat(),
        },
    )

    assert response.status_code == 422


def test_reporting_against_an_unknown_task_is_rejected(
    client, agent_headers, enrolled_agent
):
    agent_id = enrolled_agent["agent_id"]

    response = client.post(
        f"/api/v1/agents/{agent_id}/reports",
        headers=agent_headers,
        json={"task_id": "00000000-0000-0000-0000-000000000000", "events": []},
    )

    assert response.status_code == 404


def test_agent_endpoints_reject_a_wrong_key(client, enrolled_agent):
    agent_id = enrolled_agent["agent_id"]

    response = client.get(
        f"/api/v1/agents/{agent_id}/tasks", headers={"X-Agent-Key": "wrong-key"}
    )

    assert response.status_code == 401


def _place_and_dispatch(client, auth_headers, agent_headers, agent_id, window_start):
    placed = client.post(
        f"/api/v1/agents/{agent_id}/requests",
        headers=auth_headers,
        json={
            "window_start": window_start.isoformat(),
            "window_end": (window_start + timedelta(hours=2)).isoformat(),
        },
    )
    assert placed.status_code == 201
    task_id = placed.json()["id"]

    polled = client.get(f"/api/v1/agents/{agent_id}/tasks", headers=agent_headers)
    assert polled.status_code == 200
    return task_id


def test_an_event_before_the_window_start_is_rejected(
    client, auth_headers, enrolled_agent, agent_headers
):
    agent_id = enrolled_agent["agent_id"]
    window_start = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    task_id = _place_and_dispatch(
        client, auth_headers, agent_headers, agent_id, window_start
    )

    response = client.post(
        f"/api/v1/agents/{agent_id}/reports",
        headers=agent_headers,
        json={
            "task_id": task_id,
            "events": [
                {
                    "category": "processes",
                    "occurred_at": (window_start - timedelta(hours=1)).isoformat(),
                    "payload": {"name": "sneaky.exe", "pid": 1},
                }
            ],
        },
    )

    assert response.status_code == 400

    events = client.get(
        f"/api/v1/agents/{agent_id}/events",
        headers=auth_headers,
        params={"report_date": window_start.date().isoformat()},
    )
    assert events.json() == []


def test_an_event_at_the_window_end_is_rejected(
    client, auth_headers, enrolled_agent, agent_headers
):
    """The window is a half-open interval: `window_end` itself is excluded."""
    agent_id = enrolled_agent["agent_id"]
    window_start = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    window_end = window_start + timedelta(hours=2)
    task_id = _place_and_dispatch(
        client, auth_headers, agent_headers, agent_id, window_start
    )

    response = client.post(
        f"/api/v1/agents/{agent_id}/reports",
        headers=agent_headers,
        json={
            "task_id": task_id,
            "events": [
                {
                    "category": "processes",
                    "occurred_at": window_end.isoformat(),
                    "payload": {"name": "sneaky.exe", "pid": 1},
                }
            ],
        },
    )

    assert response.status_code == 400


def test_reporting_against_a_pending_task_is_rejected(
    client, auth_headers, enrolled_agent
):
    """An agent must poll (dispatching the task) before it can report on it."""
    agent_id = enrolled_agent["agent_id"]
    window_start = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    placed = client.post(
        f"/api/v1/agents/{agent_id}/requests",
        headers=auth_headers,
        json={
            "window_start": window_start.isoformat(),
            "window_end": (window_start + timedelta(hours=2)).isoformat(),
        },
    )
    assert placed.status_code == 201
    task_id = placed.json()["id"]

    response = client.post(
        f"/api/v1/agents/{agent_id}/reports",
        headers={"X-Agent-Key": enrolled_agent["agent_key"]},
        json={"task_id": task_id, "events": []},
    )

    assert response.status_code == 409


def test_an_out_of_window_report_is_audited(
    client, db_session, auth_headers, enrolled_agent, agent_headers
):
    agent_id = enrolled_agent["agent_id"]
    window_start = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    task_id = _place_and_dispatch(
        client, auth_headers, agent_headers, agent_id, window_start
    )

    client.post(
        f"/api/v1/agents/{agent_id}/reports",
        headers=agent_headers,
        json={
            "task_id": task_id,
            "events": [
                {
                    "category": "processes",
                    "occurred_at": (window_start - timedelta(hours=1)).isoformat(),
                    "payload": {"name": "sneaky.exe", "pid": 1},
                }
            ],
        },
    )

    entry = db_session.execute(
        select(AuditLogEntry).where(
            AuditLogEntry.action == "agent.report_out_of_window"
        )
    ).scalar_one()
    assert entry.target == task_id


def test_a_report_over_the_event_limit_is_rejected_by_the_endpoint(
    client, auth_headers, enrolled_agent, agent_headers
):
    agent_id = enrolled_agent["agent_id"]
    window_start = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    task_id = _place_and_dispatch(
        client, auth_headers, agent_headers, agent_id, window_start
    )

    response = client.post(
        f"/api/v1/agents/{agent_id}/reports",
        headers=agent_headers,
        json={
            "task_id": task_id,
            "events": [
                {
                    "category": "processes",
                    "occurred_at": (window_start + timedelta(minutes=1)).isoformat(),
                    "payload": {},
                }
                for _ in range(MAX_REPORT_EVENTS + 1)
            ],
        },
    )

    assert response.status_code == 422


def test_daily_report_events_are_paginated(
    client, auth_headers, enrolled_agent, agent_headers
):
    agent_id = enrolled_agent["agent_id"]
    window_start = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    task_id = _place_and_dispatch(
        client, auth_headers, agent_headers, agent_id, window_start
    )
    client.post(
        f"/api/v1/agents/{agent_id}/reports",
        headers=agent_headers,
        json={
            "task_id": task_id,
            "events": [
                {
                    "category": "processes",
                    "occurred_at": (window_start + timedelta(minutes=i)).isoformat(),
                    "payload": {"pid": i},
                }
                for i in range(5)
            ],
        },
    )
    report_date = window_start.date().isoformat()

    first_page = client.get(
        f"/api/v1/agents/{agent_id}/events",
        headers=auth_headers,
        params={"report_date": report_date, "limit": 2},
    )
    assert [e["payload"]["pid"] for e in first_page.json()] == [0, 1]

    second_page = client.get(
        f"/api/v1/agents/{agent_id}/events",
        headers=auth_headers,
        params={"report_date": report_date, "limit": 2, "offset": 2},
    )
    assert [e["payload"]["pid"] for e in second_page.json()] == [2, 3]

    over_limit = client.get(
        f"/api/v1/agents/{agent_id}/events",
        headers=auth_headers,
        params={"report_date": report_date, "limit": 100_000},
    )
    assert over_limit.status_code == 422
