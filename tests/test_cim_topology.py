"""services/cim/topology.py -- feeder/transformer ancestry walk must agree
with services/mdm/enrichment.py's walk on the same fixture graph: both
read the same grid_nodes table independently and must never disagree."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.cim import topology  # noqa: E402
from services.mdm.enrichment import DeviceMetadataEnricher  # noqa: E402

_GRID = {
    "METER001": {"node_id": "ND-M1", "node_type": "meter", "parent_id": "BUS-01"},
    "BUS-01": {"node_id": "BUS-01", "node_type": "bus", "parent_id": "TX-01"},
    "TX-01": {"node_id": "TX-01", "node_type": "transformer", "parent_id": "FDR-01"},
    "FDR-01": {"node_id": "FDR-01", "node_type": "feeder", "parent_id": None},
}


def test_cim_walk_finds_feeder_and_transformer():
    feeder, transformer = topology.feeder_and_transformer_for("METER001", node_fetcher=_GRID.get)
    assert feeder == "FDR-01"
    assert transformer == "TX-01"


def test_cim_walk_returns_none_past_max_hops_not_fabricated():
    long_chain = {f"N{i}": {"node_id": f"N{i}", "node_type": "bus", "parent_id": f"N{i + 1}"} for i in range(15)}
    long_chain["N15"] = {"node_id": "N15", "node_type": "feeder", "parent_id": None}
    result = topology.walk_to_node_type("N0", "feeder", max_hops=10, node_fetcher=long_chain.get)
    assert result is None  # feeder is 15 hops up, beyond max_hops=10


def test_cim_and_mdm_agree_on_the_same_fixture_graph():
    cim_feeder, cim_transformer = topology.feeder_and_transformer_for("METER001", node_fetcher=_GRID.get)

    mdm_enricher = DeviceMetadataEnricher(
        device_row_fetcher=lambda device_id: {
            "device_type": "smartmeter", "site_name": "Site A", "tenant_id": "default",
        },
        grid_node_fetcher=_GRID.get,
    )
    mdm_meta = mdm_enricher.enrich("METER001")

    assert cim_feeder == mdm_meta.feeder_id
    assert cim_transformer == mdm_meta.transformer_id


def test_device_with_no_grid_node_returns_none_honestly():
    feeder, transformer = topology.feeder_and_transformer_for("UNKNOWN-DEVICE", node_fetcher=lambda nid: None)
    assert feeder is None
    assert transformer is None


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
