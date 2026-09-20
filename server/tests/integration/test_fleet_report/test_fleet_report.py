"""Integration: the cross-station report (spec 002, R-1..R-4, A-1..A-3).

Events are inserted straight into the test database, the way a completed
window request leaves them, so each test controls exactly which stations,
categories, and instants exist.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from warden_server.models.agent import Agent, AgentStatus
from warden_server.models.event import Event, EventCategory
from warden_server.models.task import Task, TaskKind, TaskStatus
from warden_server.security import hash_secret_token

START = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
END = START + timedelta(hours=1)


@pytest.fixture
def make_station(db_session):
    def _make(hostname: str) -> Agent:
        agent = Agent(
            hostname=hostname,
            os="linux",
            agent_key_hash=hash_secret_token(hostname),
            status=AgentStatus.ACTIVE,
            enrolled_at=START,
        )
        db_session.add(agent)
        db_session.flush()
        db_session.add(
            Task(
                id=uuid.uuid4(),
                agent_id=agent.id,
                kind=TaskKind.WINDOW_REQUEST,
                window_start=START - timedelta(days=30),
                window_end=START + timedelta(days=30),
                status=TaskStatus.COMPLETED,
                created_by="admin",
                created_at=START,
            )
        )
        db_session.commit()
        return agent

    return _make


@pytest.fixture
def add_event(db_session):
    def _add(agent, occurred_at, category=EventCategory.PROCESSES, payload=None):
        task = db_session.query(Task).filter(Task.agent_id == agent.id).one()
        event = Event(
            agent_id=agent.id,
            task_id=task.id,
            category=category,
            occurred_at=occurred_at,
            payload=payload or {"name": "app.exe"},
        )
        db_session.add(event)
        db_session.commit()
        return event

    return _add


def _fleet(client, headers, start=START, end=END, **extra):
    params = {"start": start.isoformat(), "end": end.isoformat(), **extra}
    return client.get("/api/v1/events", headers=headers, params=params)


def test_events_from_every_station_come_back_labeled_with_their_station(
    client, auth_headers, make_station, add_event
):
    first = make_station("WS-01")
    second = make_station("WS-02")
    add_event(first, START + timedelta(minutes=5))
    add_event(second, START + timedelta(minutes=10))

    response = _fleet(client, auth_headers)

    assert response.status_code == 200
    rows = response.json()
    assert [(row["hostname"], row["agent_id"]) for row in rows] == [
        ("WS-01", str(first.id)),
        ("WS-02", str(second.id)),
    ]
    assert {"id", "category", "occurred_at", "payload"} <= set(rows[0])


def test_filtering_to_two_stations_excludes_the_third(
    client, auth_headers, make_station, add_event
):
    stations = [make_station(f"WS-0{n}") for n in (1, 2, 3)]
    for station in stations:
        add_event(station, START + timedelta(minutes=5))

    response = _fleet(
        client,
        auth_headers,
        agent_id=[str(stations[0].id), str(stations[2].id)],
    )

    hostnames = {row["hostname"] for row in response.json()}
    assert hostnames == {"WS-01", "WS-03"}


def test_the_category_filter_narrows_the_result(
    client, auth_headers, make_station, add_event
):
    station = make_station("WS-01")
    add_event(station, START + timedelta(minutes=1), EventCategory.PRINTING)
    add_event(station, START + timedelta(minutes=2), EventCategory.WEB)

    response = _fleet(client, auth_headers, category="printing")

    assert [row["category"] for row in response.json()] == ["printing"]


def test_a_range_with_no_events_is_an_empty_list_not_an_error(
    client, auth_headers, make_station, add_event
):
    add_event(make_station("WS-01"), START - timedelta(days=2))

    response = _fleet(client, auth_headers)

    assert response.status_code == 200
    assert response.json() == []


def test_an_unknown_station_id_matches_nothing(
    client, auth_headers, make_station, add_event
):
    add_event(make_station("WS-01"), START + timedelta(minutes=5))

    response = _fleet(client, auth_headers, agent_id=[str(uuid.uuid4())])

    assert response.status_code == 200
    assert response.json() == []


def test_the_range_includes_its_start_and_excludes_its_end(
    client, auth_headers, make_station, add_event
):
    station = make_station("WS-01")
    at_start = add_event(station, START)
    add_event(station, END)

    response = _fleet(client, auth_headers)

    assert [row["id"] for row in response.json()] == [str(at_start.id)]


def test_rows_are_ordered_by_time(client, auth_headers, make_station, add_event):
    station = make_station("WS-01")
    late = add_event(station, START + timedelta(minutes=30))
    early = add_event(station, START + timedelta(minutes=10))

    response = _fleet(client, auth_headers)

    assert [row["id"] for row in response.json()] == [str(early.id), str(late.id)]


def test_events_sharing_a_timestamp_page_without_loss_or_repeat(
    client, auth_headers, make_station, add_event
):
    station = make_station("WS-01")
    same_instant = START + timedelta(minutes=5)
    expected = {str(add_event(station, same_instant).id) for _ in range(7)}

    pages = [
        _fleet(client, auth_headers, limit=3, offset=offset).json()
        for offset in (0, 3, 6)
    ]

    assert [len(page) for page in pages] == [3, 3, 1]
    seen = [row["id"] for page in pages for row in page]
    assert len(seen) == len(set(seen))
    assert set(seen) == expected


def test_a_naive_timestamp_in_the_query_is_read_as_utc(
    client, auth_headers, make_station, add_event
):
    station = make_station("WS-01")
    inside = add_event(station, START + timedelta(minutes=5))

    response = client.get(
        "/api/v1/events",
        headers=auth_headers,
        params={"start": "2026-09-01T12:00:00", "end": "2026-09-01T13:00:00"},
    )

    assert [row["id"] for row in response.json()] == [str(inside.id)]


def test_an_end_before_the_start_is_a_422(client, auth_headers):
    response = _fleet(client, auth_headers, start=END, end=START)

    assert response.status_code == 422


def test_a_limit_above_the_maximum_is_a_422(client, auth_headers):
    assert _fleet(client, auth_headers, limit=2001).status_code == 422


def test_the_report_requires_an_operator_token(client):
    assert _fleet(client, {}).status_code == 401


def test_a_long_report_range_is_allowed_while_a_long_agent_window_is_still_refused(
    client, auth_headers, enrolled_agent
):
    """Principle 3 caps what an agent is asked for, not reads of stored data."""
    week = _fleet(client, auth_headers, start=START - timedelta(days=5), end=START)
    window_start = START
    over_cap = client.post(
        f"/api/v1/agents/{enrolled_agent['agent_id']}/requests",
        headers=auth_headers,
        json={
            "window_start": window_start.isoformat(),
            "window_end": (window_start + timedelta(hours=4, minutes=1)).isoformat(),
        },
    )

    assert week.status_code == 200
    assert over_cap.status_code == 422


def test_the_events_table_is_indexed_by_time():
    index_names = {index.name for index in Event.__table__.indexes}

    assert "ix_events_occurred_at" in index_names
