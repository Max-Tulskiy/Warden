"""Tests for the Chromium history collector against a real SQLite database
built with the same schema Chrome/Chromium/Edge actually use (constitution
principle 7): no mocking of the reading logic itself.
"""

import sqlite3
from pathlib import Path

from warden_agent.collectors.web.chromium import (
    ChromiumHistoryCollector,
    chrome_time_to_datetime,
)

# An arbitrary, fixed Chromium timestamp (microseconds since 1601-01-01 UTC)
# corresponding to a moment in 2024 -- the exact value does not matter, only
# that it round-trips through chrome_time_to_datetime correctly.
_VISIT_TIME_1 = 13_370_000_000_000_000
_VISIT_TIME_2 = _VISIT_TIME_1 + 1_000_000


def _make_history_db(path: Path, visits: list[tuple[str, str, int]]) -> None:
    # tests overwrite an existing db to simulate newly appeared visits
    path.unlink(missing_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT, title TEXT)"
        )
        connection.execute(
            "CREATE TABLE visits "
            "(id INTEGER PRIMARY KEY, url INTEGER, visit_time INTEGER)"
        )
        for index, (url, title, visit_time) in enumerate(visits, start=1):
            connection.execute(
                "INSERT INTO urls (id, url, title) VALUES (?, ?, ?)",
                (index, url, title),
            )
            connection.execute(
                "INSERT INTO visits (url, visit_time) VALUES (?, ?)",
                (index, visit_time),
            )
        connection.commit()
    finally:
        connection.close()


def test_chrome_time_to_datetime_converts_the_1601_epoch():
    # Exactly one day (86400 * 1_000_000 microseconds) after the epoch.
    result = chrome_time_to_datetime(86_400_000_000)

    assert result.year == 1601
    assert result.day == 2


async def test_visits_are_reported_with_url_and_title(tmp_path):
    history = tmp_path / "History"
    _make_history_db(history, [("https://example.com", "Example", _VISIT_TIME_1)])
    collector = ChromiumHistoryCollector(profile_paths=[history])

    events = await collector.collect()

    assert len(events) == 1
    assert events[0].payload["url"] == "https://example.com"
    assert events[0].payload["title"] == "Example"
    assert events[0].payload["browser"] == "chromium"


async def test_only_visits_newer_than_the_last_read_are_reported(tmp_path):
    history = tmp_path / "History"
    _make_history_db(history, [("https://example.com", "Example", _VISIT_TIME_1)])
    collector = ChromiumHistoryCollector(profile_paths=[history])
    await collector.collect()

    _make_history_db(
        history,
        [
            ("https://example.com", "Example", _VISIT_TIME_1),
            ("https://second.example", "Second", _VISIT_TIME_2),
        ],
    )

    events = await collector.collect()

    assert len(events) == 1
    assert events[0].payload["url"] == "https://second.example"


async def test_a_missing_profile_yields_no_events(tmp_path):
    collector = ChromiumHistoryCollector(profile_paths=[tmp_path / "does-not-exist"])

    assert await collector.collect() == []


async def test_multiple_profiles_are_all_read(tmp_path):
    profile_a = tmp_path / "profile_a" / "History"
    profile_a.parent.mkdir()
    _make_history_db(profile_a, [("https://a.example", "A", _VISIT_TIME_1)])
    profile_b = tmp_path / "profile_b" / "History"
    profile_b.parent.mkdir()
    _make_history_db(profile_b, [("https://b.example", "B", _VISIT_TIME_1)])
    collector = ChromiumHistoryCollector(profile_paths=[profile_a, profile_b])

    events = await collector.collect()

    urls = {event.payload["url"] for event in events}
    assert urls == {"https://a.example", "https://b.example"}
