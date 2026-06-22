"""ADMS Phase 3 (P3-2) — field-device state readback & command-echo verification.

Closes the loop on governed actuation. Today a control action dispatches a command
and waits for the protocol **ack** — but a device can ACK and still fail to move (a
stuck breaker, a rejected/clamped setpoint). Echo verification reads the device's
*reported* state back from its telemetry after the command and confirms it actually
reached the commanded state, so a divergence becomes a governed FAILED (and the
handler reverts) instead of a silent model/field mismatch.

Read-only against telemetry; no actuation here. Used by oc_switch (breaker, hard
gate) and oc_voltvar (setpoint, soft gate — only enforced when the device echoes a
setpoint at all).
"""
import os
import time

import common


def echo_enabled() -> bool:
    return os.getenv("OC_VERIFY_ECHO", "true").strip().lower() in ("1", "true", "yes", "on")


ECHO_TIMEOUT_S = float(os.getenv("OC_ECHO_TIMEOUT_S", "12"))
ECHO_POLL_S = float(os.getenv("OC_ECHO_POLL_S", "0.5"))
SETPOINT_TOL_KW = float(os.getenv("OC_ECHO_SETPOINT_TOL_KW", "1.0"))


def read_device_state(device_id: str) -> dict | None:
    """Latest reported state for a device from telemetry (canonical columns +
    the metadata JSONB long tail). Returns None if the device has never reported."""
    row = common.query_one(
        "SELECT EXTRACT(EPOCH FROM time) AS ts, EXTRACT(EPOCH FROM (now()-time)) AS age, "
        "power_kw, frequency, voltage, metadata "
        "FROM telemetry WHERE device_id = %s ORDER BY time DESC LIMIT 1", (device_id,))
    if not row:
        return None
    md = row["metadata"] if isinstance(row["metadata"], dict) else {}
    gc = md.get("grid_connected")
    sp = md.get("setpoint_kw")
    return {
        "ts": float(row["ts"]), "age": float(row["age"]),
        "power_kw": row["power_kw"], "frequency": row["frequency"], "voltage": row["voltage"],
        "grid_connected": (bool(gc) if gc is not None else None),
        "mode": md.get("mode"),
        "setpoint_kw": (float(sp) if sp is not None else None),
    }


def _field_match(state: dict, field: str, want) -> bool | None:
    """Tri-state: True match / False mismatch / None field not reported by device."""
    have = state.get(field)
    if have is None:
        return None
    if field == "setpoint_kw":
        return abs(float(have) - float(want)) <= SETPOINT_TOL_KW
    return have == want


def verify_echo(device_id: str, expect: dict, *, timeout: float | None = None) -> dict:
    """Poll the device's telemetry until a reading taken AFTER verification began
    matches every field in `expect`, or until timeout.

    Result `confirmed`:
      True  — a fresh post-command reading matched all expected fields;
      False — the device reported the field(s) but never reached the commanded value
              within the timeout (a real divergence — the device did not move);
      None  — the device does not report any of the expected fields (unverifiable;
              callers may treat as a soft skip).
    """
    deadline = time.monotonic() + (timeout or ECHO_TIMEOUT_S)
    start = read_device_state(device_id)
    baseline_ts = start["ts"] if start else 0.0
    any_reported = False
    last = start
    while time.monotonic() < deadline:
        st = read_device_state(device_id)
        if st and st["ts"] > baseline_ts:           # a sample taken after we started
            last = st
            results = {f: _field_match(st, f, v) for f, v in expect.items()}
            if any(r is not None for r in results.values()):
                any_reported = True
            if all(results.get(f) is True for f in expect):
                return {"confirmed": True, "timed_out": False,
                        "observed": _summary(st), "expected": expect}
        time.sleep(ECHO_POLL_S)
    return {
        "confirmed": (False if any_reported else None),
        "timed_out": True,
        "reason": ("device reported but never reached the commanded state"
                   if any_reported else "device does not report the expected field(s)"),
        "observed": _summary(last) if last else None,
        "expected": expect,
    }


def _summary(st: dict) -> dict:
    return {"grid_connected": st.get("grid_connected"), "mode": st.get("mode"),
            "setpoint_kw": st.get("setpoint_kw"), "power_kw": st.get("power_kw"),
            "age_s": round(st.get("age", 0.0), 1)}
