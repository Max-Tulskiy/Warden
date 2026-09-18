"""Tests for loading agent settings from a TOML file and validating them."""

import pytest
from pydantic import ValidationError

from warden_agent.config import AgentSettings, load_settings


def test_defaults_are_used_when_no_file_is_given():
    settings = load_settings(None)

    assert settings.server_url == "https://localhost:8000"
    assert settings.retention_hours == 8


def test_values_from_the_toml_file_are_applied(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        'server_url = "https://warden.example.internal"\npoll_interval_seconds = 30\n'
    )

    settings = load_settings(config_file)

    assert settings.server_url == "https://warden.example.internal"
    assert settings.poll_interval_seconds == 30


def test_a_missing_file_path_falls_back_to_defaults(tmp_path):
    settings = load_settings(tmp_path / "does-not-exist.toml")

    assert settings.server_url == "https://localhost:8000"


def test_retention_below_the_request_window_cap_is_rejected():
    with pytest.raises(ValidationError, match="at least 4 hours"):
        AgentSettings(retention_hours=2)
