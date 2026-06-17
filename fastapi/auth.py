"""DIEP API authentication & authorization (Phase 9J, extended Phase 21).

Self-contained, dependency-free security layer for the FastAPI app:
  - HS256 JWT (stdlib hmac/hashlib/base64 — no PyJWT) for user sessions;
  - hashed API keys for machine clients and the portal BFF;
  - roles: viewer < operator < engineer < admin, plus `service` for machine ingest;
  - FastAPI dependencies require_role(...) and rate_limit(...);
  - audit() — append-only audit_events rows for state-changing actions, with
    automatic request-correlation via RequestIDMiddleware;
  - a DB-backed, runtime-mutable user store (portal_users) layered under the
    same USERS env defaults, enabling real logout (JWT revocation) and a
    password-reset workflow (Phase 21).

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
import secrets
import uuid
import contextvars

import redis
import psycopg2
import psycopg2.extras
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("diep-auth")

AUTH_ENFORCED = os.getenv("DIEP_AUTH_ENFORCED", "1") == "1"
JWT_SECRET = os.getenv("DIEP_JWT_SECRET", "diep-dev-jwt-secret-CHANGE-ME")
JWT_TTL = int(os.getenv("DIEP_JWT_TTL", "3600"))            # short-lived access token
REFRESH_TTL = int(os.getenv("DIEP_REFRESH_TTL", str(30 * 24 * 3600)))  # 30d refresh (mobile)
RESET_TTL = int(os.getenv("DIEP_PASSWORD_RESET_TTL", "900"))  # 15 minutes

# --- API keys: token -> (principal_name, role). Lab defaults; override via env. ---
API_KEYS = {
    os.getenv("DIEP_SERVICE_TOKEN", "diep-service-dev-token-CHANGE-ME"): ("svc-machine", "service"),
    os.getenv("DIEP_OPERATOR_KEY", "diep-operator-dev-key-CHANGE-ME"): ("api-operator", "operator"),
    os.getenv("DIEP_ADMIN_KEY", "diep-admin-dev-key-CHANGE-ME"): ("api-admin", "admin"),
}

# --- Bootstrap users for JWT issuance (username -> (password, role, tenant)).
# Lab defaults; these seed the DB-backed `portal_users` table on first use
# (see _ensure_users_seeded) so passwords become runtime-mutable afterward.
# tenant=None  => global (sees all tenants); a tenant id scopes the principal.
USERS = {
    os.getenv("DIEP_ADMIN_USER", "admin"):
        (os.getenv("DIEP_ADMIN_PASSWORD", "diep-admin-2026"), "admin", None),
    "operator": (os.getenv("DIEP_OPERATOR_PASSWORD", "diep-operator-2026"), "operator", "default"),
    "engineer": (os.getenv("DIEP_ENGINEER_PASSWORD", "diep-engineer-2026"), "engineer", "default"),
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

# Per-request correlation id, set by RequestIDMiddleware, read by audit().
_request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "diep_request_id", default=None)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Stamps every request/response with X-Request-ID and makes it available
    to audit() via a contextvar, without changing any existing route signature."""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        token = _request_id_ctx.set(rid)
        try:
            response = await call_next(request)
        finally:
            _request_id_ctx.reset(token)
        response.headers["X-Request-ID"] = rid
        return response


def _db():
    return psycopg2.connect(**_DB)


# --- password hashing (PBKDF2-HMAC-SHA256, stdlib — no new dependency) -----
_PBKDF2_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${_b64u(salt)}${_b64u(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt_b64, digest_b64 = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        salt = _b64u_dec(salt_b64)
        expected = _b64u_dec(digest_b64)
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations))
        return hmac.compare_digest(candidate, expected)
    except Exception:  # noqa: BLE001 — any malformed hash is simply a non-match
        return False


# --- DB-backed user store, seeded from USERS on first use ------------------
def _ensure_users_seeded() -> None:
    conn = _db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM portal_users")
        if cur.fetchone()[0] == 0:
            for username, (password, role, tenant) in USERS.items():
                cur.execute(
                    "INSERT INTO portal_users (username, password_hash, role, tenant) "
                    "VALUES (%s, %s, %s, %s) ON CONFLICT (username) DO NOTHING",
                    (username, hash_password(password), role, tenant),
                )
            conn.commit()
        cur.close()
    finally:
        conn.close()


