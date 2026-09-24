"""Integration: a session is valid only for its operator's current version.

Spec 004, R-4, A-6, A-11. The operator's version is changed straight in the
database here, so the check itself is tested apart from the operations that
change it (see `test_revocation.py`).
"""

import time
from typing import Any

import jwt
import pytest

from warden_server.config import get_settings

PANEL_READ = "/api/v1/agents"


def _forge(subject: str, **claims: Any) -> dict[str, str]:
    """Auth headers carrying a correctly signed token with chosen claims."""
    settings = get_settings()
    payload = {"sub": subject, "exp": int(time.time()) + 600, **claims}
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return {"Authorization": f"Bearer {token}"}


def _set_version(db_session, operator, version: int) -> None:
    operator.token_version = version
    db_session.commit()


def test_a_token_from_a_real_login_works(client, auth_headers):
    assert client.get(PANEL_READ, headers=auth_headers).status_code == 200


def test_a_new_operator_starts_at_version_zero(operator):
    assert operator.token_version == 0


def test_raising_the_version_ends_a_session_but_not_a_new_login(
    client, auth_headers, db_session, operator, operator_password
):
    _set_version(db_session, operator, operator.token_version + 1)

    assert client.get(PANEL_READ, headers=auth_headers).status_code == 401

    fresh = client.post(
        "/api/v1/auth/login",
        json={"username": operator.username, "password": operator_password},
    )
    assert fresh.status_code == 200
    headers = {"Authorization": f"Bearer {fresh.json()['access_token']}"}
    assert client.get(PANEL_READ, headers=headers).status_code == 200


def test_only_the_exact_version_is_accepted(client, db_session, operator):
    _set_version(db_session, operator, 5)

    assert client.get(PANEL_READ, headers=_forge("admin", ver=5)).status_code == 200
    assert client.get(PANEL_READ, headers=_forge("admin", ver=4)).status_code == 401
    assert client.get(PANEL_READ, headers=_forge("admin", ver=6)).status_code == 401


def test_a_token_with_no_version_is_refused(client, operator):
    """A session issued before versions existed is refused once."""
    assert client.get(PANEL_READ, headers=_forge("admin")).status_code == 401


@pytest.mark.parametrize("version", ["0", 0.0, True, None])
def test_a_token_whose_version_is_not_an_integer_is_refused(client, operator, version):
    assert (
        client.get(PANEL_READ, headers=_forge("admin", ver=version)).status_code == 401
    )


def test_a_signed_token_for_an_unknown_operator_is_refused(client, operator):
    assert client.get(PANEL_READ, headers=_forge("nobody", ver=0)).status_code == 401


def test_no_token_and_a_garbage_token_are_refused(client, operator):
    assert client.get(PANEL_READ).status_code == 401
    assert (
        client.get(PANEL_READ, headers={"Authorization": "Bearer x.y.z"}).status_code
        == 401
    )


def test_the_refusal_is_the_same_response_as_for_an_invalid_token(
    client, auth_headers, db_session, operator
):
    """An ended session must not be distinguishable from an invalid one."""
    _set_version(db_session, operator, 1)

    ended = client.get(PANEL_READ, headers=auth_headers)
    invalid = client.get(PANEL_READ, headers={"Authorization": "Bearer x.y.z"})

    assert ended.status_code == invalid.status_code == 401
    assert ended.json() == invalid.json()
