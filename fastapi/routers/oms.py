"""ADMS M2 — Outage Management System (OMS).

Infers outage cases from three signals and resolves impact through the M1
network model:
  - "last gasp": a meter's latest telemetry has state='LAST_GASP' (dying-gasp
    published by the smart-meter simulator on power loss / remote disconnect),
  - heartbeat gap: a meter that has reported before but not within the timeout,
  - manual reports: customer calls captured by the Call Handler.

Affected customers are resolved by walking up to the nearest switch-fed section
(the FLISR-isolatable unit) and counting service_points downstream of it
(common.downstream_node_ids) — no metadata duplicated from M1.

Reuses common.* and auth.require_role, matching app.py style.
"""
import os
import uuid

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

import common
from auth import require_role
from routers.dms import (  # P6: reuse M1 loaders
    _se_nodes, _se_edges, _customers_by_node, _pf_loads, _lastgasp_load_floor,
    _se_measurements)
from dms import outage_inference as oi  # P6-M7 outage inference (pure engine)
from dms import state_estimation as se  # P6 follow-up: M2 SE corroboration

# A node is treated as "SE-dead" (de-energized) when state estimation marks it
# unenergized or estimates its voltage below this per-unit floor.
SE_DEAD_PU = float(os.getenv("OMS_SE_DEAD_PU", "0.5"))
from dms import contingency as ct  # P6-M8 reuse M5 N-1
from dms import outage_validation as ov  # P6-M8 validation hooks
from dms import crew_dispatch as cd  # P6-M9 crew dispatch recommendation

router = APIRouter(prefix="/oms", tags=["oms"])

READ_ROLES = ("viewer", "operator", "engineer", "admin", "service")
WRITE_ROLES = ("operator", "engineer", "admin")
DETECT_ROLES = ("operator", "engineer", "admin", "service")

HEARTBEAT_TIMEOUT_S = int(os.getenv("OMS_HEARTBEAT_TIMEOUT_S", "180"))
OPEN_STATUSES = ("DETECTED", "CONFIRMED")


# --- schemas -----------------------------------------------------------------
class CallReport(BaseModel):
    customer_id: str | None = Field(None, examples=["CUST-001"])
    meter_device_id: str | None = Field(None, examples=["METER001"])
    node_id: str | None = None
    caller_name: str | None = None
    caller_phone: str | None = None
    description: str | None = Field(None, examples=["No power since 14:00"])


class CaseUpdate(BaseModel):
    status: str | None = None  # CONFIRMED | RESTORED | CLOSED
    notes: str | None = None


class ManualCase(BaseModel):
    affected_node_id: str
    cause: str = "manual"
    notes: str | None = None


# --- topology helpers (read from M1) -----------------------------------------
def _meter_node(meter_device_id: str) -> str | None:
    row = common.query_one(
        "SELECT node_id FROM grid_nodes WHERE device_id = %s AND node_type = 'meter'",
        (meter_device_id,),
    )
    if row:
        return row["node_id"]
    row = common.query_one(
        "SELECT node_id FROM service_points WHERE meter_device_id = %s LIMIT 1",
        (meter_device_id,),
    )
    return row["node_id"] if row else None


def _section_root(node_id: str) -> str:
    """Nearest upstream node fed by a switchable edge (the isolatable section),
    or node_id itself if none — the unit OMS attributes an outage to."""
    parent = {n["node_id"]: n["parent_id"]
              for n in common.query_all("SELECT node_id, parent_id FROM grid_nodes")}
    switch_fed = {e["to_node"]
                  for e in common.query_all("SELECT to_node FROM grid_edges WHERE is_switchable = TRUE")}
    cur, seen = node_id, set()
    while cur is not None and cur not in seen:
        seen.add(cur)
        if cur in switch_fed:
            return cur
        cur = parent.get(cur)
    return node_id


