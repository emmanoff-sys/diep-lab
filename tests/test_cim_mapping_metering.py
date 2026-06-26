"""services/cim/mapping/metering.py -- Customer/ServicePoint maps 1:1;
UsagePoint deduplicates by (node_id, meter_device_id) -- the seed data's
SP-001/002/003 sharing one node+meter is exactly the case this must not
get wrong (3 ServicePoints, 1 UsagePoint, 3 customers listed)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.cim import db as cim_db
from services.cim.mapping import metering as mapping_metering

_SHARED_SP_ROWS = [
    {"service_point_id": "SP-001", "customer_id": "CUST-001", "node_id": "ND-METER001",
     "meter_device_id": "METER001", "tenant_id": "default"},
    {"service_point_id": "SP-002", "customer_id": "CUST-002", "node_id": "ND-METER001",
     "meter_device_id": "METER001", "tenant_id": "default"},
    {"service_point_id": "SP-003", "customer_id": "CUST-003", "node_id": "ND-METER001",
     "meter_device_id": "METER001", "tenant_id": "default"},
]

_NULL_KEY_SP_ROWS = [
    {"service_point_id": "SP-X1", "customer_id": "CUST-X1", "node_id": None,
     "meter_device_id": None, "tenant_id": "default"},
    {"service_point_id": "SP-X2", "customer_id": "CUST-X2", "node_id": None,
     "meter_device_id": None, "tenant_id": "default"},
]

_CUSTOMER_ROW = {"customer_id": "CUST-001", "name": "Acme Tenant", "address": "1 Main St",
                  "phone": "555-0100", "priority": "standard", "tenant_id": "default"}


def _patch(query_all):
    orig = cim_db.query_all
    cim_db.query_all = query_all

    def restore():
        cim_db.query_all = orig
    return restore


def test_customer_from_row_maps_every_field():
    c = mapping_metering.customer_from_row(_CUSTOMER_ROW)
    assert c.customerName == "Acme Tenant"
    assert c.priority == "standard"
    assert c.address == "1 Main St"
    assert c.phone == "555-0100"
    assert c.tenantId == "default"


def test_service_point_maps_one_to_one():
    sp = mapping_metering.service_point_from_row(_SHARED_SP_ROWS[0])
    assert sp.customerId == "CUST-001"
    assert sp.nodeId == "ND-METER001"
    assert sp.meterDeviceId == "METER001"


def test_usage_point_dedups_service_points_sharing_one_node_and_meter():
    restore = _patch(lambda sql, params=(): [] if "LEFT JOIN" in sql else list(_SHARED_SP_ROWS))
    try:
        ups = mapping_metering.list_usage_points(tenant_id=None, limit=100, offset=0)
    finally:
        restore()
    assert len(ups) == 1, f"expected exactly 1 UsagePoint for 3 ServicePoints sharing one meter, got {len(ups)}"
    assert ups[0].meterDeviceId == "METER001"
    assert ups[0].synthesized is False


def test_usage_point_lists_all_three_contributing_customers():
    restore = _patch(lambda sql, params=(): [] if "LEFT JOIN" in sql else list(_SHARED_SP_ROWS))
    try:
        ups = mapping_metering.list_usage_points(tenant_id=None, limit=100, offset=0)
    finally:
        restore()
    assert len(ups[0].customerIds) == 3


def test_service_points_with_null_node_and_meter_each_get_their_own_usage_point():
    """A NULL node_id/meter_device_id key must not be treated as one shared
    group (Postgres GROUP BY would merge NULL=NULL; this mapping deliberately
    keys by service_point_id instead in that case -- see metering.py)."""
    restore = _patch(lambda sql, params=(): [] if "LEFT JOIN" in sql else list(_NULL_KEY_SP_ROWS))
    try:
        ups = mapping_metering.list_usage_points(tenant_id=None, limit=100, offset=0)
    finally:
        restore()
    assert len(ups) == 2, "two NULL-keyed service points must not collapse into one UsagePoint"


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
