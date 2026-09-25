"""Integration: views of collected data and of the log are recorded (spec 008).

Each test goes through the real endpoints against the in-memory database and
reads the audit table directly afterwards. Audit rows are ordered by
`occurred_at`, never by `id`, which is a random UUID.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from warden_server.models.audit import AuditLogEntry

START = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
END = START + timedelta(hours=1)
RANGE = {"start": START.isoformat(), "end": END.isoformat()}


def _entries(db_session) -> list[AuditLogEntry]:
    return list(
        db_session.execute(select(AuditLogEntry).order_by(AuditLogEntry.occurred_at))
        .scalars()
        .all()
    )


def _views(db_session) -> list[AuditLogEntry]:
    return [entry for entry in _entries(db_session) if entry.action.startswith("view.")]


def _count(db_session) -> int:
    return db_session.execute(
        select(func.count()).select_from(AuditLogEntry)
    ).scalar_one()


def test_a_daily_report_view_names_the_station_and_the_day(
    client, auth_headers, enrolled_agent, db_session
):
    station = enrolled_agent["agent_id"]

    response = client.get(
        f"/api/v1/agents/{station}/events",
        headers=auth_headers,
        params={"report_date": "2026-09-01", "limit": 50},
    )

    assert response.status_code == 200
    (entry,) = _views(db_session)
    assert entry.actor == "admin"
    assert entry.action == "view.daily_report"
    assert entry.target == station
    assert entry.detail == {"report_date": "2026-09-01", "limit": 50, "offset": 0}


def test_a_fleet_report_view_names_the_period_and_the_filters(
    client, auth_headers, enrolled_agent, db_session
):
    station = enrolled_agent["agent_id"]

    response = client.get(
        "/api/v1/events",
        headers=auth_headers,
        params={**RANGE, "agent_id": [station], "category": "processes", "limit": 20},
    )

    assert response.status_code == 200
    (entry,) = _views(db_session)
    assert entry.actor == "admin"
    assert entry.action == "view.fleet_report"
    assert entry.target == "fleet"
    assert entry.detail == {
        "start": START.isoformat(),
        "end": END.isoformat(),
        "agent_id": [station],
        "category": "processes",
        "limit": 20,
        "offset": 0,
    }


def test_an_unfiltered_fleet_report_view_records_no_stations_and_no_category(
    client, auth_headers, db_session
):
    client.get("/api/v1/events", headers=auth_headers, params=RANGE)

    (entry,) = _views(db_session)
    assert entry.detail["agent_id"] == []
    assert entry.detail["category"] is None


def test_an_inventory_history_view_names_the_station(
    client, auth_headers, enrolled_agent, db_session
):
    station = enrolled_agent["agent_id"]

    response = client.get(
        f"/api/v1/agents/{station}/inventory/changes", headers=auth_headers
    )

    assert response.status_code == 200
    (entry,) = _views(db_session)
    assert entry.actor == "admin"
    assert entry.action == "view.inventory_changes"
    assert entry.target == station
    assert entry.detail == {"limit": 500, "offset": 0}


def test_an_audit_log_view_names_the_period_and_the_filters(
    client, auth_headers, db_session
):
    response = client.get(
        "/api/v1/audit",
        headers=auth_headers,
        params={**RANGE, "actor": "admin", "action": "operator", "limit": 10},
    )

    assert response.status_code == 200
    (entry,) = _views(db_session)
    assert entry.actor == "admin"
    assert entry.action == "view.audit_log"
    assert entry.target == "audit_log"
    assert entry.detail == {
        "start": START.isoformat(),
        "end": END.isoformat(),
        "actor": "admin",
        "action": "operator",
        "limit": 10,
        "offset": 0,
    }


def test_an_observers_view_is_recorded_under_the_observers_name(
    client, viewer_headers, enrolled_agent, db_session
):
    station = enrolled_agent["agent_id"]

    response = client.get(f"/api/v1/agents/{station}/events", headers=viewer_headers)

    assert response.status_code == 200
    (entry,) = _views(db_session)
    assert entry.actor == "watcher"
    assert entry.action == "view.daily_report"


def test_an_observer_is_refused_the_audit_log_and_nothing_is_recorded(
    client, viewer_headers, db_session
):
    before = _count(db_session)

    response = client.get("/api/v1/audit", headers=viewer_headers, params=RANGE)

    assert response.status_code == 403
    assert _count(db_session) == before


STATION = "00000000-0000-0000-0000-000000000001"
VIEW_URLS = [
    f"/api/v1/agents/{STATION}/events",
    "/api/v1/events",
    f"/api/v1/agents/{STATION}/inventory/changes",
    "/api/v1/audit",
]


@pytest.mark.parametrize("url", VIEW_URLS)
def test_a_view_without_a_session_is_refused_and_nothing_is_recorded(
    client, operator, db_session, url
):
    before = _count(db_session)

    response = client.get(url, params=RANGE)

    assert response.status_code == 401
    assert _count(db_session) == before


@pytest.mark.parametrize(
    ("url", "params"),
    [
        (f"/api/v1/agents/{STATION}/events", {"limit": 0}),
        (f"/api/v1/agents/{STATION}/inventory/changes", {"offset": -1}),
        ("/api/v1/events", {"start": END.isoformat(), "end": START.isoformat()}),
        ("/api/v1/audit", {"start": END.isoformat(), "end": START.isoformat()}),
    ],
)
def test_a_view_with_invalid_parameters_is_refused_and_nothing_is_recorded(
    client, auth_headers, db_session, url, params
):
    before = _count(db_session)

    response = client.get(url, headers=auth_headers, params=params)

    assert response.status_code == 422
    assert _count(db_session) == before


@pytest.mark.parametrize(
    "url",
    ["/api/v1/agents", "/api/v1/policy", "/api/v1/operators", "/api/v1/auth/me"],
)
def test_helper_and_metadata_reads_are_not_recorded(
    client, auth_headers, db_session, url
):
    before = _count(db_session)

    response = client.get(url, headers=auth_headers)

    assert response.status_code == 200
    assert _count(db_session) == before


def test_the_same_view_twice_and_a_later_page_are_three_entries(
    client, auth_headers, enrolled_agent, db_session
):
    url = f"/api/v1/agents/{enrolled_agent['agent_id']}/events"

    client.get(url, headers=auth_headers, params={"report_date": "2026-09-01"})
    client.get(url, headers=auth_headers, params={"report_date": "2026-09-01"})
    client.get(
        url, headers=auth_headers, params={"report_date": "2026-09-01", "offset": 500}
    )

    entries = _views(db_session)
    assert [entry.detail["offset"] for entry in entries] == [0, 0, 500]


def test_a_view_that_matches_nothing_is_still_recorded(
    client, auth_headers, enrolled_agent, db_session
):
    response = client.get(
        f"/api/v1/agents/{enrolled_agent['agent_id']}/events", headers=auth_headers
    )

    assert response.json() == []
    assert len(_views(db_session)) == 1


@pytest.mark.parametrize(
    "case",
    [
        ("reports", f"/api/v1/agents/{STATION}/events", {}),
        ("reports", "/api/v1/events", RANGE),
        ("reports", f"/api/v1/agents/{STATION}/inventory/changes", {}),
        ("audit", "/api/v1/audit", RANGE),
    ],
    ids=["daily_report", "fleet_report", "inventory_changes", "audit_log"],
)
def test_a_view_whose_entry_cannot_be_stored_returns_no_data(
    client, auth_headers, db_session, monkeypatch, case
):
    module, url, params = case

    def refuse(*args, **kwargs):
        raise RuntimeError("the audit log is unavailable")

    monkeypatch.setattr(f"warden_server.api.{module}.log_event", refuse)
    before = _count(db_session)

    with pytest.raises(RuntimeError, match="unavailable"):
        client.get(url, headers=auth_headers, params=params)

    assert _count(db_session) == before


def test_the_views_group_filter_returns_only_views(client, auth_headers):
    now = datetime.now(UTC)
    window = {
        "start": (now - timedelta(hours=1)).isoformat(),
        "end": (now + timedelta(hours=1)).isoformat(),
    }
    client.get("/api/v1/events", headers=auth_headers, params=RANGE)

    views = client.get(
        "/api/v1/audit", headers=auth_headers, params={**window, "action": "view"}
    ).json()
    operator_entries = client.get(
        "/api/v1/audit", headers=auth_headers, params={**window, "action": "operator"}
    ).json()
    one_code = client.get(
        "/api/v1/audit",
        headers=auth_headers,
        params={**window, "action": "view.fleet_report"},
    ).json()

    assert {row["action"] for row in views} >= {"view.fleet_report"}
    assert all(row["action"].startswith("view.") for row in views)
    assert operator_entries
    assert not any(row["action"].startswith("view.") for row in operator_entries)
    assert [row["action"] for row in one_code] == ["view.fleet_report"]
