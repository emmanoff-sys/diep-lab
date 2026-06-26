"""services/cim/mapping/devices.py -- devices row -> EndDevice/Meter.
Monkeypatches services.cim.db.query_all/query_one (no real DB needed) so
this isolates the transformation logic; the live SQL itself is separately
proven against the real database (see CIM_INTEROPERABILITY_REPORT.md)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.cim import db as cim_db
from services.cim import topology
from services.cim.mapping import devices as mapping_devices

_FAKE_DEVICE_ROW = {
    "device_id": "METER001", "device_type": "smartmeter", "location": "Site A",
    "status": "ONLINE", "site_name": "Site A", "tenant_id": "default",
}
_FAKE_BATTERY_ROW = {
    "device_id": "BAT001", "device_type": "battery", "location": "Site A",
    "status": "ONLINE", "site_name": "Site A", "tenant_id": "default",
}


def _patch(query_all=None, query_one=None, node_fetcher=None):
    orig_all, orig_one, orig_walk = cim_db.query_all, cim_db.query_one, topology._fetch_grid_node
    if query_all is not None:
        cim_db.query_all = query_all
    if query_one is not None:
        cim_db.query_one = query_one
    topology._fetch_grid_node = node_fetcher or (lambda node_id: None)

    def restore():
        cim_db.query_all, cim_db.query_one, topology._fetch_grid_node = orig_all, orig_one, orig_walk
    return restore


def test_end_device_from_row_maps_every_field():
    ed = mapping_devices.end_device_from_row(_FAKE_DEVICE_ROW)
    assert ed.name == "METER001"
    assert ed.deviceType == "smartmeter"
    assert ed.status == "ONLINE"
    assert ed.siteName == "Site A"
    assert ed.tenantId == "default"
    assert ed.mRID  # deterministic, non-empty


def test_meter_specializes_end_device():
    m = mapping_devices.meter_from_row(_FAKE_DEVICE_ROW)
    assert m.deviceType == "smartmeter"
    assert hasattr(m, "formNumber")


def test_list_end_devices_resolves_feeder_transformer_ancestry():
    grid_nodes = {
        "METER001": {"node_id": "ND-M1", "node_type": "meter", "parent_id": "TX-01"},
        "TX-01": {"node_id": "TX-01", "node_type": "transformer", "parent_id": "FDR-01"},
        "FDR-01": {"node_id": "FDR-01", "node_type": "feeder", "parent_id": None},
    }
    restore = _patch(
        query_all=lambda sql, params=(): [_FAKE_DEVICE_ROW],
        node_fetcher=lambda nid: grid_nodes.get(nid),
    )
    try:
        result = mapping_devices.list_end_devices(tenant_id=None, limit=10, offset=0)
    finally:
        restore()
    assert len(result) == 1
    ed = result[0]
    assert ed.feederMRID is not None
    assert ed.transformerMRID is not None


def test_device_with_no_grid_node_gets_none_ancestry_not_fabricated():
    restore = _patch(query_all=lambda sql, params=(): [_FAKE_BATTERY_ROW])
    try:
        result = mapping_devices.list_end_devices(tenant_id=None, limit=10, offset=0)
    finally:
        restore()
    assert result[0].feederMRID is None
    assert result[0].transformerMRID is None


def test_mrid_is_deterministic_across_calls():
    ed1 = mapping_devices.end_device_from_row(_FAKE_DEVICE_ROW)
    ed2 = mapping_devices.end_device_from_row(_FAKE_DEVICE_ROW)
    assert ed1.mRID == ed2.mRID


def main():
    # Default: no grid_nodes entry for any device (topology walk returns
    # None, not a fabricated value) -- individual tests override as needed.
    topology._fetch_grid_node = lambda node_id: None
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