def _user_row(username: str) -> dict | None:
    conn = _db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT username, password_hash, role, tenant, token_version, "
            "must_change_password FROM portal_users WHERE username = %s",
            (username,),
        )
        row = cur.fetchone()
        cur.close()
        return dict(row) if row else None
    finally:
        conn.close()


def authenticate_user(username: str, password: str):
    """Returns (role, tenant, token_version) on success, else None."""
    _ensure_users_seeded()
    row = _user_row(username)
    if row and verify_password(password, row["password_hash"]):
        return row["role"], row["tenant"], row["token_version"]
    return None


def create_user(username: str, password: str, role: str, tenant: str | None) -> None:
    if role not in ("viewer", "operator", "engineer", "admin"):
        raise ValueError(f"invalid role '{role}'")
    _ensure_users_seeded()
    conn = _db()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO portal_users (username, password_hash, role, tenant) VALUES (%s, %s, %s, %s)",
            (username, hash_password(password), role, tenant),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()


def list_users() -> list[dict]:
    _ensure_users_seeded()
    conn = _db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT username, role, tenant, must_change_password, created_at, updated_at "
            "FROM portal_users ORDER BY username"
        )
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
        for r in rows:
            for k in ("created_at", "updated_at"):
                if r.get(k) is not None:
                    r[k] = r[k].isoformat()
        return rows
    finally:
        conn.close()


def delete_user(username: str) -> None:
    conn = _db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT role FROM portal_users WHERE username = %s", (username,))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"unknown user '{username}'")
        if row[0] == "admin":
            cur.execute("SELECT count(*) FROM portal_users WHERE role = 'admin'")
            if cur.fetchone()[0] <= 1:
                raise HTTPException(status_code=409, detail="cannot remove the last remaining admin")
        cur.execute("DELETE FROM portal_users WHERE username = %s", (username,))
        conn.commit()
        cur.close()
    finally:
        conn.close()


def _bump_token_version(username: str, new_version: int) -> None:
    """Persist + cache the new token_version so verify_jwt() can invalidate
    outstanding tokens for this user immediately (password reset / logout-all)."""
    try:
        _REDIS.set(f"tokenversion:{username}", new_version)
    except redis.RedisError:
        logger.warning("could not cache token_version for %s (Redis unavailable)", username)


# --- password reset ----------------------------------------------------------
def request_password_reset(username: str) -> str | None:
    """Issues a short-lived, single-purpose reset token. Returns None if the
    username doesn't exist (caller should still respond generically to avoid
    username enumeration)."""
    _ensure_users_seeded()
    row = _user_row(username)
    if row is None:
        return None
    return issue_jwt(username, row["role"], ttl=RESET_TTL, token_use="pwreset",
                     tenant=row["tenant"], token_version=row["token_version"])


def confirm_password_reset(token: str, new_password: str) -> bool:
    payload = verify_jwt(token, expected_use="pwreset")
    if payload is None:
        return False
    username = payload["sub"]
    conn = _db()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE portal_users SET password_hash = %s, token_version = token_version + 1, "
            "must_change_password = false, updated_at = now() WHERE username = %s "
            "RETURNING token_version",
            (hash_password(new_password), username),
        )
        row = cur.fetchone()
        conn.commit()
        cur.close()
    finally:
        conn.close()
    if row is None:
        return False
    _bump_token_version(username, row[0])
    return True


