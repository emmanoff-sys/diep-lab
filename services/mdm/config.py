"""MDM configuration — stdlib only, no third-party imports (so importing this
module never fails regardless of what's installed)."""
from __future__ import annotations

import os


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class Settings:
    # MQTT (mirrors ingestor/telemetry_ingestor.py's env var names)
    MQTT_BROKER = os.getenv("MQTT_BROKER", "diep-mqtt")
    MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
    MQTT_USER = os.getenv("MQTT_USER", "")
    MQTT_PASS = os.getenv("MQTT_PASS", "")
    MQTT_TLS = _bool("MQTT_TLS", False)
    MQTT_CA_CERTS = os.getenv("MQTT_CA_CERTS")
    MQTT_CLIENT_CERT = os.getenv("MQTT_CLIENT_CERT")
    MQTT_CLIENT_KEY = os.getenv("MQTT_CLIENT_KEY")

    # Input: subscribe to the same telemetry wildcard the ingestor uses;
    # MDM only acts on envelope-shaped messages, ignoring legacy flat payloads
    # (those drivers haven't migrated — see AMI_INGEST_PHASE4_CONTRACT.md §1).
    TELEMETRY_TOPIC = os.getenv("MDM_TELEMETRY_TOPIC", "diep/+/+")

    # Output: the "trusted" stream — see services/mdm/topics.py. Deliberately
    # NOT added to contracts/topics.py (that package is frozen this phase).
    TRUSTED_TOPIC_SUFFIX = os.getenv("MDM_TRUSTED_TOPIC_SUFFIX", "trusted")

    # Database (mirrors fastapi/common.py's DB_CONFIG env var names — same
    # .env, read-only usage for device metadata enrichment).
    DB_HOST = os.getenv("DB_HOST", "diep-timescaledb")
    DB_NAME = os.getenv("DB_NAME", "diep")
    DB_USER = os.getenv("DB_USER", "diep")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "diep123")

    # Duplicate detection
    DEDUP_POLICY = os.getenv("MDM_DEDUP_POLICY", "timestamp_sequence_correlation")
    DEDUP_CACHE_SIZE = int(os.getenv("MDM_DEDUP_CACHE_SIZE", "50000"))

    # Gap detection: expected sampling interval per measurement_type, seconds.
    # Falls back to DEFAULT_EXPECTED_INTERVAL_S when a measurement_type isn't
    # listed. Configurable via MDM_EXPECTED_INTERVALS="voltage=5,power_kw=5".
    DEFAULT_EXPECTED_INTERVAL_S = float(os.getenv("MDM_DEFAULT_EXPECTED_INTERVAL_S", "5"))
    GAP_TOLERANCE_MULTIPLIER = float(os.getenv("MDM_GAP_TOLERANCE_MULTIPLIER", "2.0"))

    # Clock drift: how far timestamp_utc may lag/lead MDM's own receive time
    # before it's flagged (does not change quality — see timestamps.py).
    CLOCK_DRIFT_THRESHOLD_S = float(os.getenv("MDM_CLOCK_DRIFT_THRESHOLD_S", "30"))

    # Out-of-range physical limits per measurement_type, for the quality
    # engine's OUT_OF_RANGE check. Conservative defaults for the measurement
    # types AMI Ingest Phase 4 actually publishes today (voltage/current/
    # power_kw/frequency); unlisted types are not range-checked.
    RANGE_LIMITS = {
        "voltage": (0.0, 500.0),
        "current": (0.0, 200.0),
        "power_kw": (-1000.0, 1000.0),
        "frequency": (45.0, 65.0),
    }

    HEALTH_PORT = int(os.getenv("MDM_HEALTH_PORT", "9201"))

    @classmethod
    def expected_intervals(cls) -> dict[str, float]:
        raw = os.getenv("MDM_EXPECTED_INTERVALS", "")
        out: dict[str, float] = {}
        for pair in raw.split(","):
            pair = pair.strip()
            if not pair or "=" not in pair:
                continue
            k, v = pair.split("=", 1)
            try:
                out[k.strip()] = float(v.strip())
            except ValueError:
                continue
        return out
