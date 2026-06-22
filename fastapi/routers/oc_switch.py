"""ADMS Phase 2 (OC-2) — governed switch operations.

Registers the high-risk `switch_op` action type with the OC-1 governance core. A
switch operation opens/closes a switchable `grid_edge` in the **network model**
(the authoritative switch state) and, when the edge is device-backed
(`attrs.device_id`), also dispatches the breaker command via the existing command
path (Kafka -> dispatcher -> MQTT -> device) and waits briefly for the ack.

All of this runs *inside* the OC-1 lifecycle (request -> approve(two-person) ->
execute -> audit), gated by `OC_CONTROLS_ENABLED`. Hard interlocks are evaluated at
plan time (and re-checked at execute time) and block unless explicitly overridden:

  1. no-op            — edge already in the requested state;
  2. critical island  — opening would de-energize critical/medical customers;
  3. close-into-fault — closing would re-energize a node with an active outage;
  4. source paralleling — closing would tie two already-energized sources.
"""
import os
import time

from fastapi import HTTPException

import common
from routers.controls import ControlHandler, register_handler

ACK_TIMEOUT_S = float(os.getenv("OC_SWITCH_ACK_TIMEOUT_S", "8"))
ACK_POLL_S = 0.5
CRITICAL_PRIORITIES = ("critical", "medical")


# --- topology helpers (energization over the M1 graph) -----------------------
def _edges():
    return common.query_all(
        "SELECT edge_id, from_node, to_node, edge_type, is_switchable, normally_closed, "
        "is_closed, attrs FROM grid_edges")


def _substations():
    return [r["node_id"] for r in common.query_all(
        "SELECT node_id FROM grid_nodes WHERE node_type = 'substation'")]


def _energized(edges, flip_edge=None, flip_state=None) -> set:
    """Nodes reachable from substations over closed directed edges, optionally
    overriding one edge's closed state (to preview a switch operation)."""
    adj: dict[str, list[str]] = {}
    for e in edges:
        closed = flip_state if (flip_edge and e["edge_id"] == flip_edge) else e["is_closed"]
        if closed:
            adj.setdefault(e["from_node"], []).append(e["to_node"])
    seen = set(_substations())
    stack = list(seen)
    while stack:
        c = stack.pop()
        for n in adj.get(c, []):
            if n not in seen:
                seen.add(n)
                stack.append(n)
    return seen


def _customers_in(nodes) -> list:
    if not nodes:
        return []
    return common.query_all(
        "SELECT sp.customer_id, sp.node_id, c.priority FROM service_points sp "
        "LEFT JOIN customers c ON c.customer_id = sp.customer_id WHERE sp.node_id = ANY(%s)",
        (list(nodes),))


def _active_outage_nodes() -> set:
    return {r["affected_node_id"] for r in common.query_all(
        "SELECT DISTINCT affected_node_id FROM outage_cases "
        "WHERE status IN ('DETECTED','CONFIRMED') AND affected_node_id IS NOT NULL")}


