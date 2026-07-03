"""Unit tests — PKCE (RFC 7636) verification logic (SRS SEC-001)."""

from __future__ import annotations

import hashlib
from base64 import urlsafe_b64encode

import pytest

from identity_service.core.pkce import (
    compute_code_challenge,
    generate_auth_code,
    validate_code_verifier,
    verify_pkce,
)


def _make_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return urlsafe_b64encode(digest).rstrip(b"=").decode()


class TestValidateCodeVerifier:
    def test_valid_verifier(self) -> None:
        verifier = "a" * 43
        assert validate_code_verifier(verifier)

    def test_valid_max_length(self) -> None:
        verifier = "a" * 128
        assert validate_code_verifier(verifier)

    def test_too_short(self) -> None:
        assert not validate_code_verifier("a" * 42)

    def test_too_long(self) -> None:
        assert not validate_code_verifier("a" * 129)

    def test_invalid_chars(self) -> None:
        assert not validate_code_verifier("a" * 42 + "@")  # '@' is not allowed

    def test_allowed_special_chars(self) -> None:
        verifier = "a" * 39 + "-._~"
        assert validate_code_verifier(verifier)


class TestVerifyPKCE:
    def test_correct_verifier(self) -> None:
        verifier = "x" * 43
        challenge = _make_challenge(verifier)
        assert verify_pkce(verifier, challenge)

    def test_wrong_verifier(self) -> None:
        verifier = "x" * 43
        challenge = _make_challenge("y" * 43)
        assert not verify_pkce(verifier, challenge)

    def test_invalid_verifier_length(self) -> None:
        assert not verify_pkce("short", _make_challenge("short"))

    def test_compute_challenge_matches_verify(self) -> None:
        verifier = "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789-._~AbCd"
        challenge = compute_code_challenge(verifier)
        assert verify_pkce(verifier, challenge)


class TestGenerateAuthCode:
    def test_length(self) -> None:
        code = generate_auth_code()
        assert len(code) >= 43

    def test_uniqueness(self) -> None:
        codes = {generate_auth_code() for _ in range(100)}
        assert len(codes) == 100
