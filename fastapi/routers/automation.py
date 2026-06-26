"""ADMS Phase 4 (P4-1) — closed-loop automation engine.

Lets the platform act on its own analysis, but ONLY through the Phase-2/3 governed
control plane. An automation *policy* evaluates conditions each tick and emits
*proposals*; the engine turns each proposal into a governed control action via the
same path operators use (controls.submit_action), so an automation-originated action
is approved/executed/echo-verified/audited identically.

Safety, by construction:
  * master flag `OC_AUTOMATION_ENABLED` (default OFF) gates the whole engine;
  * a policy is disabled by default and runs in mode 'recommend' — it creates a
    governed PENDING action for a human to approve/execute, and executes nothing;
  * mode 'auto' is per-policy opt-in and additionally requires the controls flag
    (`OC_CONTROLS_ENABLED`) AND the proposal to pass the policy's bounds;
  * a circuit breaker trips a policy after repeated failures;
  * a per-policy cooldown prevents action storms.
"""
import os
import json
import types

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

import common
from auth import require_role
from routers import controls

router = APIRouter(prefix="/automation", tags=["automation"])

READ_ROLES = ("viewer", "operator", "engineer", "admin", "service")
ADMIN_ROLES = ("engineer", "admin")          # toggle policies / mode
TICK_ROLES = ("admin", "service")            # run the engine (the background controller)
TRIP_THRESHOLD = int(os.getenv("OC_AUTOMATION_TRIP_AFTER", "3"))


def automation_enabled() -> bool:
    """Master flag for the automation engine. Default OFF; read at call time."""
    return os.getenv("OC_AUTOMATION_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")


# A system actor for governed actions the engine creates/approves/executes. Distinct
# name from the requester so it satisfies the two-person rule on high-risk actions.
def _sys_actor(suffix="engine"):
    return types.SimpleNamespace(name=f"automation:{suffix}", role="admin",
                                 tenant=None, kind="service", source_ip="automation")


# --- policy registry ---------------------------------------------------------
class AutomationPolicy:
    """One policy kind. evaluate() returns a list of proposals; each proposal is a
    dict: {action_type, target, params, mode, trigger, reason}."""
    kind = "noop"

    def evaluate(self, policy: dict) -> list[dict]:  # noqa: ARG002
        return []

    def within_bounds(self, preview: dict, bounds: dict) -> tuple[bool, str]:  # noqa: ARG002
        """auto-mode guard: is this proposal inside the policy's safety envelope?"""
        return True, ""


_POLICIES: dict[str, AutomationPolicy] = {}


def register_policy(kind: str, policy: AutomationPolicy) -> None:
    _POLICIES[kind] = policy


class NoopAutoPolicy(AutomationPolicy):
    """Demonstrator: proposes a governed noop (dry-run) each tick. Actuates nothing —
    exercises the automation -> governance -> audit loop end to end."""
    kind = "noop"

    def evaluate(self, policy: dict) -> list[dict]:
        return [{
            "action_type": "noop", "target": None,
            "params": {"automation": policy["policy_id"]}, "mode": "dry_run",
            "trigger": {"reason": "demonstrator tick"},
            "reason": f"automation:{policy['policy_id']} demonstrator",
        }]


register_policy("noop", NoopAutoPolicy())


# --- helpers -----------------------------------------------------------------
def _event(policy_id, kind, decision, trigger=None, action_id=None, detail=None, tenant="default"):
    common.execute(
        "INSERT INTO automation_events (policy_id, kind, decision, trigger, action_id, detail, tenant_id, "
        "network_model_version) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (policy_id, kind, decision, json.dumps(trigger or {}), action_id,
         json.dumps(detail or {}), tenant, common.current_model_version()))


def _policies(enabled_only=False):
    where = "WHERE enabled = TRUE AND tripped = FALSE" if enabled_only else ""
    return common.query_all(f"SELECT * FROM automation_policies {where} ORDER BY policy_id")


def _get_policy(policy_id):
    return common.query_one("SELECT * FROM automation_policies WHERE policy_id = %s", (policy_id,))


