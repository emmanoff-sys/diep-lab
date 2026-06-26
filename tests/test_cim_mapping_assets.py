"""services/cim/mapping/assets.py -- der_assets -> Asset. DER-only by
design (smartmeters have no der_assets row, hence no Asset record) --
see SUPPORTED_OBJECTS.md for why this is a documented gap, not a bug."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.cim import db as cim_db
from services.cim.mapping import assets as mapping_assets

_BATTERY_ROW = {
    "der_id": "BAT001", "der_type": "battery", "node_id": "ND-BAT001",
    "rated_kw": 50.0, "rated_kwh": 200.0, "controllable": True,
    "vpp_group": "vpp-1", "tenant_id": "default",
}


def _patch(query_all=None, query_one=None):
    orig_all, orig_one = cim_db.query_all, cim_db.query_one
    if query_all is not None:
        cim_db.query_all = query_all
    if query_one is not None:
        cim_db.query_one = query_one

    def restore():
        cim_db.query_all, cim_db.query_one = orig_all, orig_one
    return restore


def test_asset_from_row_maps_every_field():
    a = mapping_assets.asset_from_row(_BATTERY_ROW)
    assert a.assetType == "battery"
    assert a.ratedKw == 50.0
    assert a.ratedKwh == 200.0
    assert a.controllable is True
    assert a.vppGroup == "vpp-1"
    assert a.nodeId == "ND-BAT001"


def test_list_assets_returns_der_rows_only():
    restore = _patch(query_all=lambda sql, params=(): [_BATTERY_ROW])
    try:
        result = mapping_assets.list_assets(tenant_id=None, limit=10, offset=0)
    finally:
        restore()
    assert len(result) == 1
    assert result[0].name == "BAT001"


def test_get_asset_returns_none_for_a_smartmeter_device_id():
    """A smartmeter device_id has no der_assets row -- get_asset must
    return None, not a fabricated/zeroed Asset."""
    restore = _patch(query_one=lambda sql, params=(): None)
    try:
        result = mapping_assets.get_asset("SIT-METER-001", tenant_id=None)
    finally:
        restore()
    assert result is None


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
