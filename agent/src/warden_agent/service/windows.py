"""Windows service entry point, using `pywin32`'s `ServiceFramework`.

Unlike systemd, a Windows service needs actual glue code to receive
start/stop control requests from the Service Control Manager and to run the
agent's asyncio event loop on the service's own thread. `pywin32` only
exists on Windows, so the service class itself -- which must subclass
`win32serviceutil.ServiceFramework` -- is defined inside `main()` rather
than at module level; this module must stay importable on any platform
(constitution principle 1). The glue is unit-tested against stand-in
modules; the real `pywin32` is exercised only on the `windows-latest` CI
leg and a live check (Section VI).

The installer registers the PyInstaller-frozen executable itself as the
service binary, so the Service Control Manager starts it with no arguments.
That start has to be handed to the service dispatcher; any argument means
an administrator is running a command such as `install` or `debug`.
"""

import asyncio
import sys
from pathlib import Path

from warden_agent.__main__ import run
from warden_agent.config import load_settings

_DEFAULT_CONFIG_PATH = Path(r"C:\ProgramData\Warden\agent\config.toml")


def main(argv: list[str] | None = None) -> None:
    import servicemanager  # Windows-only; see module docstring
    import win32event
    import win32service
    import win32serviceutil

    class WardenAgentService(win32serviceutil.ServiceFramework):
        _svc_name_ = "WardenAgent"
        _svc_display_name_ = "Warden Insider-Activity Monitoring Agent"
        _svc_description_ = (
            "Observes hardware/software inventory, removable media, printing, "
            "processes, and browsing history; reports on request from the "
            "Warden server."
        )

        def __init__(self, args: object) -> None:
            win32serviceutil.ServiceFramework.__init__(self, args)
            self._stop_event = win32event.CreateEvent(None, 0, 0, None)
            self._stop_requested = False
            self._loop: asyncio.AbstractEventLoop | None = None
            self._task: asyncio.Task[None] | None = None

        def SvcStop(self) -> None:
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            # Set before reading the loop: SvcDoRun publishes the loop and
            # then checks this flag, so a stop that arrives while it is
            # starting is seen by one side or the other.
            self._stop_requested = True
            loop, task = self._loop, self._task
            if loop is not None and task is not None:
                loop.call_soon_threadsafe(task.cancel)
            win32event.SetEvent(self._stop_event)

        def SvcDoRun(self) -> None:
            settings = load_settings(_DEFAULT_CONFIG_PATH)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            task = loop.create_task(run(settings))
            self._task, self._loop = task, loop
            if self._stop_requested:
                task.cancel()
            try:
                # Cancelling the task, rather than stopping the loop under
                # it, lets run() close its connection on the way out.
                loop.run_until_complete(task)
            except asyncio.CancelledError:
                pass
            finally:
                loop.close()

    argv = sys.argv if argv is None else argv
    if len(argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(WardenAgentService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(WardenAgentService, argv=argv)


if __name__ == "__main__":
    main()
