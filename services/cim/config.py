"""CIM service configuration — stdlib only, no third-party imports (so
importing this module never fails regardless of what's installed)."""
from __future__ import annotations

import os


class Settings:
    # Database (mirrors services/mdm/config.py's env var names — same
    # .env, read-only usage; CIM never writes to this DB).
    DB_HOST = os.getenv("DB_HOST", "diep-timescaledb")
    DB_NAME = os.getenv("DB_NAME", "diep")
    DB_USER = os.getenv("DB_USER", "diep")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "diep123")

    HEALTH_PORT = int(os.getenv("CIM_HEALTH_PORT", "9204"))

    # Bearer-token -> tenant_id map, deliberately separate from
    # fastapi/auth.py (DB-backed, stateful, JWT/audit/rate-limit machinery
    # too heavy a coupling for a read-only adapter service). Format:
    # "token1=tenant-a,token2=tenant-b,token3=" -- an empty tenant after
    # '=' means unscoped (sees every tenant's data; the service-level
    # case, analogous to fastapi/auth.py's admin/service roles).
    CIM_API_KEYS_RAW = os.getenv(
        "CIM_API_KEYS", "diep-cim-dev-token-CHANGE-ME="
    )

    # Pagination -- the first place in this repo enforcing it; CIM is a
    # new externally-facing layer, worth doing from the start.
    DEFAULT_LIMIT = int(os.getenv("CIM_DEFAULT_LIMIT", "100"))
    MAX_LIMIT = int(os.getenv("CIM_MAX_LIMIT", "1000"))

    @classmethod
    def api_keys(cls) -> dict[str, str | None]:
        out: dict[str, str | None] = {}
        for pair in cls.CIM_API_KEYS_RAW.split(","):
            pair = pair.strip()
            if not pair or "=" not in pair:
                continue
            token, tenant = pair.split("=", 1)
            token = token.strip()
            tenant = tenant.strip()
            if token:
                out[token] = tenant or None
        return out
