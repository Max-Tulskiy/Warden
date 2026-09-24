"""Every use of the three limits reads the one in force (spec 006, A-1..A-6).

The policy is saved straight through the service here, so these tests show what
each endpoint does with it, apart from the endpoint that saves it.
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from warden_server.config import Settings, get_settings
from warden_server.models.enrollment import EnrollmentToken
from warden_server.schemas.policy import PolicyValues
from warden_server.services import policy as policy_service

SLACK = 15  # seconds of tolerance for "now + N"


def _save(db_session, *, window=4, token=24, session=480):
    policy_service.save_policy(
        db_session,
        PolicyValues(
            max_request_window_hours=window,
            enrollment_token_ttl_hours=token,
            session_lifetime_minutes=session,
        ),
        actor="admin",
    )
    db_session.commit()


def _window(hours):
    end = datetime.now(UTC) - timedelta(minutes=5)
    return {
        "window_start": (end - timedelta(hours=hours)).isoformat(),
        "window_end": end.isoformat(),
    }


def _request(client, headers, agent_id, hours):
    return client.post(
        f"/api/v1/agents/{agent_id}/requests", headers=headers, json=_window(hours)
    )


def _expiry(access_token: str) -> float:
    settings = get_settings()
    claims = jwt.decode(
        access_token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )
    return claims["exp"]


def _login(client, password):
    response = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": password}
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _within(actual: float, expected: datetime) -> bool:
    return abs(actual - expected.timestamp()) <= SLACK


# ---------------------------------------------------------------- the window


def test_a_saved_window_limit_refuses_a_longer_request_and_accepts_the_limit(
    client, auth_headers, enrolled_agent, db_session
):
    _save(db_session, window=2)
    agent_id = enrolled_agent["agent_id"]

    too_long = _request(client, auth_headers, agent_id, 3)
    at_the_limit = _request(client, auth_headers, agent_id, 2)

    assert too_long.status_code == 422
    assert "2 hours" in too_long.json()["detail"]
    assert at_the_limit.status_code == 201


def test_a_request_already_queued_is_not_touched_by_a_later_lower_limit(
    client, auth_headers, enrolled_agent, db_session
):
    agent_id = enrolled_agent["agent_id"]
    queued = _request(client, auth_headers, agent_id, 4)
    assert queued.status_code == 201

    _save(db_session, window=1)

    assert (
        client.get(
            f"/api/v1/agents/{agent_id}/events", headers=auth_headers
        ).status_code
        == 200
    )
    assert _request(client, auth_headers, agent_id, 2).status_code == 422


def test_with_nothing_saved_the_default_limit_applies(
    client, auth_headers, enrolled_agent
):
    agent_id = enrolled_agent["agent_id"]

    assert _request(client, auth_headers, agent_id, 4).status_code == 201


def test_a_configured_six_hours_never_lets_a_longer_window_through(
    client, auth_headers, enrolled_agent, monkeypatch
):
    """Principle 3, with nothing saved and a configuration that says otherwise."""
    monkeypatch.setattr(
        policy_service, "get_settings", lambda: Settings(max_request_window_hours=6)
    )
    agent_id = enrolled_agent["agent_id"]

    assert _request(client, auth_headers, agent_id, 5).status_code == 422
    assert _request(client, auth_headers, agent_id, 4).status_code == 201


def test_an_unknown_station_is_still_a_404_within_the_limit(
    client, auth_headers, db_session
):
    _save(db_session, window=2)

    response = _request(client, auth_headers, "00000000-0000-4000-8000-000000000000", 1)

    assert response.status_code == 404


# ---------------------------------------------------------------- enrollment tokens


def test_a_saved_token_lifetime_applies_to_the_next_token_only(
    client, auth_headers, db_session
):
    before = client.post("/api/v1/enrollment-tokens", headers=auth_headers)
    before_expiry = datetime.fromisoformat(before.json()["expires_at"])
    assert _within(before_expiry.timestamp(), datetime.now(UTC) + timedelta(hours=24))

    _save(db_session, token=2)
    after = client.post("/api/v1/enrollment-tokens", headers=auth_headers)

    after_expiry = datetime.fromisoformat(after.json()["expires_at"])
    assert _within(after_expiry.timestamp(), datetime.now(UTC) + timedelta(hours=2))
    stored = {
        row.expires_at.replace(tzinfo=UTC) for row in db_session.query(EnrollmentToken)
    }
    assert before_expiry.replace(tzinfo=UTC) in stored  # the earlier one is unchanged


# ---------------------------------------------------------------- sessions


def test_with_nothing_saved_a_session_lasts_the_configured_time(
    client, operator, operator_password
):
    token = _login(client, operator_password)

    assert _within(_expiry(token), datetime.now(UTC) + timedelta(minutes=480))


def test_a_saved_session_length_applies_to_the_next_sign_in(
    client, operator, operator_password, db_session
):
    _save(db_session, session=30)

    token = _login(client, operator_password)

    assert _within(_expiry(token), datetime.now(UTC) + timedelta(minutes=30))


def test_a_session_issued_before_the_change_keeps_its_expiry_and_still_works(
    client, operator, operator_password, db_session
):
    held = _login(client, operator_password)
    held_expiry = _expiry(held)

    _save(db_session, session=5)

    response = client.get("/api/v1/agents", headers={"Authorization": f"Bearer {held}"})
    assert response.status_code == 200
    assert _expiry(held) == held_expiry
    assert _within(held_expiry, datetime.now(UTC) + timedelta(minutes=480))


@pytest.mark.parametrize("session", [5, 60, 1440])
def test_a_password_change_returns_a_token_of_the_length_in_force(
    client, auth_headers, operator_password, db_session, session
):
    _save(db_session, session=session)

    response = client.post(
        "/api/v1/auth/password",
        headers=auth_headers,
        json={
            "current_password": operator_password,
            "new_password": "a-brand-new-passphrase",
        },
    )

    assert response.status_code == 200
    assert _within(
        _expiry(response.json()["access_token"]),
        datetime.now(UTC) + timedelta(minutes=session),
    )
