"""Live checks of the Windows removable-media backend against the real OS.

Skipped everywhere except an actual Windows runner (the `windows-latest`
leg of the agent's CI matrix): this is the one place `pywin32` calls
(`win32api.GetLogicalDriveStrings`, `win32file.GetDriveType`) are exercised
for real rather than left as "written but unverified" (constitution
Section VI). No removable media is expected to be attached on a CI runner,
so an empty result is the correct outcome, not merely a tolerated one.
"""

import sys

import pytest

from warden_agent.collectors.removable_media.windows import (
    WindowsRemovableMediaCollector,
)

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="exercises real pywin32 calls, Windows only"
)


async def test_enumerate_removable_drives_runs_without_error():
    collector = WindowsRemovableMediaCollector()

    events = await collector.collect()

    assert isinstance(events, list)


def test_enumerate_removable_drives_returns_drive_letters():
    drives = WindowsRemovableMediaCollector._enumerate_removable_drives()

    assert isinstance(drives, set)
    for drive in drives:
        assert drive.endswith(":\\")
