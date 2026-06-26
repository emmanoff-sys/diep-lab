"""CIM REST API -- the FastAPI app + every route. Kept as a single module:
this app is small enough (12 resource types x list/detail + one export
endpoint + health/metrics) that splitting now would be premature, the same
"monolith by necessity, not by accident" precedent as fastapi/app.py at
its current size.

Every route is tenant-filtered via `auth.require_principal` -- see
auth.py for why this doesn't reuse fastapi/auth.py.
"""
from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response

from . import auth, schemas, validation
from .config import Settings
from .mapping import assets as mapping_assets
from .mapping import devices as mapping_devices
from .mapping import measurements as mapping_measurements
from .mapping import metering as mapping_metering
from .mapping import network as mapping_network
from .metrics import CimMetrics
from .serialization import json_export, profiles, xml_export

app = FastAPI(title="DIEP CIM / IEC 61968 Interoperability Layer", version="1.0")
metrics = CimMetrics()


def _limit_offset(limit: int = Query(Settings.DEFAULT_LIMIT, ge=1),
                   offset: int = Query(0, ge=0)) -> tuple[int, int]:
    return validation.validate_limit(limit, Settings.MAX_LIMIT), offset


@app.exception_handler(validation.CimValidationError)
def _handle_validation_error(request, exc: validation.CimValidationError):
    return Response(
        content=f'{{"error": "{exc.reason}", "detail": "{exc.detail}"}}',
        status_code=400, media_type="application/json",
    )


@app.get("/health")
def health() -> dict:
    return {"status": "UP", "service": "cim"}


@app.get("/metrics")
def metrics_endpoint():
    try:
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    except ImportError:
        return PlainTextResponse("prometheus_client not installed", status_code=503)
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# --- EndDevice / Meter -------------------------------------------------

@app.get("/cim/end-devices", response_model=list[schemas.EndDeviceOut])
def list_end_devices(device_type: str | None = None, site_name: str | None = None,
                      lo: tuple[int, int] = Depends(_limit_offset),
                      principal: auth.CimPrincipal = Depends(auth.require_principal)):
    limit, offset = lo
    return mapping_devices.list_end_devices(
        tenant_id=principal.tenant_id, device_type=device_type, site_name=site_name, limit=limit, offset=offset,
    )


@app.get("/cim/end-devices/{device_id}", response_model=schemas.EndDeviceOut)
def get_end_device(device_id: str, principal: auth.CimPrincipal = Depends(auth.require_principal)):
    obj = mapping_devices.get_end_device(device_id, tenant_id=principal.tenant_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="end device not found")
    return obj


@app.get("/cim/meters", response_model=list[schemas.MeterOut])
def list_meters(site_name: str | None = None, lo: tuple[int, int] = Depends(_limit_offset),
                 principal: auth.CimPrincipal = Depends(auth.require_principal)):
    limit, offset = lo
    return mapping_devices.list_meters(tenant_id=principal.tenant_id, site_name=site_name, limit=limit, offset=offset)


@app.get("/cim/meters/{device_id}", response_model=schemas.MeterOut)
def get_meter(device_id: str, principal: auth.CimPrincipal = Depends(auth.require_principal)):
    obj = mapping_devices.get_meter(device_id, tenant_id=principal.tenant_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="meter not found")
    return obj


# --- Asset ---------------------------------------------------------------

@app.get("/cim/assets", response_model=list[schemas.AssetOut])
def list_assets(der_type: str | None = None, vpp_group: str | None = None,
                 lo: tuple[int, int] = Depends(_limit_offset),
                 principal: auth.CimPrincipal = Depends(auth.require_principal)):
    limit, offset = lo
    return mapping_assets.list_assets(
        tenant_id=principal.tenant_id, der_type=der_type, vpp_group=vpp_group, limit=limit, offset=offset,
    )


@app.get("/cim/assets/{der_id}", response_model=schemas.AssetOut)
def get_asset(der_id: str, principal: auth.CimPrincipal = Depends(auth.require_principal)):
    obj = mapping_assets.get_asset(der_id, tenant_id=principal.tenant_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="asset not found")
    return obj


# --- Customer / ServicePoint / UsagePoint -------------------------------

