"""WP-011-03 OA-084 — GIS asset identity resolution tests."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.gis_connector import GISAssetIdentityMap, SCADAConnectorError  # noqa: E402
from services.gis_connector.harness import GIS_CANONICAL_IDENTITY_MAP  # noqa: E402

_SIMPLE_MAP: dict[str, tuple[str, str]] = {
    "GIS-NODE-F1": ("f1", "node"),
    "GIS-NODE-A": ("a", "node"),
    "GIS-EDGE-E1": ("e1", "edge"),
}


def test_resolve_known_node():
    identity = GISAssetIdentityMap(_SIMPLE_MAP)
    cid, kind = identity.resolve("GIS-NODE-F1")
    assert cid == "f1"
    assert kind == "node"


def test_resolve_known_edge():
    identity = GISAssetIdentityMap(_SIMPLE_MAP)
    cid, kind = identity.resolve("GIS-EDGE-E1")
    assert cid == "e1"
    assert kind == "edge"


def test_resolve_unknown_gis_id_raises():
    identity = GISAssetIdentityMap(_SIMPLE_MAP)
    with pytest.raises(SCADAConnectorError, match="not in identity map"):
        identity.resolve("GIS-NODE-UNKNOWN")


def test_fail_fast_construction_rejects_unknown_canonical_id():
    known = frozenset({"f1", "a"})
    with pytest.raises(SCADAConnectorError, match="unknown canonical IDs"):
        GISAssetIdentityMap({"GIS-EDGE-E1": ("e1", "edge")}, known_asset_ids=known)


def test_construction_accepts_all_known_canonical_ids():
    known = frozenset({"f1", "a", "e1"})
    identity = GISAssetIdentityMap(_SIMPLE_MAP, known_asset_ids=known)
    assert "GIS-NODE-F1" in identity.mapped_gis_ids


def test_detect_ambiguities_none_when_all_unique():
    identity = GISAssetIdentityMap(_SIMPLE_MAP)
    assert identity.detect_ambiguities() == ()


def test_detect_ambiguities_returns_colliding_canonical_id():
    collision_map = {
        "GIS-NODE-X": ("f1", "node"),
        "GIS-NODE-Y": ("f1", "node"),  # f1 appears twice
        "GIS-EDGE-E1": ("e1", "edge"),
    }
    identity = GISAssetIdentityMap(collision_map)
    ambiguities = identity.detect_ambiguities()
    assert "f1" in ambiguities


def test_detect_missing_returns_unmapped_gis_ids():
    identity = GISAssetIdentityMap(_SIMPLE_MAP)
    batch_ids = frozenset({"GIS-NODE-F1", "GIS-NODE-A", "GIS-NODE-UNKNOWN"})
    missing = identity.detect_missing(batch_ids)
    assert "GIS-NODE-UNKNOWN" in missing
    assert "GIS-NODE-F1" not in missing


def test_detect_missing_empty_when_all_mapped():
    identity = GISAssetIdentityMap(_SIMPLE_MAP)
    assert identity.detect_missing(frozenset(_SIMPLE_MAP.keys())) == ()


def test_mapped_gis_ids_is_sorted():
    identity = GISAssetIdentityMap(_SIMPLE_MAP)
    ids = identity.mapped_gis_ids
    assert list(ids) == sorted(ids)


def test_canonical_harness_identity_map_covers_all_two_feeder_assets():
    expected_canonical_nodes = {"f1", "a", "b", "c", "f2", "d", "e"}
    expected_canonical_edges = {"e1", "sw1", "e2", "tie1", "e3", "e4"}
    resolved_nodes = {
        cid for _, (cid, kind) in GIS_CANONICAL_IDENTITY_MAP.items() if kind == "node"
    }
    resolved_edges = {
        cid for _, (cid, kind) in GIS_CANONICAL_IDENTITY_MAP.items() if kind == "edge"
    }
    assert resolved_nodes == expected_canonical_nodes
    assert resolved_edges == expected_canonical_edges


def test_all_two_feeder_gis_ids_resolve_without_error():
    identity = GISAssetIdentityMap(GIS_CANONICAL_IDENTITY_MAP)
    for gis_id in GIS_CANONICAL_IDENTITY_MAP:
        canonical_id, kind = identity.resolve(gis_id)
        assert canonical_id
        assert kind in ("node", "edge")
