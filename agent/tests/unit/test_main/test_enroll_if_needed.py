"""Tests for the first-run enrollment logic in the CLI entry point."""

from unittest.mock import AsyncMock

import pytest

from warden_agent.__main__ import enroll_if_needed
from warden_agent.collectors.registry import current_platform
from warden_agent.config import AgentSettings
from warden_agent.errors import NotConfiguredError
from warden_agent.state import AgentState


async def test_an_already_enrolled_state_is_returned_unchanged(tmp_path):
    settings = AgentSettings(state_path=tmp_path / "state.json")
    state = AgentState(agent_id="a1", agent_key="k1")
    client = AsyncMock()

    result = await enroll_if_needed(settings, state, client)

    assert result is state
    client.enroll.assert_not_awaited()


async def test_missing_token_without_prior_enrollment_is_not_configured(tmp_path):
    settings = AgentSettings(state_path=tmp_path / "state.json", enrollment_token=None)
    client = AsyncMock()

    with pytest.raises(NotConfiguredError) as error:
        await enroll_if_needed(settings, AgentState(), client)

    assert error.value.reason == "not_configured"
    client.enroll.assert_not_awaited()


async def test_a_state_from_another_server_is_not_enrolled_here(tmp_path):
    settings = AgentSettings(
        server_url="https://new.example", state_path=tmp_path / "state.json"
    )
    state = AgentState(agent_id="a1", agent_key="k1", server_url="https://old.example")
    client = AsyncMock()

    with pytest.raises(NotConfiguredError) as error:
        await enroll_if_needed(settings, state, client)

    assert error.value.reason == "server_changed"


async def test_a_token_enrolls_again_when_the_server_was_changed(tmp_path):
    settings = AgentSettings(
        server_url="https://new.example",
        enrollment_token="tok",
        state_path=tmp_path / "state.json",
    )
    state = AgentState(agent_id="a1", agent_key="k1", server_url="https://old.example")
    client = AsyncMock()
    client.enroll.return_value = ("a2", "k2")

    result = await enroll_if_needed(settings, state, client)

    assert (result.agent_id, result.server_url) == ("a2", "https://new.example")


async def test_a_state_recorded_without_its_server_is_accepted(tmp_path):
    """An agent enrolled by an earlier version keeps working unchanged (A-16)."""
    settings = AgentSettings(
        server_url="https://any.example", state_path=tmp_path / "state.json"
    )
    state = AgentState(agent_id="a1", agent_key="k1")
    client = AsyncMock()

    assert await enroll_if_needed(settings, state, client) is state


async def test_enrolling_saves_and_returns_the_new_state(tmp_path):
    state_path = tmp_path / "state.json"
    settings = AgentSettings(
        state_path=state_path, enrollment_token="tok", hostname="WORKSTATION-01"
    )
    client = AsyncMock()
    client.enroll.return_value = ("a1", "k1")

    result = await enroll_if_needed(settings, AgentState(), client)

    assert result.agent_id == "a1"
    assert result.agent_key == "k1"
    client.enroll.assert_awaited_once_with(
        token="tok", hostname="WORKSTATION-01", os_name=current_platform()
    )
    assert AgentState.load(state_path) == result
    assert result.server_url == settings.server_url
