"""Windows service entry point, using `pywin32`'s `ServiceFramework`.

Unlike systemd, a Windows service needs actual glue code to receive
start/stop control requests from the Service Control Manager and to run the
agent's asyncio event loop on the service's own thread. `pywin32` only
exists on Windows, so the service class itself -- which must subclass
`win32serviceutil.ServiceFramework` -- is defined inside `main()` rather
than at module level; this module must stay importable on any platform
(constitution principle 1). None of this is exercised outside the
`windows-latest` CI leg and a live check (Section VI).
"""

import asyncio
from pathlib import Path

from warden_agent.__main__ import run
from warden_agent.config import load_settings

_DEFAULT_CONFIG_PATH = Path(r"C:\ProgramData\Warden\agent\config.toml")


def main() -> None:
    import win32event  # Windows-only; see module docstring
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
            self._loop: asyncio.AbstractEventLoop | None = None

        def SvcStop(self) -> None:
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            if self._loop is not None:
                self._loop.call_soon_threadsafe(self._loop.stop)
            win32event.SetEvent(self._stop_event)

        def SvcDoRun(self) -> None:
            settings = load_settings(_DEFAULT_CONFIG_PATH)
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(run(settings))

    win32serviceutil.HandleCommandLine(WardenAgentService)


if __name__ == "__main__":
    main()
