"""Tests for platform backend selection."""

from warden_agent.collectors.inventory import (
    LinuxInventoryCollector,
    WindowsInventoryCollector,
)
from warden_agent.collectors.printing import (
    LinuxPrintingCollector,
    WindowsPrintingCollector,
)
from warden_agent.collectors.registry import build_collectors, build_inventory_collector
from warden_agent.collectors.removable_media import (
    LinuxRemovableMediaCollector,
    WindowsRemovableMediaCollector,
)
from warden_agent.collectors.web import (
    ChromiumHistoryCollector,
    FirefoxHistoryCollector,
)


def test_build_collectors_selects_linux_backends(tmp_path):
    collectors = build_collectors(home=tmp_path, os_name="linux")

    kinds = {type(collector) for collector in collectors}
    assert LinuxRemovableMediaCollector in kinds
    assert LinuxPrintingCollector in kinds
    assert WindowsRemovableMediaCollector not in kinds


def test_build_collectors_selects_windows_backends(tmp_path):
    collectors = build_collectors(home=tmp_path, os_name="windows")

    kinds = {type(collector) for collector in collectors}
    assert WindowsRemovableMediaCollector in kinds
    assert WindowsPrintingCollector in kinds
    assert LinuxRemovableMediaCollector not in kinds


def test_web_collectors_are_only_included_when_a_profile_exists(tmp_path):
    collectors = build_collectors(home=tmp_path, os_name="linux")

    web_types = (ChromiumHistoryCollector, FirefoxHistoryCollector)
    assert not any(isinstance(collector, web_types) for collector in collectors)


def test_a_chromium_profile_adds_the_chromium_collector(tmp_path):
    profile = tmp_path / ".config" / "google-chrome" / "Default"
    profile.mkdir(parents=True)
    (profile / "History").write_text("")

    collectors = build_collectors(home=tmp_path, os_name="linux")

    found_chromium = any(
        isinstance(collector, ChromiumHistoryCollector) for collector in collectors
    )
    assert found_chromium


def test_build_inventory_collector_selects_by_platform(tmp_path):
    linux_collector = build_inventory_collector(os_name="linux")
    windows_collector = build_inventory_collector(os_name="windows")

    assert isinstance(linux_collector, LinuxInventoryCollector)
    assert isinstance(windows_collector, WindowsInventoryCollector)
