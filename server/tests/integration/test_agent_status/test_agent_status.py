"""Integration: an operator disables and re-enables a station.

Covers `specs/002-panel-reports-and-settings/spec.md` R-8, R-9, R-10 and
acceptance criteria A-8, A-9, A-10 against the real HTTP endpoints.
"""

import uuid

import pytest
from sqlalchemy import select

from warden_server.models.audit import AuditLogEntry


def _set_status(client, headers, agent_id, status):
    return client.patch(
        f"/api/v1/agents/{agent_id}", headers=headers, json={"status": status}
    )


def _audit_rows(db_session, action):
    return list(
        db_session.execute(select(AuditLogEntry).where(AuditLogEntry.action == action))
        .scalars()
        .all()
    )


def _agent_calls(client, agent_id):
    """One call per agent-facing endpoint, taking the headers to send."""
    return {
        "tasks": lambda headers: client.get(
            f"/api/v1/agents/{agent_id}/tasks", headers=headers
        ),
        "reports": lambda headers: client.post(
            f"/api/v1/agents/{agent_id}/reports",
            headers=headers,
            json={"task_id": str(uuid.uuid4()), "events": []},
        ),
        "inventory": lambda headers: client.post(
            f"/api/v1/agents/{agent_id}/inventory",
            headers=headers,
            json={"hardware": {}, "software": {}},
        ),
    }


def test_disabling_returns_the_station_with_its_new_status(
    client, auth_headers, enrolled_agent
):
    response = _set_status(client, auth_headers, enrolled_agent["agent_id"], "disabled")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == enrolled_agent["agent_id"]
    assert body["status"] == "disabled"


@pytest.mark.parametrize("endpoint", ["tasks", "reports", "inventory"])
def test_a_disabled_agent_is_rejected_like_a_wrong_key(
    client, auth_headers, enrolled_agent, agent_headers, endpoint
):
    agent_id = enrolled_agent["agent_id"]
    call = _agent_calls(client, agent_id)[endpoint]
    _set_status(client, auth_headers, agent_id, "disabled")

    disabled = call(agent_headers)
    wrong_key = call({"X-Agent-Key": "not-the-agent-key"})

    assert disabled.status_code == 401
    assert disabled.json() == wrong_key.json()


def test_re_enabling_lets_the_same_key_authenticate_again(
    client, auth_headers, enrolled_agent, agent_headers
):
    agent_id = enrolled_agent["agent_id"]
    _set_status(client, auth_headers, agent_id, "disabled")
    assert (
        client.get(
            f"/api/v1/agents/{agent_id}/tasks", headers=agent_headers
        ).status_code
        == 401
    )

    re_enabled = _set_status(client, auth_headers, agent_id, "active")

    assert re_enabled.status_code == 200
    assert re_enabled.json()["status"] == "active"
    assert (
        client.get(
            f"/api/v1/agents/{agent_id}/tasks", headers=agent_headers
        ).status_code
        == 200
    )


def test_each_status_change_is_audited_with_the_hostname(
    client, auth_headers, enrolled_agent, db_session
):
    agent_id = enrolled_agent["agent_id"]

    _set_status(client, auth_headers, agent_id, "disabled")
    _set_status(client, auth_headers, agent_id, "active")

    disabled = _audit_rows(db_session, "agent.disabled")
    enabled = _audit_rows(db_session, "agent.enabled")
    assert len(disabled) == 1
    assert len(enabled) == 1
    assert disabled[0].actor == "admin"
    assert disabled[0].target == agent_id
    assert disabled[0].detail["hostname"] == "WORKSTATION-01"
    assert enabled[0].target == agent_id


def test_setting_the_current_status_is_a_no_op_without_an_audit_row(
    client, auth_headers, enrolled_agent, db_session
):
    response = _set_status(client, auth_headers, enrolled_agent["agent_id"], "active")

    assert response.status_code == 200
    assert response.json()["status"] == "active"
    assert _audit_rows(db_session, "agent.enabled") == []
    assert _audit_rows(db_session, "agent.disabled") == []


def test_an_unknown_station_is_a_404(client, auth_headers):
    response = _set_status(client, auth_headers, uuid.uuid4(), "disabled")

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown agent"


def test_changing_status_requires_an_operator_token(client, enrolled_agent):
    response = client.patch(
        f"/api/v1/agents/{enrolled_agent['agent_id']}", json={"status": "disabled"}
    )

    assert response.status_code == 401


def test_an_agent_key_cannot_change_a_status(client, enrolled_agent, agent_headers):
    response = client.patch(
        f"/api/v1/agents/{enrolled_agent['agent_id']}",
        headers=agent_headers,
        json={"status": "disabled"},
    )

    assert response.status_code == 401


def test_an_invalid_status_value_is_a_422(client, auth_headers, enrolled_agent):
    response = _set_status(client, auth_headers, enrolled_agent["agent_id"], "deleted")

    assert response.status_code == 422
