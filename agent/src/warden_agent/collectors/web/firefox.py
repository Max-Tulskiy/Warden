"""Firefox browsing-history collector.

Reads visits from `places.sqlite`. Same locked-file workaround as the
Chromium backend (`chromium.py`); the two are separate classes rather than
one parameterized reader because the schema and the timestamp epoch genuinely
differ between the two browser families, not just the file name.
"""

import asyncio
import shutil
import sqlite3
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from warden_agent.core.models import OutgoingEvent

#: Firefox timestamps are microseconds since the Unix epoch (unlike
#: Chromium's 1601-01-01 epoch).
_FIREFOX_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def firefox_time_to_datetime(unix_microseconds: int) -> datetime:
    return _FIREFOX_EPOCH + timedelta(microseconds=unix_microseconds)


class FirefoxHistoryCollector:
    category = "web"

    def __init__(self, *, profile_paths: list[Path]) -> None:
        self._profile_paths = profile_paths
        self._last_visit_date: dict[Path, int] = {}

    async def collect(self) -> list[OutgoingEvent]:
        return await asyncio.to_thread(self._collect_sync)

    def _collect_sync(self) -> list[OutgoingEvent]:
        events: list[OutgoingEvent] = []
        for path in self._profile_paths:
            events.extend(self._collect_profile(path))
        return events

    def _collect_profile(self, places_path: Path) -> list[OutgoingEvent]:
        if not places_path.is_file():
            return []
        since = self._last_visit_date.get(places_path, 0)

        with tempfile.TemporaryDirectory() as tmp_dir:
            copy_path = Path(tmp_dir) / "places.sqlite"
            try:
                shutil.copy2(places_path, copy_path)
            except OSError:
                return []
            rows = self._query_new_visits(copy_path, since)

        events = []
        max_visit_date = since
        for url, title, visit_date in rows:
            max_visit_date = max(max_visit_date, visit_date)
            events.append(
                OutgoingEvent(
                    category=self.category,
                    occurred_at=firefox_time_to_datetime(visit_date),
                    payload={"url": url, "title": title, "browser": "firefox"},
                )
            )
        self._last_visit_date[places_path] = max_visit_date
        return events

    @staticmethod
    def _query_new_visits(copy_path: Path, since: int) -> list[tuple[str, str, int]]:
        connection = sqlite3.connect(f"file:{copy_path}?mode=ro", uri=True)
        try:
            return connection.execute(
                "SELECT moz_places.url, moz_places.title, moz_historyvisits.visit_date "
                "FROM moz_historyvisits "
                "JOIN moz_places ON moz_historyvisits.place_id = moz_places.id "
                "WHERE moz_historyvisits.visit_date > ? "
                "ORDER BY moz_historyvisits.visit_date",
                (since,),
            ).fetchall()
        finally:
            connection.close()