# --- handler -----------------------------------------------------------------
class SwitchOpHandler(ControlHandler):
    risk = "high"

    def _resolve(self, target, params):
        if not target:
            raise HTTPException(status_code=422, detail="switch_op requires target (edge_id)")
        edges = _edges()
        edge = next((e for e in edges if e["edge_id"] == target), None)
        if edge is None:
            raise HTTPException(status_code=404, detail=f"unknown edge '{target}'")
        if not edge["is_switchable"]:
            raise HTTPException(status_code=409, detail=f"edge '{target}' is not switchable")
        if "close" not in params:
            raise HTTPException(status_code=422, detail="params.close (bool) required")
        return edges, edge, bool(params["close"])

    def _interlocks(self, edges, edge, want_closed):
        before = _energized(edges)
        after = _energized(edges, flip_edge=edge["edge_id"], flip_state=want_closed)
        lost, gained = before - after, after - before
        blocks = []
        if not want_closed:
            crit = [c for c in _customers_in(lost) if (c["priority"] or "") in CRITICAL_PRIORITIES]
            if crit:
                blocks.append(f"opening would island {len(crit)} critical/medical customer(s)")
        else:
            faulted = _active_outage_nodes() & gained
            if faulted:
                blocks.append(f"closing would re-energize node(s) with an active outage: {sorted(faulted)}")
            if edge["from_node"] in before and edge["to_node"] in before:
                blocks.append("closing would parallel two already-energized sources")
        return before, after, lost, gained, blocks

    def plan(self, target, params):
        edges, edge, want_closed = self._resolve(target, params)
        override = bool(params.get("override", False))
        if edge["is_closed"] == want_closed:
            raise HTTPException(status_code=409,
                                detail=f"edge already {'closed' if want_closed else 'open'} (no-op)")
        _before, _after, lost, gained, blocks = self._interlocks(edges, edge, want_closed)
        if blocks and not override:
            raise HTTPException(status_code=409,
                                detail={"blocked_by_interlocks": blocks,
                                        "hint": "set params.override=true with a reason to proceed"})
        attrs = edge["attrs"] if isinstance(edge["attrs"], dict) else {}
        before_state = {"edge_id": edge["edge_id"], "is_closed": edge["is_closed"],
                        "device_id": attrs.get("device_id")}
        preview = {
            "edge": edge["edge_id"], "from": edge["from_node"], "to": edge["to_node"],
            "set_closed": want_closed,
            "customers_lost": len(_customers_in(lost)),
            "customers_restored": len(_customers_in(gained)),
            "interlocks": blocks, "overridden": bool(blocks and override),
            "device_backed": bool(attrs.get("device_id")),
        }
        return before_state, preview

    def execute(self, action):
        target, params = action["target"], action["params"]
        # Re-check at execute time (TOCTOU): raises if now unsafe/no-op.
        self.plan(target, params)
        edges, edge, want_closed = self._resolve(target, params)
        # 1) authoritative model actuation.
        common.execute("UPDATE grid_edges SET is_closed = %s WHERE edge_id = %s",
                       (want_closed, edge["edge_id"]))
        after = {"edge_id": edge["edge_id"], "is_closed": want_closed, "model_updated": True}
        # 2) field device, if the edge is device-backed.
        attrs = edge["attrs"] if isinstance(edge["attrs"], dict) else {}
        device_id = attrs.get("device_id")
        if device_id:
            cmd = attrs.get("cmd_close" if want_closed else "cmd_open",
                            "grid_connect" if want_closed else "island")
            after["device"] = self._dispatch_and_wait(device_id, cmd)
        return after

    def rollback(self, action):
        before = action.get("before_state") or {}
        edge_id = before.get("edge_id") or action.get("target")
        prev = before.get("is_closed")
        if prev is None:
            raise HTTPException(status_code=409, detail="no before_state to roll back to")
        common.execute("UPDATE grid_edges SET is_closed = %s WHERE edge_id = %s", (prev, edge_id))
        after = {"edge_id": edge_id, "restored_is_closed": prev}
        if before.get("device_id"):
            cmd = "grid_connect" if prev else "island"
            after["device"] = self._dispatch_and_wait(before["device_id"], cmd)
        return after

    # --- device path ---------------------------------------------------------
    def _dispatch_and_wait(self, device_id, command_type):
        from app import _dispatch_command, CommandRequest  # lazy: avoid import cycle
        res = _dispatch_command(CommandRequest(
            device_id=device_id, command_type=command_type, params={}, issued_by="oc-switch"))
        command_id = res.get("command_id") if isinstance(res, dict) else None
        ack = self._poll_ack(command_id) if command_id else {"acked": False, "reason": "no command_id"}
        return {"device_id": device_id, "command_type": command_type,
                "command_id": command_id, **ack}

    @staticmethod
    def _poll_ack(command_id):
        deadline = time.monotonic() + ACK_TIMEOUT_S
        while time.monotonic() < deadline:
            row = common.query_one("SELECT status FROM commands WHERE command_id = %s", (command_id,))
            status = (row or {}).get("status")
            if status in ("ACKED", "FAILED"):
                return {"acked": status == "ACKED", "status": status, "timed_out": False}
            time.sleep(ACK_POLL_S)
        return {"acked": False, "status": "PENDING", "timed_out": True,
                "note": f"no device ack within {ACK_TIMEOUT_S}s (model state is authoritative)"}


register_handler("switch_op", SwitchOpHandler())
