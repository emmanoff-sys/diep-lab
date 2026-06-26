"""MDM Prometheus metrics.

prometheus_client is imported lazily (same pattern as the rest of this
package) so this module stays importable without it; MdmMetrics falls back
to a no-op implementation if it's genuinely missing at runtime, rather than
crashing the service over an observability dependency.

Spec asks for "duplicate rate" and "estimated percentage" as metrics. Per
standard Prometheus practice, rates/percentages are computed at query time
from raw counters via PromQL (e.g.
`rate(mdm_measurements_estimated_total[5m]) / rate(mdm_measurements_processed_total[5m])`),
not stored as a pre-computed gauge — storing a pre-divided ratio loses the
ability to re-window it and can divide by a stale/zero denominator. The
counters below are what those PromQL rates are computed from.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("diep-mdm.metrics")


class _NoOpMetric:
    def labels(self, *args, **kwargs):
        return self

    def inc(self, amount: float = 1.0) -> None:
        pass

    def observe(self, amount: float) -> None:
        pass


class MdmMetrics:
    """Singleton-style holder — instantiate once in service.py and pass it
    through the pipeline; tests can construct their own throwaway instance."""

    def __init__(self):
        try:
            from prometheus_client import Counter, Histogram
        except ImportError:
            logger.warning("prometheus_client not installed — metrics are no-ops")
            self.measurements_processed_total = _NoOpMetric()
            self.measurements_estimated_total = _NoOpMetric()
            self.envelopes_rejected_total = _NoOpMetric()
            self.duplicates_total = _NoOpMetric()
            self.gap_events_total = _NoOpMetric()
            self.quality_transitions_total = _NoOpMetric()
            self.processing_latency_seconds = _NoOpMetric()
            return

        self.measurements_processed_total = Counter(
            "mdm_measurements_processed_total", "Measurements that passed validation and were published",
        )
        self.measurements_estimated_total = Counter(
            "mdm_measurements_estimated_total", "Measurements published with estimated=true",
        )
        self.envelopes_rejected_total = Counter(
            "mdm_envelopes_rejected_total", "Envelopes rejected by the validation engine", ["reason"],
        )
        self.duplicates_total = Counter(
            "mdm_duplicates_total", "Envelopes dropped as duplicates", ["matched_on"],
        )
        self.gap_events_total = Counter(
            "mdm_gap_events_total", "Missing-interval gap events detected", ["measurement_type"],
        )
        self.quality_transitions_total = Counter(
            "mdm_quality_transitions_total", "MDM-initiated quality escalations (never overwrites a non-GOOD flag)", ["reason"],
        )
        self.processing_latency_seconds = Histogram(
            "mdm_processing_latency_seconds", "End-to-end pipeline latency per envelope (receive to publish)",
        )
