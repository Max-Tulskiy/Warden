"""Live checks of the Windows inventory backend's registry reading.

Skipped everywhere except an actual Windows runner: exercises real `winreg`
calls against the machine's own Uninstall hive (constitution Section VI).
Any real Windows install has at least a few entries there, so this checks
both "it does not raise" and "it finds something," not just the former.
"""

import sys

import pytest

from warden_agent.collectors.inventory.windows import WindowsInventoryCollector

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="exercises real winreg calls, Windows only"
)


async def test_snapshot_runs_without_error():
    collector = WindowsInventoryCollector()

    hardware, software = await collector.snapshot()

    assert hardware["cpu_count"] >= 1
    assert isinstance(software, dict)


def test_reads_at_least_one_real_registry_entry():
    entries = WindowsInventoryCollector._read_uninstall_entries()

    assert len(entries) > 0
