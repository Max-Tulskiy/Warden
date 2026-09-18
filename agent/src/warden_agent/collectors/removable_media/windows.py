"""Windows removable-media backend: polls logical drives via `pywin32`.

`win32file.GetDriveType` returns `DRIVE_REMOVABLE` for a drive letter backed
by removable media (a USB flash drive, an SD card reader); `pywin32` only
exists on Windows, so it is imported lazily inside the function that needs
it -- this module must stay importable on any platform (constitution
principle 1). Only that thin polling glue is untested outside the
`windows-latest` CI leg and a live check (Section VI); the diffing logic it
delegates to is shared with the Linux backend and fully unit-tested there.
"""

import asyncio
from datetime import UTC, datetime

from warden_agent.collectors.removable_media.diff import diff_devices
from warden_agent.core.models import OutgoingEvent

# win32con.DRIVE_REMOVABLE, hardcoded to avoid importing pywin32 at module
# level (see the docstring above) -- this is a stable Win32 API constant.
_DRIVE_REMOVABLE = 2


class WindowsRemovableMediaCollector:
    category = "removable_media"

    def __init__(self) -> None:
        self._previous: set[str] = set()

    async def collect(self) -> list[OutgoingEvent]:
        return await asyncio.to_thread(self._collect_sync)

    def _collect_sync(self) -> list[OutgoingEvent]:
        now = datetime.now(UTC)
        current = self._enumerate_removable_drives()
        events = [
            OutgoingEvent(
                category=self.category,
                occurred_at=now,
                payload={"device": drive, "action": action},
            )
            for drive, action in diff_devices(self._previous, current)
        ]
        self._previous = current
        return events

    @staticmethod
    def _enumerate_removable_drives() -> set[str]:
        import win32api  # Windows-only; see module docstring
        import win32file

        drives = set()
        for drive in win32api.GetLogicalDriveStrings().split("\x00"):
            if drive and win32file.GetDriveType(drive) == _DRIVE_REMOVABLE:
                drives.add(drive)
        return drives
