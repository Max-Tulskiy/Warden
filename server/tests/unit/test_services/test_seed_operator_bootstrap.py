"""Tests for the idempotent first-run operator bootstrap."""

from warden_server.models.operator import Operator, OperatorRole, OperatorStatus
from warden_server.security import hash_password, verify_password
from warden_server.services.bootstrap import ensure_seed_operator


def test_creates_an_operator_when_none_exists(db_session):
    ensure_seed_operator(db_session, username="admin", password="s3cret")
    db_session.commit()

    operator = db_session.query(Operator).one()
    assert operator.username == "admin"
    assert verify_password("s3cret", operator.password_hash)


def test_the_seed_operator_is_an_active_administrator(db_session):
    ensure_seed_operator(db_session, username="admin", password="s3cret")
    db_session.commit()

    operator = db_session.query(Operator).one()
    assert operator.role is OperatorRole.ADMIN
    assert operator.status is OperatorStatus.ACTIVE


def test_does_nothing_when_an_operator_already_exists(db_session):
    db_session.add(
        Operator(
            username="existing",
            password_hash=hash_password("orig"),
            role=OperatorRole.VIEWER,
        )
    )
    db_session.commit()

    ensure_seed_operator(db_session, username="admin", password="s3cret")
    db_session.commit()

    usernames = {op.username for op in db_session.query(Operator).all()}
    assert usernames == {"existing"}
