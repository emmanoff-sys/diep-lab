"""services/cim/metrics.py -- lazy prometheus_client import; falls back to
no-ops when absent rather than crashing the service over an observability
dependency."""
import os
import sys
from importlib.util import find_spec

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.cim.metrics import CimMetrics, _NoOpMetric  # noqa: E402

# Instantiated once, module level: prometheus_client's default registry
# raises on a second Counter("cim_requests_total", ...) registration within
# one process, so every "real metrics" assertion shares this one instance
# rather than constructing a fresh CimMetrics() per test.
_METRICS = CimMetrics()


def test_metrics_object_has_all_three_instruments():
    assert hasattr(_METRICS, "requests_total")
    assert hasattr(_METRICS, "mapping_errors_total")
    assert hasattr(_METRICS, "request_latency_seconds")


def test_noop_metric_methods_dont_raise_and_are_chainable():
    noop = _NoOpMetric()
    noop.labels(route="/cim/meters", status="200").inc()
    noop.observe(0.05)
    noop.set(1.0)
    noop.set_function(lambda: 1.0)


def test_real_counter_used_when_prometheus_client_available():
    if find_spec("prometheus_client") is None:
        assert isinstance(_METRICS.requests_total, _NoOpMetric)
        return
    assert not isinstance(_METRICS.requests_total, _NoOpMetric)
    _METRICS.requests_total.labels(route="/cim/meters", status="200").inc()


def test_falls_back_to_noop_when_prometheus_client_unavailable():
    import builtins
    real_import = builtins.__import__

    def blocking_import(name, *args, **kwargs):
        if name == "prometheus_client":
            raise ImportError("simulated absence")
        return real_import(name, *args, **kwargs)

    builtins.__import__ = blocking_import
    try:
        m = CimMetrics()  # fresh instance -- never touches the real registry on this path
    finally:
        builtins.__import__ = real_import
    assert isinstance(m.requests_total, _NoOpMetric)
    assert isinstance(m.mapping_errors_total, _NoOpMetric)
    assert isinstance(m.request_latency_seconds, _NoOpMetric)
    m.requests_total.labels(route="/x", status="200").inc()  # must not raise


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
