"""Integration: saving and resetting the operating policy (spec 006, A-1..A-13)."""

import pytest
from sqlalchemy import select

from warden_server.config import Settings
from warden_server.models.audit import AuditLogEntry
from warden_server.models.policy import PolicyOverride
from warden_server.services import policy as policy_service

POLICY = "/api/v1/policy"
SAVED = {
    "max_request_window_hours": 2,
    "enrollment_token_ttl_hours": 12,
    "session_lifetime_minutes": 60,
}
EDITABLE = tuple(SAVED)


def _put(client, headers, **changes):
    return client.put(POLICY, headers=headers, json={**SAVED, **changes})


def _audit(db_session, action):
    db_session.expire_all()
    return list(
        db_session.execute(
            select(AuditLogEntry).where(AuditLogEntry.action == action)
        ).scalars()
    )


def _rows(db_session) -> int:
    db_session.expire_all()
    return db_session.query(PolicyOverride).count()


# ---------------------------------------------------------------- saving


def test_a_save_puts_the_values_in_force_and_says_a_policy_is_saved(
    client, auth_headers
):
    response = _put(client, auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert {field: body[field] for field in EDITABLE} == SAVED
    assert body["overridden"] is True
    assert client.get(POLICY, headers=auth_headers).json() == body


def test_a_save_leaves_the_configured_defaults_and_the_bounds_in_view(
    client, auth_headers
):
    before = client.get(POLICY, headers=auth_headers).json()

    after = _put(client, auth_headers).json()

    assert after["defaults"] == before["defaults"]
    assert after["bounds"] == before["bounds"]


def test_a_save_does_not_touch_the_limits_that_stay_in_the_configuration(
    client, auth_headers
):
    before = client.get(POLICY, headers=auth_headers).json()

    after = _put(client, auth_headers).json()

    for field in (
        "min_password_length",
        "max_report_events",
        "max_inventory_entries",
        "max_page_size",
    ):
        assert after[field] == before[field]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_request_window_hours", 0),
        ("max_request_window_hours", 5),
        ("max_request_window_hours", -1),
        ("enrollment_token_ttl_hours", 0),
        ("enrollment_token_ttl_hours", 169),
        ("session_lifetime_minutes", 4),
        ("session_lifetime_minutes", 1441),
        ("max_request_window_hours", 2.5),
        ("max_request_window_hours", "2"),
        ("enrollment_token_ttl_hours", True),
        ("session_lifetime_minutes", None),
    ],
)
def test_a_value_out_of_range_or_not_a_whole_number_is_refused_and_nothing_is_stored(
    client, auth_headers, db_session, field, value
):
    response = _put(client, auth_headers, **{field: value})

    assert response.status_code == 422
    assert _rows(db_session) == 0
    assert client.get(POLICY, headers=auth_headers).json()["overridden"] is False
    assert _audit(db_session, "policy.changed") == []


def test_a_missing_value_or_an_extra_field_is_refused(client, auth_headers, db_session):
    incomplete = {k: v for k, v in SAVED.items() if k != "session_lifetime_minutes"}

    assert client.put(POLICY, headers=auth_headers, json=incomplete).status_code == 422
    assert _put(client, auth_headers, min_password_length=1).status_code == 422
    assert _rows(db_session) == 0


def test_a_window_above_four_hours_is_refused_whatever_else_is_saved(
    client, auth_headers
):
    """Principle 3: the panel can lower the window limit, never raise it."""
    for hours in (5, 8, 24):
        assert (
            _put(client, auth_headers, max_request_window_hours=hours).status_code
            == 422
        )


# ---------------------------------------------------------------- auditing


def test_the_first_save_is_audited_with_every_value_and_the_new_override(
    client, auth_headers, db_session
):
    defaults = client.get(POLICY, headers=auth_headers).json()["defaults"]

    _put(client, auth_headers)

    (row,) = _audit(db_session, "policy.changed")
    assert row.actor == "admin"
    assert row.detail == {
        **{field: [defaults[field], SAVED[field]] for field in EDITABLE},
        "overridden": [False, True],
    }


def test_a_later_save_audits_only_what_changed(client, auth_headers, db_session):
    _put(client, auth_headers)

    _put(client, auth_headers, max_request_window_hours=3)

    rows = _audit(db_session, "policy.changed")
    assert len(rows) == 2
    assert rows[-1].detail == {"max_request_window_hours": [2, 3]}


