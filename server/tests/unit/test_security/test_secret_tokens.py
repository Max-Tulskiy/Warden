"""Tests for high-entropy secret tokens (enrollment tokens, agent keys)."""

from warden_server.security import (
    generate_secret_token,
    hash_secret_token,
    verify_secret_token,
)


def test_generate_secret_token_produces_distinct_values():
    assert generate_secret_token() != generate_secret_token()


def test_verify_secret_token_accepts_the_original_token():
    token = generate_secret_token()

    assert verify_secret_token(token, hash_secret_token(token))


def test_verify_secret_token_rejects_a_wrong_token():
    token = generate_secret_token()
    other_hash = hash_secret_token(generate_secret_token())

    assert not verify_secret_token(token, other_hash)


def test_hash_secret_token_is_deterministic():
    token = generate_secret_token()

    assert hash_secret_token(token) == hash_secret_token(token)
