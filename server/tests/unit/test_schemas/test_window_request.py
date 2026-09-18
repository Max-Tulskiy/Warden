"""Tests for the server-side half of the ≤4h window check (principle 3)."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from warden_server.schemas.task import WindowRequestIn


def _window(hours: float) -> dict:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return {"window_start": start, "window_end": start + timedelta(hours=hours)}


def test_a_four_hour_window_is_accepted():
    request = WindowRequestIn(**_window(4))

    assert request.window_end - request.window_start == timedelta(hours=4)


def test_a_window_over_four_hours_is_rejected():
    with pytest.raises(ValidationError, match="must not exceed 4 hours"):
        WindowRequestIn(**_window(4.01))


def test_a_window_where_end_is_not_after_start_is_rejected():
    start = datetime(2026, 1, 1, tzinfo=UTC)

    with pytest.raises(ValidationError, match="window_end must be after window_start"):
        WindowRequestIn(window_start=start, window_end=start)