def _section_service_points(node_id: str) -> list[dict]:
    reachable = common.downstream_node_ids(node_id, energized_only=False)
    return common.query_all(
        "SELECT sp.service_point_id, sp.customer_id, sp.node_id, sp.meter_device_id, "
        "c.name, c.priority FROM service_points sp "
        "LEFT JOIN customers c ON c.customer_id = sp.customer_id "
        "WHERE sp.node_id = ANY(%s)",
        (reachable,),
    )


def _node_name(node_id: str | None) -> str | None:
    if not node_id:
        return None
    row = common.query_one("SELECT name, site_name FROM grid_nodes WHERE node_id = %s", (node_id,))
    if not row:
        return node_id
    return row.get("name") or row.get("site_name") or node_id


# --- detection ---------------------------------------------------------------
def _open_case_for_node(node_id: str) -> dict | None:
    return common.query_one(
        "SELECT * FROM outage_cases WHERE affected_node_id = %s AND status = ANY(%s) "
        "ORDER BY detected_at DESC LIMIT 1",
        (node_id, list(OPEN_STATUSES)),
    )


def _meters_out() -> dict:
    """Map meter_device_id -> cause for meters currently showing outage signals."""
    out: dict[str, str] = {}
    meters = common.query_all("SELECT device_id FROM devices WHERE device_type = 'smartmeter'")
    for m in meters:
        dev = m["device_id"]
        latest = common.query_one(
            "SELECT state, EXTRACT(EPOCH FROM (now() - time)) AS age "
            "FROM telemetry WHERE device_id = %s ORDER BY time DESC LIMIT 1",
            (dev,),
        )
        if latest is None:
            continue  # never reported — skip to avoid cold-start false positives
        state = (latest.get("state") or "").upper()
        age = float(latest.get("age") or 0)
        if state == "LAST_GASP":
            out[dev] = "last_gasp"
        elif age > HEARTBEAT_TIMEOUT_S:
            out[dev] = "heartbeat"
    return out


def _meter_is_back(meter_device_id: str) -> bool:
    latest = common.query_one(
        "SELECT state, EXTRACT(EPOCH FROM (now() - time)) AS age "
        "FROM telemetry WHERE device_id = %s ORDER BY time DESC LIMIT 1",
        (meter_device_id,),
    )
    if latest is None:
        return False
    state = (latest.get("state") or "").upper()
    age = float(latest.get("age") or 0)
    return state != "LAST_GASP" and age <= HEARTBEAT_TIMEOUT_S


def _upsert_case(node_id: str, meters: dict, causes: set) -> tuple[dict, bool]:
    """Create or update the open case for a section node. meters: {dev: meter_node}."""
    cause = "mixed" if len(causes) > 1 else (next(iter(causes)) if causes else "unknown")
    sps = _section_service_points(node_id)
    customers_affected = len(sps)
    existing = _open_case_for_node(node_id)
    if existing:
        common.execute(
            "UPDATE outage_cases SET customers_affected = %s, cause = %s WHERE case_id = %s",
            (customers_affected, cause, existing["case_id"]),
        )
        case_id, created = existing["case_id"], False
    else:
        case_id = str(uuid.uuid4())
        common.execute(
            "INSERT INTO outage_cases (case_id, status, cause, affected_node_id, customers_affected, "
            "network_model_version) VALUES (%s, 'DETECTED', %s, %s, %s, %s)",
            (case_id, cause, node_id, customers_affected, common.current_model_version()),
        )
        created = True
    for dev, mnode in meters.items():
        common.execute(
            "INSERT INTO outage_case_meters (case_id, meter_device_id, node_id) VALUES (%s, %s, %s) "
            "ON CONFLICT (case_id, meter_device_id) DO NOTHING",
            (case_id, dev, mnode),
        )
    return common.query_one("SELECT * FROM outage_cases WHERE case_id = %s", (case_id,)), created


