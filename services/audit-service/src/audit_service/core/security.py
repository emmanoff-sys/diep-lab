"""JWKS-backed JWT validation for the audit service (ENG-SPEC-005-04 §5, §12.3).

- JWKS fetched from identity-service /api/v1/jwks; cached JWKS_CACHE_TTL_SECONDS (default 300 s)
- RS256 only — HS256 tokens raise TokenValidationError with clear message
- Write API requires aud=reos-internal; Query/Verify API requires aud=reos
- Prometheus counters: audit_jwks_cache_hits_total, audit_jwks_cache_misses_total
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import structlog
from audit_service.config import settings
from audit_service.core.exceptions import JWKSFetchError, TokenValidationError
from jose import JWTError, jwt
from prometheus_client import Counter

logger = structlog.get_logger(__name__)

_cache_hits = Counter("audit_jwks_cache_hits_total", "JWKS cache hits")
_cache_misses = Counter("audit_jwks_cache_misses_total", "JWKS cache misses (refetches)")


class JWKSCache:
    """Thread-safe async JWKS cache with configurable TTL."""

    def __init__(self, jwks_url: str, ttl_seconds: int) -> None:
        self._url = jwks_url
        self._ttl = ttl_seconds
        self._keys: list[dict[str, Any]] = []
        self._last_fetch: float = 0.0
        self._lock: asyncio.Lock = asyncio.Lock()

    @property
    def last_fetch_age_seconds(self) -> float:
        return time.monotonic() - self._last_fetch if self._last_fetch else float("inf")

    async def get_keys(self) -> list[dict[str, Any]]:
        if self._cache_is_fresh():
            _cache_hits.inc()
            return self._keys
        async with self._lock:
            if self._cache_is_fresh():
                _cache_hits.inc()
                return self._keys
            await self._refresh()
        _cache_misses.inc()
        return self._keys

    def _cache_is_fresh(self) -> bool:
        return bool(self._keys) and (time.monotonic() - self._last_fetch) < self._ttl

    async def _refresh(self) -> None:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(self._url)
                resp.raise_for_status()
                data: dict[str, Any] = resp.json()
        except Exception as exc:
            raise JWKSFetchError(f"JWKS fetch from {self._url} failed: {exc}") from exc

        keys = data.get("keys")
        if not isinstance(keys, list) or not keys:
            raise JWKSFetchError(f"JWKS response missing 'keys' array: {data}")

        self._keys = keys
        self._last_fetch = time.monotonic()
        logger.info("audit.jwks_cache_refreshed", url=self._url, key_count=len(keys))


jwks_cache = JWKSCache(
    jwks_url=settings.JWKS_URL,
    ttl_seconds=settings.JWKS_CACHE_TTL_SECONDS,
)


async def decode_service_token(raw_token: str) -> dict[str, Any]:
    """Validate RS256 token and assert aud=reos-internal (Write API)."""
    return await _decode(raw_token, settings.JWT_AUDIENCE_INTERNAL)


async def decode_user_token(raw_token: str) -> dict[str, Any]:
    """Validate RS256 token and assert aud=reos (Query/Verify API)."""
    return await _decode(raw_token, settings.JWT_AUDIENCE_USER)


async def _decode(raw_token: str, required_audience: str) -> dict[str, Any]:
    # Reject HS256 before touching keys — alg header check
    try:
        unverified_header = jwt.get_unverified_header(raw_token)
    except JWTError as exc:
        raise TokenValidationError(f"Malformed JWT header: {exc}") from exc

    if unverified_header.get("alg", "").upper() != "RS256":
        raise TokenValidationError(
            f"Only RS256 tokens accepted; got alg={unverified_header.get('alg')}"
        )

    keys = await jwks_cache.get_keys()
    last_exc: Exception = TokenValidationError("No JWKS keys available")

    for key in keys:
        try:
            payload: dict[str, Any] = jwt.decode(
                raw_token,
                key,
                algorithms=["RS256"],
                audience=required_audience,
            )
            return payload
        except JWTError as exc:
            last_exc = exc
            continue

    raise TokenValidationError(str(last_exc)) from last_exc
