"""ADMS Phase 2 (OC-1) — operational-controls governance core.

Safe-by-default actuation substrate. Every control action flows through
request -> (approve) -> execute -> verify -> audit, with:

  - a master feature flag OC_CONTROLS_ENABLED (default OFF) that gates LIVE
    actuation only — dry-run planning and the whole governance API stay available
    so the workflow can be exercised safely with controls disabled;
  - dry-run by default (plan + audit, no actuation);
  - separation of duties: a high-risk action's approver must differ from its
    requester; low-risk actions may be self-approved (single operator);
  - an append-only audit trail (control_audit) for every transition;
  - a handler registry so later modules (OC-2 switch ops, OC-3 FLISR, OC-4
    Volt/VAR) register their own plan/execute/rollback without touching the core.

OC-1 ships the framework plus a trivially safe `noop` action type that exercises
the full governed lifecycle end to end. No grid or device actuation is wired here.
"""
import os
import json
import uuid

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

import common
from auth import require_role

router = APIRouter(prefix="/controls", tags=["controls"])

# operator+ may request/execute; only engineer/admin may approve. Read is broad.
REQUEST_ROLES = ("operator", "engineer", "admin")
APPROVE_ROLES = ("engineer", "admin")
READ_ROLES = ("viewer", "operator", "engineer", "admin", "service")


def controls_enabled() -> bool:
    """Master flag for LIVE actuation. Default OFF; read at call time so it can be
    toggled without a code change. Dry-run never depends on this."""
    return os.getenv("OC_CONTROLS_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")


# --- handler registry --------------------------------------------------------
class ControlHandler:
    """One action_type's plan/execute/rollback. Later modules subclass + register.

    plan() validates and returns (before_state, preview). It MUST raise
    HTTPException to block an unsafe/invalid action (interlocks live here).
    execute() performs the actuation and returns after_state.
    rollback() best-effort reverts using action['before_state'].
    """
    risk = "low"

    def plan(self, target, params):  # noqa: ARG002
        return {}, {}

    def execute(self, action):  # noqa: ARG002
        return {}

    def rollback(self, action):
        return action.get("before_state") or {}


_HANDLERS: dict[str, ControlHandler] = {}


def register_handler(action_type: str, handler: ControlHandler) -> None:
    _HANDLERS[action_type] = handler


class NoopHandler(ControlHandler):
    """Governance demonstrator: exercises the full lifecycle, actuates nothing."""
    risk = "low"

    def plan(self, target, params):
        return {"noop": True}, {"noop": True, "echo": params}

    def execute(self, action):
        return {"noop": True, "executed": True}


register_handler("noop", NoopHandler())


# --- helpers -----------------------------------------------------------------
def _audit(action_id, event, actor, detail=None):
    common.execute(
        "INSERT INTO control_audit (action_id, event, actor, detail) VALUES (%s,%s,%s,%s)",
        (action_id, event, actor, json.dumps(detail or {})),
    )


def _get(action_id):
    return common.query_one("SELECT * FROM control_actions WHERE action_id = %s", (action_id,))


def _assert_tenant(principal, row):
    """Tenant-scoped principals may only touch their own tenant's actions."""
    if principal.tenant is not None and row.get("tenant_id") not in (None, principal.tenant):
        raise HTTPException(status_code=403, detail="action belongs to another tenant")


# --- models ------------------------------------------------------------------
class ActionRequest(BaseModel):
    action_type: str = Field(..., examples=["noop"])
    target: str | None = None
    params: dict = Field(default_factory=dict)
    mode: str = Field("dry_run", pattern="^(dry_run|live)$")
    reason: str | None = None


class ReasonBody(BaseModel):
    reason: str | None = None


# --- endpoints ---------------------------------------------------------------
@router.get("/status")
def status(_p=Depends(require_role(*READ_ROLES))):
    """Capability + safety posture of the control plane."""
    return {
        "controls_enabled": controls_enabled(),
        "live_actuation": controls_enabled(),
        "default_mode": "dry_run",
        "registered_action_types": sorted(_HANDLERS.keys()),
        "approval": {"high_risk": "two_person (approver != requester)",
                     "low_risk": "single_operator"},
        "request_roles": list(REQUEST_ROLES),
        "approve_roles": list(APPROVE_ROLES),
    }


