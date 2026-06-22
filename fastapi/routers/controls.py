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
import csv
import io
import json
import logging
import uuid

from fastapi import APIRouter, HTTPException, Depends, Response
from pydantic import BaseModel, Field
from prometheus_client import Counter, Gauge

import common
from auth import require_role

router = APIRouter(prefix="/controls", tags=["controls"])

# OC-6 — operational audit & safety reporting. Every governed transition feeds
# both the immutable DB audit (control_audit) and Prometheus, so the control
# plane is observable and alertable. These live on the default registry and are
# scraped by the existing /metrics endpoint.
log = logging.getLogger("diep.controls")

CONTROL_EVENTS = Counter(
    "diep_control_events_total",
    "Governed control-action lifecycle transitions",
    ["event", "action_type", "risk"])  # REQUESTED|APPROVED|REJECTED|DRYRUN|EXECUTED|FAILED|BLOCKED|ROLLED_BACK
CONTROL_LIVE_BLOCKED = Counter(
    "diep_control_live_blocked_total",
    "Live executions refused by a governance gate",
    ["action_type", "reason"])  # flag_off | needs_approval
CONTROLS_ENABLED_G = Gauge(
    "diep_controls_enabled", "1 if OC_CONTROLS_ENABLED (live actuation) else 0")
CONTROL_ACTIONS_G = Gauge(
    "diep_control_actions", "Current control_actions count by status", ["status"])

# Events whose occurrence is operationally significant enough to log at WARNING
# (so a log-based alert can catch them even without Prometheus).
_ALERT_EVENTS = {"BLOCKED", "FAILED", "ROLLED_BACK"}
_KNOWN_STATUSES = ("PENDING", "APPROVED", "REJECTED", "EXECUTED", "FAILED", "ROLLED_BACK")

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

    def risk_for(self, target, params):  # noqa: ARG002
        """Per-action risk ('low'|'high'). Default is the static class risk;
        override for magnitude-dependent risk (e.g. OC-4 Volt/VAR rate limit)."""
        return self.risk

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
def _audit(action_id, event, actor, detail=None, *, action_type=None, risk=None):
    """Append an immutable audit row AND emit the matching Prometheus counter.
    Safety-relevant events (BLOCKED/FAILED/ROLLED_BACK) are also logged at WARNING
    so a log-based alert can catch them independent of the metrics pipeline."""
    common.execute(
        "INSERT INTO control_audit (action_id, event, actor, detail) VALUES (%s,%s,%s,%s)",
        (action_id, event, actor, json.dumps(detail or {})),
    )
    CONTROL_EVENTS.labels(event, action_type or "n/a", risk or "n/a").inc()
    if event in _ALERT_EVENTS:
        log.warning("control-action %s: %s by %s (type=%s risk=%s) %s",
                    action_id, event, actor, action_type, risk, json.dumps(detail or {}))


