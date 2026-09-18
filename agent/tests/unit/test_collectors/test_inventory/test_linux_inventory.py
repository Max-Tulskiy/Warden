"""Tests for the Linux software-inventory backend's tool-selection logic.

`subprocess.run` and `shutil.which` are mocked -- the dev machine running
these tests is not assumed to have `dpkg-query`/`rpm` installed, and the
point of this test is the fallback logic, not the real tool output (that is
`test_parsing.py`'s job on fixture text, and a live check on an actual
Debian/RPM system per constitution Section VI).
"""

from unittest.mock import patch

from warden_agent.collectors.inventory.linux import LinuxInventoryCollector


def test_prefers_dpkg_when_available():
    collector = LinuxInventoryCollector()

    with (
        patch("warden_agent.collectors.inventory.linux.shutil.which") as which,
        patch.object(collector, "_run", return_value="bash\t5.2\n") as run,
    ):
        which.side_effect = lambda tool: tool == "dpkg-query"

        software = collector._collect_software()

    assert software == {"bash": "5.2"}
    assert run.call_args[0][0][0] == "dpkg-query"


def test_falls_back_to_rpm_when_dpkg_is_absent():
    collector = LinuxInventoryCollector()

    with (
        patch("warden_agent.collectors.inventory.linux.shutil.which") as which,
        patch.object(collector, "_run", return_value="glibc\t2.38\n") as run,
    ):
        which.side_effect = lambda tool: tool == "rpm"

        software = collector._collect_software()

    assert software == {"glibc": "2.38"}
    assert run.call_args[0][0][0] == "rpm"


def test_returns_empty_when_neither_tool_is_available():
    collector = LinuxInventoryCollector()

    with patch(
        "warden_agent.collectors.inventory.linux.shutil.which", return_value=None
    ):
        software = collector._collect_software()

    assert software == {}


async def test_snapshot_returns_hardware_and_software():
    collector = LinuxInventoryCollector()

    with patch.object(collector, "_collect_software", return_value={"bash": "5.2"}):
        hardware, software = await collector.snapshot()

    assert software == {"bash": "5.2"}
    assert hardware["cpu_count"] >= 1