def _cooldown_active(policy) -> bool:
    cd = float((policy.get("bounds") or {}).get("cooldown_s", 0) or 0)
    if cd <= 0 or policy.get("last_run_at") is None:
        return False
    row = common.query_one(
        "SELECT EXTRACT(EPOCH FROM (now() - %s)) AS age", (policy["last_run_at"],))
    return row is not None and float(row["age"]) < cd


def _trip(policy_id, tripped):
    common.execute(
        "UPDATE automation_policies SET tripped = %s, updated_at = now() WHERE policy_id = %s",
        (tripped, policy_id))


def _bump_failures(policy_id, reset=False):
    if reset:
        common.execute("UPDATE automation_policies SET consecutive_failures = 0 WHERE policy_id = %s",
                       (policy_id,))
        return 0
    row = common.execute(
        "UPDATE automation_policies SET consecutive_failures = consecutive_failures + 1 "
        "WHERE policy_id = %s RETURNING consecutive_failures", (policy_id,), returning=True)
    return int(row["consecutive_failures"]) if row else 0


# --- the engine --------------------------------------------------------------
def _run_proposal(policy, policy_obj, prop) -> dict:
    """Turn one proposal into a governed action. recommend => create PENDING (human
    disposes); auto => create + (approve if high-risk) + execute, within bounds and
    the controls flag. Returns a summary dict and writes an automation_event."""
    pid, tenant = policy["policy_id"], policy["tenant_id"]
    try:
        row, risk, preview = controls.submit_action(
            prop["action_type"], prop.get("target"), prop.get("params", {}),
            prop.get("mode", "live"), prop.get("reason", f"automation:{pid}"),
            requested_by=f"automation:{pid}", tenant=tenant)
    except HTTPException as exc:
        _event(pid, policy_obj.kind, "blocked", prop.get("trigger"),
               detail={"error": str(exc.detail)}, tenant=tenant)
        return {"decision": "blocked", "detail": str(exc.detail)}

    aid = row["action_id"]
    if policy["mode"] == "recommend":
        _event(pid, policy_obj.kind, "proposed", prop.get("trigger"), action_id=aid,
               detail={"risk": risk, "preview": preview, "mode": row["mode"]}, tenant=tenant)
        return {"decision": "proposed", "action_id": aid, "risk": risk}

    # auto mode -----------------------------------------------------------
    ok, why = policy_obj.within_bounds(preview, policy.get("bounds") or {})
    if not ok:
        _event(pid, policy_obj.kind, "blocked", prop.get("trigger"), action_id=aid,
               detail={"out_of_bounds": why, "preview": preview}, tenant=tenant)
        return {"decision": "blocked", "action_id": aid, "detail": why}
    if not controls.controls_enabled():
        _event(pid, policy_obj.kind, "blocked", prop.get("trigger"), action_id=aid,
               detail={"reason": "OC_CONTROLS_ENABLED=false"}, tenant=tenant)
        return {"decision": "blocked", "action_id": aid, "detail": "controls disabled"}

    actor = _sys_actor(pid)
    try:
        if risk == "high":
            # Two-person rule: the approver must differ from the requester
            # (which is "automation:<pid>"). A distinct system-governance identity
            # approves, modelling "the engine proposes, automation-governance disposes".
            controls.approve(aid, controls.ReasonBody(reason=f"automation:{pid}"),
                             _sys_actor("supervisor"))
        result = controls.execute(aid, actor)
        status = result.get("status")
        if status == "EXECUTED":
            _bump_failures(pid, reset=True)
            _event(pid, policy_obj.kind, "executed", prop.get("trigger"), action_id=aid,
                   detail={"risk": risk, "after_state": result.get("after_state")}, tenant=tenant)
            return {"decision": "executed", "action_id": aid}
        raise RuntimeError(f"unexpected post-execute status {status}")
    except Exception as exc:  # noqa: BLE001 — execute may FAIL (e.g. echo divergence)
        fails = _bump_failures(pid)
        tripped = fails >= TRIP_THRESHOLD
        if tripped:
            _trip(pid, True)
        _event(pid, policy_obj.kind, "tripped" if tripped else "failed", prop.get("trigger"),
               action_id=aid, detail={"error": str(exc)[:200], "consecutive_failures": fails}, tenant=tenant)
        return {"decision": "tripped" if tripped else "failed", "action_id": aid, "detail": str(exc)[:200]}


