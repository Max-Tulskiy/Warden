"""Tests for the policy request schema (spec 006, R-2, R-9, A-2, A-7)."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from warden_server.config import Settings
from warden_server.schemas import task as task_schemas
from warden_server.schemas.policy import (
    SESSION_MINUTES_BOUNDS,
    TOKEN_TTL_HOURS_BOUNDS,
    WINDOW_HOURS_BOUNDS,
    PolicyUpdateIn,
)
from warden_server.schemas.task import WindowRequestIn

VALID = {
    "max_request_window_hours": 2,
    "enrollment_token_ttl_hours": 12,
    "session_lifetime_minutes": 60,
}

BOUNDS = {
    "max_request_window_hours": WINDOW_HOURS_BOUNDS,
    "enrollment_token_ttl_hours": TOKEN_TTL_HOURS_BOUNDS,
    "session_lifetime_minutes": SESSION_MINUTES_BOUNDS,
}


def _with(**changes):
    return {**VALID, **changes}


def test_a_full_in_range_policy_is_accepted():
    parsed = PolicyUpdateIn(**VALID)

    assert (
        parsed.max_request_window_hours,
        parsed.enrollment_token_ttl_hours,
        parsed.session_lifetime_minutes,
    ) == (2, 12, 60)


@pytest.mark.parametrize("field", list(BOUNDS))
def test_each_value_is_accepted_at_both_ends_of_its_range(field):
    low, high = BOUNDS[field]

    assert getattr(PolicyUpdateIn(**_with(**{field: low})), field) == low
    assert getattr(PolicyUpdateIn(**_with(**{field: high})), field) == high


@pytest.mark.parametrize("field", list(BOUNDS))
def test_each_value_is_rejected_just_outside_its_range(field):
    low, high = BOUNDS[field]

    with pytest.raises(ValidationError):
        PolicyUpdateIn(**_with(**{field: low - 1}))
    with pytest.raises(ValidationError):
        PolicyUpdateIn(**_with(**{field: high + 1}))


def test_a_window_above_four_hours_is_rejected_however_it_is_asked():
    """Principle 3: four hours is a ceiling, not a value the panel can raise."""
    for hours in (5, 6, 24, 1000):
        with pytest.raises(ValidationError):
            PolicyUpdateIn(**_with(max_request_window_hours=hours))


@pytest.mark.parametrize("value", [2.5, 2.0, "2", "two", True, False, None, [2]])
@pytest.mark.parametrize("field", list(BOUNDS))
def test_only_a_whole_number_is_accepted(field, value):
    with pytest.raises(ValidationError):
        PolicyUpdateIn(**_with(**{field: value}))


@pytest.mark.parametrize("field", list(BOUNDS))
def test_every_value_is_required(field):
    incomplete = {key: value for key, value in VALID.items() if key != field}

    with pytest.raises(ValidationError):
        PolicyUpdateIn(**incomplete)


def test_any_other_field_is_rejected():
    with pytest.raises(ValidationError):
        PolicyUpdateIn(**_with(max_page_size=10))
    with pytest.raises(ValidationError):
        PolicyUpdateIn(**_with(min_password_length=1))


def test_a_window_request_no_longer_reads_the_settings(monkeypatch):
    """The configured limit is enforced by the endpoint, from the database; the
    schema knows only the constant ceiling, so principle 3 holds without one."""
    monkeypatch.setattr(
        task_schemas,
        "get_settings",
        lambda: Settings(max_request_window_hours=1),
        raising=False,
    )
    start = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)

    accepted = WindowRequestIn(
        window_start=start, window_end=start + timedelta(hours=2)
    )

    assert accepted.window_end - accepted.window_start == timedelta(hours=2)


def test_a_window_over_the_ceiling_is_still_rejected_with_no_database():
    start = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)

    with pytest.raises(ValidationError, match="must not exceed 4 hours"):
        WindowRequestIn(
            window_start=start, window_end=start + timedelta(hours=4, minutes=1)
        )