def test_saving_what_is_already_in_force_succeeds_and_records_nothing(
    client, auth_headers, db_session
):
    _put(client, auth_headers)

    again = _put(client, auth_headers)

    assert again.status_code == 200
    assert len(_audit(db_session, "policy.changed")) == 1


def test_a_first_save_equal_to_the_defaults_is_audited_as_taking_over(
    client, auth_headers, db_session
):
    defaults = client.get(POLICY, headers=auth_headers).json()["defaults"]

    response = client.put(POLICY, headers=auth_headers, json=defaults)

    assert response.status_code == 200
    (row,) = _audit(db_session, "policy.changed")
    assert row.detail == {"overridden": [False, True]}


# ---------------------------------------------------------------- saved wins


def test_a_saved_policy_stays_in_force_when_the_configuration_changes(
    client, auth_headers, monkeypatch
):
    _put(client, auth_headers)

    monkeypatch.setattr(
        policy_service,
        "get_settings",
        lambda: Settings(jwt_expire_minutes=15, enrollment_token_ttl_hours=2),
    )
    body = client.get(POLICY, headers=auth_headers).json()

    assert body["session_lifetime_minutes"] == 60
    assert body["enrollment_token_ttl_hours"] == 12
    # ...while the panel is shown what a reset would go back to.
    assert body["defaults"]["session_lifetime_minutes"] == 15
    assert body["defaults"]["enrollment_token_ttl_hours"] == 2


# ---------------------------------------------------------------- resetting


def test_a_reset_puts_the_configured_values_back(client, auth_headers, db_session):
    defaults = client.get(POLICY, headers=auth_headers).json()["defaults"]
    _put(client, auth_headers)

    response = client.delete(POLICY, headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert {field: body[field] for field in EDITABLE} == defaults
    assert body["overridden"] is False
    assert _rows(db_session) == 0


def test_a_reset_is_audited_with_the_values_it_returned_to(
    client, auth_headers, db_session
):
    defaults = client.get(POLICY, headers=auth_headers).json()["defaults"]
    _put(client, auth_headers)

    client.delete(POLICY, headers=auth_headers)

    (row,) = _audit(db_session, "policy.reset")
    assert row.actor == "admin"
    assert row.detail == {
        **{field: [SAVED[field], defaults[field]] for field in EDITABLE},
        "overridden": [True, False],
    }


def test_a_reset_with_nothing_saved_succeeds_and_records_nothing(
    client, auth_headers, db_session
):
    response = client.delete(POLICY, headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["overridden"] is False
    assert _audit(db_session, "policy.reset") == []


def test_after_a_reset_the_configuration_decides_again(
    client, auth_headers, monkeypatch
):
    _put(client, auth_headers)
    client.delete(POLICY, headers=auth_headers)

    monkeypatch.setattr(
        policy_service, "get_settings", lambda: Settings(jwt_expire_minutes=15)
    )

    assert (
        client.get(POLICY, headers=auth_headers).json()["session_lifetime_minutes"]
        == 15
    )


# ---------------------------------------------------------------- who may


def test_an_observer_may_read_but_not_change_the_policy(
    client, viewer_headers, db_session
):
    assert client.get(POLICY, headers=viewer_headers).status_code == 200

    save = _put(client, viewer_headers)
    reset = client.delete(POLICY, headers=viewer_headers)

    assert (save.status_code, reset.status_code) == (403, 403)
    assert _rows(db_session) == 0
    assert _audit(db_session, "policy.changed") == []


def test_no_token_is_unauthorized_everywhere(client):
    assert client.get(POLICY).status_code == 401
    assert client.put(POLICY, json=SAVED).status_code == 401
    assert client.delete(POLICY).status_code == 401


def test_nothing_secret_reaches_the_audit_log(client, auth_headers, db_session):
    _put(client, auth_headers)
    client.delete(POLICY, headers=auth_headers)

    text = " ".join(
        f"{row.actor} {row.action} {row.target} {row.detail}"
        for row in db_session.execute(select(AuditLogEntry)).scalars()
        if row.action.startswith("policy.")
    )
    assert "Bearer" not in text and "password" not in text.lower()
