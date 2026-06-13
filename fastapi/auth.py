"""DIEP API authentication & authorization (Phase 9J).

Self-contained, dependency-free security layer for the FastAPI app:
  - HS256 JWT (stdlib hmac/hashlib/base64 — no PyJWT) for user sessions;
  - hashed API keys for machine clients and the portal BFF;
  - roles: viewer < operator < admin, plus `service` for machine ingest;
  - FastAPI dependencies require_role(...) and rate_limit(...);
  - audit() — append-only audit_events rows for state-changing actions.

Secrets come from environment variables with **lab defaults** so the stack runs
out of the box; production MUST override them (see .env.example) and rotate.
Enforcement is gated by DIEP_AUTH_ENFORCED (default on) so it can be staged.
"""
from __future__ import annotations

import os
import json
import time
import hmac
import base64
import hashlib
import logging

import redis
import psycopg2
from fastapi import Request, HTTPException

logger = logging.getLogger("diep-auth")

AUTH_ENFORCED = os.getenv("DIEP_AUTH_ENFORCED", "1") == "1"
JWT_SECRET = os.getenv("DIEP_JWT_SECRET", "diep-dev-jwt-secret-CHANGE-ME")
JWT_TTL = int(os.getenv("DIEP_JWT_TTL", "3600"))            # short-lived access token
REFRESH_TTL = int(os.getenv("DIEP_REFRESH_TTL", str(30 * 24 * 3600)))  # 30d refresh (mobile)

# --- API keys: token -> (principal_name, role). Lab defaults; override via env. ---
API_KEYS = {
    os.getenv("DIEP_SERVICE_TOKEN", "diep-service-dev-token-CHANGE-ME"): ("svc-machine", "service"),
    os.getenv("DIEP_OPERATOR_KEY", "diep-operator-dev-key-CHANGE-ME"): ("api-operator", "operator"),
    os.getenv("DIEP_ADMIN_KEY", "diep-admin-dev-key-CHANGE-ME"): ("api-admin", "admin"),
}

# --- Users for JWT issuance (username -> (password, role, tenant)). Lab defaults. ---
# tenant=None  => global (sees all tenants); a tenant id scopes the principal.
USERS = {
    os.getenv("DIEP_ADMIN_USER", "admin"):
        (os.getenv("DIEP_ADMIN_PASSWORD", "diep-admin-2026"), "admin", None),
    "operator": (os.getenv("DIEP_OPERATOR_PASSWORD", "diep-operator-2026"), "operator", "default"),
    "viewer": (os.getenv("DIEP_VIEWER_PASSWORD", "diep-viewer-2026"), "viewer", "default"),
    # Phase 12 — per-tenant operator logins (multi-tenancy demo).
    "acme-op": (os.getenv("DIEP_ACME_PASSWORD", "acme-2026"), "operator", "acme"),
    "globex-op": (os.getenv("DIEP_GLOBEX_PASSWORD", "globex-2026"), "operator", "globex"),
}

_DB = {
    "host": os.getenv("DB_HOST", "diep-timescaledb"),
    "database": os.getenv("DB_NAME", "diep"),
    "user": os.getenv("DB_USER", "diep"),
    "password": os.getenv("DB_PASSWORD", "diep123"),
}
_REDIS = redis.Redis(host=os.getenv("REDIS_HOST", "diep-redis"), port=6379,
                      password=os.getenv("REDIS_PASSWORD") or None, decode_responses=True)


