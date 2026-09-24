"""A disabled account cannot sign in or use a session (spec 005, R-5, A-10).

The status is changed straight in the database here, so these tests show the
check itself, apart from the endpoint that will normally flip it (which also
raises the session version, a second and independent reason the sessions end).
"""

import pytest
from sqlalchemy import select

from warden_server.models.audit import AuditLogEntry
from warden_server.models.operator import OperatorStatus
from warden_server.services import throttle


@pytest.fixture(autouse=True)
def _reset_throttle():
    throttle.clear_all()
    yield
    throttle.clear_all()


def _set_status(db_session, operator, status):
    operator.status = status
    db_session.commit()


def _login(client, username, password):
    return client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )


def _failure_reasons(db_session):
    rows = db_session.execute(
        select(AuditLogEntry).where(AuditLogEntry.action == "operator.login_failed")
    ).scalars()
    return [row.detail.get("reason") for row in rows]


def test_a_disabled_operator_cannot_sign_in_and_is_told_what_a_wrong_password_gets(
    client, viewer, viewer_password, db_session
):
    wrong = _login(client, viewer.username, "not-the-password")
    _set_status(db_session, viewer, OperatorStatus.DISABLED)

    refused = _login(client, viewer.username, viewer_password)

    assert refused.status_code == 401
    assert refused.json() == wrong.json()


def test_the_audit_log_tells_a_disabled_account_from_a_wrong_password(
    client, viewer, viewer_password, db_session
):
    _set_status(db_session, viewer, OperatorStatus.DISABLED)

    _login(client, viewer.username, viewer_password)
    _login(client, viewer.username, "not-the-password")

    assert _failure_reasons(db_session) == ["disabled", "bad_password"]


def test_a_disabled_operators_existing_session_is_refused_and_returns_on_enabling(
    client, viewer, viewer_headers, db_session
):
    assert client.get("/api/v1/agents", headers=viewer_headers).status_code == 200

    _set_status(db_session, viewer, OperatorStatus.DISABLED)
    assert client.get("/api/v1/agents", headers=viewer_headers).status_code == 401

    # The session version never moved, so it is the status alone doing this.
    _set_status(db_session, viewer, OperatorStatus.ACTIVE)
    assert client.get("/api/v1/agents", headers=viewer_headers).status_code == 200


def test_a_disabled_administrator_is_refused_on_an_administrator_endpoint_too(
    client, auth_headers, operator, db_session
):
    _set_status(db_session, operator, OperatorStatus.DISABLED)

    assert (
        client.post("/api/v1/enrollment-tokens", headers=auth_headers).status_code
        == 401
    )
