"""Tests for operator password hashing (Argon2id)."""

from warden_server.security import hash_password, verify_password


def test_verify_password_accepts_the_original_password():
    password_hash = hash_password("correct-horse-battery-staple")

    assert verify_password("correct-horse-battery-staple", password_hash)


def test_verify_password_rejects_a_wrong_password():
    password_hash = hash_password("correct-horse-battery-staple")

    assert not verify_password("wrong-password", password_hash)


def test_hash_password_does_not_store_the_password_in_the_clear():
    password_hash = hash_password("correct-horse-battery-staple")

    assert "correct-horse-battery-staple" not in password_hash
