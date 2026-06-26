"""services/cim/mapping/network.py -- grid_nodes/grid_edges -> ConnectivityNode,
Terminal, Transformer, Feeder. Terminal-ID determinism and leaf-node
synthesis are the two behaviors most worth pinning down here (no
dedicated table backs Terminal -- see CIM_MAPPING_GUIDE.md)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.cim import db as cim_db
from services.cim.mapping import network as mapping_network

_NODE_ROW = {
    "node_id": "TX-01", "node_type": "transformer", "name": "Transformer 1",
    "parent_id": "FDR-01", "site_name": "Site A", "device_id": None,
    "latitude": 9.07, "longitude": 7.39, "nominal_kv": 11.0, "tenant_id": "default",
}
_EDGE_ROW = {"edge_id": "E-01", "from_node": "BUS-01", "to_node": "ND-METER001",
             "edge_type": "line", "tenant_id": "default"}


def _patch(query_all):
    orig = cim_db.query_all
    cim_db.query_all = query_all

    def restore():
        cim_db.query_all = orig
    return restore


def test_connectivity_node_independent_of_node_type():
    cn = mapping_network.connectivity_node_from_row(_NODE_ROW)
    assert cn.nodeType == "transformer"
    assert cn.parentMRID is not None  # FDR-01 ancestor resolved


def test_transformer_mapping_from_node_type_transformer():
    restore = _patch(lambda sql, params=(): [_NODE_ROW])
    try:
        result = mapping_network.list_transformers(tenant_id=None, limit=10, offset=0)
    finally:
        restore()
    assert len(result) == 1
    assert result[0].nominalKv == 11.0


def test_terminal_ids_are_deterministic_two_per_edge():
    restore = _patch(lambda sql, params=(): [_EDGE_ROW] if "NOT EXISTS" not in sql else [])
    try:
        terms1 = mapping_network.list_terminals(tenant_id=None, limit=10, offset=0)
        terms2 = mapping_network.list_terminals(tenant_id=None, limit=10, offset=0)
    finally:
        restore()
    # 2 terminals from the edge (leaf-node pass returns nothing since our
    # fake query_all serves both edge and leaf queries identically here --
    # filtered below to isolate the edge-derived ones)
    edge_terms = [t for t in terms1 if t.conductingEquipmentRef == "E-01"]
    assert len(edge_terms) == 2
    assert {t.sequenceNumber for t in edge_terms} == {1, 2}
    assert terms1[0].mRID == terms2[0].mRID, "Terminal mRIDs must be stable across calls"


def test_terminal_connects_to_correct_connectivity_node():
    restore = _patch(lambda sql, params=(): [_EDGE_ROW] if "NOT EXISTS" not in sql else [])
    try:
        terms = mapping_network.list_terminals(tenant_id=None, limit=10, offset=0)
    finally:
        restore()
    edge_terms = sorted([t for t in terms if t.conductingEquipmentRef == "E-01"], key=lambda t: t.sequenceNumber)
    assert len(edge_terms) == 2
    from services.cim import identifiers
    assert edge_terms[0].connectivityNodeMRID == identifiers.mrid_for("ConnectivityNode", "BUS-01")
    assert edge_terms[1].connectivityNodeMRID == identifiers.mrid_for("ConnectivityNode", "ND-METER001")


def test_leaf_node_with_no_edges_gets_synthesized_terminal():
    def fake_query_all(sql, params=()):
        if "grid_edges" in sql and "NOT EXISTS" not in sql:
            return []  # no edges at all
        if "NOT EXISTS" in sql:
            return [{"node_id": "ND-SOLAR-LEAF", "tenant_id": "default"}]
        return []
    restore = _patch(fake_query_all)
    try:
        terms = mapping_network.list_terminals(tenant_id=None, limit=10, offset=0)
    finally:
        restore()
    assert len(terms) == 1
    assert terms[0].conductingEquipmentRef == "ND-SOLAR-LEAF"
    assert terms[0].sequenceNumber == 1


def main():
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    passed = 0
    for t in tests:
        t()
        print(f"PASS: {t.__name__}")
        passed += 1
    print(f"\n{passed}/{len(tests)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
