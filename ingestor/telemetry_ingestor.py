#!/usr/bin/env python3
"""DIEP Telemetry Ingestor — MQTT → FastAPI /telemetry.

Bridges device telemetry into the platform's data plane. Subscribes to the
3-level telemetry topics (diep/<domain>/<device_id>), normalizes each device's
native payload onto the canonical TelemetryPayload schema, and POSTs it to
FastAPI /telemetry — which writes the TimescaleDB hypertable AND the Redis
`state:` mirror that powers /state, asset health, and the digital twins.

Mirrors the command dispatcher pattern (Kafka→MQTT→HTTP); this is the inbound
telemetry counterpart (MQTT→HTTP). Command/ack topics are 4 levels, so the
3-level subscription wildcard excludes them automatically.

Post-SIT stabilization sprint: the MQTT receive callback only enqueues raw
bytes onto a bounded queue; a small worker-thread pool does validation
(including explicit non-finite-value rejection — the SIT's silent-data-loss
finding) and persistence. This keeps paho's network-loop thread free to
service PINGREQ/PINGRESP under load, which the prior single-threaded,
synchronous-POST design did not (the SIT's throughput-ceiling finding).

Dependencies: paho-mqtt, requests, prometheus-client
"""
import json
import logging
import math
import os
import queue
import signal
import threading
import time
from collections import OrderedDict

import requests
import paho.mqtt.client as mqtt

# AMI Ingest Phase 4 — envelope-shaped payloads (drivers/dlms publishes these;
# see AMI_INGEST_PHASE4_CONTRACT.md and contracts/telemetry.py, the source of
# truth this module defers to). Mounted read-only — see docker-compose-ingestor.yml.
from contracts import TelemetryEnvelope
from contracts.telemetry import ContractValidationError

from health import start_health_server
from metrics import IngestorMetrics

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("diep-ingestor")

