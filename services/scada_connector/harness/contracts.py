"""OA-079 / OA-073 — canonical contract validators.

Client-side validators that connector test suites call to assert that
produced objects conform to the canonical contracts defined in WP-011-01
OA-070. These are the implementation of the validators specified in
OA-073 §3.
"""

from __future__ import annotations

from typing import Any

VALID_NODE_TYPES = frozenset({"feeder", "substation", "bus", "switch", "load", "meter", "junction"})
VALID_EDGE_TYPES = frozenset(
    {"line", "cable", "switch", "breaker", "transformer", "fuse", "recloser"}
)
ALLOWED_EVENT_TYPES = frozenset({"breaker_operation", "alarm", "telemetry"})
ALLOWED_ASSET_KINDS = frozenset({"node", "edge"})
REQUIRED_PAYLOAD_KEYS: dict[str, tuple[str, ...]] = {
    "breaker_operation": ("status", "available"),
    "alarm": ("available",),
    "telemetry": ("energized",),
}


def validate_operational_event(event: Any) -> None:
    """Raise AssertionError if event does not satisfy OperationalEvent v1.0."""
    assert event.event_id, "event_id is required and must be non-empty"
    assert (
        event.event_type in ALLOWED_EVENT_TYPES
    ), f"event_type '{event.event_type}' not in allowed set: {ALLOWED_EVENT_TYPES}"
    assert event.asset_id, "asset_id is required and must be non-empty"
    assert (
        event.asset_kind in ALLOWED_ASSET_KINDS
    ), f"asset_kind '{event.asset_kind}' must be 'node' or 'edge'"
    assert event.sequence > 0, "sequence must be a positive integer"
    assert event.observed_at, "observed_at is required (ISO 8601 UTC timestamp)"
    assert event.actor, "actor is required and must be non-empty"
    assert isinstance(event.payload, dict), "payload must be a dict"
    required = REQUIRED_PAYLOAD_KEYS[event.event_type]
    missing = [k for k in required if k not in event.payload]
    assert not missing, f"payload missing required keys for {event.event_type}: {missing}"


def validate_mapped_topology(obj: Any) -> None:
    """Raise AssertionError if obj does not satisfy MappedTopology v1.0."""
    assert obj.source_system, "source_system is required"
    assert obj.external_model_id, "external_model_id is required"
    assert obj.external_model_version, "external_model_version is required"
    assert obj.nodes, "at least one node is required"
    assert obj.edges, "at least one edge is required"
    for node in obj.nodes:
        assert node["node_id"], "node node_id is required"
        assert (
            node["node_type"] in VALID_NODE_TYPES
        ), f"node_type '{node['node_type']}' not in allowed set"
        assert -90.0 <= node["latitude"] <= 90.0, "latitude must be in [-90, 90]"
        assert -180.0 <= node["longitude"] <= 180.0, "longitude must be in [-180, 180]"
        assert node["nominal_kv"] > 0, "nominal_kv must be positive"
    for edge in obj.edges:
        assert edge["edge_id"], "edge edge_id is required"
        assert edge["from_node"] != edge["to_node"], "from_node must differ from to_node"
        assert (
            edge["edge_type"] in VALID_EDGE_TYPES
        ), f"edge_type '{edge['edge_type']}' not in allowed set"


def validate_historical_event(event: Any) -> None:
    """Raise AssertionError if event does not satisfy HistoricalEvent v1.0."""
    assert event.asset_id, "asset_id is required and must be non-empty"
    assert event.kind, "kind is required and must be non-empty"
    assert event.observed_at, "observed_at is required (ISO 8601 UTC timestamp)"
