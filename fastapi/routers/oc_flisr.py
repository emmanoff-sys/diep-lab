"""ADMS Phase 2 (OC-3) — governed FLISR execution.

Registers the high-risk `flisr` action type with the OC-1 governance core. It
reuses the read-only DMS planner (`dms.plan_flisr`) to compute the isolation +
restoration switch sequence, then — under request -> two-person approve -> execute
-> audit — applies that sequence to the network model **transactionally**: any
failure mid-sequence reverts every switch already moved. Rollback restores the
pre-FLISR switch state captured at plan time.

The planner is inherently safe (it refuses to re-energize the faulted node and
will not back-feed through it); the governance adds approval, audit, the flag
gate, and atomic revert on top.
"""
import json
import uuid

from fastapi import HTTPException

import common
from routers.controls import ControlHandler, register_handler
from routers.dms import plan_flisr


class FlisrHandler(ControlHandler):
    risk = "high"

    def _plan(self, target, params):
        # target carries the fault node (params may override / supply a fault edge).
        fault_node = params.get("fault_node") or target
        fault_edge = params.get("fault_edge")
        return plan_flisr(fault_node, fault_edge)

    def plan(self, target, params):
        p = self._plan(target, params)
        before = {"switches": p["before_switch_state"]}
        preview = {k: p[k] for k in (
            "fault_node", "fault_edge", "isolated_edges", "restored_edges",
            "customers_lost", "customers_restored", "customers_still_out",
            "still_out_nodes", "steps")}
        preview["restores_all"] = p["customers_still_out"] == 0
        return before, preview

    def execute(self, action):
        p = self._plan(action["target"], action["params"])      # re-plan (TOCTOU)
        before = (action.get("before_state") or {}).get("switches") or p["before_switch_state"]
        applied = []
        try:
            # open the isolating switch, then close the restoring tie(s).
            common.execute("UPDATE grid_edges SET is_closed = FALSE WHERE edge_id = %s",
                           (p["isolated_edge"],))
            applied.append(p["isolated_edge"])
            for eid in p["restored_edges"]:
                common.execute("UPDATE grid_edges SET is_closed = TRUE WHERE edge_id = %s", (eid,))
                applied.append(eid)
        except Exception:
            # transactional abort: revert every switch already moved to its prior state.
            for eid in applied:
                prev = before.get(eid)
                if prev is not None:
                    common.execute("UPDATE grid_edges SET is_closed = %s WHERE edge_id = %s", (prev, eid))
            raise

        event_id = str(uuid.uuid4())
        steps = list(p["steps"]) + ["executed via governed /controls flisr action"]
        common.execute(
            "INSERT INTO flisr_events (event_id, fault_node, fault_edge, isolated_edges, restored_edges, "
            "customers_lost, customers_restored, executed, steps, network_model_version) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (event_id, p["fault_node"], p["fault_edge"], json.dumps(p["isolated_edges"]),
             json.dumps(p["restored_edges"]), p["customers_lost"], p["customers_restored"],
             True, json.dumps(steps), common.current_model_version()),
        )
        return {
            "flisr_event_id": event_id,
            "isolated_edges": p["isolated_edges"],
            "restored_edges": p["restored_edges"],
            "customers_restored": p["customers_restored"],
            "customers_still_out": p["customers_still_out"],
            "switches_moved": applied,
        }

    def rollback(self, action):
        before = (action.get("before_state") or {}).get("switches") or {}
        if not before:
            raise HTTPException(status_code=409, detail="no before_state to roll back to")
        restored = {}
        for eid, prev in before.items():
            common.execute("UPDATE grid_edges SET is_closed = %s WHERE edge_id = %s", (prev, eid))
            restored[eid] = prev
        return {"restored_switches": restored}


register_handler("flisr", FlisrHandler())
