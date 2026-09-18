"""SQLite-backed local event buffer (constitution principles 2 and 4).

Events accumulate here continuously as collectors run; nothing is sent to
the server until a `window_request` task asks for a specific slice of it
(principle 2), and nothing lives here longer than the configured retention
(principle 4) -- `prune` is called by the collection loop before every pass.
"""

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_category_time
    ON events (category, occurred_at);
"""


@dataclass(frozen=True)
class BufferedEvent:
    category: str
    occurred_at: datetime
    payload: dict[str, Any]


class Buffer:
    """A thin, thread-safe wrapper over a single SQLite file.

    `check_same_thread=False` plus an explicit lock lets collectors write
    from a worker thread (a blocking collector runs via
    `asyncio.to_thread`) while the scheduler reads from the event loop's own
    thread.
    """

    def __init__(self, path: Path) -> None:
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        path.chmod(0o600)
        with self._lock:
            self._connection.executescript(_SCHEMA)
            self._connection.commit()

    def add_event(
        self, category: str, occurred_at: datetime, payload: dict[str, Any]
    ) -> None:
        with self._lock, self._cursor() as cursor:
            cursor.execute(
                "INSERT INTO events (category, occurred_at, payload) VALUES (?, ?, ?)",
                (
                    category,
                    occurred_at.astimezone(UTC).isoformat(),
                    json.dumps(payload),
                ),
            )

    def events_in_window(
        self, category: str, start: datetime, end: datetime
    ) -> list[BufferedEvent]:
        with self._lock, self._cursor() as cursor:
            rows = cursor.execute(
                "SELECT category, occurred_at, payload FROM events "
                "WHERE category = ? AND occurred_at >= ? AND occurred_at < ? "
                "ORDER BY occurred_at",
                (
                    category,
                    start.astimezone(UTC).isoformat(),
                    end.astimezone(UTC).isoformat(),
                ),
            ).fetchall()
        return [
            BufferedEvent(
                category=row[0],
                occurred_at=datetime.fromisoformat(row[1]),
                payload=json.loads(row[2]),
            )
            for row in rows
        ]

    def prune(self, older_than: datetime) -> int:
        """Delete events older than the cutoff; returns how many were removed."""
        with self._lock, self._cursor() as cursor:
            cursor.execute(
                "DELETE FROM events WHERE occurred_at < ?",
                (older_than.astimezone(UTC).isoformat(),),
            )
            return cursor.rowcount

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        cursor = self._connection.cursor()
        try:
            yield cursor
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        finally:
            cursor.close()
