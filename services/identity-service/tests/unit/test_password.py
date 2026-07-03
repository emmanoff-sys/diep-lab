"""Unit tests — Argon2id password hashing (SRS SEC-001 / OWASP ASVS Level 2)."""

from __future__ import annotations

import pytest

from identity_service.core.password import hash_password, needs_rehash, verify_password


def test_hash_and_verify_roundtrip() -> None:
    pw = "Str0ng!P@ssword"
    hashed = hash_password(pw)
    assert verify_password(pw, hashed)


def test_wrong_password_rejected() -> None:
    hashed = hash_password("Correct!Horse1Battery")
    assert not verify_password("Wrong!Horse2Battery", hashed)


def test_different_hashes_for_same_password() -> None:
    pw = "Same!Pass1word"
    h1 = hash_password(pw)
    h2 = hash_password(pw)
    assert h1 != h2  # salts differ


def test_hash_is_argon2id() -> None:
    hashed = hash_password("Some!Passw0rd")
    assert hashed.startswith("$argon2id$")


def test_verify_rejects_garbage_hash() -> None:
    assert not verify_password("anypassword", "notahash")


def test_needs_rehash_fresh_hash() -> None:
    hashed = hash_password("Some!Passw0rd")
    assert not needs_rehash(hashed)


class TestPasswordComplexityValidation:
    """Covers the Pydantic validator in UserRegisterRequest."""

    def test_schema_rejects_no_uppercase(self) -> None:
        from identity_service.schemas.user import UserRegisterRequest
        import pytest

        with pytest.raises(Exception):
            UserRegisterRequest(
                email="a@b.com", username="user1", password="nouppercase1!"
            )

    def test_schema_rejects_no_digit(self) -> None:
        from identity_service.schemas.user import UserRegisterRequest

        with pytest.raises(Exception):
            UserRegisterRequest(
                email="a@b.com", username="user1", password="NoDigitHere!!"
            )

    def test_schema_accepts_strong_password(self) -> None:
        from identity_service.schemas.user import UserRegisterRequest

        req = UserRegisterRequest(
            email="a@b.com", username="user1", password="Str0ng!Password"
        )
        assert req.password == "Str0ng!Password"