def _run_detection() -> dict:
    """One detection sweep: open/extend cases from current signals, link new
    reports, and auto-restore cases whose meters are all back."""
    # 1. group outage signals by network section.
    groups: dict[str, dict] = {}

    def _add(node_id, dev, mnode, cause):
        g = groups.setdefault(node_id, {"meters": {}, "causes": set()})
        if dev:
            g["meters"][dev] = mnode
        g["causes"].add(cause)

    for dev, cause in _meters_out().items():
        mnode = _meter_node(dev)
        root = _section_root(mnode) if mnode else dev
        _add(root, dev, mnode, cause)

    new_reports = common.query_all("SELECT * FROM outage_reports WHERE status = 'NEW'")
    for r in new_reports:
        mnode = r.get("node_id") or (_meter_node(r["meter_device_id"]) if r.get("meter_device_id") else None)
        if mnode is None and r.get("customer_id"):
            sp = common.query_one("SELECT node_id FROM service_points WHERE customer_id = %s LIMIT 1",
                                  (r["customer_id"],))
            mnode = sp["node_id"] if sp else None
        root = _section_root(mnode) if mnode else (r.get("node_id") or "UNKNOWN")
        _add(root, r.get("meter_device_id"), mnode, "manual")

    created, updated = [], []
    for node_id, g in groups.items():
        if node_id == "UNKNOWN":
            continue
        case, was_created = _upsert_case(node_id, g["meters"], g["causes"])
        (created if was_created else updated).append(case["case_id"])

    # 2. link NEW reports to the open case covering their section.
    for r in new_reports:
        mnode = r.get("node_id") or (_meter_node(r["meter_device_id"]) if r.get("meter_device_id") else None)
        if mnode is None and r.get("customer_id"):
            sp = common.query_one("SELECT node_id FROM service_points WHERE customer_id = %s LIMIT 1",
                                  (r["customer_id"],))
            mnode = sp["node_id"] if sp else None
        root = _section_root(mnode) if mnode else None
        case = _open_case_for_node(root) if root else None
        if case:
            common.execute(
                "UPDATE outage_reports SET status = 'LINKED', case_id = %s WHERE report_id = %s",
                (case["case_id"], r["report_id"]),
            )
            # a corroborated case is CONFIRMED.
            if case["status"] == "DETECTED":
                common.execute(
                    "UPDATE outage_cases SET status = 'CONFIRMED', confirmed_at = now(), cause = "
                    "CASE WHEN cause = 'manual' THEN 'manual' ELSE 'mixed' END WHERE case_id = %s",
                    (case["case_id"],),
                )

    # 3. auto-restore: open cases whose attached meters are all back online.
    restored = []
    for case in common.query_all("SELECT * FROM outage_cases WHERE status = ANY(%s)", (list(OPEN_STATUSES),)):
        meters = common.query_all("SELECT meter_device_id FROM outage_case_meters WHERE case_id = %s",
                                  (case["case_id"],))
        if meters and all(_meter_is_back(m["meter_device_id"]) for m in meters):
            common.execute("UPDATE outage_cases SET status = 'RESTORED', restored_at = now() WHERE case_id = %s",
                           (case["case_id"],))
            restored.append(case["case_id"])

    return {"created": created, "updated": updated, "restored": restored,
            "signals": {"meters_out": list(_meters_out().keys()), "new_reports": len(new_reports)}}


# --- endpoints ---------------------------------------------------------------
@router.post("/detect")
def detect(_p=Depends(require_role(*DETECT_ROLES))):
    """Run one outage-detection sweep. Safe to call repeatedly (idempotent on
    open cases); driven by oms/outage_detector.py on an interval in production."""
    return _run_detection()


