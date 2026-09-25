"""Tests for the example configs the packages install.

The .deb/.rpm install agent/config.example.toml and the .msi installs
packaging/windows/config.example.toml. Both must load, carry the same
settings, and keep the agent's files where each package prepares a
directory for them -- the Windows service cannot create
C:\\var\\lib\\warden-agent the way the Linux package creates /var/lib.
"""

import tomllib
from pathlib import Path, PureWindowsPath

from warden_agent.config import load_settings

_REPO = Path(__file__).resolve().parents[4]
_LINUX_EXAMPLE = _REPO / "agent" / "config.example.toml"
_WINDOWS_EXAMPLE = _REPO / "packaging" / "windows" / "config.example.toml"
_WINDOWS_DATA_DIR = PureWindowsPath(r"C:\ProgramData\Warden\agent")


def test_both_examples_load():
    for example in (_LINUX_EXAMPLE, _WINDOWS_EXAMPLE):
        load_settings(example)


# The Windows station is connected from the installer's wizard or the
# connection window, which write the server and never a token; the Linux example
# still carries both for an administrator to fill in.
_CONNECTION_KEYS = {"server_url", "enrollment_token"}


def test_both_examples_carry_the_same_settings():
    linux = tomllib.loads(_LINUX_EXAMPLE.read_text(encoding="utf-8"))
    windows = tomllib.loads(_WINDOWS_EXAMPLE.read_text(encoding="utf-8"))

    assert set(windows) == set(linux) - _CONNECTION_KEYS
    for key in windows.keys() - {"buffer_path", "state_path"}:
        assert windows[key] == linux[key], key


def test_the_windows_example_holds_no_token_and_no_placeholder_server():
    values = tomllib.loads(_WINDOWS_EXAMPLE.read_text(encoding="utf-8"))

    assert "enrollment_token" not in values
    assert "server_url" not in values


def test_the_windows_example_keeps_the_agent_files_in_the_protected_directory():
    values = tomllib.loads(_WINDOWS_EXAMPLE.read_text(encoding="utf-8"))

    for key in ("buffer_path", "state_path"):
        assert PureWindowsPath(values[key]).parent == _WINDOWS_DATA_DIR, key