@router.post("/actions")
def create_action(body: ActionRequest, principal=Depends(require_role(*REQUEST_ROLES))):
    """Request a control action. Runs the handler's plan/interlocks and records a
    PENDING action. Actuates nothing — execution is a separate, gated step."""
    handler = _HANDLERS.get(body.action_type)
    if handler is None:
        raise HTTPException(status_code=422, detail=f"unknown action_type '{body.action_type}'")
    before, preview = handler.plan(body.target, body.params)  # may raise HTTPException (interlock)
    action_id = str(uuid.uuid4())
    tenant = principal.tenant or "default"
    common.execute(
        "INSERT INTO control_actions (action_id, action_type, target, params, mode, risk, "
        "status, reason, requested_by, before_state, tenant_id) "
        "VALUES (%s,%s,%s,%s,%s,%s,'PENDING',%s,%s,%s,%s)",
        (action_id, body.action_type, body.target, json.dumps(body.params), body.mode,
         handler.risk, body.reason, principal.name, json.dumps(before), tenant),
    )
    _audit(action_id, "REQUESTED", principal.name,
           {"action_type": body.action_type, "target": body.target,
            "mode": body.mode, "risk": handler.risk, "preview": preview})
    return {**_get(action_id), "preview": preview}


@router.post("/actions/{action_id}/approve")
def approve(action_id: str, body: ReasonBody, principal=Depends(require_role(*APPROVE_ROLES))):
    row = _get(action_id)
    if row is None:
        raise HTTPException(status_code=404, detail="action not found")
    _assert_tenant(principal, row)
    if row["status"] != "PENDING":
        raise HTTPException(status_code=409, detail=f"cannot approve from status {row['status']}")
    # Separation of duties: a high-risk action cannot be approved by its requester.
    if row["risk"] == "high" and principal.name == row["requested_by"]:
        raise HTTPException(status_code=403,
                            detail="high-risk action requires a different approver (separation of duties)")
    common.execute(
        "UPDATE control_actions SET status='APPROVED', approved_by=%s, approved_at=now() "
        "WHERE action_id=%s", (principal.name, action_id))
    _audit(action_id, "APPROVED", principal.name, {"reason": body.reason})
    return _get(action_id)


@router.post("/actions/{action_id}/reject")
def reject(action_id: str, body: ReasonBody, principal=Depends(require_role(*APPROVE_ROLES))):
    row = _get(action_id)
    if row is None:
        raise HTTPException(status_code=404, detail="action not found")
    _assert_tenant(principal, row)
    if row["status"] != "PENDING":
        raise HTTPException(status_code=409, detail=f"cannot reject from status {row['status']}")
    common.execute("UPDATE control_actions SET status='REJECTED', approved_by=%s WHERE action_id=%s",
                   (principal.name, action_id))
    _audit(action_id, "REJECTED", principal.name, {"reason": body.reason})
    return _get(action_id)


