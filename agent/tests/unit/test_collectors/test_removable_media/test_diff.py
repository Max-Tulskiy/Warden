"""Tests for the pure connect/disconnect diffing shared by both platforms."""

from warden_agent.collectors.removable_media.diff import diff_devices


def test_a_new_device_is_reported_as_connected():
    assert diff_devices(previous=set(), current={"sdb"}) == [("sdb", "connected")]


def test_a_missing_device_is_reported_as_disconnected():
    assert diff_devices(previous={"sdb"}, current=set()) == [("sdb", "disconnected")]


def test_an_unchanged_device_produces_no_event():
    assert diff_devices(previous={"sdb"}, current={"sdb"}) == []


def test_connects_and_disconnects_are_both_reported_in_one_pass():
    changes = diff_devices(previous={"sdb"}, current={"sdc"})

    assert set(changes) == {("sdc", "connected"), ("sdb", "disconnected")}


def test_output_is_sorted_for_a_deterministic_order():
    changes = diff_devices(previous=set(), current={"sdc", "sdb"})

    assert changes == [("sdb", "connected"), ("sdc", "connected")]
