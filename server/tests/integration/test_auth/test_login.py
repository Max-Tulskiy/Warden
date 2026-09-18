"""Integration: operator login and access to protected panel endpoints."""

import pytest
from sqlalchemy import select

from warden_server.models.audit import AuditLogEntry
from warden_server.services import throttle


@pytest.fixture(autouse=True)
def _reset_login_throttle():
    """The throttle is process-wide state, not per-session (services/
    throttle.py) -- tests must not leak failed-attempt counts into each
    other regardless of run order."""
    throttle.clear_all()
    yield
    throttle.clear_all()


def test_login_with_correct_credentials_returns_a_bearer_token(
    client, operator, operator_password
):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": operator.username, "password": operator_password},
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"  # noqa: S105 -- OAuth2 scheme name


def test_login_with_a_wrong_password_is_rejected(client, operator):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": operator.username, "password": "wrong"},
    )

    assert response.status_code == 401


def test_panel_endpoints_reject_a_request_without_a_token(client):
    response = client.get("/api/v1/agents")

    assert response.status_code == 401


def test_panel_endpoints_accept_a_valid_token(client, auth_headers):
    response = client.get("/api/v1/agents", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == []


def test_a_failed_login_is_audited_without_leaking_the_password(
    client, db_session, operator
):
    client.post(
        "/api/v1/auth/login",
        json={"username": operator.username, "password": "a-guessed-password"},
    )

    entry = db_session.execute(
        select(AuditLogEntry).where(AuditLogEntry.action == "operator.login_failed")
    ).scalar_one()
    assert entry.actor == operator.username
    assert "a-guessed-password" not in str(entry.detail)


def test_repeated_failed_logins_are_throttled(client, operator):
    for _ in range(throttle.MAX_ATTEMPTS):
        response = client.post(
            "/api/v1/auth/login",
            json={"username": operator.username, "password": "wrong"},
        )
        assert response.status_code == 401

    throttled = client.post(
        "/api/v1/auth/login",
        json={"username": operator.username, "password": "wrong"},
    )
    assert throttled.status_code == 429


def test_a_successful_login_resets_the_throttle_counter(
    client, operator, operator_password
):
    for _ in range(throttle.MAX_ATTEMPTS - 1):
        client.post(
            "/api/v1/auth/login",
            json={"username": operator.username, "password": "wrong"},
        )

    ok = client.post(
        "/api/v1/auth/login",
        json={"username": operator.username, "password": operator_password},
    )
    assert ok.status_code == 200

    again = client.post(
        "/api/v1/auth/login",
        json={"username": operator.username, "password": operator_password},
    )
    assert again.status_code == 200


def test_an_oversized_password_is_rejected_before_hashing(client, operator):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": operator.username, "password": "x" * 1025},
    )

    assert response.status_code == 422
