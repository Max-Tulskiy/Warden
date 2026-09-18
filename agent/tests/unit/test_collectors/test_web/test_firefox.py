"""Tests for the Firefox history collector against a real SQLite database
built with the `places.sqlite` schema (constitution principle 7)."""

import sqlite3
from pathlib import Path

from warden_agent.collectors.web.firefox import (
    FirefoxHistoryCollector,
    firefox_time_to_datetime,
)

_VISIT_DATE_1 = 1_700_000_000_000_000  # microseconds since the Unix epoch
_VISIT_DATE_2 = _VISIT_DATE_1 + 1_000_000


def _make_places_db(path: Path, visits: list[tuple[str, str, int]]) -> None:
    # tests overwrite an existing db to simulate newly appeared visits
    path.unlink(missing_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE moz_places (id INTEGER PRIMARY KEY, url TEXT, title TEXT)"
        )
        connection.execute(
            "CREATE TABLE moz_historyvisits "
            "(id INTEGER PRIMARY KEY, place_id INTEGER, visit_date INTEGER)"
        )
        for index, (url, title, visit_date) in enumerate(visits, start=1):
            connection.execute(
                "INSERT INTO moz_places (id, url, title) VALUES (?, ?, ?)",
                (index, url, title),
            )
            connection.execute(
                "INSERT INTO moz_historyvisits (place_id, visit_date) VALUES (?, ?)",
                (index, visit_date),
            )
        connection.commit()
    finally:
        connection.close()


def test_firefox_time_to_datetime_converts_the_unix_epoch():
    result = firefox_time_to_datetime(0)

    assert result.year == 1970
    assert result.month == 1
    assert result.day == 1


async def test_visits_are_reported_with_url_and_title(tmp_path):
    places = tmp_path / "places.sqlite"
    _make_places_db(places, [("https://example.org", "Example Org", _VISIT_DATE_1)])
    collector = FirefoxHistoryCollector(profile_paths=[places])

    events = await collector.collect()

    assert len(events) == 1
    assert events[0].payload["url"] == "https://example.org"
    assert events[0].payload["browser"] == "firefox"


async def test_only_visits_newer_than_the_last_read_are_reported(tmp_path):
    places = tmp_path / "places.sqlite"
    _make_places_db(places, [("https://example.org", "Example", _VISIT_DATE_1)])
    collector = FirefoxHistoryCollector(profile_paths=[places])
    await collector.collect()

    _make_places_db(
        places,
        [
            ("https://example.org", "Example", _VISIT_DATE_1),
            ("https://second.example", "Second", _VISIT_DATE_2),
        ],
    )

    events = await collector.collect()

    assert len(events) == 1
    assert events[0].payload["url"] == "https://second.example"


async def test_a_missing_profile_yields_no_events(tmp_path):
    collector = FirefoxHistoryCollector(profile_paths=[tmp_path / "does-not-exist"])

    assert await collector.collect() == []
