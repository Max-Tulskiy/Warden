"""The Windows side of the connection tool, over stand-in `win32` modules.

pywin32 exists only on Windows, so these tests install stand-ins for the part of
it the backend uses, the way `test_windows_service.py` does. The `windows-latest`
CI leg imports the same module against the real one.
"""

import ctypes
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from warden_agent.configurator import windows
from warden_agent.configurator.backend import ServiceState
from warden_agent.configurator.paths import AgentPaths

# The real values of the Service Control Manager's states.
STOPPED, START_PENDING, STOP_PENDING, RUNNING, CONTINUE_PENDING = 1, 2, 3, 4, 5
PAUSE_PENDING, PAUSED = 6, 7
ERROR_SERVICE_DOES_NOT_EXIST = 1060


class _Win32Error(Exception):
    def __init__(self, winerror: int, function: str, message: str) -> None:
        super().__init__(winerror, function, message)
        self.winerror = winerror


class _FakeScm:
    """Answers the two calls the backend makes, from a scripted state."""

    def __init__(self) -> None:
        self.state: int | None = RUNNING  # None: the service is not installed
        self.restarted: list[str] = []

    def modules(self) -> dict[str, types.ModuleType]:
        def query(name: str):
            if self.state is None:
                raise _Win32Error(ERROR_SERVICE_DOES_NOT_EXIST, "Query", "no such")
            return (16, self.state, 0, 0, 0, 0, 0)

        return {
            "pywintypes": SimpleNamespace(error=_Win32Error),
            "win32service": SimpleNamespace(
                SERVICE_STOPPED=STOPPED,
                SERVICE_START_PENDING=START_PENDING,
                SERVICE_STOP_PENDING=STOP_PENDING,
                SERVICE_RUNNING=RUNNING,
                SERVICE_CONTINUE_PENDING=CONTINUE_PENDING,
                SERVICE_PAUSE_PENDING=PAUSE_PENDING,
                SERVICE_PAUSED=PAUSED,
            ),
            "win32serviceutil": SimpleNamespace(
                QueryServiceStatus=query,
                RestartService=self.restarted.append,
            ),
        }


@pytest.fixture
def scm(monkeypatch) -> _FakeScm:
    fake = _FakeScm()
    for name, module in fake.modules().items():
        monkeypatch.setitem(sys.modules, name, module)
    return fake


def test_the_agents_folder_is_under_program_data(monkeypatch):
    monkeypatch.setenv("PROGRAMDATA", "X:\\PD")

    backend = windows.WindowsBackend()

    assert backend.paths == AgentPaths.for_directory(
        Path("X:\\PD") / "Warden" / "agent"
    )


def test_a_folder_can_be_given_instead(tmp_path):
    paths = AgentPaths.for_directory(tmp_path)

    assert windows.WindowsBackend(paths).paths is paths


@pytest.mark.parametrize("answer", [1, 0])
def test_elevation_is_what_the_shell_says(monkeypatch, answer):
    fake = SimpleNamespace(shell32=SimpleNamespace(IsUserAnAdmin=lambda: answer))
    monkeypatch.setattr(ctypes, "windll", fake, raising=False)

    assert windows.WindowsBackend().is_elevated() is bool(answer)


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (RUNNING, ServiceState.RUNNING),
        (START_PENDING, ServiceState.RUNNING),
        (CONTINUE_PENDING, ServiceState.RUNNING),
        (STOPPED, ServiceState.STOPPED),
        (STOP_PENDING, ServiceState.STOPPED),
        (PAUSED, ServiceState.STOPPED),
        (PAUSE_PENDING, ServiceState.STOPPED),
        (None, ServiceState.NOT_INSTALLED),
    ],
)
def test_the_service_state_is_the_service_control_managers(scm, state, expected):
    scm.state = state

    assert windows.WindowsBackend().service_state() is expected


def test_a_failure_other_than_not_installed_is_not_hidden(scm, monkeypatch):
    def refuse(_name):
        raise _Win32Error(5, "Query", "access denied")

    monkeypatch.setattr(sys.modules["win32serviceutil"], "QueryServiceStatus", refuse)

    with pytest.raises(_Win32Error):
        windows.WindowsBackend().service_state()


def test_a_running_service_is_restarted(scm):
    windows.WindowsBackend().restart_service()

    assert scm.restarted == ["WardenAgent"]


@pytest.mark.parametrize("state", [STOPPED, None])
def test_a_service_that_is_not_running_is_left_for_the_installer_to_start(scm, state):
    scm.state = state

    windows.WindowsBackend().restart_service()

    assert scm.restarted == []


class _Calls:
    def __init__(self, monkeypatch):
        self.calls: list[tuple[str, object]] = []
        stub = types.ModuleType("warden_agent.configurator.view")
        stub.run_window = lambda backend: self._record("window", backend, 0)
        stub.run_selftest = lambda backend: self._record("selftest", backend, 0)
        monkeypatch.setitem(sys.modules, "warden_agent.configurator.view", stub)
        monkeypatch.setattr(
            windows, "run_cli", lambda argv, backend: self._record("cli", argv, 3)
        )

    def _record(self, what, detail, code):
        self.calls.append((what, detail))
        return code


def test_started_with_no_arguments_it_opens_the_window(monkeypatch):
    calls = _Calls(monkeypatch)

    assert windows.main([]) == 0

    assert [what for what, _ in calls.calls] == ["window"]
    assert isinstance(calls.calls[0][1], windows.WindowsBackend)


def test_started_with_apply_or_check_it_runs_the_command_line(monkeypatch):
    calls = _Calls(monkeypatch)

    code = windows.main(["--apply", "--server", "https://a.example"])

    assert code == 3
    assert calls.calls == [("cli", ["--apply", "--server", "https://a.example"])]


def test_started_with_selftest_it_builds_the_window_off_screen(monkeypatch):
    calls = _Calls(monkeypatch)

    assert windows.main(["--selftest"]) == 0

    assert [what for what, _ in calls.calls] == ["selftest"]


def test_gui_opens_the_window_too(monkeypatch):
    calls = _Calls(monkeypatch)

    windows.main(["--gui"])

    assert [what for what, _ in calls.calls] == ["window"]


def test_a_configuration_path_moves_the_folder(monkeypatch, tmp_path):
    calls = _Calls(monkeypatch)

    windows.main(["--gui", "--config", str(tmp_path / "config.toml")])

    assert calls.calls[0][1].paths == AgentPaths.for_directory(tmp_path)
