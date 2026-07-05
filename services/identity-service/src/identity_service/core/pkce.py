"""PKCE (RFC 7636) code_challenge verification and auth-code generation.

Only S256 is accepted — plain method is prohibited (SRS SEC-001).
"""

from __future__ import annotations

import hashlib
import re
import secrets
from base64 import urlsafe_b64encode

_VERIFIER_RE = re.compile(r"^[A-Za-z0-9\-._~]{43,128}$")


def generate_auth_code() -> str:
    """Cryptographically-secure single-use authorization code (32 bytes = 43 chars base64url)."""
    return secrets.token_urlsafe(32)


def validate_code_verifier(verifier: str) -> bool:
    """Return True if verifier satisfies RFC 7636 §4.1 character and length constraints."""
    return bool(_VERIFIER_RE.fullmatch(verifier))


def compute_code_challenge(verifier: str) -> str:
    """SHA-256 of verifier, base64url-encoded without padding (S256 method)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def verify_pkce(verifier: str, stored_challenge: str) -> bool:
    """Constant-time verification of PKCE S256 challenge.

    Returns False (not raises) on any mismatch — callers translate to OAuth2 error.
    """
    if not validate_code_verifier(verifier):
        return False
    computed = compute_code_challenge(verifier)
    return secrets.compare_digest(computed, stored_challenge)
