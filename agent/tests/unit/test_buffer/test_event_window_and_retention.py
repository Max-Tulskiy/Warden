"""Tests for the local SQLite buffer (constitution principles 2 and 4)."""

from datetime import UTC, datetime, timedelta

from warden_agent.buffer import Buffer


def _buffer(tmp_path):
    return Buffer(tmp_path / "buffer.db")


def test_events_in_window_returns_only_events_inside_the_range(tmp_path):
    buffer = _buffer(tmp_path)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    buffer.add_event("processes", base - timedelta(minutes=1), {"name": "before"})
    buffer.add_event("processes", base + timedelta(minutes=1), {"name": "inside"})
    buffer.add_event("processes", base + timedelta(hours=2), {"name": "after"})

    result = buffer.events_in_window("processes", base, base + timedelta(hours=1))

    assert [event.payload["name"] for event in result] == ["inside"]


def test_events_in_window_is_scoped_to_the_requested_category(tmp_path):
    buffer = _buffer(tmp_path)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    buffer.add_event("processes", now, {"name": "p"})
    buffer.add_event("web", now, {"url": "example.com"})

    result = buffer.events_in_window(
        "processes", now - timedelta(minutes=1), now + timedelta(minutes=1)
    )

    assert len(result) == 1
    assert result[0].category == "processes"


def test_prune_removes_only_events_older_than_the_cutoff(tmp_path):
    buffer = _buffer(tmp_path)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    buffer.add_event("processes", now - timedelta(hours=10), {"name": "old"})
    buffer.add_event("processes", now - timedelta(hours=1), {"name": "recent"})

    removed = buffer.prune(now - timedelta(hours=8))

    assert removed == 1
    remaining = buffer.events_in_window(
        "processes", now - timedelta(hours=24), now + timedelta(hours=24)
    )
    assert [event.payload["name"] for event in remaining] == ["recent"]


def test_events_round_trip_the_payload_exactly(tmp_path):
    buffer = _buffer(tmp_path)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    payload = {"device": "USB Flash Drive", "action": "connected", "size_mb": 32768}

    buffer.add_event("removable_media", now, payload)

    result = buffer.events_in_window(
        "removable_media", now - timedelta(minutes=1), now + timedelta(minutes=1)
    )
    assert result[0].payload == payload