# --- JWT (HS256, stdlib) ---------------------------------------------------
def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _b64u_dec(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue_jwt(sub: str, role: str, ttl: int = JWT_TTL, token_use: str = "access",
              tenant: str | None = None, token_version: int = 0) -> str:
    now = int(time.time())
    jti = uuid.uuid4().hex
    header = _b64u(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64u(json.dumps(
        {"sub": sub, "role": role, "tenant": tenant, "use": token_use,
         "tv": token_version, "jti": jti, "iat": now, "exp": now + ttl}).encode())
    signing_input = f"{header}.{payload}"
    sig = hmac.new(JWT_SECRET.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64u(sig)}"


def issue_refresh(sub: str, role: str, tenant: str | None = None, token_version: int = 0) -> str:
    """Long-lived refresh token (mobile). Exchanged at /auth/refresh for access tokens."""
    return issue_jwt(sub, role, ttl=REFRESH_TTL, token_use="refresh", tenant=tenant,
                     token_version=token_version)


def verify_jwt(token: str, expected_use: str | None = None):
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
        signing_input = f"{header_b64}.{payload_b64}"
        expected = hmac.new(JWT_SECRET.encode(), signing_input.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64u(expected), sig_b64):
            return None
        payload = json.loads(_b64u_dec(payload_b64))
        if payload.get("exp", 0) < time.time():
            return None
        if expected_use is not None and payload.get("use") != expected_use:
            return None
        jti = payload.get("jti")
        if jti:
            try:
                if _REDIS.exists(f"revoked:{jti}"):
                    return None
            except redis.RedisError:
                pass  # fail-open on limiter/cache outage rather than block all auth
        try:
            current_tv = _REDIS.get(f"tokenversion:{payload.get('sub')}")
            if current_tv is not None and int(current_tv) != payload.get("tv", 0):
                return None
        except redis.RedisError:
            pass
        return payload
    except Exception:  # noqa: BLE001 — any malformed token is simply unauthenticated
        return None


def revoke_token(token: str) -> bool:
    """Revokes a single token's jti (logout). Returns True if it was a valid,
    not-already-expired token."""
    payload = verify_jwt(token)
    if payload is None:
        return False
    jti = payload.get("jti")
    exp = payload.get("exp", 0)
    remaining = max(int(exp - time.time()), 1)
    try:
        _REDIS.setex(f"revoked:{jti}", remaining, "1")
    except redis.RedisError:
        logger.warning("logout could not record revocation for jti=%s (Redis unavailable)", jti)
        return False
    return True


# --- principal + role checks ----------------------------------------------
class Principal:
    def __init__(self, name: str, role: str, kind: str, source_ip: str | None = None,
                 tenant: str | None = None, token: str | None = None):
        self.name = name
        self.role = role
        self.kind = kind
        self.source_ip = source_ip
        self.tenant = tenant  # None => global (sees all tenants); else scoped
        self.token = token    # raw bearer token, when kind == "jwt" (needed for logout)

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
    if role == "engineer":
        return any(r in allowed for r in ("engineer", "operator", "viewer"))
    if role == "operator":
        return any(r in allowed for r in ("operator", "viewer"))
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
        # Refresh/reset tokens cannot authorize API calls — only access tokens.
        if payload and payload.get("use", "access") == "access":
            return Principal(payload["sub"], payload["role"], "jwt", ip,
                             tenant=payload.get("tenant"), token=token)
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
def _device_site(device_id: str) -> str | None:
    conn = _db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT site_name FROM devices WHERE device_id = %s", (device_id,))
        row = cur.fetchone()
        cur.close()
        return row[0] if row else None
    except Exception:  # noqa: BLE001 — best-effort enrichment, never block the caller
        return None
    finally:
        conn.close()


def audit(principal: Principal | None, action: str, resource: str, result: str,
          detail: dict | None = None, site: str | None = None,
          device_id: str | None = None) -> None:
    """Append an audit_events row. Best-effort: never fail the request.
    request_id is taken automatically from the current request's context
    (see RequestIDMiddleware); site is taken from the explicit arg, else
    looked up from device_id when given."""
    who = principal.name if principal else "anonymous"
    role = principal.role if principal else None
    ip = principal.source_ip if principal else None
    if site is None and device_id is not None:
        site = _device_site(device_id)
    request_id = _request_id_ctx.get()
    try:
        conn = psycopg2.connect(**_DB)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO audit_events (principal, role, action, resource, source_ip, result, "
            "detail, site, request_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (who, role, action, resource, ip, result, json.dumps(detail or {}), site, request_id),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("audit write failed for %s/%s: %s", action, resource, exc)


def list_audit_events(principal_filter: str | None = None, action_filter: str | None = None,
                      since: str | None = None, limit: int = 50, offset: int = 0) -> list[dict]:
    conn = _db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        clauses, params = [], []
        if principal_filter:
            clauses.append("principal = %s")
            params.append(principal_filter)
        if action_filter:
            clauses.append("action = %s")
            params.append(action_filter)
        if since:
            clauses.append("ts >= %s")
            params.append(since)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])
        cur.execute(
            f"SELECT id, ts, principal, role, action, resource, site, request_id, "
            f"source_ip, result, detail FROM audit_events {where} "
            f"ORDER BY ts DESC LIMIT %s OFFSET %s",
            params,
        )
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
        for r in rows:
            r["ts"] = r["ts"].isoformat()
            r["id"] = str(r["id"])
        return rows
    finally:
        conn.close()
