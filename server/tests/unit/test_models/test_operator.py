"""Tests for the operator model's role and status (spec 005, R-1, R-14)."""

import pytest
from sqlalchemy.exc import IntegrityError

from warden_server.models.operator import Operator, OperatorRole, OperatorStatus


def test_the_roles_are_exactly_administrator_and_observer():
    assert {role.value for role in OperatorRole} == {"admin", "viewer"}


def test_the_statuses_are_exactly_active_and_disabled():
    assert {status.value for status in OperatorStatus} == {"active", "disabled"}


def test_an_operator_cannot_be_stored_without_a_role(db_session):
    """No default: creating an account without saying what it may do is an
    error, never a silent administrator."""
    db_session.add(Operator(username="nobody", password_hash="x"))

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_a_new_operator_is_active_unless_said_otherwise(db_session):
    operator = Operator(username="new", password_hash="x", role=OperatorRole.VIEWER)
    db_session.add(operator)
    db_session.commit()

    db_session.refresh(operator)
    assert operator.status is OperatorStatus.ACTIVE


@pytest.mark.parametrize("role", list(OperatorRole))
@pytest.mark.parametrize("status", list(OperatorStatus))
def test_a_stored_role_and_status_read_back_as_the_enum_members(
    db_session, role, status
):
    operator = Operator(username="rt", password_hash="x", role=role, status=status)
    db_session.add(operator)
    db_session.commit()

    db_session.expire_all()
    stored = db_session.get(Operator, operator.id)
    assert stored.role is role
    assert stored.status is status
