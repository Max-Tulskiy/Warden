"""Tests for the persisted enrollment state (agent id and key)."""

from warden_agent.state import AgentState


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
