"""services/cim/validation.py -- query-parameter validation against this
service's own registries (profiles, node_types, ISO timestamps, limits).
Every rejection carries a distinct reason code, never a generic error."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.cim import validation  # noqa: E402


def test_known_profiles_pass():
    for p in ("metering", "network", "measurements", "full"):
        assert validation.validate_profile(p) == p


def test_unknown_profile_raises_invalid_profile():
    raised_reason = None
    try:
        validation.validate_profile("not-a-real-profile")
    except validation.CimValidationError as exc:
        raised_reason = exc.reason
    assert raised_reason == "invalid_profile"


def test_known_node_types_pass_including_recloser():
    """recloser was added to grid_nodes' CHECK constraint by
    sql/021_network_electrical.sql, after sql/013's original list --
    validation.py must track the living set, not a stale snapshot."""
    for nt in ("substation", "feeder", "transformer", "switch", "recloser", "bus", "meter", "der", "load"):
        assert validation.validate_node_type(nt) == nt


def test_unknown_node_type_raises_invalid_node_type():
    raised_reason = None
    try:
        validation.validate_node_type("not-a-real-type")
    except validation.CimValidationError as exc:
        raised_reason = exc.reason
    assert raised_reason == "invalid_node_type"


def test_none_node_type_is_a_valid_unfiltered_request():
    assert validation.validate_node_type(None) is None


def test_valid_iso_timestamp_parses():
    dt = validation.validate_iso_timestamp("2026-06-25T23:05:26.701346+00:00", "since")
    assert dt is not None
    assert dt.year == 2026


def test_z_suffixed_timestamp_also_parses():
    dt = validation.validate_iso_timestamp("2026-06-25T23:05:26Z", "since")
    assert dt is not None


def test_malformed_timestamp_raises_invalid_timestamp():
    raised_reason = None
    try:
        validation.validate_iso_timestamp("not-a-date", "since")
    except validation.CimValidationError as exc:
        raised_reason = exc.reason
    assert raised_reason == "invalid_timestamp"


def test_limit_within_range_passes():
    assert validation.validate_limit(100, 1000) == 100


def test_limit_out_of_range_raises_invalid_limit():
    for bad in (0, -1, 1001):
        raised_reason = None
        try:
            validation.validate_limit(bad, 1000)
        except validation.CimValidationError as exc:
            raised_reason = exc.reason
        assert raised_reason == "invalid_limit", f"limit={bad} should have been rejected"


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
