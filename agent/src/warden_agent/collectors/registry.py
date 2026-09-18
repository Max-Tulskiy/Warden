"""Selects the platform backend for each collector category at runtime.

This is the one place constitution principle 1 allows a platform check
outside a `linux.py`/`windows.py` file itself -- everywhere else imports
from here, never a specific backend directly.
"""

import platform
from pathlib import Path

from warden_agent.collectors.base import Collector, InventoryCollector
from warden_agent.collectors.inventory import (
    LinuxInventoryCollector,
    WindowsInventoryCollector,
)
from warden_agent.collectors.printing import (
    LinuxPrintingCollector,
    WindowsPrintingCollector,
)
from warden_agent.collectors.processes import ProcessCollector
from warden_agent.collectors.removable_media import (
    LinuxRemovableMediaCollector,
    WindowsRemovableMediaCollector,
)
from warden_agent.collectors.web import (
    ChromiumHistoryCollector,
    FirefoxHistoryCollector,
)
from warden_agent.collectors.web.paths import (
    discover_chromium_profiles,
    discover_firefox_profiles,
)


def current_platform() -> str:
    return "windows" if platform.system().lower() == "windows" else "linux"


def build_collectors(*, home: Path, os_name: str | None = None) -> list[Collector]:
    """Build the event collectors (media, printing, processes, web) for one platform."""
    os_name = os_name or current_platform()

    web_collectors: list[Collector] = []
    chromium_profiles = discover_chromium_profiles(home, os_name)
    if chromium_profiles:
        web_collectors.append(ChromiumHistoryCollector(profile_paths=chromium_profiles))
    firefox_profiles = discover_firefox_profiles(home, os_name)
    if firefox_profiles:
        web_collectors.append(FirefoxHistoryCollector(profile_paths=firefox_profiles))

    if os_name == "windows":
        return [
            WindowsRemovableMediaCollector(),
            WindowsPrintingCollector(),
            ProcessCollector(),
            *web_collectors,
        ]
    return [
        LinuxRemovableMediaCollector(),
        LinuxPrintingCollector(),
        ProcessCollector(),
        *web_collectors,
    ]


def build_inventory_collector(*, os_name: str | None = None) -> InventoryCollector:
    os_name = os_name or current_platform()
    if os_name == "windows":
        return WindowsInventoryCollector()
    return LinuxInventoryCollector()
