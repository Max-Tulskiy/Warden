"""The connection tool on Windows: the real service, `%ProgramData%`, elevation.

The one module of the configurator that knows it is running on Windows, in the
pattern of `service/windows.py`. `pywin32` and `ctypes.windll` exist only there,
so they are imported inside the methods that use them and this module stays
importable anywhere (constitution principle 1). Against stand-in modules the
logic is unit-tested; the real calls are exercised only on the `windows-latest`
CI leg and by a person on a real machine (Section VI).

The frozen executable starts at `main`: with no arguments it opens the window,
with `--apply` or `--check` it runs the command line the installer calls, and
with `--selftest` it builds the window off screen and leaves, so the release
build can prove the executable starts.
"""

import importlib
import os
import sys
from pathlib import Path

from warden_agent.configurator.backend import ServiceState
from warden_agent.configurator.cli import parse_args, run_cli
from warden_agent.configurator.paths import AgentPaths

SERVICE_NAME = "WardenAgent"

#: The Service Control Manager's answer when there is no such service.
_ERROR_SERVICE_DOES_NOT_EXIST = 1060


def _default_directory() -> Path:
    return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Warden" / "agent"


class WindowsBackend:
    def __init__(self, paths: AgentPaths | None = None) -> None:
        self._paths = paths or AgentPaths.for_directory(_default_directory())

    @property
    def paths(self) -> AgentPaths:
        return self._paths

    def is_elevated(self) -> bool:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())

    def service_state(self) -> ServiceState:
        import pywintypes
        import win32service
        import win32serviceutil

        try:
            state = win32serviceutil.QueryServiceStatus(SERVICE_NAME)[1]
        except pywintypes.error as exc:
            if exc.winerror == _ERROR_SERVICE_DOES_NOT_EXIST:
                return ServiceState.NOT_INSTALLED
            raise
        running = (
            win32service.SERVICE_RUNNING,
            win32service.SERVICE_START_PENDING,
            win32service.SERVICE_CONTINUE_PENDING,
        )
        return ServiceState.RUNNING if state in running else ServiceState.STOPPED

    def restart_service(self) -> None:
        """Restart the service if it is running.

        One that is stopped or not installed yet is left alone: during an
        install the installer starts it, already configured.
        """
        if self.service_state() is ServiceState.RUNNING:
            import win32serviceutil

            win32serviceutil.RestartService(SERVICE_NAME)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    # Imported through `importlib` so the window (and Qt behind it) is loaded
    # only when it is asked for.
    view = importlib.import_module("warden_agent.configurator.view")
    if not argv:
        return int(view.run_window(WindowsBackend()))
    if "--selftest" in argv:
        return int(view.run_selftest(WindowsBackend()))

    args = parse_args(argv)
    backend = WindowsBackend(
        AgentPaths.for_directory(args.config.parent) if args.config else None
    )
    if args.gui:
        return int(view.run_window(backend))
    return run_cli(argv, backend)


if __name__ == "__main__":
    raise SystemExit(main())
