"""Tests for the Windows service entry point.

pywin32 exists only on Windows, so these tests install stand-in modules
for the part of it the entry point uses. They check the two ways the
frozen executable is started -- by the Service Control Manager with no
arguments, and by an administrator with a command such as `install` --
and that a stop request ends the agent cleanly. The `windows-latest` CI
leg imports the same module against the real pywin32.
"""

import asyncio
import sys
import threading
from types import SimpleNamespace

import pytest

from warden_agent.service import windows as service

_TIMEOUT_SECONDS = 5


class _FakeServiceFramework:
    def __init__(self, args: object) -> None:
        self.args = args
        self.statuses: list[int] = []

    def ReportServiceStatus(self, status: int) -> None:  # pywin32 spells it this way
        self.statuses.append(status)


class _FakePywin32:
    """Records what the entry point asks of pywin32."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.hosted: type | None = None
        self.command_line: tuple[type, list[str]] | None = None
        self.modules = {
            "servicemanager": SimpleNamespace(
                Initialize=lambda: self.calls.append("Initialize"),
                PrepareToHostSingle=self._prepare,
                StartServiceCtrlDispatcher=lambda: self.calls.append("Dispatch"),
            ),
            "win32event": SimpleNamespace(
                CreateEvent=lambda *_args: threading.Event(),
                SetEvent=lambda event: event.set(),
            ),
            "win32service": SimpleNamespace(SERVICE_STOP_PENDING=3),
            "win32serviceutil": SimpleNamespace(
                ServiceFramework=_FakeServiceFramework,
                HandleCommandLine=self._handle_command_line,
            ),
        }

    def _prepare(self, cls: type) -> None:
        self.calls.append("PrepareToHostSingle")
        self.hosted = cls

    def _handle_command_line(self, cls: type, argv: list[str]) -> None:
        self.command_line = (cls, argv)


@pytest.fixture
def pywin32(monkeypatch):
    fake = _FakePywin32()
    for name, module in fake.modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    return fake


@pytest.fixture
def agent_run(monkeypatch):
    """Replace the agent with one that runs until it is cancelled."""
    state = SimpleNamespace(started=threading.Event(), cleaned_up=False)

    async def run(_settings: object) -> None:
        state.started.set()
        try:
            await asyncio.Event().wait()
        finally:
            state.cleaned_up = True

    monkeypatch.setattr(service, "run", run)
    monkeypatch.setattr(service, "load_settings", lambda _path: object())
    return state


def _service_class(pywin32: _FakePywin32) -> type:
    service.main(["warden-agent.exe"])
    assert pywin32.hosted is not None
    return pywin32.hosted


def test_started_without_arguments_it_hands_itself_to_the_service_manager(pywin32):
    service.main(["warden-agent.exe"])

    assert pywin32.calls == ["Initialize", "PrepareToHostSingle", "Dispatch"]
    assert pywin32.hosted is not None
    assert pywin32.hosted._svc_name_ == "WardenAgent"
    assert pywin32.command_line is None


def test_started_with_a_command_it_runs_that_command(pywin32):
    service.main(["warden-agent.exe", "install"])

    assert pywin32.calls == []
    assert pywin32.command_line is not None
    cls, argv = pywin32.command_line
    assert cls._svc_name_ == "WardenAgent"
    assert argv == ["warden-agent.exe", "install"]


def test_a_stop_request_ends_the_agent_cleanly(pywin32, agent_run):
    instance = _service_class(pywin32)(("WardenAgent",))
    errors: list[BaseException] = []

    def do_run() -> None:
        try:
            instance.SvcDoRun()
        except BaseException as error:  # any exception fails the test below
            errors.append(error)

    thread = threading.Thread(target=do_run)
    thread.start()
    assert agent_run.started.wait(_TIMEOUT_SECONDS)

    instance.SvcStop()
    thread.join(_TIMEOUT_SECONDS)

    assert not thread.is_alive()
    assert errors == []
    assert agent_run.cleaned_up
    assert instance.statuses == [3]


def test_a_stop_request_before_the_agent_starts_still_ends_it(pywin32, agent_run):
    instance = _service_class(pywin32)(("WardenAgent",))

    instance.SvcStop()
    thread = threading.Thread(target=instance.SvcDoRun)
    thread.start()
    thread.join(_TIMEOUT_SECONDS)

    assert not thread.is_alive()
