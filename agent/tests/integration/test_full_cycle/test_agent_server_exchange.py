"""End-to-end: enroll, place a request, collect, poll, answer, verify on the
server -- the agent's transport and scheduler driven against the real
server app (no mocks on either side), matching the flow in
`specs/001-agent-server-complex/plan.md`.
"""

from datetime import UTC, datetime, timedelta

from warden_agent.buffer import Buffer
from warden_agent.core.scheduler import run_poll_pass


async def test_agent_enrolls_against_the_real_server(server_client, enrollment_token):
    agent_id, agent_key = await server_client.enroll(
        token=enrollment_token, hostname="WORKSTATION-IT", os_name="linux"
    )

    assert agent_id
    assert agent_key


async def test_full_window_request_cycle_against_the_real_server(
    tmp_path, server_client, raw_client, enrollment_token, operator_bearer_token
):
    agent_id, agent_key = await server_client.enroll(
        token=enrollment_token, hostname="WORKSTATION-IT", os_name="linux"
    )

    window_start = datetime(2026, 1, 1, 9, tzinfo=UTC)
    window_end = window_start + timedelta(hours=1)
    placed = await raw_client.post(
        f"/api/v1/agents/{agent_id}/requests",
        headers={"Authorization": f"Bearer {operator_bearer_token}"},
        json={
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
        },
    )
    assert placed.status_code == 201

    buffer = Buffer(tmp_path / "buffer.db")
    buffer.add_event(
        "processes",
        window_start + timedelta(minutes=15),
        {"name": "notepad.exe", "pid": 4242},
    )

    tasks = await run_poll_pass(
        server_client,
        buffer,
        agent_id=agent_id,
        agent_key=agent_key,
        max_window_hours=4,
    )
    assert len(tasks) == 1

    stored = await raw_client.get(
        f"/api/v1/agents/{agent_id}/events",
        headers={"Authorization": f"Bearer {operator_bearer_token}"},
        params={"report_date": window_start.date().isoformat()},
    )
    assert stored.status_code == 200
    events = stored.json()
    assert len(events) == 1
    assert events[0]["payload"]["name"] == "notepad.exe"


async def test_inventory_snapshot_is_visible_as_a_change_on_the_server(
    server_client, raw_client, enrollment_token, operator_bearer_token
):
    agent_id, agent_key = await server_client.enroll(
        token=enrollment_token, hostname="WORKSTATION-IT", os_name="linux"
    )

    await server_client.push_inventory(
        agent_id=agent_id,
        agent_key=agent_key,
        hardware={"cpu": "x86_64"},
        software={"bash": "5.2"},
    )

    changes = await raw_client.get(
        f"/api/v1/agents/{agent_id}/inventory/changes",
        headers={"Authorization": f"Bearer {operator_bearer_token}"},
    )
    assert changes.status_code == 200
    assert len(changes.json()) == 1


async def test_a_request_over_four_hours_is_rejected_by_the_real_server(
    server_client, raw_client, enrollment_token, operator_bearer_token
):
    agent_id, _ = await server_client.enroll(
        token=enrollment_token, hostname="WORKSTATION-IT", os_name="linux"
    )
    window_start = datetime(2026, 1, 1, tzinfo=UTC)

    response = await raw_client.post(
        f"/api/v1/agents/{agent_id}/requests",
        headers={"Authorization": f"Bearer {operator_bearer_token}"},
        json={
            "window_start": window_start.isoformat(),
            "window_end": (window_start + timedelta(hours=5)).isoformat(),
        },
    )

    assert response.status_code == 422
