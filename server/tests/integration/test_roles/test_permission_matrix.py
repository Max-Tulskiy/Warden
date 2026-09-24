"""The permission matrix: what each role may do (spec 005, R-7..R-9, A-1, A-2).

Every operator-facing endpoint is called with an administrator's token and an
observer's token, and the outcome is compared with the table in plan section 1.
This is the executable copy of that table:
`test_every_operator_endpoint_is_in_the_matrix` fails when an endpoint is added to
the API without a row here, so a new endpoint cannot ship without someone
deciding which role may call it.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from warden_server.main import app
from warden_server.services import throttle


@dataclass(frozen=True)
class Endpoint:
    method: str
    path: str
    observer: bool  # may an observer call it?
    body: str | None = None  # a key of BODIES
    params: str | None = None  # a key of PARAMS

    @property
    def label(self) -> str:
        return f"{self.method} {self.path}"


ENDPOINTS = [
    # Both roles.
    Endpoint("GET", "/api/v1/agents", observer=True),
    Endpoint("GET", "/api/v1/agents/{agent_id}/events", observer=True),
    Endpoint("GET", "/api/v1/agents/{agent_id}/inventory/changes", observer=True),
    Endpoint("GET", "/api/v1/events", observer=True, params="range"),
    Endpoint("GET", "/api/v1/policy", observer=True),
    Endpoint("GET", "/api/v1/auth/me", observer=True),
    Endpoint("POST", "/api/v1/auth/password", observer=True, body="wrong_password"),
    Endpoint("POST", "/api/v1/auth/logout-all", observer=True),
    # Administrators only.
    Endpoint("POST", "/api/v1/enrollment-tokens", observer=False),
    Endpoint("PATCH", "/api/v1/agents/{agent_id}", observer=False, body="agent_status"),
    Endpoint(
        "POST", "/api/v1/agents/{agent_id}/requests", observer=False, body="window"
    ),
    Endpoint("GET", "/api/v1/audit", observer=False, params="range"),
    Endpoint("PUT", "/api/v1/policy", observer=False, body="policy"),
    Endpoint("DELETE", "/api/v1/policy", observer=False),
    Endpoint("GET", "/api/v1/operators", observer=False),
    Endpoint("POST", "/api/v1/operators", observer=False, body="new_operator"),
    Endpoint(
        "PATCH", "/api/v1/operators/{operator_id}", observer=False, body="no_change"
    ),
    Endpoint(
        "POST",
        "/api/v1/operators/{operator_id}/password",
        observer=False,
        body="reset_password",
    ),
]


def _bodies() -> dict[str, dict]:
    now = datetime.now(UTC)
    return {
        "wrong_password": {
            "current_password": "definitely-not-the-password",
            "new_password": "some-new-long-passphrase",
        },
        "agent_status": {"status": "active"},
        "window": {
            "window_start": (now - timedelta(hours=2)).isoformat(),
            "window_end": (now - timedelta(hours=1)).isoformat(),
        },
        "new_operator": {
            "username": "matrix-user",
            "role": "viewer",
            "password": "a-long-enough-password",
        },
        "no_change": {"status": "active"},
        "policy": {
            "max_request_window_hours": 2,
            "enrollment_token_ttl_hours": 12,
            "session_lifetime_minutes": 60,
        },
        "reset_password": {"new_password": "another-long-passphrase"},
    }


def _params() -> dict[str, dict]:
    now = datetime.now(UTC)
    return {
        "range": {
            "start": (now - timedelta(hours=1)).isoformat(),
            "end": (now + timedelta(hours=1)).isoformat(),
        }
    }


@pytest.fixture(autouse=True)
def _reset_throttle():
    throttle.clear_all()
    yield
    throttle.clear_all()


def _call(client, endpoint: Endpoint, headers, *, agent_id, operator_id):
    return client.request(
        endpoint.method,
        endpoint.path.format(agent_id=agent_id, operator_id=operator_id),
        headers=headers,
        json=_bodies()[endpoint.body] if endpoint.body else None,
        params=_params()[endpoint.params] if endpoint.params else None,
    )


@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=lambda e: e.label)
def test_an_administrator_is_never_refused_on_grounds_of_role(
    client, auth_headers, viewer, enrolled_agent, endpoint
):
    response = _call(
        client,
        endpoint,
        auth_headers,
        agent_id=enrolled_agent["agent_id"],
        operator_id=viewer.id,
    )

    assert response.status_code not in (401, 403), response.text


@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=lambda e: e.label)
def test_an_observer_gets_what_the_table_says(
    client, viewer_headers, viewer, enrolled_agent, endpoint
):
    response = _call(
        client,
        endpoint,
        viewer_headers,
        agent_id=enrolled_agent["agent_id"],
        operator_id=viewer.id,
    )

    if endpoint.observer:
        assert response.status_code not in (401, 403), response.text
    else:
        assert response.status_code == 403, response.text


@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=lambda e: e.label)
def test_no_token_is_unauthorized_everywhere(client, enrolled_agent, viewer, endpoint):
    response = _call(
        client,
        endpoint,
        {},
        agent_id=enrolled_agent["agent_id"],
        operator_id=viewer.id,
    )

    assert response.status_code == 401


def test_a_refused_observer_is_told_they_lack_the_role_not_that_they_are_signed_out(
    client, viewer_headers
):
    response = client.get("/api/v1/operators", headers=viewer_headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "Administrator role required"


def test_every_operator_endpoint_is_in_the_matrix():
    """An endpoint that takes a bearer token must have a row above."""
    in_schema = {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method, operation in operations.items()
        if operation.get("security")
    }

    assert in_schema == {(e.method, e.path) for e in ENDPOINTS}


def test_the_contract_documents_the_403_of_every_administrator_only_operation():
    """A caller reading the contract must be able to learn that an observer is
    refused; FastAPI does not derive that from a dependency on its own."""
    paths = app.openapi()["paths"]

    undocumented = [
        endpoint.label
        for endpoint in ENDPOINTS
        if not endpoint.observer
        and "403" not in paths[endpoint.path][endpoint.method.lower()]["responses"]
    ]

    assert undocumented == []