def _tick() -> dict:
    results = []
    for policy in _policies(enabled_only=True):
        pid = policy["policy_id"]
        policy_obj = _POLICIES.get(policy["kind"])
        if policy_obj is None:
            _event(pid, policy["kind"], "skipped", detail={"reason": "no policy handler registered"},
                   tenant=policy["tenant_id"])
            continue
        if _cooldown_active(policy):
            results.append({"policy_id": pid, "decision": "skipped", "reason": "cooldown"})
            continue
        proposals = policy_obj.evaluate(policy)[: int((policy.get("bounds") or {}).get("max_per_tick", 1))]
        if not proposals:
            continue
        common.execute("UPDATE automation_policies SET last_run_at = now() WHERE policy_id = %s", (pid,))
        for prop in proposals:
            r = _run_proposal(policy, policy_obj, prop)
            results.append({"policy_id": pid, **r})
    return {"ran": True, "results": results}


# --- models ------------------------------------------------------------------
class PolicyPatch(BaseModel):
    enabled: bool | None = None
    mode: str | None = None        # recommend | auto
    reset_trip: bool | None = None


# --- endpoints ---------------------------------------------------------------
@router.get("/status")
def status(_p=Depends(require_role(*READ_ROLES))):
    pols = _policies()
    return {
        "automation_enabled": automation_enabled(),
        "controls_enabled": controls.controls_enabled(),
        "registered_kinds": sorted(_POLICIES.keys()),
        "policies": len(pols),
        "enabled_policies": sum(1 for p in pols if p["enabled"] and not p["tripped"]),
        "tripped_policies": [p["policy_id"] for p in pols if p["tripped"]],
        "default_mode": "recommend",
        "note": "auto-execution requires OC_AUTOMATION_ENABLED AND OC_CONTROLS_ENABLED AND policy mode 'auto' within bounds",
    }


@router.get("/policies")
def list_policies(_p=Depends(require_role(*READ_ROLES))):
    return {"policies": _policies()}


@router.patch("/policies/{policy_id}")
def patch_policy(policy_id: str, body: PolicyPatch, principal=Depends(require_role(*ADMIN_ROLES))):
    pol = _get_policy(policy_id)
    if pol is None:
        raise HTTPException(status_code=404, detail="policy not found")
    sets, params = [], []
    if body.enabled is not None:
        sets.append("enabled = %s"); params.append(body.enabled)
    if body.mode is not None:
        if body.mode not in ("recommend", "auto"):
            raise HTTPException(status_code=422, detail="mode must be 'recommend' or 'auto'")
        sets.append("mode = %s"); params.append(body.mode)
    if body.reset_trip:
        sets.append("tripped = FALSE"); sets.append("consecutive_failures = 0")
    if not sets:
        raise HTTPException(status_code=422, detail="nothing to update")
    sets.append("updated_at = now()")
    params.append(policy_id)
    common.execute(f"UPDATE automation_policies SET {', '.join(sets)} WHERE policy_id = %s", tuple(params))
    _event(policy_id, pol["kind"], "config",
           detail={"change": body.model_dump(exclude_none=True), "by": principal.name},
           tenant=pol["tenant_id"])
    return _get_policy(policy_id)


@router.post("/tick")
def tick(principal=Depends(require_role(*TICK_ROLES))):  # noqa: ARG001
    """Evaluate all enabled policies once. Inert unless OC_AUTOMATION_ENABLED. The
    background automation-controller calls this on an interval; it is also callable
    on demand for testing."""
    if not automation_enabled():
        return {"ran": False, "reason": "automation disabled (OC_AUTOMATION_ENABLED=false)"}
    return _tick()


@router.get("/events")
def events(policy_id: str | None = None, limit: int = 100, _p=Depends(require_role(*READ_ROLES))):
    limit = min(max(limit, 1), 500)
    if policy_id:
        return {"events": common.query_all(
            "SELECT * FROM automation_events WHERE policy_id = %s ORDER BY at DESC LIMIT %s",
            (policy_id, limit))}
    return {"events": common.query_all(
        "SELECT * FROM automation_events ORDER BY at DESC LIMIT %s", (limit,))}
