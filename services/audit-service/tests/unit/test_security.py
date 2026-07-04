"""Unit tests: JWT validation and JWKS cache (ENG-SPEC-005-04 §26.1 / §5).

Uses mock JWKS responses — no real identity-service required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from audit_service.core.exceptions import TokenValidationError
from audit_service.core.security import JWKSCache, _decode


class TestJWKSCache:
    @pytest.mark.asyncio
    async def test_cache_returns_keys_after_refresh(self) -> None:
        cache = JWKSCache("http://test/jwks", ttl_seconds=300)
        mock_keys = [{"kty": "RSA", "kid": "test-key-1"}]

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {"keys": mock_keys}
            mock_client_cls.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_resp
            )
            keys = await cache.get_keys()

        assert keys == mock_keys

    @pytest.mark.asyncio
    async def test_cache_does_not_refetch_within_ttl(self) -> None:
        cache = JWKSCache("http://test/jwks", ttl_seconds=300)
        mock_keys = [{"kty": "RSA", "kid": "k1"}]

        fetch_count = 0

        async def mock_get(*args: object, **kwargs: object) -> MagicMock:
            nonlocal fetch_count
            fetch_count += 1
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"keys": mock_keys}
            return resp

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__.return_value.get = mock_get
            await cache.get_keys()  # first fetch
            await cache.get_keys()  # should hit cache

        assert fetch_count == 1

    @pytest.mark.asyncio
    async def test_stale_threshold_reported_correctly(self) -> None:
        cache = JWKSCache("http://test/jwks", ttl_seconds=300)
        # Never fetched — should be inf
        assert cache.last_fetch_age_seconds == float("inf")


class TestTokenDecode:
    @pytest.mark.asyncio
    async def test_hs256_token_rejected_before_key_lookup(self) -> None:
        import base64
        import hashlib
        import hmac
        import json

        header = (
            base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
            .rstrip(b"=")
            .decode()
        )
        payload_b64 = (
            base64.urlsafe_b64encode(json.dumps({"sub": str(uuid4()), "aud": "reos"}).encode())
            .rstrip(b"=")
            .decode()
        )
        sig = (
            base64.urlsafe_b64encode(
                hmac.new(b"secret", f"{header}.{payload_b64}".encode(), hashlib.sha256).digest()
            )
            .rstrip(b"=")
            .decode()
        )
        hs256_token = f"{header}.{payload_b64}.{sig}"

        with pytest.raises(TokenValidationError, match="RS256"):
            await _decode(hs256_token, "reos")

    @pytest.mark.asyncio
    async def test_no_keys_raises_token_validation_error(self) -> None:
        with patch(
            "audit_service.core.security.jwks_cache.get_keys",
            new_callable=AsyncMock,
            return_value=[],
        ):
            # Build a minimal RS256 header token (will fail validation but check error type)
            import base64
            import json as _json

            header = (
                base64.urlsafe_b64encode(_json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
                .rstrip(b"=")
                .decode()
            )
            fake_token = f"{header}.e30.sig"
            with pytest.raises(TokenValidationError):
                await _decode(fake_token, "reos")
