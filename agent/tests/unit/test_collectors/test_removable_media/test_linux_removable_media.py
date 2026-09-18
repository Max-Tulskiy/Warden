"""Tests for the Linux removable-media backend against a fake sysfs/procfs
tree built under `tmp_path` -- this is the real file-reading logic running
for real, not a mock of it (constitution principle 7).
"""

import shutil

from warden_agent.collectors.removable_media.linux import LinuxRemovableMediaCollector


def _make_block_device(sys_block: object, name: str, *, removable: bool) -> None:
    device_dir = sys_block / name  # type: ignore[operator]
    device_dir.mkdir()
    (device_dir / "removable").write_text("1" if removable else "0")


async def test_a_newly_appeared_removable_device_is_reported_connected(tmp_path):
    sys_block = tmp_path / "sys_block"
    sys_block.mkdir()
    proc_mounts = tmp_path / "mounts"
    proc_mounts.write_text("")
    collector = LinuxRemovableMediaCollector(
        sys_block_path=sys_block, proc_mounts_path=proc_mounts
    )
    await collector.collect()  # baseline: nothing connected yet

    _make_block_device(sys_block, "sdb", removable=True)

    events = await collector.collect()

    assert len(events) == 1
    assert events[0].payload == {
        "device": "sdb",
        "action": "connected",
        "mountpoint": None,
    }


async def test_internal_non_removable_disks_are_never_reported(tmp_path):
    sys_block = tmp_path / "sys_block"
    sys_block.mkdir()
    proc_mounts = tmp_path / "mounts"
    proc_mounts.write_text("")
    _make_block_device(sys_block, "sda", removable=False)
    collector = LinuxRemovableMediaCollector(
        sys_block_path=sys_block, proc_mounts_path=proc_mounts
    )

    events = await collector.collect()

    assert events == []


async def test_a_removed_device_is_reported_disconnected(tmp_path):
    sys_block = tmp_path / "sys_block"
    sys_block.mkdir()
    proc_mounts = tmp_path / "mounts"
    proc_mounts.write_text("")
    _make_block_device(sys_block, "sdb", removable=True)
    collector = LinuxRemovableMediaCollector(
        sys_block_path=sys_block, proc_mounts_path=proc_mounts
    )
    await collector.collect()  # baseline: sdb is connected

    shutil.rmtree(sys_block / "sdb")

    events = await collector.collect()

    assert len(events) == 1
    assert events[0].payload == {
        "device": "sdb",
        "action": "disconnected",
        "mountpoint": None,
    }


async def test_the_mountpoint_is_read_from_proc_mounts(tmp_path):
    sys_block = tmp_path / "sys_block"
    sys_block.mkdir()
    proc_mounts = tmp_path / "mounts"
    proc_mounts.write_text("/dev/sdb1 /media/usb vfat rw,relatime 0 0\n")
    _make_block_device(sys_block, "sdb", removable=True)
    collector = LinuxRemovableMediaCollector(
        sys_block_path=sys_block, proc_mounts_path=proc_mounts
    )

    events = await collector.collect()

    assert events[0].payload["mountpoint"] == "/media/usb"
