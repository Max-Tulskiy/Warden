"""Tests for the cross-station report query model (spec 002, R-1, A-2)."""

import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from warden_server.models.event import EventCategory
from warden_server.schemas.report import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    ReportFilter,
)

START = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def test_a_valid_range_is_accepted_with_defaults():
    parsed = ReportFilter(start=START, end=START + timedelta(hours=1))

    assert parsed.agent_id == []
    assert parsed.category is None
    assert parsed.limit == DEFAULT_PAGE_SIZE
    assert parsed.offset == 0


def test_a_range_longer_than_four_hours_is_accepted():
    """The 4h cap governs agent requests, not reads of stored events."""
    parsed = ReportFilter(start=START, end=START + timedelta(days=7))

    assert parsed.end - parsed.start == timedelta(days=7)


def test_an_end_equal_to_the_start_is_rejected():
    with pytest.raises(ValidationError, match="end must be after start"):
        ReportFilter(start=START, end=START)


def test_an_end_before_the_start_is_rejected():
    with pytest.raises(ValidationError, match="end must be after start"):
        ReportFilter(start=START, end=START - timedelta(minutes=1))


def test_naive_timestamps_are_treated_as_utc():
    parsed = ReportFilter(
        start=datetime(2026, 9, 1, 12, 0), end=datetime(2026, 9, 1, 13, 0)
    )

    assert parsed.start == START
    assert parsed.start.tzinfo is not None


def test_one_naive_and_one_aware_timestamp_do_not_raise_type_error():
    parsed = ReportFilter(start=datetime(2026, 9, 1, 12, 0), end=START + timedelta(1))

    assert parsed.end > parsed.start


def test_a_naive_start_after_an_aware_end_is_a_validation_error_not_a_type_error():
    with pytest.raises(ValidationError, match="end must be after start"):
        ReportFilter(start=datetime(2026, 9, 1, 12, 0), end=START - timedelta(hours=1))


def test_offset_timestamps_are_converted_to_utc():
    """SQLite drops an offset instead of applying it, so the filter must hand
    the database UTC values already."""
    plus_three = timezone(timedelta(hours=3))

    parsed = ReportFilter(
        start=datetime(2026, 9, 1, 15, 0, tzinfo=plus_three),
        end=datetime(2026, 9, 1, 13, 0, tzinfo=UTC),
    )

    assert parsed.start == START
    assert parsed.start.utcoffset() == timedelta(0)


def test_a_limit_above_the_maximum_is_rejected():
    with pytest.raises(ValidationError):
        ReportFilter(
            start=START, end=START + timedelta(hours=1), limit=MAX_PAGE_SIZE + 1
        )


def test_a_zero_limit_and_a_negative_offset_are_rejected():
    with pytest.raises(ValidationError):
        ReportFilter(start=START, end=START + timedelta(hours=1), limit=0)
    with pytest.raises(ValidationError):
        ReportFilter(start=START, end=START + timedelta(hours=1), offset=-1)


def test_station_and_category_filters_are_parsed():
    station = uuid.uuid4()

    parsed = ReportFilter(
        start=START,
        end=START + timedelta(hours=1),
        agent_id=[station],
        category="printing",
    )

    assert parsed.agent_id == [station]
    assert parsed.category is EventCategory.PRINTING


def test_an_unknown_category_is_rejected():
    with pytest.raises(ValidationError):
        ReportFilter(start=START, end=START + timedelta(hours=1), category="keystrokes")