def _refresh_gauges():
    """Reflect current control-plane state into Prometheus gauges. Called after
    each mutating endpoint and on the readiness report — cheap, and keeps the
    scrape itself free of DB work."""
    try:
        CONTROLS_ENABLED_G.set(1 if controls_enabled() else 0)
        counts = {s: 0 for s in _KNOWN_STATUSES}
        for row in common.query_all("SELECT status, COUNT(*) AS n FROM control_actions GROUP BY status"):
            counts[row["status"]] = int(row["n"])
        for status, n in counts.items():
            CONTROL_ACTIONS_G.labels(status).set(n)
    except Exception as exc:  # noqa: BLE001 — metrics must never break a request
        log.debug("gauge refresh skipped: %s", exc)


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
    risk = handler.risk_for(body.target, body.params)
    action_id = str(uuid.uuid4())
    tenant = principal.tenant or "default"
    common.execute(
        "INSERT INTO control_actions (action_id, action_type, target, params, mode, risk, "
        "status, reason, requested_by, before_state, tenant_id) "
        "VALUES (%s,%s,%s,%s,%s,%s,'PENDING',%s,%s,%s,%s)",
        (action_id, body.action_type, body.target, json.dumps(body.params), body.mode,
         risk, body.reason, principal.name, json.dumps(before), tenant),
    )
    _audit(action_id, "REQUESTED", principal.name,
           {"action_type": body.action_type, "target": body.target,
            "mode": body.mode, "risk": risk, "preview": preview},
           action_type=body.action_type, risk=risk)
    _refresh_gauges()
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
    _audit(action_id, "APPROVED", principal.name, {"reason": body.reason},
           action_type=row["action_type"], risk=row["risk"])
    _refresh_gauges()
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
    _audit(action_id, "REJECTED", principal.name, {"reason": body.reason},
           action_type=row["action_type"], risk=row["risk"])
    _refresh_gauges()
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
        _audit(action_id, "DRYRUN", principal.name, {},
               action_type=row["action_type"], risk=row["risk"])
        common.execute("UPDATE control_actions SET status='EXECUTED', executed_at=now(), "
                       "after_state=%s, error=NULL WHERE action_id=%s",
                       (json.dumps({"dry_run": True}), action_id))
        _refresh_gauges()
        return {**_get(action_id), "dry_run": True}

    # live — master flag first, then the approval rule by risk.
    if not controls_enabled():
        CONTROL_LIVE_BLOCKED.labels(row["action_type"], "flag_off").inc()
        _audit(action_id, "BLOCKED", principal.name, {"reason": "OC_CONTROLS_ENABLED=false"},
               action_type=row["action_type"], risk=row["risk"])
        raise HTTPException(status_code=403,
                            detail="operational controls disabled (OC_CONTROLS_ENABLED=false); "
                                   "live actuation refused")
    if row["risk"] == "high":
        # two-person: a high-risk live action must be APPROVED (by a different actor).
        if row["status"] != "APPROVED":
            CONTROL_LIVE_BLOCKED.labels(row["action_type"], "needs_approval").inc()
            _audit(action_id, "BLOCKED", principal.name,
                   {"reason": f"high-risk live action not approved (status={row['status']})"},
                   action_type=row["action_type"], risk=row["risk"])
            raise HTTPException(status_code=409,
                                detail=f"high-risk live action requires two-person approval "
                                       f"(status={row['status']})")
    else:
        # single-operator: low-risk may execute without a separate approver.
        if row["status"] not in ("PENDING", "APPROVED"):
            raise HTTPException(status_code=409, detail=f"cannot execute from status {row['status']}")
    try:
        after = handler.execute(dict(row))
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        common.execute("UPDATE control_actions SET status='FAILED', error=%s WHERE action_id=%s",
                       (str(exc), action_id))
        _audit(action_id, "FAILED", principal.name, {"error": str(exc)},
               action_type=row["action_type"], risk=row["risk"])
        _refresh_gauges()
        raise HTTPException(status_code=500, detail=f"execution failed: {exc}")
    common.execute("UPDATE control_actions SET status='EXECUTED', executed_at=now(), "
                   "after_state=%s, error=NULL WHERE action_id=%s", (json.dumps(after), action_id))
    _audit(action_id, "EXECUTED", principal.name, {"after_state": after, "mode": "live"},
           action_type=row["action_type"], risk=row["risk"])
    log.warning("control-action %s: LIVE EXECUTED by %s (type=%s risk=%s)",
                action_id, principal.name, row["action_type"], row["risk"])
    _refresh_gauges()
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
    _audit(action_id, "ROLLED_BACK", principal.name, {"after_state": after},
           action_type=row["action_type"], risk=row["risk"])
    _refresh_gauges()
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


# --- OC-6: operational audit & safety reporting ------------------------------
def _scope(principal, *extra):
    """(WHERE clause, params) scoping control_actions to the caller's tenant plus
    any literal extra conditions (no user params — keep them constant/safe)."""
    conds, params = [], []
    if principal.tenant is not None:
        conds.append("tenant_id = %s")
        params.append(principal.tenant)
    conds.extend(extra)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    return where, tuple(params)


@router.get("/report/readiness")
def readiness(principal=Depends(require_role(*READ_ROLES))):
    """Control-readiness / safety snapshot: posture, queue state, and 24h activity
    — a single view an operator (or dashboard) reads to judge whether the control
    plane is safe and healthy. Also refreshes the Prometheus gauges."""
    _refresh_gauges()
    where, params = _scope(principal)

    counts = {s: 0 for s in _KNOWN_STATUSES}
    for r in common.query_all(f"SELECT status, COUNT(*) AS n FROM control_actions {where} GROUP BY status", params):
        counts[r["status"]] = int(r["n"])

    aw_where, aw_params = _scope(principal, "status = 'PENDING'", "risk = 'high'")
    awaiting_approval = int(common.query_one(
        f"SELECT COUNT(*) AS n FROM control_actions {aw_where}", aw_params)["n"])

    op_where, op_params = _scope(principal, "status = 'PENDING'")
    oldest = common.query_one(
        f"SELECT EXTRACT(EPOCH FROM (now() - MIN(created_at))) AS age FROM control_actions {op_where}", op_params)
    oldest_pending = float(oldest["age"]) if oldest and oldest["age"] is not None else None

    last = common.query_one(f"SELECT MAX(created_at) AS ts FROM control_actions {where}", params)
    last_action_at = last["ts"].isoformat() if last and last["ts"] else None

    # 24h activity from the audit trail (event-timestamped), tenant-scoped via join.
    tjoin, tparams = ("", ())
    if principal.tenant is not None:
        tjoin, tparams = ("AND a.tenant_id = %s", (principal.tenant,))
    events_24h = {r["event"]: int(r["n"]) for r in common.query_all(
        "SELECT ca.event, COUNT(*) AS n FROM control_audit ca "
        "JOIN control_actions a ON a.action_id = ca.action_id "
        f"WHERE ca.at > now() - interval '24 hours' {tjoin} GROUP BY ca.event", tparams)}

    enabled = controls_enabled()
    warnings = []
    if enabled:
        warnings.append("LIVE actuation enabled (OC_CONTROLS_ENABLED=true) — actions can actuate.")
    if counts["FAILED"]:
        warnings.append(f"{counts['FAILED']} action(s) in FAILED state — investigate.")
    if awaiting_approval:
        warnings.append(f"{awaiting_approval} high-risk action(s) awaiting two-person approval.")
    if oldest_pending is not None and oldest_pending > 3600:
        warnings.append(f"oldest PENDING action is {int(oldest_pending // 60)} min old.")
    if events_24h.get("BLOCKED"):
        warnings.append(f"{events_24h['BLOCKED']} live execution(s) refused by a governance gate in 24h.")

    return {
        "controls_enabled": enabled,
        "posture": "LIVE" if enabled else "SAFE",
        "registered_action_types": sorted(_HANDLERS.keys()),
        "approval_model": {"high_risk": "two_person", "low_risk": "single_operator"},
        "counts": counts,
        "awaiting_approval": awaiting_approval,
        "awaiting_execution": counts["APPROVED"],
        "oldest_pending_age_seconds": oldest_pending,
        "last_action_at": last_action_at,
        "activity_24h": {
            "requested": events_24h.get("REQUESTED", 0),
            "dry_runs": events_24h.get("DRYRUN", 0),
            "executed_live": events_24h.get("EXECUTED", 0),
            "blocked": events_24h.get("BLOCKED", 0),
            "failed": events_24h.get("FAILED", 0),
            "rolled_back": events_24h.get("ROLLED_BACK", 0),
        },
        "ready": counts["FAILED"] == 0,
        "warnings": warnings,
    }


