"""OA-083 — canonical topology translation for GIS features.

Deterministic translation of raw GIS topology batch data into the
canonical MappedTopology contract (WP-011-01 OA-070 v1.0). Each field
mapping is explicit; no defaults are assumed for mandatory fields.

No ADMS business logic: the translator does not interpret what a new
feeder means for the operational model — that is WP-007's job.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.adms_topology_import.mapping import MappedTopology
from services.scada_connector.framework import SCADAConnectorError

from .identity import GISAssetIdentityMap

# GIS feature class vocabulary → canonical node_type (OA-070 v1.0)
_GIS_NODE_TYPE_MAP: dict[str, str] = {
    "feeder": "feeder",
    "substation": "substation",
    "primary_substation": "substation",
    "hv_bus": "bus",
    "mv_bus": "bus",
    "lv_bus": "bus",
    "busbar": "bus",
    "bus": "bus",
    "switch_node": "switch",
    "switch": "switch",
    "load_point": "load",
    "load": "load",
    "smart_meter": "meter",
    "meter": "meter",
    "junction": "junction",
}

# GIS feature class vocabulary → canonical edge_type (OA-070 v1.0)
_GIS_EDGE_TYPE_MAP: dict[str, str] = {
    "overhead_line": "line",
    "line": "line",
    "underground_cable": "cable",
    "cable": "cable",
    "hv_cable": "cable",
    "mv_cable": "cable",
    "circuit_breaker": "breaker",
    "breaker": "breaker",
    "disconnector": "switch",
    "load_switch": "switch",
    "switch": "switch",
    "distribution_transformer": "transformer",
    "power_transformer": "transformer",
    "transformer": "transformer",
    "fuse": "fuse",
    "recloser": "recloser",
}


@dataclass(frozen=True)
class GISNodeFeature:
    """A raw GIS node feature before translation."""

    gis_id: str
    feature_class: str
    name: str
    latitude: float
    longitude: float
    nominal_kv: float
    phases: str
    attributes: dict[str, Any]


@dataclass(frozen=True)
class GISEdgeFeature:
    """A raw GIS edge feature before translation."""

    gis_id: str
    feature_class: str
    name: str
    from_gis_id: str
    to_gis_id: str
    is_switchable: bool
    normally_closed: bool
    is_closed: bool
    rating_kw: float | None
    phases: str
    attributes: dict[str, Any]


@dataclass(frozen=True)
class GISTopologyBatch:
    """A complete GIS topology model snapshot."""

    source_system: str
    model_id: str
    model_version: str
    node_features: tuple[GISNodeFeature, ...]
    edge_features: tuple[GISEdgeFeature, ...]


@dataclass(frozen=True)
class GISFeatureRejection:
    gis_id: str
    reason: str


@dataclass(frozen=True)
class GISTranslationResult:
    success: bool
    topology: MappedTopology | None
    rejections: tuple[GISFeatureRejection, ...]
    total_features: int
    translated_nodes: int
    translated_edges: int


class GISTopologyTranslator:
    """Translates a GISTopologyBatch into a canonical MappedTopology.

    Deterministic: given the same batch and identity map, always produces
    the same result. No wall clock, no randomness. Individual feature
    rejections do not abort the translation; the result records all
    rejections and succeeds if at least one node and one edge translated.
    """

    def __init__(self, identity_map: GISAssetIdentityMap) -> None:
        self._map = identity_map

    def translate(self, batch: GISTopologyBatch) -> GISTranslationResult:
        rejections: list[GISFeatureRejection] = []
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []

        for feature in batch.node_features:
            node, rejection = self._translate_node(feature, batch)
            if rejection is not None:
                rejections.append(rejection)
            else:
                nodes.append(node)  # type: ignore[arg-type]

        for feature in batch.edge_features:
            edge, rejection = self._translate_edge(feature, batch)
            if rejection is not None:
                rejections.append(rejection)
            else:
                edges.append(edge)  # type: ignore[arg-type]

        total = len(batch.node_features) + len(batch.edge_features)
        if not nodes or not edges:
            return GISTranslationResult(
                success=False,
                topology=None,
                rejections=tuple(rejections),
                total_features=total,
                translated_nodes=len(nodes),
                translated_edges=len(edges),
            )

        topology = MappedTopology(
            source_system=batch.source_system,
            external_model_id=batch.model_id,
            external_model_version=batch.model_version,
            nodes=tuple(nodes),
            edges=tuple(edges),
        )
        return GISTranslationResult(
            success=True,
            topology=topology,
            rejections=tuple(rejections),
            total_features=total,
            translated_nodes=len(nodes),
            translated_edges=len(edges),
        )

    def _translate_node(
        self,
        feature: GISNodeFeature,
        batch: GISTopologyBatch,
    ) -> tuple[dict[str, Any] | None, GISFeatureRejection | None]:
        try:
            canonical_id, _ = self._map.resolve(feature.gis_id)
        except SCADAConnectorError as exc:
            return None, GISFeatureRejection(gis_id=feature.gis_id, reason=str(exc))

        node_type = _GIS_NODE_TYPE_MAP.get(feature.feature_class.lower())
        if node_type is None:
            return None, GISFeatureRejection(
                gis_id=feature.gis_id,
                reason=f"unknown GIS feature_class for node: '{feature.feature_class}'",
            )

        return {
            "node_id": canonical_id,
            "node_type": node_type,
            "name": feature.name,
            "latitude": feature.latitude,
            "longitude": feature.longitude,
            "nominal_kv": feature.nominal_kv,
            "phases": feature.phases,
            "attrs": {
                "external_id": feature.gis_id,
                "source": "gis",
                "source_system": batch.source_system,
                "model_id": batch.model_id,
                "model_version": batch.model_version,
                "metadata": dict(feature.attributes),
            },
        }, None

    def _translate_edge(
        self,
        feature: GISEdgeFeature,
        batch: GISTopologyBatch,
    ) -> tuple[dict[str, Any] | None, GISFeatureRejection | None]:
        try:
            canonical_id, _ = self._map.resolve(feature.gis_id)
        except SCADAConnectorError as exc:
            return None, GISFeatureRejection(gis_id=feature.gis_id, reason=str(exc))

        try:
            from_node, _ = self._map.resolve(feature.from_gis_id)
        except SCADAConnectorError as exc:
            return None, GISFeatureRejection(
                gis_id=feature.gis_id,
                reason=f"from_node resolution failed: {exc}",
            )

        try:
            to_node, _ = self._map.resolve(feature.to_gis_id)
        except SCADAConnectorError as exc:
            return None, GISFeatureRejection(
                gis_id=feature.gis_id,
                reason=f"to_node resolution failed: {exc}",
            )

        if from_node == to_node:
            return None, GISFeatureRejection(
                gis_id=feature.gis_id,
                reason=f"self-loop: from_node == to_node == '{from_node}'",
            )

        edge_type = _GIS_EDGE_TYPE_MAP.get(feature.feature_class.lower())
        if edge_type is None:
            return None, GISFeatureRejection(
                gis_id=feature.gis_id,
                reason=f"unknown GIS feature_class for edge: '{feature.feature_class}'",
            )

        return {
            "edge_id": canonical_id,
            "from_node": from_node,
            "to_node": to_node,
            "edge_type": edge_type,
            "is_switchable": feature.is_switchable,
            "normally_closed": feature.normally_closed,
            "is_closed": feature.is_closed,
            "rating_kw": feature.rating_kw,
            "phases": feature.phases,
            "attrs": {
                "external_id": feature.gis_id,
                "source": "gis",
                "source_system": batch.source_system,
                "model_id": batch.model_id,
                "model_version": batch.model_version,
                "metadata": dict(feature.attributes),
            },
        }, None
