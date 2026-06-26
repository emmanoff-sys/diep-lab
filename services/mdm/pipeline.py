"""MDM processing pipeline — orchestrates every engine into one
validate -> dedup -> timestamp -> gap -> quality -> unit -> enrich -> publish
pass per envelope. See MDM_DESIGN.md for the full architecture.

Output contract (the "trusted" payload): the input envelope's own
to_dict() shape, UNCHANGED in structure — per-measurement `quality`/`unit`/
`value` may be updated by the quality/unit engines (escalation and
normalization are real changes, not metadata), but no field is added, removed,
or renamed on TelemetryEnvelope/Measurement (contracts/ is not modified or
monkey-patched). All of MDM's own findings (device metadata, quality
transitions, unit conversions, gap events, timestamp assessment) are carried
in one additive top-level `mdm` key, layered on top of — not replacing — the
canonical schema. See MDM_DESIGN.md §3 for why this satisfies "do not modify
the canonical schema; only quality and metadata should change."
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from .duplicates import DuplicateDetector
from .enrichment import DeviceMetadataEnricher
from .gaps import GapDetector
from .metrics import MdmMetrics
from .quality import QualityAssessor
from .timestamps import TimestampNormalizer
from .topics import build_trusted_topic
from .units import UnitNormalizer
from .validation import ValidationEngine


@dataclass
class PipelineResult:
    accepted: bool
    reason: str | None = None
    topic: str | None = None
    payload: dict | None = None


class MdmPipeline:
    def __init__(
        self,
        validator: ValidationEngine | None = None,
        deduplicator: DuplicateDetector | None = None,
        timestamp_normalizer: TimestampNormalizer | None = None,
        gap_detector: GapDetector | None = None,
        quality_assessor: QualityAssessor | None = None,
        unit_normalizer: UnitNormalizer | None = None,
        enricher: DeviceMetadataEnricher | None = None,
        metrics: MdmMetrics | None = None,
    ):
        self.validator = validator or ValidationEngine()
        self.deduplicator = deduplicator or DuplicateDetector()
        self.timestamp_normalizer = timestamp_normalizer or TimestampNormalizer()
        self.gap_detector = gap_detector or GapDetector()
        self.quality_assessor = quality_assessor or QualityAssessor()
        self.unit_normalizer = unit_normalizer or UnitNormalizer()
        self.enricher = enricher or DeviceMetadataEnricher()
        self.metrics = metrics or MdmMetrics()

    def process(self, raw: dict, domain: str, received_at: datetime | None = None) -> PipelineResult:
        start = time.monotonic()
        received_at = received_at or datetime.now(timezone.utc)

        validation = self.validator.validate(raw)
        if not validation.accepted:
            self.metrics.envelopes_rejected_total.labels(reason=validation.reason).inc()
            return PipelineResult(accepted=False, reason=validation.reason)
        envelope = validation.envelope

        dup = self.deduplicator.check_and_record(envelope)
        if dup.is_duplicate:
            self.metrics.duplicates_total.labels(matched_on=",".join(dup.matched_on) or "unknown").inc()
            return PipelineResult(accepted=False, reason="duplicate")

        ts_assessment = self.timestamp_normalizer.assess(envelope, received_at)
        gap_events = self.gap_detector.check(envelope)
        for ev in gap_events:
            self.metrics.gap_events_total.labels(measurement_type=ev.measurement_type).inc()

        quality_transitions = []
        unit_conversions = []
        new_measurements = []
        estimated_count = 0
        for m in envelope.measurements:
            # Unit normalization MUST run before quality's range check —
            # RANGE_LIMITS (config.py) are expressed in canonical units, so
            # checking a not-yet-converted value (e.g. 1200 W against the
            # kW range) against them would be comparing different scales.
            m, conversion = self.unit_normalizer.normalize(m)
            if conversion is not None:
                unit_conversions.append(conversion)
            m, transition = self.quality_assessor.assess(m)
            if transition is not None:
                quality_transitions.append(transition)
                self.metrics.quality_transitions_total.labels(reason=transition.reason).inc()
            new_measurements.append(m)
            if m.estimated:
                estimated_count += 1
        envelope.measurements = new_measurements

        device_meta = self.enricher.enrich(envelope.device_id)

        self.metrics.measurements_processed_total.inc(len(envelope.measurements))
        if estimated_count:
            self.metrics.measurements_estimated_total.inc(estimated_count)

        payload = envelope.to_dict()
        payload["mdm"] = {
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "device_metadata": {
                "tenant_id": device_meta.tenant_id,
                "site_id": device_meta.site_id,
                "device_type": device_meta.device_type,
                "asset_class": device_meta.asset_class,
                "feeder_id": device_meta.feeder_id,
                "transformer_id": device_meta.transformer_id,
            },
            "quality_transitions": [
                {"measurement_type": t.measurement_type, "original_quality": t.original_quality.value,
                 "new_quality": t.new_quality.value, "reason": t.reason}
                for t in quality_transitions
            ],
            "unit_conversions": [
                {"measurement_type": c.measurement_type, "original_unit": c.original_unit,
                 "original_value": c.original_value, "canonical_unit": c.canonical_unit,
                 "canonical_value": c.canonical_value}
                for c in unit_conversions
            ],
            "gap_events": [
                {"measurement_type": g.measurement_type, "gap_seconds": g.gap_seconds,
                 "estimated_missed_samples": g.estimated_missed_samples}
                for g in gap_events
            ],
            "timestamp_assessment": {
                "drift_seconds": ts_assessment.drift_seconds,
                "is_drifted": ts_assessment.is_drifted,
                "is_out_of_order": ts_assessment.is_out_of_order,
            },
        }

        self.metrics.processing_latency_seconds.observe(time.monotonic() - start)
        topic = build_trusted_topic(domain, envelope.device_id)
        return PipelineResult(accepted=True, topic=topic, payload=payload)

    @staticmethod
    def serialize(payload: dict) -> str:
        return json.dumps(payload)