@router.get("/report/history")
def history(action_type: str | None = None, status: str | None = None,
            risk: str | None = None, since_hours: int = 168, limit: int = 200,
            principal=Depends(require_role(*READ_ROLES))):
    """Filtered action history plus summary aggregates over a time window."""
    since_hours = min(max(since_hours, 1), 24 * 90)
    limit = min(max(limit, 1), 1000)
    conds, params = [], []
    if principal.tenant is not None:
        conds.append("tenant_id = %s"); params.append(principal.tenant)
    conds.append("created_at > now() - make_interval(hours => %s)"); params.append(since_hours)
    if action_type:
        conds.append("action_type = %s"); params.append(action_type)
    if status:
        conds.append("status = %s"); params.append(status)
    if risk:
        conds.append("risk = %s"); params.append(risk)
    where = "WHERE " + " AND ".join(conds)

    def _by(col):
        return {r[col]: int(r["n"]) for r in common.query_all(
            f"SELECT {col}, COUNT(*) AS n FROM control_actions {where} GROUP BY {col}", tuple(params))}

    actions = common.query_all(
        f"SELECT * FROM control_actions {where} ORDER BY created_at DESC LIMIT %s",
        tuple(params) + (limit,))
    return {
        "since_hours": since_hours,
        "total": len(actions),
        "summary": {
            "by_action_type": _by("action_type"),
            "by_status": _by("status"),
            "by_mode": _by("mode"),
            "by_requested_by": _by("requested_by"),
        },
        "actions": actions,
    }


@router.get("/audit/export")
def export_audit(format: str = "csv", since_hours: int = 720,
                 principal=Depends(require_role(*READ_ROLES))):
    """Download the audit trail (CSV default, or JSON) over a time window. Each
    row is one governed transition joined to its action's metadata. Tenant-scoped."""
    since_hours = min(max(since_hours, 1), 24 * 365)
    tcond, tparams = ("", ())
    if principal.tenant is not None:
        tcond, tparams = ("AND a.tenant_id = %s", (principal.tenant,))
    rows = common.query_all(
        "SELECT ca.at, ca.action_id, a.action_type, a.risk, a.mode, a.target, "
        "ca.event, ca.actor, a.requested_by, a.approved_by, a.status, ca.detail "
        "FROM control_audit ca JOIN control_actions a ON a.action_id = ca.action_id "
        f"WHERE ca.at > now() - make_interval(hours => %s) {tcond} ORDER BY ca.at DESC",
        (since_hours,) + tparams)

    cols = ["at", "action_id", "action_type", "risk", "mode", "target",
            "event", "actor", "requested_by", "approved_by", "status", "detail"]
    if format == "json":
        return {"generated_at": None, "rows": rows}

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for r in rows:
        w.writerow([
            r["at"].isoformat() if r.get("at") else "",
            r.get("action_id"), r.get("action_type"), r.get("risk"), r.get("mode"),
            r.get("target") or "", r.get("event"), r.get("actor"),
            r.get("requested_by"), r.get("approved_by") or "", r.get("status"),
            json.dumps(r.get("detail") or {}),
        ])
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=control_audit_export.csv"})
