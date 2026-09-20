"""Tests for the password-change request schema (spec 002, R-6)."""

import pytest
from pydantic import ValidationError

from warden_server.schemas.auth import MIN_PASSWORD_LENGTH, PasswordChangeIn

CURRENT = "the-current-password"


def _new(length: int) -> str:
    return "n" * length


def test_the_minimum_length_is_twelve():
    assert MIN_PASSWORD_LENGTH == 12


def test_a_password_at_the_minimum_length_is_accepted():
    request = PasswordChangeIn(
        current_password=CURRENT, new_password=_new(MIN_PASSWORD_LENGTH)
    )

    assert len(request.new_password) == MIN_PASSWORD_LENGTH


def test_a_password_one_short_of_the_minimum_is_rejected():
    with pytest.raises(ValidationError, match="at least 12 characters"):
        PasswordChangeIn(
            current_password=CURRENT, new_password=_new(MIN_PASSWORD_LENGTH - 1)
        )


def test_a_password_over_the_length_cap_is_rejected():
    with pytest.raises(ValidationError):
        PasswordChangeIn(current_password=CURRENT, new_password=_new(1025))


def test_a_current_password_over_the_length_cap_is_rejected():
    with pytest.raises(ValidationError):
        PasswordChangeIn(current_password="c" * 1025, new_password=_new(20))


def test_a_new_password_equal_to_the_current_one_is_rejected():
    with pytest.raises(ValidationError, match="must differ from the current"):
        PasswordChangeIn(current_password=CURRENT, new_password=CURRENT)