@router.post("/actions/{action_id}/execute")
def execute(action_id: str, principal=Depends(require_role(*REQUEST_ROLES))):
    """Execute an action. Dry-run = plan + audit, no actuation (always allowed).
    Live = requires OC_CONTROLS_ENABLED and an APPROVED action; then actuates via
    the registered handler, capturing after_state (or FAILED on error)."""
    row = _get(action_id)
    if row is None:
        raise HTTPException(status_code=404, detail="action not found")
    _assert_tenant(principal, row)
    handler = _HANDLERS.get(row["action_type"])
    if handler is None:
        raise HTTPException(status_code=422, detail=f"no handler for '{row['action_type']}'")

    if row["mode"] == "dry_run":
        if row["status"] not in ("PENDING", "APPROVED"):
            raise HTTPException(status_code=409, detail=f"cannot execute from status {row['status']}")
        _audit(action_id, "DRYRUN", principal.name, {})
        common.execute("UPDATE control_actions SET status='EXECUTED', executed_at=now(), "
                       "after_state=%s, error=NULL WHERE action_id=%s",
                       (json.dumps({"dry_run": True}), action_id))
        return {**_get(action_id), "dry_run": True}

    # live
    if not controls_enabled():
        _audit(action_id, "BLOCKED", principal.name, {"reason": "OC_CONTROLS_ENABLED=false"})
        raise HTTPException(status_code=403,
                            detail="operational controls disabled (OC_CONTROLS_ENABLED=false); "
                                   "live actuation refused")
    if row["status"] != "APPROVED":
        raise HTTPException(status_code=409,
                            detail=f"live action must be APPROVED before execute (status={row['status']})")
    try:
        after = handler.execute(dict(row))
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        common.execute("UPDATE control_actions SET status='FAILED', error=%s WHERE action_id=%s",
                       (str(exc), action_id))
        _audit(action_id, "FAILED", principal.name, {"error": str(exc)})
        raise HTTPException(status_code=500, detail=f"execution failed: {exc}")
    common.execute("UPDATE control_actions SET status='EXECUTED', executed_at=now(), "
                   "after_state=%s, error=NULL WHERE action_id=%s", (json.dumps(after), action_id))
    _audit(action_id, "EXECUTED", principal.name, {"after_state": after})
    return _get(action_id)


@router.post("/actions/{action_id}/rollback")
def rollback(action_id: str, principal=Depends(require_role(*APPROVE_ROLES))):
    row = _get(action_id)
    if row is None:
        raise HTTPException(status_code=404, detail="action not found")
    _assert_tenant(principal, row)
    if row["status"] != "EXECUTED":
        raise HTTPException(status_code=409, detail=f"cannot roll back from status {row['status']}")
    handler = _HANDLERS.get(row["action_type"])
    if handler is None:
        raise HTTPException(status_code=422, detail=f"no handler for '{row['action_type']}'")
    after = handler.rollback(dict(row))
    common.execute("UPDATE control_actions SET status='ROLLED_BACK', after_state=%s WHERE action_id=%s",
                   (json.dumps(after), action_id))
    _audit(action_id, "ROLLED_BACK", principal.name, {"after_state": after})
    return _get(action_id)


@router.get("/actions")
def list_actions(status: str | None = None, limit: int = 50,
                 principal=Depends(require_role(*READ_ROLES))):
    limit = min(max(limit, 1), 200)
    clauses, params = [], []
    if principal.tenant is not None:
        clauses.append("tenant_id = %s")
        params.append(principal.tenant)
    if status:
        clauses.append("status = %s")
        params.append(status)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    return {"actions": common.query_all(
        f"SELECT * FROM control_actions {where} ORDER BY created_at DESC LIMIT %s", tuple(params))}


@router.get("/actions/{action_id}")
def get_action(action_id: str, principal=Depends(require_role(*READ_ROLES))):
    row = _get(action_id)
    if row is None:
        raise HTTPException(status_code=404, detail="action not found")
    _assert_tenant(principal, row)
    trail = common.query_all(
        "SELECT event, actor, detail, at FROM control_audit WHERE action_id = %s ORDER BY at", (action_id,))
    return {**row, "audit": trail}


@router.get("/audit")
def audit(action_id: str | None = None, limit: int = 100,
          principal=Depends(require_role(*READ_ROLES))):
    limit = min(max(limit, 1), 500)
    if action_id:
        return {"audit": common.query_all(
            "SELECT * FROM control_audit WHERE action_id = %s ORDER BY at", (action_id,))}
    # tenant-scoped principals only see audit for their own actions.
    if principal.tenant is not None:
        return {"audit": common.query_all(
            "SELECT ca.* FROM control_audit ca JOIN control_actions a ON a.action_id = ca.action_id "
            "WHERE a.tenant_id = %s ORDER BY ca.at DESC LIMIT %s", (principal.tenant, limit))}
    return {"audit": common.query_all(
        "SELECT * FROM control_audit ORDER BY at DESC LIMIT %s", (limit,))}
