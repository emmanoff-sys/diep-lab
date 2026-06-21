"""ADMS M4 — DERMS layer: formal DER registry + aggregation + dispatch.

Builds on the existing DERMS endpoints (/derms/*) and command path. Adds:
  - a unified DER registry (der_assets, bound to M1 grid_nodes),
  - fleet aggregation (rated capacity + live output, VPP-grouped),
  - dispatch / curtailment that reuse the validated command pipeline
    (_dispatch_command -> Kafka diep.commands -> dispatcher -> MQTT).

Closes the known DERMS multi-tenancy gap: dispatch here enforces tenant access.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

import common
from auth import require_role

router = APIRouter(prefix="/der", tags=["derms"])

READ_ROLES = ("viewer", "operator", "engineer", "admin", "service")
DISPATCH_ROLES = ("operator", "engineer", "admin")

# der_type -> (curtailment command_type, param key) for the curtailment helper.
CURTAIL_MAP = {
    "solar": ("set_limit", "max_power_kw"),
    "ev_charger": ("set_limit", "max_power_kw"),
    "battery": ("set_power_limit", "power_kw"),
    "microgrid": ("set_setpoint", "setpoint_kw"),
}


class DispatchRequest(BaseModel):
    der_id: str = Field(..., examples=["BAT001"])
    command_type: str = Field(..., examples=["discharge"])
    params: dict = Field(default_factory=dict)


class CurtailRequest(BaseModel):
    der_id: str = Field(..., examples=["INV001"])
    limit_kw: float = Field(..., examples=[5.0])


def _tenant_filter(principal):
    """(clause, params) scoping der_assets to the caller's tenant; global = all."""
    if principal is None or principal.tenant is None:
        return "", []
    return "WHERE da.tenant_id = %s", [principal.tenant]


def _assert_tenant(principal, der_id: str):
    if principal is None or principal.tenant is None:
        return
    row = common.query_one("SELECT tenant_id FROM der_assets WHERE der_id = %s", (der_id,))
    if row is not None and row["tenant_id"] != principal.tenant:
        raise HTTPException(status_code=403, detail=f"DER '{der_id}' belongs to another tenant")


def _output_kw(der_type: str, power_kw, solar_kw) -> float:
    if der_type == "solar":
        return float(solar_kw if solar_kw is not None else (power_kw or 0.0))
    return float(power_kw or 0.0)


def _fleet_rows(principal, vpp_group: str | None):
    clause, params = _tenant_filter(principal)
    if vpp_group:
        clause = (clause + " AND " if clause else "WHERE ") + "da.vpp_group = %s"
        params.append(vpp_group)
    return common.query_all(
        "SELECT da.der_id, da.der_type, da.node_id, da.rated_kw, da.rated_kwh, da.controllable, "
        "da.vpp_group, da.tenant_id, t.power_kw, t.solar_kw, t.age "
        "FROM der_assets da "
        "LEFT JOIN LATERAL (SELECT power_kw, solar_kw, EXTRACT(EPOCH FROM (now()-time)) AS age "
        "  FROM telemetry WHERE device_id = da.der_id ORDER BY time DESC LIMIT 1) t ON TRUE "
        f"{clause} ORDER BY da.der_id", tuple(params))


@router.get("/assets")
def list_der(vpp_group: str | None = None, principal=Depends(require_role(*READ_ROLES))):
    rows = _fleet_rows(principal, vpp_group)
    out = []
    for r in rows:
        fresh = r["age"] is not None and float(r["age"]) <= 600
        out.append({
            "der_id": r["der_id"], "der_type": r["der_type"], "node_id": r["node_id"],
            "rated_kw": r["rated_kw"], "rated_kwh": r["rated_kwh"],
            "controllable": r["controllable"], "vpp_group": r["vpp_group"],
            "output_kw": round(_output_kw(r["der_type"], r["power_kw"], r["solar_kw"]), 2) if fresh else None,
            "online": fresh,
        })
    return {"der_assets": out}


@router.get("/fleet")
def fleet(vpp_group: str | None = None, principal=Depends(require_role(*READ_ROLES))):
    rows = _fleet_rows(principal, vpp_group)
    by_type: dict[str, dict] = {}
    total_rated = total_kwh = total_output = 0.0
    online = 0
    for r in rows:
        fresh = r["age"] is not None and float(r["age"]) <= 600
        out = _output_kw(r["der_type"], r["power_kw"], r["solar_kw"]) if fresh else 0.0
        total_rated += r["rated_kw"] or 0.0
        total_kwh += r["rated_kwh"] or 0.0
        total_output += out
        online += 1 if fresh else 0
        b = by_type.setdefault(r["der_type"], {"count": 0, "rated_kw": 0.0, "output_kw": 0.0})
        b["count"] += 1
        b["rated_kw"] += r["rated_kw"] or 0.0
        b["output_kw"] += out
    return {
        "vpp_group": vpp_group,
        "der_count": len(rows),
        "online": online,
        "total_rated_kw": round(total_rated, 2),
        "total_storage_kwh": round(total_kwh, 2),
        "total_output_kw": round(total_output, 2),
        "by_type": {k: {"count": v["count"], "rated_kw": round(v["rated_kw"], 2),
                        "output_kw": round(v["output_kw"], 2)} for k, v in by_type.items()},
    }


def _dispatch(der_id: str, command_type: str, params: dict):
    # Lazy import: app.py imports this router at load, so importing app at module
    # scope would cycle. By call time app is fully initialised.
    from app import _dispatch_command, CommandRequest
    return _dispatch_command(CommandRequest(
        device_id=der_id, command_type=command_type, params=params, issued_by="derms"))


@router.post("/dispatch", status_code=202)
def dispatch(body: DispatchRequest, principal=Depends(require_role(*DISPATCH_ROLES))):
    der = common.query_one("SELECT * FROM der_assets WHERE der_id = %s", (body.der_id,))
    if der is None:
        raise HTTPException(status_code=404, detail=f"unknown DER '{body.der_id}'")
    if not der["controllable"]:
        raise HTTPException(status_code=409, detail=f"DER '{body.der_id}' is not controllable")
    _assert_tenant(principal, body.der_id)
    return _dispatch(body.der_id, body.command_type, body.params)


@router.post("/curtailment", status_code=202)
def curtailment(body: CurtailRequest, principal=Depends(require_role(*DISPATCH_ROLES))):
    der = common.query_one("SELECT * FROM der_assets WHERE der_id = %s", (body.der_id,))
    if der is None:
        raise HTTPException(status_code=404, detail=f"unknown DER '{body.der_id}'")
    if der["der_type"] not in CURTAIL_MAP:
        raise HTTPException(status_code=422, detail=f"cannot curtail der_type '{der['der_type']}'")
    _assert_tenant(principal, body.der_id)
    command_type, param_key = CURTAIL_MAP[der["der_type"]]
    return _dispatch(body.der_id, command_type, {param_key: body.limit_kw})
