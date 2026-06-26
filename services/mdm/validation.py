"""MDM Validation Engine.

contracts.TelemetryEnvelope already rejects most structural problems at
construction (missing required fields, impossible/non-UTC timestamps,
unsupported MAJOR schema versions, invalid quality enum, duplicate
measurement_type within one envelope) — see AMI_INGEST_PHASE4_CONTRACT.md.
This engine wraps that construction and adds the two checks the frozen
contract deliberately does NOT enforce (it only requires non-empty strings):
unit validity against a known registry, and correlation_id being a
syntactically valid UUID.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from contracts import TelemetryEnvelope
from contracts.telemetry import ContractValidationError

# measurement_type -> allowed units. Conservative: only the units AMI Ingest
# Phase 4 actually publishes today (drivers/dlms). Extend as new measurement
# types/drivers are onboarded — see MDM_DESIGN.md §2.
KNOWN_UNITS: dict[str, set[str]] = {
    "voltage": {"V", "kV"},
    "current": {"A", "mA"},
    "power_kw": {"kW", "W", "MW"},
    "frequency": {"Hz"},
    "active_power": {"kW", "W", "MW"},
    "energy_import_kwh": {"kWh", "Wh", "MWh"},
    "energy_export_kwh": {"kWh", "Wh", "MWh"},
    "power_factor": {"", "ratio"},
    "temperature": {"C", "F", "K"},
}

# Rejection reason codes — stable strings, used as the Prometheus label in
# services/mdm/metrics.py (REJECTED_TOTAL) and the audit log.
REASON_CONTRACT_VIOLATION = "contract_violation"   # ContractValidationError from the frozen contract
REASON_INVALID_UNIT = "invalid_unit"
REASON_MALFORMED_CORRELATION_ID = "malformed_correlation_id"


@dataclass
class ValidationResult:
    accepted: bool
    envelope: TelemetryEnvelope | None = None
    reason: str | None = None
    detail: str | None = None
    invalid_measurement_types: list[str] = field(default_factory=list)


class ValidationEngine:
    def __init__(self, known_units: dict[str, set[str]] | None = None):
        self.known_units = known_units if known_units is not None else KNOWN_UNITS

    def validate(self, raw: dict) -> ValidationResult:
        try:
            envelope = TelemetryEnvelope.from_dict(raw)
        except ContractValidationError as exc:
            return ValidationResult(accepted=False, reason=REASON_CONTRACT_VIOLATION, detail=str(exc))
        except TypeError as exc:
            # from_dict re-raises unexpected/missing constructor args as TypeError.
            return ValidationResult(accepted=False, reason=REASON_CONTRACT_VIOLATION, detail=str(exc))

        try:
            uuid.UUID(envelope.correlation_id)
        except (ValueError, AttributeError, TypeError):
            return ValidationResult(
                accepted=False, reason=REASON_MALFORMED_CORRELATION_ID,
                detail=f"correlation_id is not a valid UUID: {envelope.correlation_id!r}",
            )

        bad_units = [
            m.measurement_type for m in envelope.measurements
            if m.measurement_type in self.known_units and m.unit not in self.known_units[m.measurement_type]
        ]
        if bad_units:
            return ValidationResult(
                accepted=False, reason=REASON_INVALID_UNIT,
                detail=f"unit not in known registry for: {bad_units}",
                invalid_measurement_types=bad_units,
            )

        return ValidationResult(accepted=True, envelope=envelope)
