"""The interface every collector implements, and its platform-selection contract.

A category (`removable_media`, `printing`, `processes`, `web`) exposes one
`Collector`, chosen at runtime for the current platform by
`collectors.registry.for_platform` (constitution principle 1) -- callers
never import a platform backend directly.
"""

from typing import Protocol

from warden_agent.core.models import OutgoingEvent


class Collector(Protocol):
    """Something that observes one category of activity continuously.

    `collect()` returns events observed since the previous call; a backend
    is free to track its own "since" cursor however suits its data source
    (a log file offset, a browser history row id, ...).
    """

    category: str

    async def collect(self) -> list[OutgoingEvent]: ...


class InventoryCollector(Protocol):
    """Hardware/software inventory: a full snapshot, not incremental events."""

    async def snapshot(self) -> tuple[dict, dict]:
        """Return `(hardware, software)`."""
        ...
