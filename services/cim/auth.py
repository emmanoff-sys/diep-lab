"""CIM's own lightweight Bearer-token auth -- deliberately NOT
`fastapi/auth.py` (504 lines, DB-backed, stateful JWT/audit/rate-limit
machinery -- too heavy a coupling for a read-only adapter service in its
own container).

CIM_API_KEYS (services/cim/config.py) maps token -> tenant_id, or token ->
None for an unscoped/service-level token that sees every tenant's data
(analogous to fastapi/auth.py's admin/service roles, without importing
that module). Every list/detail route filters by the resolved tenant_id --
this is a deliberate fix-in-the-new-layer for a gap the prior sprint
flagged but didn't touch (`/telemetry/latest` has no tenant scoping at
all; see READY_FOR_CIM.md). CIM, as a new externally-facing layer, must
not repeat that.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request

from .config import Settings


@dataclass(frozen=True)
class CimPrincipal:
    token: str
    tenant_id: str | None  # None = unscoped, sees every tenant


def _principal_from_request(request: Request) -> CimPrincipal | None:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    token = auth[7:].strip()
    api_keys = Settings.api_keys()
    if token not in api_keys:
        return None
    return CimPrincipal(token=token, tenant_id=api_keys[token])


def require_principal(request: Request) -> CimPrincipal:
    principal = _principal_from_request(request)
    if principal is None:
        raise HTTPException(
            status_code=401, detail="authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return principal
