"""Integration: account management by an administrator (spec 005, A-4..A-14, A-18)."""

import json
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from warden_server.models.audit import AuditLogEntry
from warden_server.models.operator import Operator, OperatorRole, OperatorStatus
from warden_server.security import verify_password
from warden_server.services import throttle

PASSWORD = "initial-passphrase-1"  # noqa: S105 -- test value, not a secret
RESET_PASSWORD = "reset-passphrase-2"  # noqa: S105 -- test value, not a secret
OPERATORS = "/api/v1/operators"


@pytest.fixture(autouse=True)
def _reset_throttle():
    throttle.clear_all()
    yield
    throttle.clear_all()


def _create(client, headers, username="colleague", role="viewer", password=PASSWORD):
    return client.post(
        OPERATORS,
        headers=headers,
        json={"username": username, "role": role, "password": password},
    )


def _patch(client, headers, operator_id, **body):
    return client.patch(f"{OPERATORS}/{operator_id}", headers=headers, json=body)


def _reset(client, headers, operator_id, password=RESET_PASSWORD):
    return client.post(
        f"{OPERATORS}/{operator_id}/password",
        headers=headers,
        json={"new_password": password},
    )


def _login(client, username, password):
    return client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )


def _bearer(client, username, password) -> dict[str, str]:
    response = _login(client, username, password)
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _rows(db_session, action):
    return list(
        db_session.execute(
            select(AuditLogEntry).where(AuditLogEntry.action == action)
        ).scalars()
    )


def _row(db_session, username) -> Operator:
    db_session.expire_all()
    return db_session.execute(
        select(Operator).where(Operator.username == username)
    ).scalar_one()


# ---------------------------------------------------------------- list


def test_the_list_shows_every_account_by_username_and_no_password_data(
    client, auth_headers, viewer
):
    response = client.get(OPERATORS, headers=auth_headers)

    assert response.status_code == 200
    rows = response.json()
    assert [row["username"] for row in rows] == ["admin", "watcher"]
    assert {row["username"]: (row["role"], row["status"]) for row in rows} == {
        "admin": ("admin", "active"),
        "watcher": ("viewer", "active"),
    }
    assert all(set(row) == {"id", "username", "role", "status"} for row in rows)
    assert "argon2" not in response.text and "password" not in response.text


# ---------------------------------------------------------------- create


def test_creating_an_operator_returns_it_and_lets_them_sign_in(
    client, auth_headers, db_session
):
    response = _create(client, auth_headers)

    assert response.status_code == 201
    body = response.json()
    assert (body["username"], body["role"], body["status"]) == (
        "colleague",
        "viewer",
        "active",
    )
    assert set(body) == {"id", "username", "role", "status"}
    stored = _row(db_session, "colleague")
    assert stored.password_hash != PASSWORD
    assert verify_password(PASSWORD, stored.password_hash)
    assert _login(client, "colleague", PASSWORD).status_code == 200


def test_creating_an_operator_is_audited_with_the_role_and_no_password(
    client, auth_headers, db_session
):
    _create(client, auth_headers, role="admin")

    (row,) = _rows(db_session, "operator.created")
    assert (row.actor, row.target, row.detail) == (
        "admin",
        "colleague",
        {"role": "admin"},
    )


@pytest.mark.parametrize("username", ["watcher", "Watcher", "WATCHER"])
def test_a_username_that_exists_ignoring_case_is_a_409_and_nothing_is_stored(
    client, auth_headers, viewer, db_session, username
):
    response = _create(client, auth_headers, username=username)

    assert response.status_code == 409
    assert db_session.query(Operator).count() == 2
    assert _rows(db_session, "operator.created") == []


def test_two_requests_creating_one_name_at_once_leave_one_account_and_a_409(
    client, auth_headers, db_session, monkeypatch
):
    """The duplicate check can pass for both requests; the unique constraint
    then decides, and the loser must get the same 409, not a server error."""
    real_commit = db_session.commit
    attempts = []

    def commit_losing_the_race():
        attempts.append(1)
        if len(attempts) == 1:
            raise IntegrityError("INSERT", {}, Exception("duplicate"))
        real_commit()

    monkeypatch.setattr(db_session, "commit", commit_losing_the_race)

    response = _create(client, auth_headers)

    assert response.status_code == 409
    assert db_session.query(Operator).count() == 1
    assert _rows(db_session, "operator.created") == []


@pytest.mark.parametrize(
    "body",
    [
        {"username": "bad name", "role": "viewer", "password": PASSWORD},
        {"username": "colleague", "role": "viewer", "password": "short"},
        {"username": "colleague", "role": "root", "password": PASSWORD},
        {"username": "colleague", "password": PASSWORD},
    ],
)
def test_invalid_input_is_a_422_and_nothing_is_stored(
    client, auth_headers, db_session, body
):
    response = client.post(OPERATORS, headers=auth_headers, json=body)

    assert response.status_code == 422
    assert db_session.query(Operator).count() == 1
    assert _rows(db_session, "operator.created") == []


