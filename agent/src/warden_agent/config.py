"""Agent configuration.

Loaded from a TOML file (primary) with environment variables (prefixed
`WARDEN_AGENT_`) filling in anything the file does not set. This is a plain
`BaseSettings` rather than pydantic-settings' built-in TOML source, so the
loading behavior stays simple and easy to unit test with a temporary file.
"""

import tomllib
from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: The request-window cap from constitution principle 3; buffer retention
#: must never fall below it, or a valid request could outlive its own data.
MIN_REQUEST_WINDOW_HOURS = 4


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WARDEN_AGENT_")

    server_url: str = "https://localhost:8000"
    enrollment_token: str | None = None
    hostname: str | None = None
    poll_interval_seconds: int = 60
    inventory_interval_seconds: int = 3600
    retention_hours: int = 8
    buffer_path: Path = Path("warden-agent.db")
    state_path: Path = Path("warden-agent-state.json")

    @field_validator("retention_hours")
    @classmethod
    def _retention_covers_the_request_window(cls, value: int) -> int:
        if value < MIN_REQUEST_WINDOW_HOURS:
            raise ValueError(
                "retention_hours must be at least "
                f"{MIN_REQUEST_WINDOW_HOURS} hours (constitution principle 4): "
                "a shorter retention could drop data a still-valid request needs"
            )
        return value


def load_settings(config_path: Path | None) -> AgentSettings:
    """Build settings from a TOML file, if given and present, then env vars.

    Values present in the file are passed to the constructor explicitly, so
    they take precedence there; any field the file does not mention falls
    back to its environment variable or default in the usual `BaseSettings`
    way.
    """
    file_values: dict[str, Any] = {}
    if config_path is not None and config_path.exists():
        file_values = tomllib.loads(config_path.read_text(encoding="utf-8"))
    return AgentSettings(**file_values)
