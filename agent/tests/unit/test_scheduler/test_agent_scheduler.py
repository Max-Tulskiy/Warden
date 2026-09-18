"""Tests for `AgentScheduler`'s orchestration.

`run_forever` runs its three loops concurrently via `asyncio.gather`, and an
`AsyncMock` call that never truly suspends can let one task's loop finish an
entire tick-then-sleep cycle before another task's loop has even taken its
first turn. A stop condition based on wall-clock-style counting in the fake
`sleep` would then be racy: whichever loop happens to run first could set
the shared stop flag before a slower loop gets to tick even once. The tests
below sidestep that by having each tick record itself, and only stopping
once every loop has been seen -- which is true regardless of scheduling
order.
"""

import asyncio
from unittest.mock import AsyncMock

from warden_agent.buffer import Buffer
from warden_agent.core.scheduler import AgentScheduler


def _scheduler(tmp_path, *, client, collector, inventory_collector) -> AgentScheduler:
    return AgentScheduler(
        client=client,
        buffer=Buffer(tmp_path / "buffer.db"),
        collectors=[collector],
        inventory_collector=inventory_collector,
        agent_id="a1",
        agent_key="k1",
        poll_interval_seconds=60,
        inventory_interval_seconds=3600,
        retention_hours=8,
        max_window_hours=4,
    )


async def test_run_forever_ticks_every_loop_at_least_once_then_stops(tmp_path):
    seen: set[str] = set()
    client = AsyncMock()
    collector = AsyncMock()
    inventory_collector = AsyncMock()

    async def poll_tasks(**_kwargs):
        seen.add("poll")
        return []

    async def collect():
        seen.add("collection")
        return []

    async def snapshot():
        seen.add("inventory")
        return ({}, {})

    client.poll_tasks.side_effect = poll_tasks
    collector.collect.side_effect = collect
    inventory_collector.snapshot.side_effect = snapshot

    scheduler = _scheduler(
        tmp_path,
        client=client,
        collector=collector,
        inventory_collector=inventory_collector,
    )

    async def sleep(_seconds: float) -> None:
        # A real await, not just an `async def` that returns without ever
        # suspending: without it, whichever task the event loop happens to
        # run first never cedes control, and the other two loops never get
        # a turn at all -- a genuine asyncio gotcha, not a theoretical one
        # (this is exactly what made the first version of this test hang).
        await asyncio.sleep(0)
        # Only stop once every loop has ticked at least once -- true
        # regardless of which task the event loop happened to run first.
        if {"poll", "collection", "inventory"} <= seen:
            scheduler.stop()

    scheduler._sleep = sleep  # test-only override of the sleep hook

    await scheduler.run_forever()

    assert seen == {"poll", "collection", "inventory"}


async def test_a_failing_tick_does_not_stop_the_loop(tmp_path):
    client = AsyncMock()
    client.poll_tasks.side_effect = RuntimeError("network exploded")
    collector = AsyncMock()
    collector.collect.return_value = []
    inventory_collector = AsyncMock()
    inventory_collector.snapshot.return_value = ({}, {})

    scheduler = _scheduler(
        tmp_path,
        client=client,
        collector=collector,
        inventory_collector=inventory_collector,
    )

    async def sleep(_seconds: float) -> None:
        await asyncio.sleep(0)  # yield control -- see the comment above
        # The poll tick raises every time, proving retries survive it, so
        # the stop condition here only needs "it ran more than once".
        if client.poll_tasks.call_count >= 2:
            scheduler.stop()

    scheduler._sleep = sleep  # test-only override of the sleep hook

    # Must not raise, even though the poll tick's client call always errors.
    await scheduler.run_forever()

    assert client.poll_tasks.call_count >= 2