@app.get("/cim/customers", response_model=list[schemas.CustomerOut])
def list_customers(priority: str | None = None, lo: tuple[int, int] = Depends(_limit_offset),
                    principal: auth.CimPrincipal = Depends(auth.require_principal)):
    limit, offset = lo
    return mapping_metering.list_customers(tenant_id=principal.tenant_id, priority=priority, limit=limit, offset=offset)


@app.get("/cim/customers/{customer_id}", response_model=schemas.CustomerOut)
def get_customer(customer_id: str, principal: auth.CimPrincipal = Depends(auth.require_principal)):
    obj = mapping_metering.get_customer(customer_id, tenant_id=principal.tenant_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="customer not found")
    return obj


@app.get("/cim/service-points", response_model=list[schemas.ServicePointOut])
def list_service_points(customer_id: str | None = None, node_id: str | None = None,
                         lo: tuple[int, int] = Depends(_limit_offset),
                         principal: auth.CimPrincipal = Depends(auth.require_principal)):
    limit, offset = lo
    return mapping_metering.list_service_points(
        tenant_id=principal.tenant_id, customer_id=customer_id, node_id=node_id, limit=limit, offset=offset,
    )


@app.get("/cim/service-points/{service_point_id}", response_model=schemas.ServicePointOut)
def get_service_point(service_point_id: str, principal: auth.CimPrincipal = Depends(auth.require_principal)):
    obj = mapping_metering.get_service_point(service_point_id, tenant_id=principal.tenant_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="service point not found")
    return obj


@app.get("/cim/usage-points", response_model=list[schemas.UsagePointOut])
def list_usage_points(lo: tuple[int, int] = Depends(_limit_offset),
                       principal: auth.CimPrincipal = Depends(auth.require_principal)):
    limit, offset = lo
    return mapping_metering.list_usage_points(tenant_id=principal.tenant_id, limit=limit, offset=offset)


@app.get("/cim/usage-points/{usage_point_id}", response_model=schemas.UsagePointOut)
def get_usage_point(usage_point_id: str, principal: auth.CimPrincipal = Depends(auth.require_principal)):
    obj = mapping_metering.get_usage_point(usage_point_id, tenant_id=principal.tenant_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="usage point not found")
    return obj


# --- ConnectivityNode / Terminal / Transformer / Feeder -----------------

@app.get("/cim/connectivity-nodes", response_model=list[schemas.ConnectivityNodeOut])
def list_connectivity_nodes(node_type: str | None = None, site_name: str | None = None,
                             lo: tuple[int, int] = Depends(_limit_offset),
                             principal: auth.CimPrincipal = Depends(auth.require_principal)):
    limit, offset = lo
    validation.validate_node_type(node_type)
    return mapping_network.list_connectivity_nodes(
        tenant_id=principal.tenant_id, node_type=node_type, site_name=site_name, limit=limit, offset=offset,
    )


@app.get("/cim/connectivity-nodes/{node_id}", response_model=schemas.ConnectivityNodeOut)
def get_connectivity_node(node_id: str, principal: auth.CimPrincipal = Depends(auth.require_principal)):
    obj = mapping_network.get_connectivity_node(node_id, tenant_id=principal.tenant_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="connectivity node not found")
    return obj


@app.get("/cim/terminals", response_model=list[schemas.TerminalOut])
def list_terminals(edge_id: str | None = None, node_id: str | None = None,
                    lo: tuple[int, int] = Depends(_limit_offset),
                    principal: auth.CimPrincipal = Depends(auth.require_principal)):
    limit, offset = lo
    return mapping_network.list_terminals(
        tenant_id=principal.tenant_id, edge_id=edge_id, node_id=node_id, limit=limit, offset=offset,
    )


@app.get("/cim/transformers", response_model=list[schemas.TransformerOut])
def list_transformers(site_name: str | None = None, lo: tuple[int, int] = Depends(_limit_offset),
                       principal: auth.CimPrincipal = Depends(auth.require_principal)):
    limit, offset = lo
    return mapping_network.list_transformers(tenant_id=principal.tenant_id, site_name=site_name, limit=limit, offset=offset)


@app.get("/cim/transformers/{node_id}", response_model=schemas.TransformerOut)
def get_transformer(node_id: str, principal: auth.CimPrincipal = Depends(auth.require_principal)):
    obj = mapping_network.get_transformer(node_id, tenant_id=principal.tenant_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="transformer not found")
    return obj