@router.post("/call", status_code=201)
def call_handler(report: CallReport, _p=Depends(require_role(*WRITE_ROLES))):
    """Call Handler — record a customer-reported outage, then correlate it."""
    report_id = str(uuid.uuid4())
    common.execute(
        "INSERT INTO outage_reports (report_id, customer_id, meter_device_id, node_id, "
        "caller_name, caller_phone, description) VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (report_id, report.customer_id, report.meter_device_id, report.node_id,
         report.caller_name, report.caller_phone, report.description),
    )
    detection = _run_detection()
    row = common.query_one("SELECT * FROM outage_reports WHERE report_id = %s", (report_id,))
    return {"report": row, "detection": detection}


def _case_detail(case: dict) -> dict:
    case = dict(case)
    case["affected_node_name"] = _node_name(case.get("affected_node_id"))
    case["meters"] = common.query_all(
        "SELECT meter_device_id, node_id FROM outage_case_meters WHERE case_id = %s", (case["case_id"],))
    case["reports"] = common.query_all(
        "SELECT report_id, customer_id, caller_name, status, created_at "
        "FROM outage_reports WHERE case_id = %s ORDER BY created_at", (case["case_id"],))
    return case


@router.get("/cases")
def list_cases(status: str | None = None, _p=Depends(require_role(*READ_ROLES))):
    if status:
        rows = common.query_all("SELECT * FROM outage_cases WHERE status = %s ORDER BY detected_at DESC",
                                (status.upper(),))
    else:
        rows = common.query_all("SELECT * FROM outage_cases ORDER BY detected_at DESC")
    return {"cases": [{**r, "affected_node_name": _node_name(r["affected_node_id"])} for r in rows]}


@router.get("/cases/{case_id}")
def get_case(case_id: str, _p=Depends(require_role(*READ_ROLES))):
    case = common.query_one("SELECT * FROM outage_cases WHERE case_id = %s", (case_id,))
    if case is None:
        raise HTTPException(status_code=404, detail=f"unknown case '{case_id}'")
    return _case_detail(case)


@router.post("/cases", status_code=201)
def create_case(body: ManualCase, _p=Depends(require_role(*WRITE_ROLES))):
    if common.query_one("SELECT 1 FROM grid_nodes WHERE node_id = %s", (body.affected_node_id,)) is None:
        raise HTTPException(status_code=404, detail=f"unknown node '{body.affected_node_id}'")
    case_id = str(uuid.uuid4())
    customers = len(_section_service_points(body.affected_node_id))
    common.execute(
        "INSERT INTO outage_cases (case_id, status, cause, affected_node_id, customers_affected, notes, "
        "network_model_version) VALUES (%s, 'CONFIRMED', %s, %s, %s, %s, %s)",
        (case_id, body.cause, body.affected_node_id, customers, body.notes,
         common.current_model_version()),
    )
    common.execute("UPDATE outage_cases SET confirmed_at = now() WHERE case_id = %s", (case_id,))
    return _case_detail(common.query_one("SELECT * FROM outage_cases WHERE case_id = %s", (case_id,)))


@router.patch("/cases/{case_id}")
def update_case(case_id: str, body: CaseUpdate, _p=Depends(require_role(*WRITE_ROLES))):
    case = common.query_one("SELECT * FROM outage_cases WHERE case_id = %s", (case_id,))
    if case is None:
        raise HTTPException(status_code=404, detail=f"unknown case '{case_id}'")
    sets, params = [], []
    if body.status:
        st = body.status.upper()
        if st not in ("DETECTED", "CONFIRMED", "RESTORED", "CLOSED"):
            raise HTTPException(status_code=422, detail=f"invalid status '{body.status}'")
        sets.append("status = %s")
        params.append(st)
        stamp = {"CONFIRMED": "confirmed_at", "RESTORED": "restored_at", "CLOSED": "closed_at"}.get(st)
        if stamp:
            sets.append(f"{stamp} = now()")
    if body.notes is not None:
        sets.append("notes = %s")
        params.append(body.notes)
    if sets:
        params.append(case_id)
        common.execute(f"UPDATE outage_cases SET {', '.join(sets)} WHERE case_id = %s", tuple(params))
    return _case_detail(common.query_one("SELECT * FROM outage_cases WHERE case_id = %s", (case_id,)))


