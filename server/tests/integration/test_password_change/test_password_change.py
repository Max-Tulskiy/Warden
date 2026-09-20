"""Integration: an operator changes their own password.

Covers `specs/002-panel-reports-and-settings/spec.md` R-5, R-6, R-10 and
acceptance criteria A-4, A-5, A-6 against the real HTTP endpoints.
"""

import pytest
from sqlalchemy import select

from warden_server.models.audit import AuditLogEntry
from warden_server.models.operator import Operator
from warden_server.security import verify_password
from warden_server.services import throttle
from warden_server.services.bootstrap import ensure_seed_operator

NEW_PASSWORD = "a-brand-new-passphrase"  # noqa: S105 -- test value, not a secret


@pytest.fixture(autouse=True)
def _reset_throttle():
    """The throttle is process-wide state, so tests must not leak failure
    counts into each other regardless of run order."""
    throttle.clear_all()
    yield
    throttle.clear_all()


def _change(client, headers, current, new=NEW_PASSWORD):
    return client.post(
        "/api/v1/auth/password",
        headers=headers,
        json={"current_password": current, "new_password": new},
    )


def _login(client, password):
    return client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": password}
    )


def _audit_actions(db_session):
    rows = db_session.execute(select(AuditLogEntry)).scalars().all()
    return [row.action for row in rows]


def test_a_wrong_current_password_is_a_400_and_changes_nothing(
    client, auth_headers, operator, operator_password, db_session
):
    original_hash = operator.password_hash

    response = _change(client, auth_headers, "not-the-current-password")

    assert response.status_code == 400
    db_session.refresh(operator)
    assert operator.password_hash == original_hash
    assert "operator.password_change_failed" in _audit_actions(db_session)


def test_a_too_short_new_password_is_a_422_and_changes_nothing(
    client, auth_headers, operator, operator_password, db_session
):
    original_hash = operator.password_hash

    response = _change(client, auth_headers, operator_password, new="short")

    assert response.status_code == 422
    db_session.refresh(operator)
    assert operator.password_hash == original_hash


def test_the_new_password_logs_in_and_the_old_one_no_longer_does(
    client, auth_headers, operator_password
):
    response = _change(client, auth_headers, operator_password)

    assert response.status_code == 204
    assert _login(client, NEW_PASSWORD).status_code == 200
    assert _login(client, operator_password).status_code == 401


def test_a_successful_change_is_audited_under_the_operator(
    client, auth_headers, operator_password, db_session
):
    _change(client, auth_headers, operator_password)

    row = db_session.execute(
        select(AuditLogEntry).where(AuditLogEntry.action == "operator.password_change")
    ).scalar_one()
    assert row.actor == "admin"
    assert row.target == "admin"


def test_an_already_issued_session_keeps_working_after_the_change(
    client, auth_headers, operator_password
):
    """Documents the boundary from the spec: no session revocation."""
    _change(client, auth_headers, operator_password)

    assert client.get("/api/v1/agents", headers=auth_headers).status_code == 200


def test_the_seed_bootstrap_does_not_restore_the_old_password(
    client, auth_headers, operator, operator_password, db_session
):
    _change(client, auth_headers, operator_password)

    ensure_seed_operator(db_session, username="admin", password=operator_password)
    db_session.commit()

    db_session.refresh(operator)
    assert verify_password(NEW_PASSWORD, operator.password_hash)
    assert not verify_password(operator_password, operator.password_hash)
    assert db_session.query(Operator).count() == 1


def test_repeated_wrong_current_passwords_are_throttled(
    client, auth_headers, operator, operator_password, db_session
):
    original_hash = operator.password_hash
    for _ in range(throttle.MAX_ATTEMPTS):
        assert (
            _change(client, auth_headers, "wrong-current-password").status_code == 400
        )

    # Even the correct current password does not get past an active block.
    blocked = _change(client, auth_headers, operator_password)

    assert blocked.status_code == 429
    db_session.refresh(operator)
    assert operator.password_hash == original_hash
    assert "operator.password_change_throttled" in _audit_actions(db_session)


def test_password_change_failures_do_not_lock_the_operator_out_of_login(
    client, auth_headers, operator_password
):
    for _ in range(throttle.MAX_ATTEMPTS):
        _change(client, auth_headers, "wrong-current-password")

    assert _login(client, operator_password).status_code == 200


def test_changing_the_password_requires_an_operator_token(client, operator_password):
    response = _change(client, {}, operator_password)

    assert response.status_code == 401


def test_no_password_ever_reaches_the_audit_log(
    client, auth_headers, operator_password, db_session
):
    _change(client, auth_headers, "wrong-current-password")
    _change(client, auth_headers, operator_password)

    everything = " ".join(
        f"{row.actor} {row.action} {row.target} {row.detail}"
        for row in db_session.execute(select(AuditLogEntry)).scalars().all()
    )
    for secret in (operator_password, NEW_PASSWORD, "wrong-current-password"):
        assert secret not in everything
