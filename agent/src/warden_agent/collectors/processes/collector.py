"""Process-start collector: cross-platform via `psutil`, no OS split needed.

Unlike the other categories, this one does not need a separate platform
backend under `linux.py`/`windows.py` -- `psutil` already normalizes process
enumeration across operating systems, so principle 1's isolation has nothing
OS-specific to isolate here.
"""

import asyncio
from datetime import UTC, datetime

import psutil

from warden_agent.core.models import OutgoingEvent


class ProcessCollector:
    """Reports each process the first time it is seen, by pid.

    A pid seen again (the common case, most processes outlive one
    collection interval) is not reported twice; a pid that disappears and a
    *different* process later reuses the same number is reported again,
    since `psutil` gives a fresh `create_time` to tell them apart.
    """

    category = "processes"

    def __init__(self) -> None:
        self._seen: set[tuple[int, float]] = set()

    async def collect(self) -> list[OutgoingEvent]:
        return await asyncio.to_thread(self._collect_sync)

    def _collect_sync(self) -> list[OutgoingEvent]:
        events: list[OutgoingEvent] = []
        current: set[tuple[int, float]] = set()

        for proc in psutil.process_iter(["pid", "name", "create_time", "username"]):
            try:
                info = proc.info
            except psutil.NoSuchProcess:
                continue  # exited between process_iter listing it and reading .info

            identity = (info["pid"], info["create_time"])
            current.add(identity)
            if identity in self._seen:
                continue

            events.append(
                OutgoingEvent(
                    category=self.category,
                    occurred_at=datetime.fromtimestamp(info["create_time"], tz=UTC),
                    payload={
                        "pid": info["pid"],
                        "name": info["name"],
                        "username": info.get("username"),
                    },
                )
            )

        self._seen = current
        return events
