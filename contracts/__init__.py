"""DIEP canonical contracts — AMI Ingest Phase 4.

Single source of truth for the MQTT/Kafka telemetry contract (topics, payload
schema, quality model, versioning). See AMI_INGEST_PHASE4_CONTRACT.md for the
full specification this package implements.

Nothing downstream (MDM, OPC UA, CIM, ADMS) should redefine these shapes —
import from here.
"""
from .quality import Quality
from .telemetry import Measurement, SCHEMA_VERSION, TelemetryEnvelope, is_version_compatible

__all__ = [
    "Quality",
    "Measurement",
    "TelemetryEnvelope",
    "SCHEMA_VERSION",
    "is_version_compatible",
]
