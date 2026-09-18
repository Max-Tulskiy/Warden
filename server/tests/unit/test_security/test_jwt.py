"""Tests for operator JWT issuance and verification."""

from warden_server.security import create_access_token, decode_access_token


def test_decode_access_token_returns_the_original_subject():
    token = create_access_token("admin")

    assert decode_access_token(token) == "admin"


def test_decode_access_token_rejects_a_garbage_token():
    assert decode_access_token("not-a-real-token") is None