# --- JWT (HS256, stdlib) ---------------------------------------------------
def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _b64u_dec(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue_jwt(sub: str, role: str, ttl: int = JWT_TTL, token_use: str = "access",
              tenant: str | None = None) -> str:
    now = int(time.time())
    header = _b64u(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64u(json.dumps(
        {"sub": sub, "role": role, "tenant": tenant, "use": token_use,
         "iat": now, "exp": now + ttl}).encode())
    signing_input = f"{header}.{payload}"
    sig = hmac.new(JWT_SECRET.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64u(sig)}"


def issue_refresh(sub: str, role: str, tenant: str | None = None) -> str:
    """Long-lived refresh token (mobile). Exchanged at /auth/refresh for access tokens."""
    return issue_jwt(sub, role, ttl=REFRESH_TTL, token_use="refresh", tenant=tenant)


def verify_jwt(token: str):
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
        signing_input = f"{header_b64}.{payload_b64}"
        expected = hmac.new(JWT_SECRET.encode(), signing_input.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64u(expected), sig_b64):
            return None
        payload = json.loads(_b64u_dec(payload_b64))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:  # noqa: BLE001 — any malformed token is simply unauthenticated
        return None


def authenticate_user(username: str, password: str):
    entry = USERS.get(username)
    if entry and hmac.compare_digest(entry[0], password):
        return entry[1], entry[2]  # (role, tenant)
    return None


# --- principal + role checks ----------------------------------------------
class Principal:
    def __init__(self, name: str, role: str, kind: str, source_ip: str | None = None,
                 tenant: str | None = None):
        self.name = name
        self.role = role
        self.kind = kind
        self.source_ip = source_ip
        self.tenant = tenant  # None => global (sees all tenants); else scoped

    @property
    def is_global(self) -> bool:
        return self.tenant is None

    def __repr__(self):
        return f"Principal({self.name}, role={self.role}, tenant={self.tenant}, kind={self.kind})"


def _role_allowed(role: str, allowed: tuple) -> bool:
    if role == "admin":
        return True                       # admin is superuser
    if role == "service":
        return "service" in allowed       # machine ingest only
    if role == "operator":
        return "operator" in allowed or "viewer" in allowed
    if role == "viewer":
        return "viewer" in allowed
    return False


def _principal_from_request(request: Request) -> Principal | None:
    ip = request.client.host if request.client else None
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else None
    api_key = request.headers.get("x-api-key") or (token if token in API_KEYS else None)
    if api_key and api_key in API_KEYS:
        name, role = API_KEYS[api_key]
        return Principal(name, role, "apikey", ip, tenant=None)  # API keys are global
    if token:
        payload = verify_jwt(token)
        # Refresh tokens cannot authorize API calls — only access tokens.
        if payload and payload.get("use", "access") == "access":
            return Principal(payload["sub"], payload["role"], "jwt", ip,
                             tenant=payload.get("tenant"))
    return None


def require_role(*allowed: str):
    """FastAPI dependency: authenticate + authorize. Returns the Principal."""
    def _dep(request: Request) -> Principal:
        if not AUTH_ENFORCED:
            return Principal("auth-disabled", "admin", "disabled",
                             request.client.host if request.client else None)
        principal = _principal_from_request(request)
        if principal is None:
            raise HTTPException(status_code=401, detail="authentication required",
                                headers={"WWW-Authenticate": "Bearer"})
        if not _role_allowed(principal.role, allowed):
            raise HTTPException(status_code=403,
                                detail=f"role '{principal.role}' not permitted; need one of {list(allowed)}")
        return principal
    return _dep


def rate_limit(bucket: str, limit: int = 60, window: int = 60):
    """FastAPI dependency: fixed-window Redis rate limit, keyed by principal/IP."""
    def _dep(request: Request) -> None:
        principal = _principal_from_request(request)
        ident = principal.name if principal else (request.client.host if request.client else "anon")
        key = f"ratelimit:{bucket}:{ident}:{int(time.time() // window)}"
        try:
            count = _REDIS.incr(key)
            if count == 1:
                _REDIS.expire(key, window)
        except redis.RedisError:
            return  # fail-open on limiter outage rather than block actuation
        if count > limit:
            raise HTTPException(status_code=429,
                                detail=f"rate limit exceeded ({limit}/{window}s for '{bucket}')")
    return _dep


# --- audit -----------------------------------------------------------------
def audit(principal: Principal | None, action: str, resource: str, result: str,
          detail: dict | None = None) -> None:
    """Append an audit_events row. Best-effort: never fail the request."""
    who = principal.name if principal else "anonymous"
    role = principal.role if principal else None
    ip = principal.source_ip if principal else None
    try:
        conn = psycopg2.connect(**_DB)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO audit_events (principal, role, action, resource, source_ip, result, detail) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (who, role, action, resource, ip, result, json.dumps(detail or {})),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("audit write failed for %s/%s: %s", action, resource, exc)
