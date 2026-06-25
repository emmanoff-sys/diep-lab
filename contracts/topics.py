"""AMI Ingest Phase 4 — MQTT + Kafka topic contract.

This is the topic/key registry described in AMI_INGEST_PHASE4_CONTRACT.md
§§2/4. Two different maturity levels, by design:

- **MQTT builders** match what's actually wired and running today
  (drivers/diep_driver/base.py's `base_topic`/`cmd_topic`/`ack_topic`, used by
  every existing driver + the ingestor's `diep/+/+` subscription). The three
  new categories (alarm/status/heartbeat) are additive 4th-level suffixes
  under the same base — no existing topic string changes, so nothing
  currently subscribed breaks.
- **Kafka topic names + key/partition helpers are a specification**, not a
  wired pipeline. Telemetry today flows MQTT -> ingestor -> HTTP -> FastAPI ->
  TimescaleDB (no Kafka hop) — see AMI_INGEST_PHASE4_CONTRACT.md §4 for why
  this phase defines the Kafka contract ahead of building it (same Phase-0
  discovery-before-build discipline as docs/opcua-discovery.md), rather than
  silently standing up a second, parallel telemetry pipeline mid-incident.
"""
from __future__ import annotations

from dataclasses import dataclass

# --- MQTT ---------------------------------------------------------------

# Tenant isolation today is enforced at the envelope level (tenant_id is a
# mandatory, validated field on every TelemetryEnvelope — see telemetry.py),
# not the topic path: the broker is single-tenant in this deployment, no
# per-tenant ACLs exist yet. `build_telemetry_topic_v2` below is the target
# path-segmented layout for when that lands; not used by any driver yet.


def build_telemetry_topic(domain: str, device_id: str) -> str:
    return f"diep/{domain}/{device_id}"


def build_cmd_topic(domain: str, device_id: str) -> str:
    return f"{build_telemetry_topic(domain, device_id)}/cmd"


def build_ack_topic(domain: str, device_id: str) -> str:
    return f"{build_telemetry_topic(domain, device_id)}/ack"


def build_alarm_topic(domain: str, device_id: str) -> str:
    return f"{build_telemetry_topic(domain, device_id)}/alarm"


def build_status_topic(domain: str, device_id: str) -> str:
    """Device lifecycle (online/offline). Retained — see MQTT_TOPICS below."""
    return f"{build_telemetry_topic(domain, device_id)}/status"


def build_heartbeat_topic(domain: str, device_id: str) -> str:
    return f"{build_telemetry_topic(domain, device_id)}/heartbeat"


def build_telemetry_topic_v2(tenant_id: str, domain: str, device_id: str) -> str:
    """Target future layout once per-tenant broker ACLs exist. Not wired."""
    return f"diep/{tenant_id}/{domain}/{device_id}"


@dataclass(frozen=True)
class TopicPolicy:
    qos: int
    retained: bool
    description: str


# QoS / retained-flag policy per topic category (contract doc §2.3).
MQTT_TOPIC_POLICY = {
    "telemetry": TopicPolicy(qos=0, retained=False,
                              description="Periodic readings; loss-tolerant, high frequency."),
    "cmd": TopicPolicy(qos=1, retained=False,
                        description="Commands must arrive at least once; never retained (stale command replay risk)."),
    "ack": TopicPolicy(qos=1, retained=False,
                        description="Command acknowledgements; at-least-once."),
    "alarm": TopicPolicy(qos=1, retained=False,
                          description="Alarm events; at-least-once, not state — not retained."),
    "status": TopicPolicy(qos=1, retained=True,
                           description="Online/offline lifecycle; retained so new subscribers see last-known state immediately."),
    "heartbeat": TopicPolicy(qos=0, retained=True,
                              description="Liveness only; retained, loss-tolerant (next heartbeat supersedes)."),
}

# Wildcard subscription rules (contract doc §2.4):
#   diep/+/+            -> telemetry only (3 levels; excludes cmd/ack/alarm/status/heartbeat, all 4 levels)
#   diep/+/+/cmd         -> all commands, any domain/device
#   diep/+/+/ack         -> all acks
#   diep/+/+/alarm       -> all alarms
#   diep/+/+/status      -> all lifecycle state (retained, so a fresh subscribe gets last-known immediately)
#   diep/+/+/heartbeat   -> all heartbeats
#   diep/<domain>/#      -> everything for one domain (telemetry + all 4-level subtopics)
TELEMETRY_WILDCARD = "diep/+/+"
ALL_SUBTOPIC_WILDCARDS = {
    "cmd": "diep/+/+/cmd",
    "ack": "diep/+/+/ack",
    "alarm": "diep/+/+/alarm",
    "status": "diep/+/+/status",
    "heartbeat": "diep/+/+/heartbeat",
}


# --- Kafka (specification — see module docstring) ------------------------

KAFKA_TOPICS = {
    "commands": "diep.commands",                  # existing, wired (fastapi -> dispatcher)
    "telemetry": "diep.telemetry",                 # spec only — not yet produced/consumed
    "events": "diep.events",
    "alarms": "diep.alarms",
    "device_registration": "diep.device.registration",
    "device_state": "diep.device.state",
    "quality_events": "diep.quality.events",
}

# Retention per topic (contract doc §4.3). "compact" = log-compacted
# (latest value per key retained indefinitely — a changelog, not a stream).
KAFKA_RETENTION = {
    "diep.commands": "7d",                # unchanged from current deployment
    "diep.telemetry": "7d",               # hot-replay window for downstream consumers (MDM)
    "diep.events": "30d",                 # operational investigation window
    "diep.alarms": "30d",
    "diep.device.registration": "compact",  # full device registry is reconstructable by reading from offset 0
    "diep.device.state": "compact",         # latest known state per device_id
    "diep.quality.events": "30d",
}


def partition_key(tenant_id: str, device_id: str) -> str:
    """Pins every message for a given device to one partition, so per-device
    ordering is preserved (Kafka only orders within a partition). Cross-device
    ordering is explicitly NOT guaranteed or required — see contract doc §4.4."""
    if not tenant_id or not device_id:
        raise ValueError("partition_key requires both tenant_id and device_id")
    return f"{tenant_id}:{device_id}"
