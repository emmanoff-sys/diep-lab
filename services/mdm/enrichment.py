"""MDM Device Metadata Enrichment.

Attaches tenant/site/feeder/transformer/asset_class/device_type to a reading
WITHOUT touching the measurement payload itself (the enrichment result is a
separate DeviceMetadata record the pipeline attaches to the trusted output's
additive `mdm` metadata block — see pipeline.py — never mutating
contracts.TelemetryEnvelope fields).

Data sources (read-only, no schema change):
- `devices` JOIN `sites` for tenant_id / site_name / device_type — the same
  query shape as fastapi/app.py:_device_row.
- `grid_nodes` (sql/013_network_model.sql, ADMS M1) for feeder/transformer:
  a device's grid_nodes row links via `device_id`; walking `parent_id`
  upward to the nearest node_type='transformer' and node_type='feeder'
  ancestor gives the real electrical lineage where the M1 model has it
  mapped. Returns None for either when the device has no grid_nodes entry
  or the model doesn't reach that far up yet — that's an honest "not
  modeled yet" gap, not a fabricated value.

`asset_class` is aliased to `device_type` — the platform doesn't have a
separate asset-classification taxonomy yet (device_type IS the classification
in use), documented here rather than invented.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from . import db

DEFAULT_TTL_S = 300.0


@dataclass(frozen=True)
class DeviceMetadata:
    device_id: str
    tenant_id: str | None
    site_id: str | None
    device_type: str | None
    asset_class: str | None
    feeder_id: str | None
    transformer_id: str | None


def _default_device_row_fetcher(device_id: str) -> dict | None:
    return db.query_one(
        "SELECT d.device_id, d.device_type, d.site_name, d.tenant_id "
        "FROM devices d WHERE d.device_id = %s",
        (device_id,),
    )


def _default_grid_node_fetcher(node_id: str) -> dict | None:
    return db.query_one(
        "SELECT node_id, node_type, parent_id FROM grid_nodes WHERE node_id = %s OR device_id = %s",
        (node_id, node_id),
    )


class DeviceMetadataEnricher:
    def __init__(
        self,
        device_row_fetcher=None,
        grid_node_fetcher=None,
        ttl_s: float = DEFAULT_TTL_S,
        max_hops: int = 10,
    ):
        self._fetch_device_row = device_row_fetcher or _default_device_row_fetcher
        self._fetch_grid_node = grid_node_fetcher or _default_grid_node_fetcher
        self.ttl_s = ttl_s
        self.max_hops = max_hops
        self._cache: dict[str, tuple[DeviceMetadata, float]] = {}

    def _walk_to_node_type(self, start_device_id: str, target_type: str) -> str | None:
        node = self._fetch_grid_node(start_device_id)
        for _ in range(self.max_hops):
            if node is None:
                return None
            if node["node_type"] == target_type:
                return node["node_id"]
            parent_id = node.get("parent_id")
            if not parent_id:
                return None
            node = self._fetch_grid_node(parent_id)
        return None

    def enrich(self, device_id: str) -> DeviceMetadata:
        cached = self._cache.get(device_id)
        if cached is not None and (time.monotonic() - cached[1]) < self.ttl_s:
            return cached[0]

        row = self._fetch_device_row(device_id) or {}
        feeder_id = self._walk_to_node_type(device_id, "feeder")
        transformer_id = self._walk_to_node_type(device_id, "transformer")

        meta = DeviceMetadata(
            device_id=device_id,
            tenant_id=row.get("tenant_id"),
            site_id=row.get("site_name"),
            device_type=row.get("device_type"),
            asset_class=row.get("device_type"),
            feeder_id=feeder_id,
            transformer_id=transformer_id,
        )
        self._cache[device_id] = (meta, time.monotonic())
        return meta
