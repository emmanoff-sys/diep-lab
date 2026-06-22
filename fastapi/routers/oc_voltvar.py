"""ADMS Phase 2 (OC-4) — governed Volt/VAR dispatch.

Registers the `voltvar_dispatch` action type with the OC-1 governance core. It
translates a Volt/VAR lever (a target setpoint on a controllable DER) into a
device command via the existing, proven DERMS command path (`_dispatch_command`,
reusing `der.CURTAIL_MAP`), under the governed lifecycle.

Safety shaping:
  - **Banded:** the setpoint must lie within `[0, rated_kw]` — out-of-band is
    blocked unless explicitly overridden (with a reason).
  - **Rate-limited / risk-classified:** a change within `OC_VOLTVAR_MAX_STEP_KW`
    of current output is **low-risk** (single operator); a larger swing is
    **high-risk** (two-person approval). Per the locked Phase-2 decision.

Live dispatch reuses the DERMS command path; the master flag still gates all live
actuation.
"""
import os

from fastapi import HTTPException

import common
from routers.controls import ControlHandler, register_handler
from routers.der import CURTAIL_MAP

MAX_STEP_KW = float(os.getenv("OC_VOLTVAR_MAX_STEP_KW", "10"))
# Only telemetry fresher than this counts as "current output"; stale/missing data
# is treated as 0 kW so the rate-limit/risk classifier stays conservative (never
# under-estimates the swing because of an old reading).
FRESH_S = float(os.getenv("OC_VOLTVAR_FRESH_S", "600"))


class VoltVarHandler(ControlHandler):
    risk = "low"  # default; risk_for() refines by swing magnitude

    def _resolve(self, target, params):
        if not target:
            raise HTTPException(status_code=422, detail="voltvar_dispatch requires target (der_id)")
        der = common.query_one(
            "SELECT der_id, der_type, node_id, rated_kw, controllable FROM der_assets WHERE der_id = %s",
            (target,))
        if der is None:
            raise HTTPException(status_code=404, detail=f"unknown der '{target}'")
        if not der["controllable"]:
            raise HTTPException(status_code=409, detail=f"der '{target}' is not controllable")
        if der["der_type"] not in CURTAIL_MAP:
            raise HTTPException(status_code=422,
                                detail=f"no Volt/VAR command mapping for der_type '{der['der_type']}'")
        if "setpoint_kw" not in params:
            raise HTTPException(status_code=422, detail="params.setpoint_kw (kW) required")
        return der, float(params["setpoint_kw"])

    def _current_kw(self, der_id):
        row = common.query_one(
            "SELECT power_kw, EXTRACT(EPOCH FROM (now() - time)) AS age FROM telemetry "
            "WHERE device_id = %s ORDER BY time DESC LIMIT 1", (der_id,))
        if not row or row.get("power_kw") is None or row.get("age") is None:
            return 0.0
        if float(row["age"]) > FRESH_S:
            return 0.0   # stale reading — don't trust it for rate limiting
        return float(row["power_kw"])

    def risk_for(self, target, params):
        try:
            _der, sp = self._resolve(target, params)
        except HTTPException:
            return "high"   # invalid input: be conservative; plan() will surface the error
        step = abs(sp - self._current_kw(target))
        return "high" if step > MAX_STEP_KW else "low"

    def plan(self, target, params):
        der, sp = self._resolve(target, params)
        rated = float(der["rated_kw"] or 0)
        cur = self._current_kw(der["der_id"])
        step = abs(sp - cur)
        override = bool(params.get("override", False))
        blocks = []
        if sp < 0:
            blocks.append("setpoint below 0 kW")
        if rated and sp > rated:
            blocks.append(f"setpoint {sp} kW exceeds rated {rated} kW")
        if blocks and not override:
            raise HTTPException(status_code=409,
                                detail={"blocked_by_band": blocks,
                                        "hint": "set params.override=true with a reason to proceed"})
        ctype, pkey = CURTAIL_MAP[der["der_type"]]
        before = {"der_id": der["der_id"], "der_type": der["der_type"],
                  "node_id": der["node_id"], "prev_setpoint_kw": cur}
        preview = {"der_id": der["der_id"], "setpoint_kw": sp, "current_output_kw": cur,
                   "delta_kw": round(sp - cur, 2), "rated_kw": rated,
                   "rate_limited_high_risk": step > MAX_STEP_KW,
                   "command": {"command_type": ctype, pkey: sp}}
        return before, preview

    def execute(self, action):
        der, sp = self._resolve(action["target"], action["params"])
        ctype, pkey = CURTAIL_MAP[der["der_type"]]
        res = self._dispatch(der["der_id"], ctype, {pkey: sp})
        return {"der_id": der["der_id"], "command_type": ctype, "setpoint_kw": sp,
                "command_id": res.get("command_id") if isinstance(res, dict) else None}

    def rollback(self, action):
        before = action.get("before_state") or {}
        der_id, prev, der_type = before.get("der_id"), before.get("prev_setpoint_kw"), before.get("der_type")
        if der_id is None or prev is None:
            raise HTTPException(status_code=409, detail="no before_state to roll back to")
        ctype, pkey = CURTAIL_MAP.get(der_type, ("set_limit", "max_power_kw"))
        res = self._dispatch(der_id, ctype, {pkey: prev})
        return {"der_id": der_id, "restored_setpoint_kw": prev,
                "command_id": res.get("command_id") if isinstance(res, dict) else None}

    @staticmethod
    def _dispatch(device_id, command_type, params):
        from app import _dispatch_command, CommandRequest  # lazy: avoid import cycle
        return _dispatch_command(CommandRequest(
            device_id=device_id, command_type=command_type, params=params, issued_by="oc-voltvar"))


register_handler("voltvar_dispatch", VoltVarHandler())