@router.get("/reports")
def list_reports(status: str | None = None, _p=Depends(require_role(*READ_ROLES))):
    if status:
        rows = common.query_all("SELECT * FROM outage_reports WHERE status = %s ORDER BY created_at DESC",
                                (status.upper(),))
    else:
        rows = common.query_all("SELECT * FROM outage_reports ORDER BY created_at DESC")
    return {"reports": rows}


@router.get("/outages")
def active_outages(_p=Depends(require_role(*READ_ROLES))):
    """Active (open) outage cases with location + impact, for the OMS map."""
    rows = common.query_all(
        "SELECT oc.*, n.name AS node_name, n.latitude, n.longitude, n.site_name "
        "FROM outage_cases oc LEFT JOIN grid_nodes n ON n.node_id = oc.affected_node_id "
        "WHERE oc.status = ANY(%s) ORDER BY oc.detected_at DESC", (list(OPEN_STATUSES),))
    return {"active": rows, "count": len(rows),
            "customers_impacted": sum(r["customers_affected"] for r in rows)}


# --- P6-M7: outage detection / inference -------------------------------------
def _dark_meter_nodes() -> list[str]:
    """Grid nodes of meters currently showing outage signals (last-gasp/heartbeat)."""
    out = []
    for dev in _meters_out():
        nd = _meter_node(dev)
        if nd:
            out.append(nd)
    return out


def _se_dead_nodes(nodes: list[dict], edges: list[dict]) -> list[str] | None:
    """Nodes M2 state estimation reads as de-energized / dead-voltage — a secondary
    corroboration signal for M7. Returns None (and the caller degrades gracefully) if
    SE can't run, so outage inference never depends on it. NOTE: SE marks a node dead
    when the model shows it unenergized (a protective device opened, reflected in
    SCADA topology) or estimates a genuine deep voltage collapse — it does NOT trust a
    bare last-gasp on an otherwise-closed model."""
    try:
        est = se.estimate(nodes, edges, _se_measurements(nodes))
    except Exception:  # noqa: BLE001 — SE is best-effort corroboration only
        return None
    dead = []
    for n in est["nodes"]:
        v = n.get("estimated_voltage_pu")
        if n.get("energized") is False or (v is not None and v < SE_DEAD_PU):
            dead.append(n["node_id"])
    return dead


@router.get("/outage/infer")
def outage_infer(_p=Depends(require_role(*READ_ROLES))):
    """Infer probable failed device(s) + full affected-customer estimate from AMI
    last-gasp/heartbeat signals over the M1 network model, corroborated (secondarily)
    by M2 state estimation (P6-M7)."""
    dark = _dark_meter_nodes()
    nodes, edges, cust = _se_nodes(), _se_edges(), _customers_by_node()
    se_dead = _se_dead_nodes(nodes, edges)
    try:
        result = oi.infer(nodes, edges, dark, cust, se_dead_nodes=se_dead)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=f"outage inference failed: {exc}")
    result["dark_meter_nodes"] = sorted(dark)
    result["se_available"] = se_dead is not None
    return result


def _infer_and_n1() -> tuple[list[dict], list[dict]]:
    """M7 inference + M5 N-1 over the current model/signals (shared by M8/M9)."""
    nodes, edges = _se_nodes(), _se_edges()
    cust = _customers_by_node()
    dark = _dark_meter_nodes()
    inferred = oi.infer(nodes, edges, dark, cust)["inferred_outages"]
    contingencies = ct.analyze(nodes, edges, _pf_loads(nodes), cust,
                               load_floor=_lastgasp_load_floor())["contingencies"]
    return inferred, contingencies


