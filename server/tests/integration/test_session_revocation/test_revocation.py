"""Integration: what ends an operator's sessions (spec 004, R-1..R-3, R-6, R-7).

A "session" is a token from a login. Two logins are made through the real
endpoint to stand for two browsers; whichever one acts, the assertions are made
by reading a panel endpoint with each token.
"""

import pytest
from sqlalchemy import select

from warden_server.models.audit import AuditLogEntry
from warden_server.security import decode_access_token
from warden_server.services import throttle

PANEL_READ = "/api/v1/agents"
NEW_PASSWORD = "a-brand-new-passphrase"  # noqa: S105 -- test value, not a secret


@pytest.fixture(autouse=True)
def _reset_throttle():
    throttle.clear_all()
    yield
    throttle.clear_all()


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _login(client, password) -> str:
    response = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": password}
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _status(client, headers) -> int:
    return client.get(PANEL_READ, headers=headers).status_code


def _change(client, headers, current, new=NEW_PASSWORD):
    return client.post(
        "/api/v1/auth/password",
        headers=headers,
        json={"current_password": current, "new_password": new},
    )


def _logout_all(client, headers):
    return client.post("/api/v1/auth/logout-all", headers=headers)


def _version(db_session, operator) -> int:
    db_session.refresh(operator)
    return operator.token_version


def test_a_password_change_returns_a_working_token_for_the_current_session(
    client, auth_headers, operator_password
):
    response = _change(client, auth_headers, operator_password)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"  # noqa: S105 -- scheme name, not a secret
    assert _status(client, _bearer(body["access_token"])) == 200


def test_the_returned_token_carries_the_new_version(
    client, auth_headers, operator, operator_password, db_session
):
    before = _version(db_session, operator)

    token = _change(client, auth_headers, operator_password).json()["access_token"]

    claims = decode_access_token(token)
    assert claims is not None
    assert claims.version == before + 1 == _version(db_session, operator)


def test_a_password_change_ends_the_other_sessions_and_the_old_token(
    client, auth_headers, operator_password
):
    other_browser = _bearer(_login(client, operator_password))
    assert _status(client, other_browser) == 200

    new_token = _change(client, auth_headers, operator_password).json()["access_token"]

    assert _status(client, other_browser) == 401
    assert _status(client, auth_headers) == 401
    assert _status(client, _bearer(new_token)) == 200


def test_a_wrong_current_password_ends_nothing(
    client, auth_headers, operator, operator_password, db_session
):
    other_browser = _bearer(_login(client, operator_password))
    before = _version(db_session, operator)

    response = _change(client, auth_headers, "wrong-current-password")

    assert response.status_code == 400
    assert _version(db_session, operator) == before
    assert _status(client, other_browser) == 200
    assert _status(client, auth_headers) == 200


def test_a_refused_new_password_ends_nothing(
    client, auth_headers, operator, operator_password, db_session
):
    other_browser = _bearer(_login(client, operator_password))
    before = _version(db_session, operator)

    too_short = _change(client, auth_headers, operator_password, new="short")

    assert too_short.status_code == 422
    assert _version(db_session, operator) == before
    assert _status(client, other_browser) == 200


def test_a_throttled_attempt_ends_nothing(
    client, auth_headers, operator, operator_password, db_session
):
    other_browser = _bearer(_login(client, operator_password))
    before = _version(db_session, operator)
    for _ in range(5):
        assert (
            _change(client, auth_headers, "wrong-current-password").status_code == 400
        )

    blocked = _change(client, auth_headers, operator_password)

    assert blocked.status_code == 429
    assert _version(db_session, operator) == before
    assert _status(client, other_browser) == 200


def test_two_changes_in_a_row_each_end_what_came_before(
    client, auth_headers, operator_password
):
    first = _change(client, auth_headers, operator_password).json()["access_token"]
    second = _change(
        client, _bearer(first), NEW_PASSWORD, new="yet-another-passphrase"
    ).json()["access_token"]

    assert _status(client, _bearer(first)) == 401
    assert _status(client, _bearer(second)) == 200


def test_logout_all_ends_every_session_including_the_caller(
    client, auth_headers, operator_password
):
    other_browser = _bearer(_login(client, operator_password))

    response = _logout_all(client, auth_headers)

    assert response.status_code == 204
    assert _status(client, auth_headers) == 401
    assert _status(client, other_browser) == 401


def test_a_new_login_works_after_logout_all(client, auth_headers, operator_password):
    _logout_all(client, auth_headers)

    assert _status(client, _bearer(_login(client, operator_password))) == 200


def test_logout_all_raises_the_version_once(client, auth_headers, operator, db_session):
    before = _version(db_session, operator)

    _logout_all(client, auth_headers)

    assert _version(db_session, operator) == before + 1


def test_logout_all_without_a_token_is_unauthorized(client, operator):
    assert _logout_all(client, {}).status_code == 401


def test_an_ended_session_cannot_end_anything_again(
    client, auth_headers, operator, db_session
):
    _logout_all(client, auth_headers)
    after_first = _version(db_session, operator)

    again = _logout_all(client, auth_headers)

    assert again.status_code == 401
    assert _version(db_session, operator) == after_first


def test_both_actions_are_audited_under_the_operator(
    client, auth_headers, operator_password, db_session
):
    new_token = _change(client, auth_headers, operator_password).json()["access_token"]
    _logout_all(client, _bearer(new_token))

    rows = {
        row.action: row
        for row in db_session.execute(select(AuditLogEntry)).scalars().all()
    }
    for action in ("operator.password_change", "operator.sessions_revoked"):
        assert rows[action].actor == "admin"
        assert rows[action].target == "admin"


def test_a_failed_change_writes_no_revocation_entry(client, auth_headers, db_session):
    _change(client, auth_headers, "wrong-current-password")

    actions = [
        row.action for row in db_session.execute(select(AuditLogEntry)).scalars()
    ]
    assert "operator.sessions_revoked" not in actions
    assert "operator.password_change" not in actions


def test_no_password_or_token_reaches_the_audit_log(
    client, auth_headers, operator_password, db_session
):
    _change(client, auth_headers, "wrong-current-password")
    issued = _change(client, auth_headers, operator_password).json()["access_token"]
    _logout_all(client, _bearer(issued))

    everything = " ".join(
        f"{row.actor} {row.action} {row.target} {row.detail}"
        for row in db_session.execute(select(AuditLogEntry)).scalars().all()
    )
    authorization = auth_headers["Authorization"].removeprefix("Bearer ")
    for secret in (
        operator_password,
        NEW_PASSWORD,
        "wrong-current-password",
        issued,
        authorization,
    ):
        assert secret not in everything
