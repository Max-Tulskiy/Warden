"""Reading and rewriting the agent's configuration file without losing anything."""

from pathlib import Path

import pytest

from warden_agent.config import load_settings
from warden_agent.configurator.config_file import (
    UnsupportedConfigError,
    read_config,
    write_config,
)


def test_a_missing_file_reads_as_empty(tmp_path):
    assert read_config(tmp_path / "config.toml") == {}


def test_what_is_written_can_be_read_back_and_loaded_as_settings(tmp_path):
    path = tmp_path / "config.toml"
    windows_buffer = Path(r"C:\ProgramData\Warden\agent\buffer.db")

    write_config(
        path,
        {
            "server_url": "https://warden.example.internal",
            "ca_file": Path(r"C:\ProgramData\Warden\agent\server-ca.pem"),
            "poll_interval_seconds": 45,
            "retention_hours": 12,
            "buffer_path": windows_buffer,
        },
    )

    read = read_config(path)
    assert read["server_url"] == "https://warden.example.internal"
    assert read["poll_interval_seconds"] == 45
    assert read["buffer_path"] == str(windows_buffer)
    assert load_settings(path).retention_hours == 12
    assert (
        "buffer_path = 'C:\\ProgramData\\Warden\\agent\\buffer.db'" in path.read_text()
    )


def test_keys_an_administrator_set_and_this_code_does_not_know_survive(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        'server_url = "https://a.example"\ncustom_flag = true\nnote = "x"\n'
    )

    values = read_config(path)
    values["server_url"] = "https://b.example"
    write_config(path, values)

    assert read_config(path) == {
        "server_url": "https://b.example",
        "custom_flag": True,
        "note": "x",
    }


def test_the_enrollment_token_is_never_written(tmp_path):
    path = tmp_path / "config.toml"

    write_config(
        path, {"server_url": "https://a.example", "enrollment_token": "s3cret-value"}
    )

    assert "enrollment_token" not in path.read_text()
    assert "s3cret-value" not in path.read_text()


def test_the_server_comes_first_and_the_file_explains_itself(tmp_path):
    path = tmp_path / "config.toml"

    write_config(path, {"retention_hours": 8, "server_url": "https://a.example"})

    lines = [line for line in path.read_text().splitlines() if line]
    assert lines[0].startswith("#")
    assert lines.index('server_url = "https://a.example"') < lines.index(
        "retention_hours = 8"
    )


@pytest.mark.parametrize(
    "value", ['say "hi"', "it's", "line\nbreak", "юникод", "a\\b'c"]
)
def test_awkward_text_survives_a_round_trip(tmp_path, value):
    path = tmp_path / "config.toml"

    write_config(path, {"hostname": value})

    assert read_config(path)["hostname"] == value


def test_a_table_or_a_list_is_refused_rather_than_silently_lost(tmp_path):
    path = tmp_path / "config.toml"

    with pytest.raises(UnsupportedConfigError):
        write_config(path, {"server_url": "https://a.example", "extra": {"a": 1}})

    with pytest.raises(UnsupportedConfigError):
        write_config(path, {"server_url": "https://a.example", "extra": [1, 2]})


def test_a_failed_write_leaves_the_old_file_untouched(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('server_url = "https://old.example"\n')

    with pytest.raises(UnsupportedConfigError):
        write_config(path, {"extra": {"a": 1}})

    assert path.read_text() == 'server_url = "https://old.example"\n'
    assert [item.name for item in tmp_path.iterdir()] == ["config.toml"]
