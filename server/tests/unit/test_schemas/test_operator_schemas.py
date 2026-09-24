"""Tests for the account-management request schemas (spec 005, R-13, A-5, A-6)."""

import pytest
from pydantic import ValidationError

from warden_server.models.operator import OperatorRole, OperatorStatus
from warden_server.schemas.auth import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH
from warden_server.schemas.operator import (
    OperatorCreateIn,
    OperatorPasswordResetIn,
    OperatorUpdateIn,
)

GOOD_PASSWORD = "a-long-enough-password"  # noqa: S105 -- test value, not a secret


def _create(**overrides):
    fields = {"username": "colleague", "role": "viewer", "password": GOOD_PASSWORD}
    return OperatorCreateIn(**{**fields, **overrides})


@pytest.mark.parametrize(
    "username",
    ["a", "a" * 64, "john.doe", "john_doe", "john-doe", "john@example", "9lives"],
)
def test_a_username_of_allowed_characters_is_accepted(username):
    assert _create(username=username).username == username


@pytest.mark.parametrize(
    "username",
    [
        "",
        "a" * 65,
        ".hidden",
        "-dash",
        "_under",
        "has space",
        "sl/ash",
        "имя",
        "new\nline",
        "tab\tbed",
    ],
)
def test_a_username_outside_the_allowed_set_is_rejected(username):
    with pytest.raises(ValidationError):
        _create(username=username)


def test_the_password_length_bounds_are_the_ones_the_password_change_uses():
    assert MIN_PASSWORD_LENGTH == 12

    assert _create(password="x" * MIN_PASSWORD_LENGTH)
    assert _create(password="x" * MAX_PASSWORD_LENGTH)
    with pytest.raises(ValidationError):
        _create(password="x" * (MIN_PASSWORD_LENGTH - 1))
    with pytest.raises(ValidationError):
        _create(password="x" * (MAX_PASSWORD_LENGTH + 1))


def test_a_role_outside_the_two_is_rejected():
    with pytest.raises(ValidationError):
        _create(role="root")


def test_both_roles_are_accepted():
    assert _create(role="admin").role is OperatorRole.ADMIN
    assert _create(role="viewer").role is OperatorRole.VIEWER


def test_a_role_is_required_at_creation():
    with pytest.raises(ValidationError):
        OperatorCreateIn(username="colleague", password=GOOD_PASSWORD)


def test_an_update_needs_at_least_one_field():
    with pytest.raises(ValidationError):
        OperatorUpdateIn()
    with pytest.raises(ValidationError):
        OperatorUpdateIn(role=None, status=None)


def test_an_update_may_carry_a_role_a_status_or_both():
    assert OperatorUpdateIn(role="admin").status is None
    assert OperatorUpdateIn(status="disabled").role is None
    both = OperatorUpdateIn(role="viewer", status="active")
    assert (both.role, both.status) == (OperatorRole.VIEWER, OperatorStatus.ACTIVE)


def test_an_update_rejects_any_other_field_including_a_password():
    with pytest.raises(ValidationError):
        OperatorUpdateIn(status="active", password=GOOD_PASSWORD)
    with pytest.raises(ValidationError):
        OperatorUpdateIn(status="active", username="someone-else")


def test_an_update_rejects_an_unknown_status():
    with pytest.raises(ValidationError):
        OperatorUpdateIn(status="deleted")


def test_a_password_reset_enforces_the_same_length_and_no_extra_fields():
    assert OperatorPasswordResetIn(new_password=GOOD_PASSWORD)
    with pytest.raises(ValidationError):
        OperatorPasswordResetIn(new_password="short")
    with pytest.raises(ValidationError):
        OperatorPasswordResetIn(new_password=GOOD_PASSWORD, role="admin")
