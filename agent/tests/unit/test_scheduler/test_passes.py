"""Tests for the scheduler's individual passes (collection, poll, inventory)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from warden_agent.buffer import Buffer
from warden_agent.core.models import OutgoingEvent, TaskDTO
from warden_agent.core.scheduler import (
    backoff_delay,
    run_collection_pass,
    run_inventory_pass,
    run_poll_pass,
    validate_task_window,
)


def _task(hours: float, kind: str = "window_request") -> TaskDTO:
    start = datetime(2026, 1, 1, 10, tzinfo=UTC)
    return TaskDTO(
        id="t1",
        kind=kind,
        window_start=start,
        window_end=start + timedelta(hours=hours),
        status="dispatched",
    )


def test_validate_task_window_accepts_exactly_the_cap():
    assert validate_task_window(_task(4), max_hours=4)


def test_validate_task_window_rejects_over_the_cap():
    assert not validate_task_window(_task(4.01), max_hours=4)


def test_backoff_delay_is_the_plain_interval_without_a_failure():
    assert backoff_delay(60, consecutive_failures=0) == 60


def test_backoff_delay_does_not_grow_on_a_single_failure():
    # One bad tick is treated as a blip, not the start of an outage.
    assert backoff_delay(60, consecutive_failures=1) == 60


def test_backoff_delay_grows_geometrically_with_repeated_failures():
    assert backoff_delay(60, consecutive_failures=2) == 120
    assert backoff_delay(60, consecutive_failures=3) == 240
    assert backoff_delay(60, consecutive_failures=4) == 480


def test_backoff_delay_is_capped():
    # A disabled station (or any sustained outage) must not push the retry
    # cadence out indefinitely -- it settles at 16x the normal interval.
    assert backoff_delay(60, consecutive_failures=5) == 960
    assert backoff_delay(60, consecutive_failures=20) == 960


async def test_collection_pass_writes_events_and_prunes_old_ones(tmp_path):
    buffer = Buffer(tmp_path / "buffer.db")
    now = datetime(2026, 1, 1, 12, tzinfo=UTC)
    buffer.add_event("processes", now - timedelta(hours=20), {"name": "stale"})

    fresh_event = OutgoingEvent(
        category="processes", occurred_at=now, payload={"name": "fresh"}
    )
    collector = AsyncMock()
    collector.collect.return_value = [fresh_event]

    await run_collection_pass([collector], buffer, retention_hours=8, now=lambda: now)

    remaining = buffer.events_in_window(
        "processes", now - timedelta(days=1), now + timedelta(minutes=1)
    )
    assert [event.payload["name"] for event in remaining] == ["fresh"]


async def test_poll_pass_answers_a_window_request_from_the_buffer(tmp_path):
    buffer = Buffer(tmp_path / "buffer.db")
    task = _task(2)
    buffer.add_event(
        "processes",
        task.window_start + timedelta(minutes=10),
        {"name": "inside-window"},
    )
    buffer.add_event(
        "processes", task.window_start - timedelta(hours=1), {"name": "before"}
    )
    client = AsyncMock()
    client.poll_tasks.return_value = [task]

    await run_poll_pass(
        client,
        buffer,
        agent_id="a1",
        agent_key="k1",
        max_window_hours=4,
    )

    client.push_report.assert_awaited_once()
    _, kwargs = client.push_report.call_args
    assert kwargs["task_id"] == "t1"
    assert [event.payload["name"] for event in kwargs["events"]] == ["inside-window"]


async def test_poll_pass_refuses_a_task_whose_window_exceeds_the_cap(tmp_path):
    buffer = Buffer(tmp_path / "buffer.db")
    client = AsyncMock()
    client.poll_tasks.return_value = [_task(5)]

    await run_poll_pass(
        client, buffer, agent_id="a1", agent_key="k1", max_window_hours=4
    )

    client.push_report.assert_not_awaited()


async def test_inventory_pass_sends_the_collector_snapshot():
    client = AsyncMock()
    collector = AsyncMock()
    collector.snapshot.return_value = ({"cpu": "x86_64"}, {"nginx": "1.24"})

    await run_inventory_pass(client, collector, agent_id="a1", agent_key="k1")

    client.push_inventory.assert_awaited_once_with(
        agent_id="a1",
        agent_key="k1",
        hardware={"cpu": "x86_64"},
        software={"nginx": "1.24"},
    )
