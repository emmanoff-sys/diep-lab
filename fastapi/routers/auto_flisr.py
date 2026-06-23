"""ADMS Phase 4 (P4-2) — FLISR auto-mode policy.

Registers the `flisr` automation policy with the P4-1 engine. Each tick it looks for
active outages that the FLISR planner can actually *restore* (isolate the fault and
back-feed lost load via a tie) and emits a proposal — turned into a governed `flisr`
control action by the engine.

It is conservative by design:
  * only proposes when there is a restoration (isolation-only / load-shed is never
    proposed automatically);
  * de-duplicates against an already open/recent automation FLISR for the same fault;
  * auto-mode is bounded — `require_restores_all` and a `max_customers` ceiling — so a
    large or partial event falls back to human disposition.

Every proposal still runs through the full governed lifecycle (two-person/flag for
auto, OC-3 transactional switching, audit).
"""
from fastapi import HTTPException

import common
from routers.automation import AutomationPolicy, register_policy
from routers.dms import plan_flisr


class FlisrAutoPolicy(AutomationPolicy):
    kind = "flisr"

    def evaluate(self, policy: dict) -> list[dict]:
        pid = policy["policy_id"]
        cases = common.query_all(
            "SELECT case_id, affected_node_id, customers_affected FROM outage_cases "
            "WHERE status IN ('DETECTED','CONFIRMED') AND affected_node_id IS NOT NULL "
            "ORDER BY detected_at")
        proposals = []
        for c in cases:
            fn = c["affected_node_id"]
            # de-dup: skip if an automation FLISR for this fault is open or just executed.
            dup = common.query_one(
                "SELECT 1 FROM control_actions WHERE action_type='flisr' AND target=%s "
                "AND requested_by=%s AND (status IN ('PENDING','APPROVED') "
                "  OR (status='EXECUTED' AND executed_at > now() - interval '10 minutes')) LIMIT 1",
                (fn, f"automation:{pid}"))
            if dup:
                continue
            # only propose if the planner can actually restore lost load.
            try:
                p = plan_flisr(fn, None)
            except HTTPException:
                continue                      # not isolatable -> not an auto-FLISR candidate
            if not p["restored_edges"]:
                continue                      # isolation-only (load shed) is never auto-proposed
            proposals.append({
                "action_type": "flisr", "target": fn, "params": {"fault_node": fn},
                "mode": "live",
                "trigger": {"case_id": c["case_id"], "fault_node": fn,
                            "customers_affected": c["customers_affected"],
                            "restores_all": p["customers_still_out"] == 0},
                "reason": f"auto-FLISR for outage at {fn}",
            })
        return proposals

    def within_bounds(self, preview: dict, bounds: dict) -> tuple[bool, str]:
        if bounds.get("require_restores_all", True) and not preview.get("restores_all"):
            return False, "plan does not restore all affected customers"
        maxc = bounds.get("max_customers")
        restored = preview.get("customers_restored") or 0
        if maxc is not None and restored > maxc:
            return False, f"customers_restored {restored} exceeds max_customers {maxc}"
        return True, ""


register_policy("flisr", FlisrAutoPolicy())
