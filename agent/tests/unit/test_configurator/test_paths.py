"""Where the agent keeps its files, all in one folder."""

from pathlib import Path

from warden_agent.configurator.paths import AgentPaths


def test_every_file_lives_in_the_one_folder(tmp_path):
    paths = AgentPaths.for_directory(tmp_path)

    assert paths.config == tmp_path / "config.toml"
    assert paths.authority == tmp_path / "server-ca.pem"
    assert paths.state == tmp_path / "state.json"
    assert paths.status == tmp_path / "status.json"
    assert paths.log == tmp_path / "configurator.log"


def test_a_folder_given_as_text_is_accepted():
    assert AgentPaths.for_directory("/x").config == Path("/x/config.toml")
