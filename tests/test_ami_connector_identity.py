"""WP-011-04 OA-091 — meter identity resolution tests."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.ami_connector import AMIConnectorError, AMIMeterIdentityMap  # noqa: E402

_BASIC_MAP = {
    "AMI:METER-C-001": ("c", "node"),
    "AMI:METER-C-002": ("c", "node"),
    "AMI:METER-E-001": ("e", "node"),
}


def test_resolve_known_meter_id():
    m = AMIMeterIdentityMap(_BASIC_MAP)
    asset_id, kind = m.resolve("AMI:METER-C-001")
    assert asset_id == "c"
    assert kind == "node"


def test_resolve_unknown_meter_id_raises():
    m = AMIMeterIdentityMap(_BASIC_MAP)
    with pytest.raises(AMIConnectorError, match="not in identity map"):
        m.resolve("AMI:GHOST-METER")


def test_construction_with_known_asset_ids_validates():
    known = frozenset({"c", "e"})
    m = AMIMeterIdentityMap(_BASIC_MAP, known_asset_ids=known)
    assert m.resolve("AMI:METER-E-001") == ("e", "node")


def test_construction_with_unknown_canonical_id_raises():
    with pytest.raises(AMIConnectorError, match="unknown canonical IDs"):
        AMIMeterIdentityMap(
            {"AMI:METER-X": ("x", "node")},
            known_asset_ids=frozenset({"c", "e"}),
        )


def test_detect_ambiguities_finds_shared_canonical_id():
    m = AMIMeterIdentityMap(_BASIC_MAP)
    ambiguous = m.detect_ambiguities()
    assert "c" in ambiguous


def test_detect_ambiguities_empty_when_no_duplicates():
    m = AMIMeterIdentityMap({"AMI:M-001": ("c", "node"), "AMI:M-002": ("e", "node")})
    assert m.detect_ambiguities() == ()


def test_detect_missing_finds_absent_meter_ids():
    m = AMIMeterIdentityMap(_BASIC_MAP)
    batch_ids = frozenset({"AMI:METER-C-001", "AMI:METER-UNKNOWN"})
    missing = m.detect_missing(batch_ids)
    assert "AMI:METER-UNKNOWN" in missing
    assert "AMI:METER-C-001" not in missing


def test_detect_missing_empty_when_all_present():
    m = AMIMeterIdentityMap(_BASIC_MAP)
    batch_ids = frozenset({"AMI:METER-C-001", "AMI:METER-E-001"})
    assert m.detect_missing(batch_ids) == ()


def test_mapped_meter_ids_returns_all_keys_sorted():
    m = AMIMeterIdentityMap(_BASIC_MAP)
    ids = m.mapped_meter_ids
    assert set(ids) == set(_BASIC_MAP)
    assert ids == tuple(sorted(_BASIC_MAP))


def test_empty_mapping_allowed():
    m = AMIMeterIdentityMap({})
    assert m.mapped_meter_ids == ()
    with pytest.raises(AMIConnectorError):
        m.resolve("ANY")


def test_construction_does_not_mutate_input():
    orig = {"AMI:METER-C-001": ("c", "node")}
    m = AMIMeterIdentityMap(orig)
    orig["AMI:EXTRA"] = ("e", "node")
    assert "AMI:EXTRA" not in m.mapped_meter_ids


def test_detect_missing_returns_sorted_tuple():
    m = AMIMeterIdentityMap(_BASIC_MAP)
    missing = m.detect_missing(frozenset({"AMI:METER-Z", "AMI:METER-A"}))
    assert missing == tuple(sorted({"AMI:METER-Z", "AMI:METER-A"}))


def test_detect_ambiguities_returns_sorted_tuple():
    m = AMIMeterIdentityMap(
        {
            "AMI:M-001": ("c", "node"),
            "AMI:M-002": ("c", "node"),
            "AMI:M-003": ("e", "node"),
            "AMI:M-004": ("e", "node"),
        }
    )
    ambiguous = m.detect_ambiguities()
    assert ambiguous == ("c", "e")
