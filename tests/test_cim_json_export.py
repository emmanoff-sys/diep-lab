"""services/cim/serialization/json_export.py -- stable shape, round-trips
every field with no loss."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json  # noqa: E402

from services.cim.models import Meter  # noqa: E402
from services.cim.serialization import json_export  # noqa: E402

_METER = Meter(mRID="11111111-1111-1111-1111-111111111111", name="SIT-METER-001",
                deviceType="smartmeter", status="ONLINE", tenantId="sit-tenant")


def test_json_export_has_object_type_count_items_shape():
    out = json.loads(json_export.to_json([_METER], "Meter"))
    assert set(out.keys()) == {"objectType", "count", "items"}
    assert out["objectType"] == "Meter"
    assert out["count"] == 1


def test_json_export_round_trips_every_field_with_no_loss():
    out = json.loads(json_export.to_json([_METER], "Meter"))
    item = out["items"][0]
    expected = _METER.to_dict()
    assert item == expected, f"round-trip mismatch: {item} != {expected}"


def test_json_export_of_empty_list_is_well_formed():
    out = json.loads(json_export.to_json([], "Feeder"))
    assert out["count"] == 0
    assert out["items"] == []


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
