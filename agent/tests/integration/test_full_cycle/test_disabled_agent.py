"""The agent's view of an operator disabling and re-enabling its station.

Drives the real `ServerClient` and `run_poll_pass` against the real server
app (no stub on either side), matching `specs/002-panel-reports-and-settings`
acceptance criteria A-8 and A-9.
"""

import httpx
import pytest
from warden_server.main import app

from warden_agent.buffer import Buffer
from warden_agent.core.scheduler import run_poll_pass
from warden_agent.core.transport import ServerClient


async def _set_status(raw_client, operator_bearer_token, agent_id, status):
    response = await raw_client.patch(
        f"/api/v1/agents/{agent_id}",
        headers={"Authorization": f"Bearer {operator_bearer_token}"},
        json={"status": status},
    )
    assert response.status_code == 200


async def test_a_disabled_agent_is_rejected_without_retrying_and_recovers_on_re_enable(
    tmp_path, raw_client, enrollment_token, operator_bearer_token
):
    async def fail_if_retried(_delay: float) -> None:
        raise AssertionError("a 401 must not be retried")

    client = ServerClient(
        "http://testserver",
        transport=httpx.ASGITransport(app=app),
        sleep=fail_if_retried,
    )
    try:
        agent_id, agent_key = await client.enroll(
            token=enrollment_token, hostname="WORKSTATION-IT", os_name="linux"
        )
        buffer = Buffer(tmp_path / "buffer.db")

        async def poll():
            return await run_poll_pass(
                client,
                buffer,
                agent_id=agent_id,
                agent_key=agent_key,
                max_window_hours=4,
            )

        assert await poll() == []

        await _set_status(raw_client, operator_bearer_token, agent_id, "disabled")
        with pytest.raises(httpx.HTTPStatusError) as rejected:
            await poll()
        assert rejected.value.response.status_code == 401

        await _set_status(raw_client, operator_bearer_token, agent_id, "active")
        assert await poll() == []
    finally:
        await client.aclose()
