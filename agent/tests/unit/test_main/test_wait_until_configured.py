"""An agent that is not configured yet waits and looks again, it does not exit.

The waiting runs against the shared TLS server, so an enrollment that follows
a wait is a real one, and the fake `sleep` is where the test plays the
administrator finishing the configuration.
"""

import pytest

from warden_agent.__main__ import CONFIG_RECHECK_SECONDS, wait_until_configured
from warden_agent.config import AgentSettings
from warden_agent.state import AgentState
from warden_agent.status import StatusStore


def _settings(tmp_path, server_url, **extra) -> AgentSettings:
    return AgentSettings(
        server_url=server_url,
        state_path=tmp_path / "state.json",
        buffer_path=tmp_path / "buffer.db",
        **extra,
    )


@pytest.fixture
def ca_file(tls_server, tmp_path):
    path = tmp_path / "server-ca.pem"
    path.write_text(tls_server.authority_pem)
    return path


class _Administrator:
    """Sleeps for the agent and does something to the configuration meanwhile."""

    def __init__(self, tmp_path, action):
        self.status = StatusStore(tmp_path / "status.json")
        self.seen: list[tuple[str | None, str | None]] = []
        self.delays: list[float] = []
        self._action = action

    async def sleep(self, seconds: float) -> None:
        self.delays.append(seconds)
        status = self.status.read()
        self.seen.append((status.state, status.detail))
        self._action()


async def test_an_unconfigured_agent_waits_and_says_why(tmp_path, tls_server, ca_file):
    tls_server.answer(
        "POST", "/api/v1/enroll", 201, {"agent_id": "a1", "agent_key": "k1"}
    )
    settings = _settings(tmp_path, tls_server.url, ca_file=ca_file)
    configured = _settings(
        tmp_path, tls_server.url, ca_file=ca_file, enrollment_token="tok"
    )
    current = [settings]
    admin = _Administrator(tmp_path, lambda: current.__setitem__(0, configured))

    result, state, client = await wait_until_configured(
        settings,
        reload_settings=lambda: current[0],
        status=admin.status,
        sleep=admin.sleep,
    )
    await client.aclose()

    assert admin.seen == [("waiting", "not_configured")]
    assert admin.delays == [CONFIG_RECHECK_SECONDS]
    assert state.agent_id == "a1"
    assert result is configured


async def test_a_station_enrolled_by_the_window_meanwhile_is_picked_up(
    tmp_path, tls_server, ca_file
):
    settings = _settings(tmp_path, tls_server.url, ca_file=ca_file)
    enrolled = AgentState(agent_id="a1", agent_key="k1", server_url=tls_server.url)
    admin = _Administrator(tmp_path, lambda: enrolled.save(settings.state_path))

    _, state, client = await wait_until_configured(
        settings,
        reload_settings=lambda: settings,
        status=admin.status,
        sleep=admin.sleep,
    )
    await client.aclose()

    assert state.agent_id == "a1"
    assert tls_server.requests == []  # nothing needed enrolling


async def test_a_state_from_another_server_waits_until_the_configuration_matches(
    tmp_path, tls_server, ca_file
):
    state_path = tmp_path / "state.json"
    AgentState(agent_id="a1", agent_key="k1", server_url="https://old.example").save(
        state_path
    )
    settings = _settings(tmp_path, tls_server.url, ca_file=ca_file)
    back = _settings(tmp_path, "https://old.example", ca_file=ca_file)
    current = [settings]
    admin = _Administrator(tmp_path, lambda: current.__setitem__(0, back))

    result, state, client = await wait_until_configured(
        settings,
        reload_settings=lambda: current[0],
        status=admin.status,
        sleep=admin.sleep,
    )
    await client.aclose()

    assert admin.seen == [("waiting", "server_changed")]
    assert result.server_url == "https://old.example"
    assert state.agent_id == "a1"


async def test_an_unreadable_authority_file_waits_until_it_is_fixed(
    tmp_path, tls_server, ca_file
):
    AgentState(agent_id="a1", agent_key="k1", server_url=tls_server.url).save(
        tmp_path / "state.json"
    )
    broken = _settings(tmp_path, tls_server.url, ca_file=tmp_path / "absent.pem")
    fixed = _settings(tmp_path, tls_server.url, ca_file=ca_file)
    current = [broken]
    admin = _Administrator(tmp_path, lambda: current.__setitem__(0, fixed))

    _, _, client = await wait_until_configured(
        broken,
        reload_settings=lambda: current[0],
        status=admin.status,
        sleep=admin.sleep,
    )
    await client.aclose()

    assert admin.seen == [("waiting", "ca_unreadable")]


async def test_a_configuration_that_carries_a_token_enrolls_as_before(
    tmp_path, tls_server, ca_file
):
    tls_server.answer(
        "POST", "/api/v1/enroll", 201, {"agent_id": "a9", "agent_key": "k9"}
    )
    settings = _settings(
        tmp_path, tls_server.url, ca_file=ca_file, enrollment_token="tok"
    )
    admin = _Administrator(tmp_path, lambda: None)

    _, state, client = await wait_until_configured(
        settings,
        reload_settings=lambda: settings,
        status=admin.status,
        sleep=admin.sleep,
    )
    await client.aclose()

    assert admin.seen == []
    assert state.agent_id == "a9"
    assert AgentState.load(settings.state_path).server_url == tls_server.url
