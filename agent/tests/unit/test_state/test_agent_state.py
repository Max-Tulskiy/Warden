"""Tests for the persisted enrollment state (agent id and key)."""

import os
import stat
import sys

import pytest

from warden_agent.state import AgentState


@pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX permission bits, not meaningful on Windows"
)
def test_save_creates_the_state_file_as_owner_only_regardless_of_umask(tmp_path):
    path = tmp_path / "state.json"
    previous_umask = os.umask(0o022)
    try:
        AgentState(agent_id="a1", agent_key="k1").save(path)
    finally:
        os.umask(previous_umask)

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_a_missing_state_file_yields_an_unenrolled_state(tmp_path):
    state = AgentState.load(tmp_path / "state.json")

    assert not state.is_enrolled
    assert state.agent_id is None


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "state.json"
    original = AgentState(agent_id="a1", agent_key="k1")

    original.save(path)
    loaded = AgentState.load(path)

    assert loaded == original
    assert loaded.is_enrolled


def test_is_enrolled_is_false_with_only_one_field_set():
    assert not AgentState(agent_id="a1").is_enrolled
    assert not AgentState(agent_key="k1").is_enrolled


def test_the_server_an_agent_enrolled_with_is_saved_and_loaded(tmp_path):
    path = tmp_path / "state.json"

    AgentState(agent_id="a1", agent_key="k1", server_url="https://warden.example").save(
        path
    )

    assert AgentState.load(path).server_url == "https://warden.example"


def test_a_state_written_before_the_server_was_recorded_still_loads(tmp_path):
    path = tmp_path / "state.json"
    path.write_text('{"agent_id": "a1", "agent_key": "k1"}')

    state = AgentState.load(path)

    assert state.is_enrolled
    assert state.server_url is None


def test_a_state_belongs_to_the_server_it_enrolled_with():
    state = AgentState(agent_id="a1", agent_key="k1", server_url="https://a.example")

    assert state.is_enrolled_for("https://a.example")
    assert state.is_enrolled_for("https://a.example/")
    assert state.is_enrolled_for("HTTPS://A.EXAMPLE")
    assert not state.is_enrolled_for("https://b.example")


def test_a_state_without_a_recorded_server_matches_any_server():
    """An agent enrolled by an earlier version keeps working unchanged."""
    state = AgentState(agent_id="a1", agent_key="k1")

    assert state.is_enrolled_for("https://anything.example")


def test_an_unenrolled_state_belongs_to_no_server():
    assert not AgentState().is_enrolled_for("https://a.example")
