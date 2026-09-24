"""Tests for the audit log query model (spec 003, R-1, R-5, R-6, R-8, A-2)."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from warden_server.schemas.audit import AuditFilter
from warden_server.schemas.report import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

START = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
END = START + timedelta(hours=1)


def test_a_valid_range_is_accepted_with_defaults():
    parsed = AuditFilter(start=START, end=END)

    assert parsed.actor is None
    assert parsed.action is None
    assert parsed.limit == DEFAULT_PAGE_SIZE
    assert parsed.offset == 0


def test_a_range_of_thirty_days_is_accepted():
    """The 4h cap governs agent requests, not reads of stored rows."""
    parsed = AuditFilter(start=START, end=START + timedelta(days=30))

    assert parsed.end - parsed.start == timedelta(days=30)


def test_an_end_equal_to_the_start_is_rejected():
    with pytest.raises(ValidationError, match="end must be after start"):
        AuditFilter(start=START, end=START)


def test_an_end_before_the_start_is_rejected():
    with pytest.raises(ValidationError, match="end must be after start"):
        AuditFilter(start=START, end=START - timedelta(minutes=1))


def test_naive_timestamps_are_treated_as_utc():
    parsed = AuditFilter(
        start=datetime(2026, 9, 1, 12, 0), end=datetime(2026, 9, 1, 13, 0)
    )

    assert parsed.start == START
    assert parsed.start.tzinfo is not None


def test_one_naive_and_one_aware_timestamp_do_not_raise_type_error():
    parsed = AuditFilter(start=datetime(2026, 9, 1, 12, 0), end=START + timedelta(1))

    assert parsed.end > parsed.start


def test_a_naive_start_after_an_aware_end_is_a_validation_error_not_a_type_error():
    with pytest.raises(ValidationError, match="end must be after start"):
        AuditFilter(start=datetime(2026, 9, 1, 12, 0), end=START - timedelta(hours=1))


def test_offset_timestamps_are_converted_to_utc():
    plus_three = timezone(timedelta(hours=3))

    parsed = AuditFilter(
        start=datetime(2026, 9, 1, 15, 0, tzinfo=plus_three),
        end=datetime(2026, 9, 1, 13, 0, tzinfo=UTC),
    )

    assert parsed.start == START
    assert parsed.start.utcoffset() == timedelta(0)


def test_a_limit_above_the_maximum_is_rejected():
    with pytest.raises(ValidationError):
        AuditFilter(start=START, end=END, limit=MAX_PAGE_SIZE + 1)


def test_a_zero_limit_and_a_negative_offset_are_rejected():
    with pytest.raises(ValidationError):
        AuditFilter(start=START, end=END, limit=0)
    with pytest.raises(ValidationError):
        AuditFilter(start=START, end=END, offset=-1)


def test_an_actor_is_parsed():
    parsed = AuditFilter(start=START, end=END, actor="admin")

    assert parsed.actor == "admin"


def test_an_empty_actor_is_rejected():
    with pytest.raises(ValidationError):
        AuditFilter(start=START, end=END, actor="")


def test_an_actor_longer_than_the_column_is_rejected():
    with pytest.raises(ValidationError):
        AuditFilter(start=START, end=END, actor="a" * 256)


@pytest.mark.parametrize(
    "action", ["operator", "operator.login", "enrollment_token.create"]
)
def test_an_action_or_a_group_is_accepted(action: str):
    parsed = AuditFilter(start=START, end=END, action=action)

    assert parsed.action == action


@pytest.mark.parametrize(
    "action",
    [
        "",
        "operator.%",
        "%",
        "operator login",
        "Operator.login",
        "operator\n",
        "a" * 65,
    ],
)
def test_an_action_outside_the_code_alphabet_is_rejected(action: str):
    """Only the characters action codes are made of get through, so a filter
    value can never carry a `%`. The underscore is part of the alphabet
    (`operator.login_failed`), so the query itself escapes it."""
    with pytest.raises(ValidationError):
        AuditFilter(start=START, end=END, action=action)
