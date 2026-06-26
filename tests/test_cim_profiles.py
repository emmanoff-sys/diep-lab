"""services/cim/serialization/profiles.py -- each named profile includes
exactly its documented object-type subset, nothing extra; "full" means
unrestricted."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.cim.serialization import profiles  # noqa: E402


def test_metering_profile_includes_only_metering_classes():
    expected = {"EndDevice", "Meter", "UsagePoint", "ServicePoint", "Customer", "Measurement", "MeasurementValue"}
    for cls in expected:
        assert profiles.object_type_allowed("metering", cls), f"{cls} should be in 'metering'"
    for cls in ("ConnectivityNode", "Terminal", "Transformer", "Feeder", "Asset"):
        assert not profiles.object_type_allowed("metering", cls), f"{cls} should NOT be in 'metering'"


def test_network_profile_includes_only_network_classes():
    for cls in ("ConnectivityNode", "Terminal", "Transformer", "Feeder"):
        assert profiles.object_type_allowed("network", cls)
    for cls in ("Meter", "Customer", "Asset"):
        assert not profiles.object_type_allowed("network", cls)


def test_measurements_profile_includes_only_measurement_classes():
    assert profiles.object_type_allowed("measurements", "Measurement")
    assert profiles.object_type_allowed("measurements", "MeasurementValue")
    assert not profiles.object_type_allowed("measurements", "Meter")


def test_full_profile_allows_every_class():
    for cls in ("EndDevice", "Meter", "Asset", "Customer", "ServicePoint", "UsagePoint",
                "ConnectivityNode", "Terminal", "Transformer", "Feeder", "Measurement", "MeasurementValue"):
        assert profiles.object_type_allowed("full", cls)


def test_asset_only_appears_in_full_not_metering_or_network():
    assert not profiles.object_type_allowed("metering", "Asset")
    assert not profiles.object_type_allowed("network", "Asset")
    assert profiles.object_type_allowed("full", "Asset")


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
