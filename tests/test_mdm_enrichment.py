"""MDM Device Metadata Enrichment tests — tenant/site/device_type from
`devices`, feeder/transformer from the grid_nodes parent-chain walk. Uses
injected fetchers (see DeviceMetadataEnricher's constructor) rather than a
real DB connection, since psycopg2 isn't available in this environment —
see memory: DLMS test env gap."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.mdm.enrichment import DeviceMetadataEnricher


FAKE_DEVICES = {
    "METER001": {"tenant_id": "tenantA", "site_name": "Abuja Site A", "device_type": "meter"},
    "METER_NO_TOPOLOGY": {"tenant_id": "tenantA", "site_name": "Abuja Site A", "device_type": "meter"},
}

FAKE_GRID_NODES = {
    "METER001": {"node_id": "MTR-01", "node_type": "meter", "parent_id": "TX-01"},
    "TX-01": {"node_id": "TX-01", "node_type": "transformer", "parent_id": "FDR-01"},
    "FDR-01": {"node_id": "FDR-01", "node_type": "feeder", "parent_id": "SUB-ABUJA"},
    "SUB-ABUJA": {"node_id": "SUB-ABUJA", "node_type": "substation", "parent_id": None},
}


def _enricher(ttl_s=300.0):
    return DeviceMetadataEnricher(
        device_row_fetcher=lambda did: FAKE_DEVICES.get(did),
        grid_node_fetcher=lambda nid: FAKE_GRID_NODES.get(nid),
        ttl_s=ttl_s,
    )


def test_tenant_site_device_type_attached():
    meta = _enricher().enrich("METER001")
    assert meta.tenant_id == "tenantA"
    assert meta.site_id == "Abuja Site A"
    assert meta.device_type == "meter"


def test_asset_class_aliases_device_type():
    meta = _enricher().enrich("METER001")
    assert meta.asset_class == meta.device_type == "meter"


def test_feeder_and_transformer_resolved_via_parent_chain():
    meta = _enricher().enrich("METER001")
    assert meta.transformer_id == "TX-01"
    assert meta.feeder_id == "FDR-01"


def test_device_not_in_registry_returns_nones_not_an_error():
    meta = _enricher().enrich("UNKNOWN_DEVICE")
    assert meta.device_id == "UNKNOWN_DEVICE"
    assert meta.tenant_id is None
    assert meta.feeder_id is None
    assert meta.transformer_id is None


def test_device_with_no_grid_node_entry_gets_none_topology_honestly():
    meta = _enricher().enrich("METER_NO_TOPOLOGY")
    assert meta.tenant_id == "tenantA"  # devices-table data still present
    assert meta.feeder_id is None       # but no fabricated topology
    assert meta.transformer_id is None


def test_result_is_cached_within_ttl():
    calls = []

    def counting_fetcher(did):
        calls.append(did)
        return FAKE_DEVICES.get(did)

    enricher = DeviceMetadataEnricher(
        device_row_fetcher=counting_fetcher,
        grid_node_fetcher=lambda nid: FAKE_GRID_NODES.get(nid),
        ttl_s=300.0,
    )
    enricher.enrich("METER001")
    enricher.enrich("METER001")
    assert calls == ["METER001"]  # second call served from cache, no second DB hit


def test_cache_expires_after_ttl():
    calls = []

    def counting_fetcher(did):
        calls.append(did)
        return FAKE_DEVICES.get(did)

    enricher = DeviceMetadataEnricher(
        device_row_fetcher=counting_fetcher,
        grid_node_fetcher=lambda nid: FAKE_GRID_NODES.get(nid),
        ttl_s=0.0,  # expires immediately
    )
    enricher.enrich("METER001")
    enricher.enrich("METER001")
    assert calls == ["METER001", "METER001"]


def test_max_hops_bounds_the_walk_against_a_cycle():
    """A corrupt/cyclic parent chain must not hang the enricher forever."""
    cyclic_nodes = {
        "A": {"node_id": "A", "node_type": "bus", "parent_id": "B"},
        "B": {"node_id": "B", "node_type": "bus", "parent_id": "A"},  # cycle
    }
    enricher = DeviceMetadataEnricher(
        device_row_fetcher=lambda did: None,
        grid_node_fetcher=lambda nid: cyclic_nodes.get(nid),
        max_hops=5,
    )
    meta = enricher.enrich("A")  # must return, not loop forever
    assert meta.feeder_id is None
    assert meta.transformer_id is None
