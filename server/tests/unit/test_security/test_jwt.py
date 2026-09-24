"""Tests for operator JWT issuance and verification (spec 004)."""

import time
from typing import Any

import jwt
import pytest

from warden_server.config import get_settings
from warden_server.security import (
    TokenClaims,
    create_access_token,
    decode_access_token,
)


def _forge(payload: dict[str, Any]) -> str:
    """A correctly signed token with claims chosen by the test."""
    settings = get_settings()
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _exp() -> int:
    return int(time.time()) + 600


def test_decode_access_token_returns_the_subject_and_the_version():
    token = create_access_token("admin", 3)

    assert decode_access_token(token) == TokenClaims(subject="admin", version=3)


def test_the_version_zero_round_trips():
    assert decode_access_token(create_access_token("admin", 0)) == TokenClaims(
        "admin", 0
    )


def test_decode_access_token_rejects_a_garbage_token():
    assert decode_access_token("not-a-real-token") is None


def test_a_token_with_no_version_is_rejected():
    """A session issued before versions existed carries no `ver`."""
    assert decode_access_token(_forge({"sub": "admin", "exp": _exp()})) is None


@pytest.mark.parametrize("version", ["1", 1.0, 1.5, True, False, None, [1]])
def test_a_version_that_is_not_an_integer_is_rejected(version: Any):
    token = _forge({"sub": "admin", "ver": version, "exp": _exp()})

    assert decode_access_token(token) is None


@pytest.mark.parametrize("subject", [None, 7, ["admin"]])
def test_a_subject_that_is_not_a_string_is_rejected(subject: Any):
    token = _forge({"sub": subject, "ver": 0, "exp": _exp()})

    assert decode_access_token(token) is None


def test_an_expired_token_is_rejected():
    token = _forge({"sub": "admin", "ver": 0, "exp": int(time.time()) - 10})

    assert decode_access_token(token) is None


def test_a_token_signed_with_another_secret_is_rejected():
    token = jwt.encode(
        {"sub": "admin", "ver": 0, "exp": _exp()},
        "some-other-secret-of-sufficient-length-32b",
        algorithm=get_settings().jwt_algorithm,
    )

    assert decode_access_token(token) is None


def test_the_version_does_not_change_how_long_a_token_lasts():
    """Ending sessions must not alter the session lifetime (R-9)."""
    settings = get_settings()
    expected = time.time() + settings.jwt_expire_minutes * 60

    for version in (0, 7):
        payload = jwt.decode(
            create_access_token("admin", version),
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        assert abs(payload["exp"] - expected) < 5