MQTT_BROKER = os.getenv("MQTT_BROKER", "diep-mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "diep-nodered")
MQTT_PASS = os.getenv("MQTT_PASS", "nodered-pass-2026")
FASTAPI_BASE = os.getenv("FASTAPI_BASE", "http://diep-fastapi:8000")
# Phase 9J: machine-client service token for the authenticated /telemetry route.
SERVICE_TOKEN = os.getenv("DIEP_SERVICE_TOKEN", "diep-service-dev-token-CHANGE-ME")
AUTH_HEADERS = {"Authorization": f"Bearer {SERVICE_TOKEN}"}

# Post-SIT Work Item 4: env-configurable so the same image can subscribe to
# raw telemetry (default, used while validating Work Items 1-3 in isolation)
# or to MDM's post-quality-engine "trusted" stream (diep/+/+/trusted) once
# MDM is wired into the production path — see AMI_INGEST/MDM docs. 3 levels
# = telemetry only (cmd/ack are 4 levels); the trusted suffix adds a 4th
# level on purpose, distinguishing it from cmd/ack at the topic-shape level
# only by name, not depth -- the subscription string itself decides which.
TELEMETRY_TOPIC = os.getenv("INGESTOR_TELEMETRY_TOPIC", "diep/+/+")

# Post-SIT Work Item 2: bounded receive queue + worker pool, so HTTP latency
# never blocks the MQTT network-loop thread. Defaults are starting points
# confirmed/tuned against PERFORMANCE_REPORT.md's Round 2 benchmark.
QUEUE_MAXSIZE = int(os.getenv("INGESTOR_QUEUE_MAXSIZE", "10000"))
NUM_WORKERS = int(os.getenv("INGESTOR_WORKERS", "8"))
# How long on_message will block trying to enqueue before treating it as
# genuine overload and shedding the message (logged + metered, never
# silent). Short on purpose: long enough to absorb micro-bursts, short
# enough that the network thread is never blocked long enough to itself
# risk the keepalive loss this redesign exists to fix.
BACKPRESSURE_TIMEOUT_S = float(os.getenv("INGESTOR_BACKPRESSURE_TIMEOUT_S", "0.5"))

HEALTH_PORT = int(os.getenv("INGESTOR_HEALTH_PORT", "9203"))

# Topics whose final path segment is not the registered device_id.
TOPIC_ID_OVERRIDES = {"meter1": "METER001"}

# Fields the FastAPI TelemetryPayload schema requires (all numeric, no defaults).
CANONICAL_FIELDS = ("voltage", "current", "power_kw", "frequency", "solar_kw",
                    "battery_soc", "grid_import_kw", "grid_export_kw")

# Phase 9-Schema: device-class extended fields the drivers publish on MQTT.
# Typed nullable telemetry columns:
EXTENDED_NUMERIC = ("power_factor", "energy_import_kwh", "energy_export_kwh",
                    "temperature", "soh")
# Device-specific long tail -> telemetry.metadata JSONB:
EXTRA_FIELDS = ("vehicle_soc", "connector_status", "session_energy_kwh",
                "load_kw", "setpoint_kw", "grid_connected", "mode")

# AMI Ingest Phase 4 — bounded dedup cache (contract doc §5: same
# (tenant_id, device_id, timestamp_utc, sequence_number) is the same reading,
# regardless of transport-level retries/redelivery). In-process only; fine for
# a single ingestor instance, not a substitute for a shared store if this is
# ever scaled to multiple ingestor replicas. Guarded by _dedup_lock now that
# multiple worker threads touch it concurrently.
_SEEN_MAX = 10_000
_seen_envelopes: "OrderedDict[tuple, None]" = OrderedDict()
_dedup_lock = threading.Lock()

metrics = IngestorMetrics()
_work_queue: "queue.Queue[tuple[str, bytes]]" = queue.Queue(maxsize=QUEUE_MAXSIZE)
_stop_event = threading.Event()
_thread_local = threading.local()


def _is_duplicate_envelope(key: tuple) -> bool:
    with _dedup_lock:
        if key in _seen_envelopes:
            return True
        _seen_envelopes[key] = None
        if len(_seen_envelopes) > _SEEN_MAX:
            _seen_envelopes.popitem(last=False)
        return False


def is_envelope_payload(payload: dict) -> bool:
    """Detects an AMI Ingest Phase 4 envelope vs. the legacy flat payload —
    presence of both is unambiguous (no legacy driver publishes either field)."""
    return "schema_version" in payload and "measurements" in payload


def _finite(value) -> bool:
    """True only for an actual finite number (NaN/inf/bool/non-numeric all
    False) — the check the SIT found missing everywhere a measurement value
    crossed from MQTT into the HTTP body, which let NaN reach `requests`
    (which serializes it to literal `NaN`) and then TimescaleDB (which
    rejects it), with no record left behind once the response was dropped."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _reject_non_finite(rejections: dict, fields, raw_value, context: str) -> None:
    for field in fields:
        rejections[field] = {"quality": "INVALID", "rejected_reason": "non_finite_value"}
    logger.warning(f"Rejecting non-finite value for {fields} ({context or 'unknown'}): {raw_value}")
    metrics.messages_rejected_total.labels(reason="non_finite_value").inc()


def envelope_to_legacy_body(envelope: TelemetryEnvelope, context: str = "") -> dict:
    """Flattens a TelemetryEnvelope onto the existing legacy TelemetryPayload
    shape so FastAPI/TimescaleDB need no schema change this phase. Per-point
    quality/estimated and every envelope-level field NOT already a typed
    column are preserved in `extra` -> telemetry.metadata JSONB, so nothing is
    silently dropped even though it isn't query-able as a real column yet
    (promoting them is a future migration, not this phase's scope).

    Non-finite measurement values are withheld from `body` (the canonical
    field keeps its 0.0 default) and recorded as an explicit INVALID
    rejection in `quality_by_field` instead — see _finite()."""
    # Same 0.0-default contract as normalize() — FastAPI's TelemetryPayload
    # requires every canonical field, and DLMS (4 fields) doesn't cover all 8.
    body = {field: 0.0 for field in CANONICAL_FIELDS}
    quality_by_field = {}
    for m in envelope.measurements:
        is_flattened_field = m.measurement_type in CANONICAL_FIELDS or m.measurement_type in EXTENDED_NUMERIC
        if is_flattened_field and not _finite(m.value):
            logger.warning(f"Rejecting non-finite value for {m.measurement_type} ({context or envelope.device_id}): {m.value}")
            metrics.messages_rejected_total.labels(reason="non_finite_value").inc()
            quality_by_field[m.measurement_type] = {
                "quality": "INVALID",
                "estimated": m.estimated,
                "rejected_reason": "non_finite_value",
                "original_quality": m.quality.value,
            }
            continue
        if is_flattened_field:
            body[m.measurement_type] = m.value
        quality_by_field[m.measurement_type] = {"quality": m.quality.value, "estimated": m.estimated}
    body["device_id"] = envelope.device_id
    body["time"] = envelope.timestamp_utc
    body["extra"] = {
        "tenant_id": envelope.tenant_id,
        "site_id": envelope.site_id,
        "meter_id": envelope.meter_id,
        "schema_version": envelope.schema_version,
        "correlation_id": envelope.correlation_id,
        "sequence_number": envelope.sequence_number,
        "source_protocol": envelope.source_protocol,
        "timestamp_source": envelope.timestamp_source,
        "quality": quality_by_field,
    }
    return body


def _num(value):
    """Return a float if value is numeric (bools are not), else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _accept_or_reject(out: dict, field: str, raw_value, rejections: dict, context: str) -> None:
    if raw_value is None:
        return
    if _finite(raw_value):
        out[field] = raw_value
    else:
        _reject_non_finite(rejections, (field,), raw_value, context)


def resolve_device_id(topic: str, payload: dict) -> str:
    """Prefer the device_id in the payload; fall back to the topic's last
    segment, applying overrides for sources that don't match a registered id."""
    if isinstance(payload.get("device_id"), str) and payload["device_id"]:
        return payload["device_id"]
    seg = topic.rsplit("/", 1)[-1]
    return TOPIC_ID_OVERRIDES.get(seg, seg)


def normalize(payload: dict, context: str = "") -> dict:
    """Map a device's native telemetry onto the canonical schema. Absent fields
    default to 0.0 because the API requires every field. Non-finite values are
    withheld (default stays 0.0) and recorded under extra.quality instead of
    being forwarded as NaN/inf — see _finite()."""
    out = {field: 0.0 for field in CANONICAL_FIELDS}
    rejections: dict = {}

    # 1. Direct canonical fields (smartmeter, EV charger, microgrid frequency/solar).
    for field in CANONICAL_FIELDS:
        _accept_or_reject(out, field, _num(payload.get(field)), rejections, context)

    # 2. Device-native aliases → canonical.
    soc = _num(payload.get("soc"))
    if soc is not None:                        # battery state of charge
        _accept_or_reject(out, "battery_soc", soc, rejections, context)

    output_kw = _num(payload.get("output_kw"))
    if output_kw is not None:                  # solar inverter generation
        if _finite(output_kw):
            out["solar_kw"] = output_kw
            out["power_kw"] = output_kw
            out["grid_export_kw"] = max(0.0, output_kw)
        else:
            _reject_non_finite(rejections, ("solar_kw", "power_kw", "grid_export_kw"), output_kw, context)

    pcc_kw = _num(payload.get("pcc_kw"))
    if pcc_kw is not None:                      # microgrid point of common coupling
        if _finite(pcc_kw):
            out["power_kw"] = pcc_kw
            out["grid_import_kw"] = max(0.0, pcc_kw)
            out["grid_export_kw"] = max(0.0, -pcc_kw)
        else:
            _reject_non_finite(rejections, ("power_kw", "grid_import_kw", "grid_export_kw"), pcc_kw, context)

    # 3. Phase 9-Schema: forward device-class extended fields the drivers publish.
    for field in EXTENDED_NUMERIC:              # typed nullable columns
        _accept_or_reject(out, field, _num(payload.get(field)), rejections, context)
    if payload.get("state") is not None:
        out["state"] = str(payload["state"])
    # Device-specific long tail → metadata JSONB (telemetry.metadata).
    extra = {k: payload[k] for k in EXTRA_FIELDS if k in payload}
    if rejections:
        extra["quality"] = rejections
    if extra:
        out["extra"] = extra

    return out


def on_connect(client, userdata, flags, reason_code, properties):
    logger.info(f"MQTT connected (rc={reason_code}); subscribing {TELEMETRY_TOPIC}")
    client.subscribe(TELEMETRY_TOPIC, qos=0)


def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    logger.warning(f"MQTT disconnected (rc={reason_code})")


def on_message(client, userdata, msg):
    """Runs in paho's network-loop thread — kept deliberately thin (decode
    nothing, just enqueue) so HTTP/validation latency downstream can never
    starve PINGREQ/PINGRESP servicing the way the prior synchronous design
    did under load."""
    metrics.messages_received_total.inc()
    try:
        _work_queue.put((msg.topic, msg.payload), timeout=BACKPRESSURE_TIMEOUT_S)
        metrics.queue_depth.set(_work_queue.qsize())
    except queue.Full:
        # True sustained overload beyond provisioned queue+worker capacity:
        # shed the message visibly rather than block the network thread
        # (which is exactly how the prior design lost its keepalive).
        metrics.messages_dropped_total.labels(reason="queue_full").inc()
        logger.warning(f"Dropping message on {msg.topic}: queue full (sustained overload)")


def _get_session() -> requests.Session:
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        _thread_local.session = session
    return session


def _persist(topic: str, device_id: str, body: dict) -> None:
    start = time.monotonic()
    try:
        resp = _get_session().post(f"{FASTAPI_BASE}/telemetry", json=body, headers=AUTH_HEADERS, timeout=5)
    except requests.RequestException as exc:
        logger.error(f"POST /telemetry failed for {device_id}: {exc}")
        metrics.messages_persisted_total.labels(status="error").inc()
        return
    finally:
        metrics.post_latency_seconds.observe(time.monotonic() - start)

    if resp.status_code == 201:
        logger.info(f"Ingested {topic} -> {device_id} "
                    f"(power_kw={body['power_kw']}, soc={body['battery_soc']})")
        metrics.messages_persisted_total.labels(status="201").inc()
    elif resp.status_code == 404:
        # Telemetry for a device not in the registry — skip quietly.
        logger.debug(f"Unknown device {device_id} from {topic}; skipping")
        metrics.messages_persisted_total.labels(status="404").inc()
    else:
        logger.warning(f"/telemetry returned {resp.status_code}: {resp.text[:200]}")
        metrics.messages_persisted_total.labels(status=str(resp.status_code)).inc()


def _handle_message(topic: str, raw: bytes) -> None:
    """Validation + persistence — runs in a worker thread, off the MQTT
    network-loop thread (see on_message)."""
    try:
        payload = json.loads(raw.decode())
    except (ValueError, UnicodeDecodeError) as exc:
        logger.warning(f"Dropping unparseable telemetry on {topic}: {exc}")
        metrics.messages_rejected_total.labels(reason="unparseable_json").inc()
        return
    if not isinstance(payload, dict):
        return

    if is_envelope_payload(payload):
        # A downstream consumer (e.g. MDM's "trusted" stream) may add
        # additive top-level metadata (an "mdm" key) on top of the frozen
        # envelope shape. TelemetryEnvelope.from_dict() unpacks payload
        # fields as dataclass __init__ kwargs and is strict about unknown
        # keys (raises TypeError, not ContractValidationError) -- strip
        # before parsing rather than letting it crash this worker.
        payload = dict(payload)
        payload.pop("mdm", None)
        try:
            envelope = TelemetryEnvelope.from_dict(payload)
        except (ContractValidationError, TypeError) as exc:
            logger.warning(f"Dropping invalid envelope on {topic}: {exc}")
            metrics.messages_rejected_total.labels(reason="invalid_envelope").inc()
            return
        if _is_duplicate_envelope(envelope.dedup_key()):
            logger.debug(f"Dropping duplicate envelope {envelope.dedup_key()} on {topic}")
            metrics.messages_rejected_total.labels(reason="duplicate").inc()
            return
        envelope.stamp_ingestion_time()
        device_id = envelope.device_id
        body = envelope_to_legacy_body(envelope, context=f"{topic} device={device_id}")
    else:
        device_id = resolve_device_id(topic, payload)
        body = normalize(payload, context=f"{topic} device={device_id}")
        body["device_id"] = device_id
        # Phase 9A: preserve the edge capture time (store-and-forward replays keep real timestamps).
        if payload.get("time"):
            body["time"] = payload["time"]

    _persist(topic, device_id, body)


def _worker_loop(worker_id: int) -> None:
    logger.info(f"worker-{worker_id} started")
    while not _stop_event.is_set() or not _work_queue.empty():
        try:
            topic, raw = _work_queue.get(timeout=1)
        except queue.Empty:
            continue
        try:
            _handle_message(topic, raw)
        except Exception as exc:  # noqa: BLE001 -- one bad message must never kill a worker
            logger.error(f"worker-{worker_id} unhandled error processing {topic}: {exc}")
            metrics.messages_rejected_total.labels(reason="worker_error").inc()
        finally:
            metrics.queue_depth.set(_work_queue.qsize())
    logger.info(f"worker-{worker_id} stopped")


def _apply_mqtt_tls(client):
    """Phase 9J-S4: enable mutual TLS when MQTT_TLS=1 (cert identity, no password)."""
    if os.getenv("MQTT_TLS", "0") == "1":
        import ssl
        client.tls_set(
            ca_certs=os.getenv("MQTT_CA_CERTS"),
            certfile=os.getenv("MQTT_CLIENT_CERT"),
            keyfile=os.getenv("MQTT_CLIENT_KEY"),
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )


def _status() -> dict:
    return {
        "subscribed_topic": TELEMETRY_TOPIC,
        "queue_depth": _work_queue.qsize(),
        "queue_maxsize": QUEUE_MAXSIZE,
        "workers": NUM_WORKERS,
    }


def main():
    start_health_server(HEALTH_PORT, status_provider=_status)

    workers = [
        threading.Thread(target=_worker_loop, args=(i,), name=f"ingestor-worker-{i}", daemon=True)
        for i in range(NUM_WORKERS)
    ]
    for w in workers:
        w.start()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="diep-telemetry-ingestor")
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS)
    _apply_mqtt_tls(client)
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    delay = 2
    for attempt in range(30):
        try:
            logger.info(f"Connecting to MQTT {MQTT_BROKER}:{MQTT_PORT} (attempt {attempt + 1}/30)")
            client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            break
        except Exception as exc:
            logger.warning(f"MQTT connect attempt {attempt + 1} failed: {exc}")
            time.sleep(delay)
            delay = min(delay * 1.5, 30)
    else:
        raise RuntimeError("Failed to connect to MQTT after 30 attempts")

    def _handle_signal(signum, frame):
        logger.info(f"received signal {signum}; shutting down")
        _stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _handle_signal)

    logger.info(f"Telemetry ingestor running ({NUM_WORKERS} workers, queue maxsize={QUEUE_MAXSIZE})")
    client.loop_start()
    try:
        while not _stop_event.is_set():
            time.sleep(1)
    finally:
        client.loop_stop()
        client.disconnect()
        _stop_event.set()
        for w in workers:
            w.join(timeout=5)
        logger.info("Telemetry ingestor shut down")


if __name__ == "__main__":
    main()
