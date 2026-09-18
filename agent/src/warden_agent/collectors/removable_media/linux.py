"""Linux removable-media backend: `/sys/block/*/removable` polled each tick.

Reads sysfs and `/proc/mounts` directly instead of shelling out to `lsblk`:
one less external dependency, and the paths are constructor parameters, so
tests exercise the real file-reading logic against a temporary directory
laid out like sysfs, not a mock (constitution principle 7).
"""

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from warden_agent.collectors.removable_media.diff import diff_devices
from warden_agent.core.models import OutgoingEvent

_DEVICE_PATH_COLUMN = 0
_MOUNTPOINT_COLUMN = 1
_MIN_MOUNT_LINE_COLUMNS = 2


class LinuxRemovableMediaCollector:
    category = "removable_media"

    def __init__(
        self,
        *,
        sys_block_path: Path = Path("/sys/block"),
        proc_mounts_path: Path = Path("/proc/mounts"),
    ) -> None:
        self._sys_block_path = sys_block_path
        self._proc_mounts_path = proc_mounts_path
        self._previous: set[str] = set()

    async def collect(self) -> list[OutgoingEvent]:
        return await asyncio.to_thread(self._collect_sync)

    def _collect_sync(self) -> list[OutgoingEvent]:
        now = datetime.now(UTC)
        current = self._enumerate_removable_devices()
        events = [
            OutgoingEvent(
                category=self.category,
                occurred_at=now,
                payload={
                    "device": device,
                    "action": action,
                    "mountpoint": self._mountpoint_for(device)
                    if action == "connected"
                    else None,
                },
            )
            for device, action in diff_devices(self._previous, current)
        ]
        self._previous = current
        return events

    def _enumerate_removable_devices(self) -> set[str]:
        if not self._sys_block_path.is_dir():
            return set()
        devices = set()
        for entry in self._sys_block_path.iterdir():
            flag_path = entry / "removable"
            try:
                if flag_path.read_text(encoding="utf-8").strip() == "1":
                    devices.add(entry.name)
            except OSError:
                continue  # gone between listing and reading, or not a real device dir
        return devices

    def _mountpoint_for(self, device: str) -> str | None:
        try:
            content = self._proc_mounts_path.read_text(encoding="utf-8")
        except OSError:
            return None
        prefix = f"/dev/{device}"
        for line in content.splitlines():
            columns = line.split()
            if len(columns) < _MIN_MOUNT_LINE_COLUMNS:
                continue
            if columns[_DEVICE_PATH_COLUMN].startswith(prefix):
                return columns[_MOUNTPOINT_COLUMN]
        return None
