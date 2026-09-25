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


def test_the_state_is_where_the_configuration_says_the_agent_reads_it(tmp_path):
    """The agent reads `state_path`; writing anywhere else would enroll nothing."""
    elsewhere = tmp_path / "var" / "lib" / "state.json"
    config_dir = tmp_path / "etc"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(f"state_path = '{elsewhere}'\n")

    paths = AgentPaths.for_directory(config_dir).following_config()

    assert paths.state == elsewhere
    assert paths.status == elsewhere.parent / "status.json"
    assert paths.config == config_dir / "config.toml"


def test_without_a_state_path_the_files_stay_beside_the_configuration(tmp_path):
    paths = AgentPaths.for_directory(tmp_path).following_config()

    assert paths.state == tmp_path / "state.json"
    assert paths.status == tmp_path / "status.json"
