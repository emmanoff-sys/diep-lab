"""ADMS Phase 4 (P4-3) — continuous Volt/VAR optimization policy.

Registers the `voltvar` automation policy with the P4-1 engine, closing the loop the
read-only Volt/VAR advisory only described. Each tick it reads the rule-based voltage
violations (dms.voltvar_recommendations) and, for each one, proposes a *bounded*
governed `voltvar_dispatch` on a controllable DER on the same feeder — nudging its
real-power setpoint in the corrective direction by at most `max_step_kw`.

Bounded + conservative:
  * the step is capped so OC-4 classifies it low-risk (single-operator); a swing that
    OC-4 would deem high-risk is rejected by within_bounds (falls back to a human);
  * the setpoint is banded to the DER's rating by the OC-4 handler;
  * de-dups against an open/recent automation dispatch for the same DER.

This is a simplified, lab-honest controller (incremental correction, not a power-flow
optimum) — the value is the *governed closed loop*: every nudge is a governed action
(OC-4 banding/rate-limit, P3-2 echo where the device reports a setpoint, audit).
"""
import common
from routers.automation import AutomationPolicy, register_policy
from routers.dms import voltvar_recommendations


def _node_feeder(node_id: str) -> str | None:
    cur, guard = node_id, 0
    while cur and guard < 50:
        n = common.query_one("SELECT node_type, parent_id FROM grid_nodes WHERE node_id = %s", (cur,))
        if n is None:
            return None
        if n["node_type"] == "feeder":
            return cur
        cur, guard = n["parent_id"], guard + 1
    return None


def _der_for_node(node_id: str):
    """The most capable controllable DER on the violated node's feeder (the lever)."""
    feeder = _node_feeder(node_id)
    if feeder is None:
        return None
    for d in common.query_all(
            "SELECT der_id, der_type, rated_kw, node_id FROM der_assets "
            "WHERE controllable = TRUE ORDER BY rated_kw DESC NULLS LAST"):
        if _node_feeder(d["node_id"]) == feeder:
            return d
    return None


def _current_kw(der_id: str) -> float:
    row = common.query_one(
        "SELECT power_kw, EXTRACT(EPOCH FROM (now() - time)) AS age FROM telemetry "
        "WHERE device_id = %s ORDER BY time DESC LIMIT 1", (der_id,))
    if not row or row.get("power_kw") is None or row.get("age") is None or float(row["age"]) > 600:
        return 0.0
    return float(row["power_kw"])


class VoltVarAutoPolicy(AutomationPolicy):
    kind = "voltvar"

    def evaluate(self, policy: dict) -> list[dict]:
        pid = policy["policy_id"]
        step = float((policy.get("bounds") or {}).get("max_step_kw", 10))
        proposals, used = [], set()
        for r in voltvar_recommendations()["recommendations"]:
            der = _der_for_node(r["node_id"])
            if der is None or der["der_id"] in used:
                continue
            used.add(der["der_id"])
            dup = common.query_one(
                "SELECT 1 FROM control_actions WHERE action_type='voltvar_dispatch' AND target=%s "
                "AND requested_by=%s AND (status IN ('PENDING','APPROVED') "
                "  OR (status='EXECUTED' AND executed_at > now() - interval '10 minutes')) LIMIT 1",
                (der["der_id"], f"automation:{pid}"))
            if dup:
                continue
            cur = _current_kw(der["der_id"])
            rated = float(der["rated_kw"] or 0)
            # raise voltage -> more local real-power injection; lower -> less. Banded.
            target = cur + step if r["direction"] == "raise" else cur - step
            target = max(0.0, min(target, rated))
            if abs(target - cur) < 0.01:
                continue                              # no headroom to move
            proposals.append({
                "action_type": "voltvar_dispatch", "target": der["der_id"],
                "params": {"setpoint_kw": round(target, 2)}, "mode": "live",
                "trigger": {"node_id": r["node_id"], "direction": r["direction"],
                            "issue": r["issue"], "der_id": der["der_id"],
                            "from_kw": round(cur, 2), "to_kw": round(target, 2)},
                "reason": f"auto Volt/VAR {r['direction']} via {der['der_id']} for {r['node_id']}",
            })
        return proposals

    def within_bounds(self, preview: dict, bounds: dict) -> tuple[bool, str]:
        # Only auto-dispatch when OC-4 itself deemed the swing low-risk.
        if preview.get("rate_limited_high_risk"):
            return False, "swing exceeds OC-4 rate limit (high-risk) — needs a human"
        return True, ""


register_policy("voltvar", VoltVarAutoPolicy())
