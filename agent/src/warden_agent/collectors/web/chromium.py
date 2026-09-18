"""Chromium-family (Chrome, Chromium, Edge) browsing-history collector.

Reads visits from the SQLite `History` database Chromium-based browsers
keep per profile. The file is locked while the browser is running, so it is
copied to a temporary location before every read -- the same workaround
every third-party History reader uses, not a design choice specific to this
one.
"""

import asyncio
import shutil
import sqlite3
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from warden_agent.core.models import OutgoingEvent

#: Chromium timestamps are microseconds since 1601-01-01 UTC (the Windows
#: "FILETIME" epoch), not the Unix epoch.
_CHROME_EPOCH = datetime(1601, 1, 1, tzinfo=UTC)


def chrome_time_to_datetime(chrome_microseconds: int) -> datetime:
    return _CHROME_EPOCH + timedelta(microseconds=chrome_microseconds)


class ChromiumHistoryCollector:
    category = "web"

    def __init__(self, *, profile_paths: list[Path]) -> None:
        self._profile_paths = profile_paths
        self._last_visit_time: dict[Path, int] = {}

    async def collect(self) -> list[OutgoingEvent]:
        return await asyncio.to_thread(self._collect_sync)

    def _collect_sync(self) -> list[OutgoingEvent]:
        events: list[OutgoingEvent] = []
        for path in self._profile_paths:
            events.extend(self._collect_profile(path))
        return events

    def _collect_profile(self, history_path: Path) -> list[OutgoingEvent]:
        if not history_path.is_file():
            return []
        since = self._last_visit_time.get(history_path, 0)

        with tempfile.TemporaryDirectory() as tmp_dir:
            copy_path = Path(tmp_dir) / "History"
            try:
                shutil.copy2(history_path, copy_path)
            except OSError:
                return []
            rows = self._query_new_visits(copy_path, since)

        events = []
        max_visit_time = since
        for url, title, visit_time in rows:
            max_visit_time = max(max_visit_time, visit_time)
            events.append(
                OutgoingEvent(
                    category=self.category,
                    occurred_at=chrome_time_to_datetime(visit_time),
                    payload={"url": url, "title": title, "browser": "chromium"},
                )
            )
        self._last_visit_time[history_path] = max_visit_time
        return events

    @staticmethod
    def _query_new_visits(copy_path: Path, since: int) -> list[tuple[str, str, int]]:
        connection = sqlite3.connect(f"file:{copy_path}?mode=ro", uri=True)
        try:
            return connection.execute(
                "SELECT urls.url, urls.title, visits.visit_time "
                "FROM visits JOIN urls ON visits.url = urls.id "
                "WHERE visits.visit_time > ? ORDER BY visits.visit_time",
                (since,),
            ).fetchall()
        finally:
            connection.close()