def test_an_observer_creates_nothing(client, viewer_headers, db_session):
    response = _create(client, viewer_headers)

    assert response.status_code == 403
    assert db_session.query(Operator).count() == 1


# ---------------------------------------------------------------- role


def test_changing_a_role_returns_it_audits_from_and_to_and_keeps_the_session_version(
    client, auth_headers, viewer, db_session
):
    before = _row(db_session, "watcher").token_version

    response = _patch(client, auth_headers, viewer.id, role="admin")

    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    assert _row(db_session, "watcher").role is OperatorRole.ADMIN
    (row,) = _rows(db_session, "operator.role_changed")
    assert (row.actor, row.target, row.detail) == (
        "admin",
        "watcher",
        {"from": "viewer", "to": "admin"},
    )
    assert _row(db_session, "watcher").token_version == before


def test_a_promotion_applies_to_the_open_session_and_a_demotion_too(
    client, auth_headers, viewer, viewer_headers
):
    assert client.get(OPERATORS, headers=viewer_headers).status_code == 403

    _patch(client, auth_headers, viewer.id, role="admin")
    assert client.get(OPERATORS, headers=viewer_headers).status_code == 200

    # The promoted colleague demotes themselves? No -- the first administrator
    # demotes them, and their next administrator action is refused while their
    # session still works for what an observer may do.
    _patch(client, auth_headers, viewer.id, role="viewer")
    assert client.get(OPERATORS, headers=viewer_headers).status_code == 403
    assert client.get("/api/v1/agents", headers=viewer_headers).status_code == 200


# ---------------------------------------------------------------- status


def test_disabling_ends_the_session_refuses_sign_in_and_is_audited(
    client, auth_headers, viewer_headers, viewer_password, db_session
):
    watcher_id = _row(db_session, "watcher").id
    before = _row(db_session, "watcher").token_version

    response = _patch(client, auth_headers, watcher_id, status="disabled")

    assert response.status_code == 200
    assert response.json()["status"] == "disabled"
    assert client.get("/api/v1/agents", headers=viewer_headers).status_code == 401
    assert _login(client, "watcher", viewer_password).status_code == 401
    assert _row(db_session, "watcher").token_version == before + 1
    (row,) = _rows(db_session, "operator.disabled")
    assert (row.actor, row.target) == ("admin", "watcher")


def test_enabling_lets_the_person_sign_in_again_but_not_with_an_old_session(
    client, auth_headers, viewer_headers, viewer_password, db_session
):
    watcher_id = _row(db_session, "watcher").id
    _patch(client, auth_headers, watcher_id, status="disabled")

    response = _patch(client, auth_headers, watcher_id, status="active")

    assert response.status_code == 200
    assert _login(client, "watcher", viewer_password).status_code == 200
    # Disabling ended that session for good; enabling does not resurrect it.
    assert client.get("/api/v1/agents", headers=viewer_headers).status_code == 401
    (row,) = _rows(db_session, "operator.enabled")
    assert (row.actor, row.target) == ("admin", "watcher")


def test_setting_what_the_account_already_has_succeeds_and_records_nothing(
    client, auth_headers, viewer, db_session
):
    before = _row(db_session, "watcher").token_version

    role_again = _patch(client, auth_headers, viewer.id, role="viewer")
    status_again = _patch(client, auth_headers, viewer.id, status="active")

    assert role_again.status_code == status_again.status_code == 200
    for action in ("operator.role_changed", "operator.disabled", "operator.enabled"):
        assert _rows(db_session, action) == []
    assert _row(db_session, "watcher").token_version == before


def test_a_role_and_a_status_in_one_request_are_both_applied_and_both_audited(
    client, auth_headers, viewer, db_session
):
    response = _patch(client, auth_headers, viewer.id, role="admin", status="disabled")

    assert response.status_code == 200
    assert (response.json()["role"], response.json()["status"]) == (
        "admin",
        "disabled",
    )
    assert len(_rows(db_session, "operator.role_changed")) == 1
    assert len(_rows(db_session, "operator.disabled")) == 1


# ---------------------------------------------------------------- own account


@pytest.mark.parametrize("body", [{"role": "viewer"}, {"status": "disabled"}])
def test_an_administrator_cannot_change_their_own_role_or_status(
    client, auth_headers, operator, db_session, body
):
    response = _patch(client, auth_headers, operator.id, **body)

    assert response.status_code == 409
    stored = _row(db_session, "admin")
    assert (stored.role, stored.status) == (OperatorRole.ADMIN, OperatorStatus.ACTIVE)
    assert client.get(OPERATORS, headers=auth_headers).status_code == 200


