"""Integration: an agent's inventory snapshots surface as a change timeline."""

from sqlalchemy import select

from warden_server.models.audit import AuditLogEntry


def test_inventory_submission_updates_last_seen_and_records_changes(
    client, auth_headers, enrolled_agent, agent_headers
):
    agent_id = enrolled_agent["agent_id"]

    first = client.post(
        f"/api/v1/agents/{agent_id}/inventory",
        headers=agent_headers,
        json={"hardware": {"cpu": "x86_64"}, "software": {"nginx": "1.24"}},
    )
    assert first.status_code == 204

    changes = client.get(
        f"/api/v1/agents/{agent_id}/inventory/changes", headers=auth_headers
    )
    assert changes.status_code == 200
    assert len(changes.json()) == 1

    unchanged = client.post(
        f"/api/v1/agents/{agent_id}/inventory",
        headers=agent_headers,
        json={"hardware": {"cpu": "x86_64"}, "software": {"nginx": "1.24"}},
    )
    assert unchanged.status_code == 204

    still_one_change = client.get(
        f"/api/v1/agents/{agent_id}/inventory/changes", headers=auth_headers
    )
    assert len(still_one_change.json()) == 1

    changed = client.post(
        f"/api/v1/agents/{agent_id}/inventory",
        headers=agent_headers,
        json={"hardware": {"cpu": "x86_64"}, "software": {"nginx": "1.26"}},
    )
    assert changed.status_code == 204

    two_changes = client.get(
        f"/api/v1/agents/{agent_id}/inventory/changes", headers=auth_headers
    )
    assert len(two_changes.json()) == 2

    agents = client.get("/api/v1/agents", headers=auth_headers)
    assert agents.status_code == 200
    assert agents.json()[0]["last_seen_at"] is not None


def test_the_change_audit_entry_names_the_stored_change(
    client, auth_headers, enrolled_agent, agent_headers, db_session
):
    agent_id = enrolled_agent["agent_id"]
    response = client.post(
        f"/api/v1/agents/{agent_id}/inventory",
        headers=agent_headers,
        json={"hardware": {"cpu": "x86_64"}, "software": {"nginx": "1.24"}},
    )
    assert response.status_code == 204

    stored = client.get(
        f"/api/v1/agents/{agent_id}/inventory/changes", headers=auth_headers
    ).json()
    audited = db_session.execute(
        select(AuditLogEntry).where(AuditLogEntry.action == "agent.inventory_change")
    ).scalar_one()

    assert len(stored) == 1
    assert audited.detail == {"change_id": stored[0]["id"]}
