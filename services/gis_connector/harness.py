"""OA-086 — GIS adapter test harness datasets.

Canonical GIS topology batch whose translation yields the two-feeder
network structure defined in services.scada_connector.harness.datasets.
Used in all OA-086/OA-087 test suites for deterministic replay.
"""

from __future__ import annotations

from .translation import GISEdgeFeature, GISNodeFeature, GISTopologyBatch

# GIS external IDs → (canonical_id, asset_kind)
# Mirrors the node/edge IDs of TWO_FEEDER_TOPOLOGY via GIS feature identifiers.
GIS_CANONICAL_IDENTITY_MAP: dict[str, tuple[str, str]] = {
    "GIS-NODE-F1": ("f1", "node"),
    "GIS-NODE-A": ("a", "node"),
    "GIS-NODE-B": ("b", "node"),
    "GIS-NODE-C": ("c", "node"),
    "GIS-NODE-F2": ("f2", "node"),
    "GIS-NODE-D": ("d", "node"),
    "GIS-NODE-E": ("e", "node"),
    "GIS-EDGE-E1": ("e1", "edge"),
    "GIS-EDGE-SW1": ("sw1", "edge"),
    "GIS-EDGE-E2": ("e2", "edge"),
    "GIS-EDGE-TIE1": ("tie1", "edge"),
    "GIS-EDGE-E3": ("e3", "edge"),
    "GIS-EDGE-E4": ("e4", "edge"),
}


def _gis_node(gis_id: str, feature_class: str, name: str, **attrs) -> GISNodeFeature:
    return GISNodeFeature(
        gis_id=gis_id,
        feature_class=feature_class,
        name=name,
        latitude=9.0,
        longitude=7.0,
        nominal_kv=11.0,
        phases="ABC",
        attributes=dict(attrs),
    )


def _gis_edge(
    gis_id: str,
    feature_class: str,
    from_gis_id: str,
    to_gis_id: str,
    *,
    switchable: bool = False,
    closed: bool = True,
    rating_kw: float | None = 1000.0,
) -> GISEdgeFeature:
    return GISEdgeFeature(
        gis_id=gis_id,
        feature_class=feature_class,
        name=gis_id,
        from_gis_id=from_gis_id,
        to_gis_id=to_gis_id,
        is_switchable=switchable,
        normally_closed=closed,
        is_closed=closed,
        rating_kw=rating_kw,
        phases="ABC",
        attributes={},
    )


# Canonical GIS two-feeder batch — translates to the TWO_FEEDER_TOPOLOGY structure.
GIS_TWO_FEEDER_BATCH = GISTopologyBatch(
    source_system="gis-connector-test",
    model_id="model-wp-011-03-test",
    model_version="2026.07.09",
    node_features=(
        _gis_node("GIS-NODE-F1", "feeder", "f1"),
        _gis_node("GIS-NODE-A", "busbar", "a"),
        _gis_node("GIS-NODE-B", "busbar", "b"),
        _gis_node("GIS-NODE-C", "load_point", "c", base_load_kw=100.0, customer_count=40),
        _gis_node("GIS-NODE-F2", "feeder", "f2"),
        _gis_node("GIS-NODE-D", "busbar", "d"),
        _gis_node("GIS-NODE-E", "load_point", "e", base_load_kw=50.0, customer_count=10),
    ),
    edge_features=(
        _gis_edge("GIS-EDGE-E1", "overhead_line", "GIS-NODE-F1", "GIS-NODE-A"),
        _gis_edge(
            "GIS-EDGE-SW1",
            "disconnector",
            "GIS-NODE-A",
            "GIS-NODE-B",
            switchable=True,
            rating_kw=800.0,
        ),
        _gis_edge("GIS-EDGE-E2", "overhead_line", "GIS-NODE-B", "GIS-NODE-C", rating_kw=500.0),
        _gis_edge(
            "GIS-EDGE-TIE1",
            "load_switch",
            "GIS-NODE-B",
            "GIS-NODE-D",
            switchable=True,
            closed=False,
            rating_kw=300.0,
        ),
        _gis_edge("GIS-EDGE-E3", "overhead_line", "GIS-NODE-F2", "GIS-NODE-D"),
        _gis_edge("GIS-EDGE-E4", "overhead_line", "GIS-NODE-D", "GIS-NODE-E", rating_kw=400.0),
    ),
)
