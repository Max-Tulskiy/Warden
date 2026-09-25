"""Integration: the audit log read endpoint (spec 003, R-1..R-9, A-1..A-7).

Entries are inserted straight into the test database, the way the endpoints'
own `log_event` calls leave them, so each test controls exactly which actors,
actions, and instants exist. The `auth_headers` fixture logs in through the
API, so a real `operator.login` row exists at the current time; the fixed
ranges below sit weeks away from it and never see it.
"""

from datetime import UTC, datetime, timedelta

import pytest

from warden_server.models.audit import AuditLogEntry

START = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
END = START + timedelta(hours=1)


@pytest.fixture
def add_entry(db_session):
    def _add(
        *,
        at=START + timedelta(minutes=5),
        actor="admin",
        action="operator.login",
        target="admin",
        detail=None,
    ) -> AuditLogEntry:
        entry = AuditLogEntry(
            actor=actor,
            action=action,
            target=target,
            occurred_at=at,
            detail=detail or {},
        )
        db_session.add(entry)
        db_session.commit()
        return entry

    return _add


def _audit(client, headers, start=START, end=END, **extra):
    params = {"start": start.isoformat(), "end": end.isoformat(), **extra}
    return client.get("/api/v1/audit", headers=headers, params=params)


def _targets(response) -> list[str]:
    return [row["target"] for row in response.json()]


def test_a_real_login_shows_up_in_the_last_hour_with_its_fields(client, auth_headers):
    now = datetime.now(UTC)

    response = _audit(
        client,
        auth_headers,
        start=now - timedelta(hours=1),
        end=now + timedelta(hours=1),
        action="operator.login",
    )

    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["actor"] == "admin"
    assert rows[0]["action"] == "operator.login"
    assert rows[0]["target"] == "admin"
    assert rows[0]["detail"] == {}
    assert {"id", "occurred_at"} <= set(rows[0])


def test_entries_come_back_newest_first(client, auth_headers, add_entry):
    add_entry(at=START + timedelta(minutes=10), target="middle")
    add_entry(at=START + timedelta(minutes=30), target="newest")
    add_entry(at=START + timedelta(minutes=1), target="oldest")

    response = _audit(client, auth_headers)

    assert response.status_code == 200
    assert _targets(response) == ["newest", "middle", "oldest"]


def test_detail_is_returned_exactly_as_stored(client, auth_headers, add_entry):
    add_entry(
        action="agent.tasks_dispatched",
        detail={"task_ids": ["a", "b"], "hostname": "WS-01"},
    )

    rows = _audit(client, auth_headers).json()

    assert rows[0]["detail"] == {"task_ids": ["a", "b"], "hostname": "WS-01"}


def test_an_actor_filter_returns_only_that_actors_entries(
    client, auth_headers, add_entry
):
    add_entry(actor="admin", target="by-admin")
    add_entry(actor="WS-01", action="agent.enroll", target="by-station")

    response = _audit(client, auth_headers, actor="WS-01")

    assert _targets(response) == ["by-station"]


def test_an_actor_of_percent_is_an_exact_value_not_a_pattern(
    client, auth_headers, add_entry
):
    add_entry(actor="admin")

    response = _audit(client, auth_headers, actor="%")

    assert response.status_code == 200
    assert response.json() == []


def test_a_group_returns_every_action_under_it_and_nothing_else(
    client, auth_headers, add_entry
):
    add_entry(action="operator.login", target="login")
    add_entry(action="operator.login_failed", target="failed")
    add_entry(action="agent.disabled", target="disabled")

    response = _audit(client, auth_headers, action="operator")

    assert sorted(_targets(response)) == ["failed", "login"]


def test_a_full_code_matches_only_that_code(client, auth_headers, add_entry):
    add_entry(action="operator.login", target="login")
    add_entry(action="operator.login_failed", target="failed")
    add_entry(action="operator.login_throttled", target="throttled")

    response = _audit(client, auth_headers, action="operator.login")

    assert _targets(response) == ["login"]


def test_a_partial_code_matches_nothing(client, auth_headers, add_entry):
    add_entry(action="operator.login")

    response = _audit(client, auth_headers, action="operator.log")

    assert response.status_code == 200
    assert response.json() == []


def test_an_underscore_in_a_group_is_not_a_wildcard(client, auth_headers, add_entry):
    """`a_c` must not reach `abc.*`: the underscore is escaped in the query."""
    add_entry(action="a_c.one", target="wanted")
    add_entry(action="abc.one", target="unwanted")

    response = _audit(client, auth_headers, action="a_c")

    assert _targets(response) == ["wanted"]


def test_a_percent_in_the_action_is_rejected(client, auth_headers):
    response = _audit(client, auth_headers, action="%")

    assert response.status_code == 422


def test_actor_and_action_filters_combine(client, auth_headers, add_entry):
    add_entry(actor="admin", action="operator.login", target="hit")
    add_entry(actor="other", action="operator.login", target="wrong-actor")
    add_entry(actor="admin", action="agent.disabled", target="wrong-action")

    response = _audit(client, auth_headers, actor="admin", action="operator")

    assert _targets(response) == ["hit"]


def test_entries_sharing_one_timestamp_page_without_loss_or_repeat(
    client, auth_headers, add_entry
):
    same_instant = START + timedelta(minutes=20)
    for n in range(5):
        add_entry(at=same_instant, target=f"row-{n}")

    seen: list[str] = []
    for offset in (0, 2, 4):
        page = _audit(client, auth_headers, limit=2, offset=offset)
        assert page.status_code == 200
        seen.extend(_targets(page))

    assert sorted(seen) == [f"row-{n}" for n in range(5)]


def test_an_entry_exactly_at_start_is_included_and_one_exactly_at_end_excluded(
    client, auth_headers, add_entry
):
    add_entry(at=START, target="at-start")
    add_entry(at=END, target="at-end")

    response = _audit(client, auth_headers)

    assert _targets(response) == ["at-start"]


def test_an_empty_range_is_an_empty_list_not_an_error(client, auth_headers):
    response = _audit(client, auth_headers)

    assert response.status_code == 200
    assert response.json() == []


def test_an_end_before_the_start_is_rejected(client, auth_headers):
    response = _audit(client, auth_headers, start=END, end=START)

    assert response.status_code == 422


def test_a_thirty_day_range_is_accepted(client, auth_headers):
    """A log read is not an agent window (constitution principle 3)."""
    response = _audit(client, auth_headers, end=START + timedelta(days=30))

    assert response.status_code == 200


def test_an_unknown_action_is_returned_verbatim(client, auth_headers, add_entry):
    add_entry(action="policy.changed_by_a_later_version", target="future")

    rows = _audit(client, auth_headers).json()

    assert rows[0]["action"] == "policy.changed_by_a_later_version"


def test_no_token_is_unauthorized(client):
    response = _audit(client, {})

    assert response.status_code == 401


def test_a_garbage_token_is_unauthorized(client):
    response = _audit(client, {"Authorization": "Bearer not-a-token"})

    assert response.status_code == 401


def test_the_occurred_at_index_is_declared_on_the_table():
    names = {index.name for index in AuditLogEntry.__table__.indexes}

    assert "ix_audit_log_occurred_at" in names
