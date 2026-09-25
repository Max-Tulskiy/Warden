"""Orchestrates the agent's three independent loops (constitution D-1, D-4).

- **collection**: runs every registered collector and writes its events to
  the buffer, then prunes anything past retention (principle 4).
- **poll**: asks the server for tasks and answers `window_request` tasks
  from the buffer (principle 2) -- the only place events ever leave it.
- **inventory**: periodically sends a hardware/software snapshot and, by the
  same request, updates the agent's `last_seen_at` on the server (D-4).

Each loop is a plain `while True: ... await sleep(...)`, not a scheduling
library -- the pass functions below do the actual work and are called
directly, in isolation, by tests; `AgentScheduler.run_forever` is just the
timing wrapper used in production.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Final

from warden_agent.buffer import Buffer
from warden_agent.collectors.base import Collector, InventoryCollector
from warden_agent.core.models import OutgoingEvent, TaskDTO
from warden_agent.core.transport import ServerClient

logger = logging.getLogger(__name__)

#: Categories a window-request task can be answered with -- inventory is
#: reported separately (D-4), never as part of a window response.
REPORTABLE_CATEGORIES = ("removable_media", "printing", "processes", "web")

#: How many times the normal interval a failing tick's retry delay may grow
#: to. A station left disabled fails every poll with a 401 forever; without
#: a cap, geometric growth would eventually leave the agent waiting hours to
#: notice it was re-enabled.
MAX_BACKOFF_MULTIPLIER: Final = 16


def validate_task_window(task: TaskDTO, max_hours: int) -> bool:
    """The agent's own half of the ≤N-hour check (constitution principle 3)."""
    return task.window_end - task.window_start <= timedelta(hours=max_hours)


def backoff_delay(interval_seconds: int, *, consecutive_failures: int) -> int:
    """How long a scheduled loop should wait before its next tick.

    A single failed tick is treated as a blip and keeps the normal cadence;
    from the second consecutive failure on, the delay doubles each time, up
    to `MAX_BACKOFF_MULTIPLIER` times the interval -- so a station stuck
    failing every tick (a disabled station polling into a 401, a server
    that is down) stops hammering the server and filling the log once a
    tick, while still checking back on its own once whatever was wrong is
    fixed.
    """
    if consecutive_failures <= 1:
        return interval_seconds
    multiplier = min(2 ** (consecutive_failures - 1), MAX_BACKOFF_MULTIPLIER)
    return interval_seconds * multiplier


async def run_collection_pass(
    collectors: list[Collector],
    buffer: Buffer,
    *,
    retention_hours: int,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> None:
    current = now()
    for collector in collectors:
        for event in await collector.collect():
            buffer.add_event(event.category, event.occurred_at, event.payload)
    buffer.prune(current - timedelta(hours=retention_hours))


async def run_poll_pass(
    client: ServerClient,
    buffer: Buffer,
    *,
    agent_id: str,
    agent_key: str,
    max_window_hours: int,
) -> list[TaskDTO]:
    tasks = await client.poll_tasks(agent_id=agent_id, agent_key=agent_key)

    for task in tasks:
        if task.kind != "window_request":
            continue
        if not validate_task_window(task, max_window_hours):
            # Should be unreachable if the server's own check (principle 3)
            # is intact; refusing here rather than trusting the server keeps
            # a server-side defect from ever making the agent leak more
            # history than the constitution allows.
            logger.error(
                "task %s window exceeds %dh, refusing to answer it",
                task.id,
                max_window_hours,
            )
            continue

        events = [
            OutgoingEvent(
                category=category,
                occurred_at=item.occurred_at,
                payload=item.payload,
            )
            for category in REPORTABLE_CATEGORIES
            for item in buffer.events_in_window(
                category, task.window_start, task.window_end
            )
        ]
        await client.push_report(
            agent_id=agent_id, agent_key=agent_key, task_id=task.id, events=events
        )

    return tasks


async def run_inventory_pass(
    client: ServerClient,
    inventory_collector: InventoryCollector,
    *,
    agent_id: str,
    agent_key: str,
) -> None:
    hardware, software = await inventory_collector.snapshot()
    await client.push_inventory(
        agent_id=agent_id, agent_key=agent_key, hardware=hardware, software=software
    )


class AgentScheduler:
    """Runs the three passes above on their own intervals until stopped."""

    # Many collaborators and policy knobs come together here on purpose --
    # this is the composition root that wires the buffer, transport, and
    # collectors into one running agent; splitting it up would just move
    # the same parameter list one level out.
    def __init__(  # noqa: PLR0913
        self,
        *,
        client: ServerClient,
        buffer: Buffer,
        collectors: list[Collector],
        inventory_collector: InventoryCollector,
        agent_id: str,
        agent_key: str,
        poll_interval_seconds: int,
        inventory_interval_seconds: int,
        retention_hours: int,
        max_window_hours: int,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._client = client
        self._buffer = buffer
        self._collectors = collectors
        self._inventory_collector = inventory_collector
        self._agent_id = agent_id
        self._agent_key = agent_key
        self._poll_interval = poll_interval_seconds
        self._inventory_interval = inventory_interval_seconds
        self._retention_hours = retention_hours
        self._max_window_hours = max_window_hours
        self._sleep = sleep
        self._stopping = asyncio.Event()

    def stop(self) -> None:
        self._stopping.set()

    async def run_forever(self) -> None:
        await asyncio.gather(
            self._loop(self._collection_tick, self._poll_interval),
            self._loop(self._poll_tick, self._poll_interval),
            self._loop(self._inventory_tick, self._inventory_interval),
        )

    async def _loop(
        self, tick: Callable[[], Awaitable[None]], interval_seconds: int
    ) -> None:
        consecutive_failures = 0
        while not self._stopping.is_set():
            try:
                await tick()
            except Exception:
                logger.exception("scheduled task failed, continuing on the next tick")
                consecutive_failures += 1
            else:
                consecutive_failures = 0
            await self._sleep(
                backoff_delay(
                    interval_seconds, consecutive_failures=consecutive_failures
                )
            )

    async def _collection_tick(self) -> None:
        await run_collection_pass(
            self._collectors, self._buffer, retention_hours=self._retention_hours
        )

    async def _poll_tick(self) -> None:
        await run_poll_pass(
            self._client,
            self._buffer,
            agent_id=self._agent_id,
            agent_key=self._agent_key,
            max_window_hours=self._max_window_hours,
        )

    async def _inventory_tick(self) -> None:
        await run_inventory_pass(
            self._client,
            self._inventory_collector,
            agent_id=self._agent_id,
            agent_key=self._agent_key,
        )
