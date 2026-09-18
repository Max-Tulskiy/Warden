"""Tests for the cross-platform hardware snapshot -- runs for real, no fixtures
needed: `psutil` and `platform` behave the same way on every CI platform.
"""

import json

from warden_agent.collectors.inventory.hardware import collect_hardware


def test_snapshot_has_the_expected_shape():
    snapshot = collect_hardware()

    assert snapshot["cpu_count"] >= 1
    assert snapshot["memory_total_bytes"] > 0
    assert isinstance(snapshot["disks"], list)
    assert snapshot["os"]


def test_snapshot_is_json_serializable():
    json.dumps(collect_hardware())