@router.get("/outage/validate")
def outage_validate(_p=Depends(require_role(*READ_ROLES))):
    """Cross-check M7 outage inference against the M5 N-1 contingency model and flag
    inconsistencies (does not auto-resolve) (P6-M8)."""
    try:
        inferred, contingencies = _infer_and_n1()
        return ov.cross_check(inferred, contingencies)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=f"outage validation failed: {exc}")


@router.get("/crew/recommend")
def crew_recommend(_p=Depends(require_role(*READ_ROLES))):
    """Prioritized crew-dispatch recommendation by customers affected + restoration
    complexity (tie availability from M5). Read-only — no actuation/ticketing (P6-M9)."""
    try:
        inferred, contingencies = _infer_and_n1()
        return cd.recommend(inferred, contingencies)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=f"crew recommendation failed: {exc}")


@router.get("/kpis")
def kpis(window_hours: int = 24, _p=Depends(require_role(*READ_ROLES))):
    """OMS KPIs + SAIDI/SAIFI placeholders over a rolling window."""
    window_hours = min(max(window_hours, 1), 24 * 30)
    total_sp = common.query_one("SELECT COUNT(*) AS n FROM service_points")["n"] or 0
    call_volume = common.query_one(
        "SELECT COUNT(*) AS n FROM outage_reports WHERE created_at > now() - make_interval(hours => %s)",
        (window_hours,))["n"]
    active = common.query_one(
        "SELECT COUNT(*) AS n, COALESCE(SUM(customers_affected),0) AS c "
        "FROM outage_cases WHERE status = ANY(%s)", (list(OPEN_STATUSES),))
    restored = common.query_one(
        "SELECT COUNT(*) AS n, COALESCE(AVG(EXTRACT(EPOCH FROM (restored_at - detected_at))/60.0),0) AS avg_min "
        "FROM outage_cases WHERE restored_at > now() - make_interval(hours => %s)", (window_hours,))
    # SAIFI ~ customer-interruptions / customers served; SAIDI ~ customer-minutes / customers served.
    ci = common.query_one(
        "SELECT COALESCE(SUM(customers_affected),0) AS interruptions, "
        "COALESCE(SUM(customers_affected * EXTRACT(EPOCH FROM "
        "(COALESCE(restored_at, now()) - detected_at))/60.0),0) AS customer_minutes "
        "FROM outage_cases WHERE detected_at > now() - make_interval(hours => %s)", (window_hours,))
    saifi = (ci["interruptions"] / total_sp) if total_sp else 0.0
    saidi_min = (ci["customer_minutes"] / total_sp) if total_sp else 0.0
    return {
        "window_hours": window_hours,
        "total_service_points": total_sp,
        "call_volume": call_volume,
        "active_outages": active["n"],
        "customers_impacted": active["c"],
        "avg_restoration_minutes": round(float(restored["avg_min"]), 1),
        "restored_in_window": restored["n"],
        "saifi": round(saifi, 4),
        "saidi_minutes": round(saidi_min, 2),
        "note": "SAIDI/SAIFI are placeholders computed from outage_cases over the window.",
    }


# --- public (no auth) --------------------------------------------------------
@router.get("/public/outages")
def public_outages():
    """Public-facing outage status by area. No auth, no PII — area name, status,
    customers affected, and time reported only."""
    rows = common.query_all(
        "SELECT oc.status, oc.customers_affected, oc.detected_at, "
        "COALESCE(n.name, n.site_name, oc.affected_node_id) AS area "
        "FROM outage_cases oc LEFT JOIN grid_nodes n ON n.node_id = oc.affected_node_id "
        "WHERE oc.status = ANY(%s) ORDER BY oc.detected_at DESC", (list(OPEN_STATUSES),))
    return {
        "outages": rows,
        "active_outages": len(rows),
        "customers_affected": sum(r["customers_affected"] for r in rows),
        "as_of": None,  # set by client; server stays cache-friendly
    }
