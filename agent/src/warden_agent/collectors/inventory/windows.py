"""Windows inventory backend: hardware via `psutil`, software via the registry.

Reads the two conventional Uninstall registry hives
(`SOFTWARE\\...\\Uninstall` and its Wow6432Node twin for 32-bit applications
on a 64-bit install) the same way Control Panel's "Programs and Features"
does. `winreg` only exists on Windows, so it is imported lazily inside the
functions that need it -- this module must stay importable on any platform
(constitution principle 1). Only that thin registry-reading glue is
untested outside the `windows-latest` CI leg and a live check (Section VI);
`parse_uninstall_entries` carries the actual logic and is unit-tested on
fixture data on every platform.
"""

import asyncio
from typing import Any

from warden_agent.collectors.inventory.hardware import collect_hardware

_UNINSTALL_KEYS = (
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
    r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
)


def parse_uninstall_entries(entries: list[dict[str, str]]) -> dict[str, str]:
    """Turn raw registry values into a `{name: version}` mapping.

    An entry without a `DisplayName` is a registry artifact (a hotfix, a
    leftover key), not an installed program, and is skipped.
    """
    software: dict[str, str] = {}
    for entry in entries:
        name = entry.get("DisplayName")
        if name:
            software[name] = entry.get("DisplayVersion", "")
    return software


class WindowsInventoryCollector:
    async def snapshot(self) -> tuple[dict[str, Any], dict[str, str]]:
        return await asyncio.to_thread(self._snapshot_sync)

    def _snapshot_sync(self) -> tuple[dict[str, Any], dict[str, str]]:
        entries = self._read_uninstall_entries()
        return collect_hardware(), parse_uninstall_entries(entries)

    @staticmethod
    def _read_uninstall_entries() -> list[dict[str, str]]:
        import winreg  # Windows-only; see module docstring

        entries: list[dict[str, str]] = []
        for key_path in _UNINSTALL_KEYS:
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
            except OSError:
                continue  # the Wow6432Node hive does not exist on 32-bit Windows
            with key:
                for index in range(winreg.QueryInfoKey(key)[0]):
                    subkey_name = winreg.EnumKey(key, index)
                    entries.append(_read_uninstall_entry(key, subkey_name))
        return entries


def _read_uninstall_entry(parent_key: Any, subkey_name: str) -> dict[str, str]:
    import winreg  # Windows-only; see module docstring

    entry: dict[str, str] = {}
    try:
        with winreg.OpenKey(parent_key, subkey_name) as subkey:
            for value_name in ("DisplayName", "DisplayVersion"):
                try:
                    entry[value_name] = winreg.QueryValueEx(subkey, value_name)[0]
                except OSError:
                    pass  # this particular value is absent on this entry, skip it
    except OSError:
        pass  # the subkey vanished (uninstalled mid-enumeration) or is inaccessible
    return entry