@app.get("/cim/feeders", response_model=list[schemas.FeederOut])
def list_feeders(site_name: str | None = None, lo: tuple[int, int] = Depends(_limit_offset),
                  principal: auth.CimPrincipal = Depends(auth.require_principal)):
    limit, offset = lo
    return mapping_network.list_feeders(tenant_id=principal.tenant_id, site_name=site_name, limit=limit, offset=offset)


@app.get("/cim/feeders/{node_id}", response_model=schemas.FeederOut)
def get_feeder(node_id: str, principal: auth.CimPrincipal = Depends(auth.require_principal)):
    obj = mapping_network.get_feeder(node_id, tenant_id=principal.tenant_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="feeder not found")
    return obj


# --- Measurement / MeasurementValue -------------------------------------

@app.get("/cim/measurements", response_model=list[schemas.MeasurementOut])
def list_measurements(device_id: str | None = None, measurement_type: str | None = None,
                       lo: tuple[int, int] = Depends(_limit_offset),
                       principal: auth.CimPrincipal = Depends(auth.require_principal)):
    limit, offset = lo
    return mapping_measurements.list_measurements(
        tenant_id=principal.tenant_id, device_id=device_id, measurement_type=measurement_type,
        limit=limit, offset=offset,
    )


@app.get("/cim/measurement-values", response_model=list[schemas.MeasurementValueOut])
def list_measurement_values(device_id: str | None = None, measurement_type: str | None = None,
                             since: str | None = None, until: str | None = None,
                             lo: tuple[int, int] = Depends(_limit_offset),
                             principal: auth.CimPrincipal = Depends(auth.require_principal)):
    limit, offset = lo
    since_dt = validation.validate_iso_timestamp(since, "since")
    until_dt = validation.validate_iso_timestamp(until, "until")
    return mapping_measurements.list_measurement_values(
        tenant_id=principal.tenant_id, device_id=device_id, measurement_type=measurement_type,
        since=since_dt, until=until_dt, limit=limit, offset=offset,
    )


# --- Export (any object type, JSON or XML, optionally profile-filtered) -

_EXPORT_REGISTRY: dict[str, tuple[object, str]] = {
    "end-devices": (mapping_devices.list_end_devices, "EndDevice"),
    "meters": (mapping_devices.list_meters, "Meter"),
    "assets": (mapping_assets.list_assets, "Asset"),
    "customers": (mapping_metering.list_customers, "Customer"),
    "service-points": (mapping_metering.list_service_points, "ServicePoint"),
    "usage-points": (mapping_metering.list_usage_points, "UsagePoint"),
    "connectivity-nodes": (mapping_network.list_connectivity_nodes, "ConnectivityNode"),
    "terminals": (mapping_network.list_terminals, "Terminal"),
    "transformers": (mapping_network.list_transformers, "Transformer"),
    "feeders": (mapping_network.list_feeders, "Feeder"),
    "measurements": (mapping_measurements.list_measurements, "Measurement"),
    "measurement-values": (mapping_measurements.list_measurement_values, "MeasurementValue"),
}


@app.get("/cim/export/{object_type}")
def export(object_type: str, format: str = "json", profile: str = "full",
            lo: tuple[int, int] = Depends(_limit_offset),
            principal: auth.CimPrincipal = Depends(auth.require_principal)):
    """Generic export across all 12 CIM classes. Does not support the
    same per-type query filters as the dedicated resource routes above --
    list-then-export client-side for filtered XML/JSON. See API_REFERENCE.md."""
    validation.validate_format(format)
    validation.validate_profile(profile)
    if object_type not in _EXPORT_REGISTRY:
        raise HTTPException(status_code=404, detail=f"unknown object type {object_type!r}")
    list_fn, class_name = _EXPORT_REGISTRY[object_type]
    if not profiles.object_type_allowed(profile, class_name):
        raise HTTPException(status_code=400, detail=f"{class_name} is not included in profile {profile!r}")
    limit, offset = lo
    objects = list_fn(tenant_id=principal.tenant_id, limit=limit, offset=offset)
    if format == "xml":
        return Response(content=xml_export.to_xml(objects, class_name), media_type="application/xml")
    return Response(content=json_export.to_json(objects, class_name), media_type="application/json")