def test_an_administrator_cannot_reset_their_own_password_here(
    client, auth_headers, operator, operator_password, db_session
):
    response = _reset(client, auth_headers, operator.id)

    assert response.status_code == 409
    assert _login(client, "admin", operator_password).status_code == 200
    assert _rows(db_session, "operator.password_reset") == []


def test_the_last_administrator_cannot_be_locked_out_by_the_panel(
    client, auth_headers, operator, db_session
):
    """With one administrator, the only account they could demote is their own,
    and that is refused; nothing else can leave the deployment with none."""
    others = [
        _patch(client, auth_headers, operator.id, role="viewer"),
        _patch(client, auth_headers, operator.id, status="disabled"),
    ]

    assert [response.status_code for response in others] == [409, 409]
    admins = db_session.query(Operator).filter_by(
        role=OperatorRole.ADMIN, status=OperatorStatus.ACTIVE
    )
    assert admins.count() == 1


def test_one_administrator_can_disable_another_and_the_other_is_locked_out(
    client, auth_headers, db_session
):
    second = _create(client, auth_headers, username="second", role="admin").json()
    second_headers = _bearer(client, "second", PASSWORD)
    assert client.get(OPERATORS, headers=second_headers).status_code == 200

    response = _patch(client, auth_headers, second["id"], status="disabled")

    assert response.status_code == 200
    assert client.get(OPERATORS, headers=second_headers).status_code == 401
    assert client.get(OPERATORS, headers=auth_headers).status_code == 200


# ---------------------------------------------------------------- password reset


def test_a_reset_replaces_the_password_and_ends_the_accounts_sessions(
    client, auth_headers, viewer_headers, viewer_password, db_session
):
    watcher_id = _row(db_session, "watcher").id
    before = _row(db_session, "watcher").token_version

    response = _reset(client, auth_headers, watcher_id)

    assert response.status_code == 204
    assert _login(client, "watcher", viewer_password).status_code == 401
    assert _login(client, "watcher", RESET_PASSWORD).status_code == 200
    assert client.get("/api/v1/agents", headers=viewer_headers).status_code == 401
    assert _row(db_session, "watcher").token_version == before + 1
    (row,) = _rows(db_session, "operator.password_reset")
    assert (row.actor, row.target) == ("admin", "watcher")


def test_a_reset_unlocks_an_account_the_throttle_had_locked(
    client, auth_headers, viewer, viewer_password
):
    for _ in range(5):
        assert _login(client, "watcher", "not-the-password").status_code == 401
    assert _login(client, "watcher", viewer_password).status_code == 429
    for _ in range(5):
        throttle.record_failure("password-change:watcher")

    _reset(client, auth_headers, viewer.id)

    assert _login(client, "watcher", RESET_PASSWORD).status_code == 200
    assert not throttle.is_throttled("password-change:watcher")


def test_a_disabled_account_can_have_its_password_reset(client, auth_headers, viewer):
    _patch(client, auth_headers, viewer.id, status="disabled")

    assert _reset(client, auth_headers, viewer.id).status_code == 204


# ---------------------------------------------------------------- unknown, no token


def test_an_unknown_account_is_a_404_on_both_id_endpoints(client, auth_headers):
    unknown = uuid.uuid4()

    assert _patch(client, auth_headers, unknown, status="active").status_code == 404
    assert _reset(client, auth_headers, unknown).status_code == 404


def test_no_token_is_unauthorized_on_every_account_endpoint(client, viewer):
    assert client.get(OPERATORS).status_code == 401
    assert client.post(OPERATORS, json={}).status_code == 401
    assert client.patch(f"{OPERATORS}/{viewer.id}", json={}).status_code == 401
    reset = client.post(f"{OPERATORS}/{viewer.id}/password", json={})
    assert reset.status_code == 401


# ---------------------------------------------------------------- secrets


def test_no_password_or_hash_reaches_the_audit_log_or_any_response(
    client, auth_headers, viewer, viewer_password, db_session
):
    responses = [
        _create(client, auth_headers, username="second", password=PASSWORD),
        _patch(client, auth_headers, viewer.id, role="admin"),
        _patch(client, auth_headers, viewer.id, status="disabled"),
        _reset(client, auth_headers, viewer.id),
        client.get(OPERATORS, headers=auth_headers),
    ]

    audit = " ".join(
        f"{row.actor} {row.action} {row.target} {json.dumps(row.detail)}"
        for row in db_session.execute(select(AuditLogEntry)).scalars()
    )
    everything = audit + " ".join(response.text for response in responses)
    hashes = [
        row.password_hash for row in db_session.execute(select(Operator)).scalars()
    ]
    for secret in (PASSWORD, RESET_PASSWORD, viewer_password, *hashes):
        assert secret not in everything
