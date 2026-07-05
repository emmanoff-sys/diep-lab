"""AIOKafka consumer for audit events (ENG-SPEC-005-04 §10).

Topics consumed:
  iam.audit.events  — primary audit stream (AuditEventCreate schema)
  user.registered   — existing identity-service topic (converted on arrival)

Delivery: at-least-once; manual offset commit after DB commit.
Retry: 3 attempts, 1 s / 2 s / 4 s exponential backoff, then DLQ.
DLQ: audit.dead.events
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC
from typing import Any

import structlog
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from audit_service.config import settings
from audit_service.domain.events import user_registered_to_audit
from prometheus_client import Counter

logger = structlog.get_logger(__name__)

_consumed = Counter(
    "audit_kafka_events_consumed_total", "Kafka messages consumed", ["topic", "outcome"]
)
_dlq_sent = Counter("audit_dlq_events_total", "Dead-letter queue messages sent", ["topic"])
_consumer: AIOKafkaConsumer | None = None
_dlq_producer: AIOKafkaProducer | None = None
_consumer_task: asyncio.Task[None] | None = None
_running: bool = False


def is_running() -> bool:
    return _running


async def start_consumer(write_event_fn: Any) -> None:
    """Start the Kafka consumer and DLQ producer; launch background consume task."""
    global _consumer, _dlq_producer, _consumer_task, _running

    _dlq_producer = AIOKafkaProducer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: v if isinstance(v, bytes) else json.dumps(v).encode("utf-8"),
        acks="all",
        enable_idempotence=True,
    )
    await _dlq_producer.start()

    _consumer = AIOKafkaConsumer(
        settings.KAFKA_IAM_AUDIT_EVENTS_TOPIC,
        settings.KAFKA_USER_EVENTS_TOPIC,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=settings.KAFKA_CONSUMER_GROUP_ID,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        max_poll_records=settings.KAFKA_MAX_POLL_RECORDS,
        session_timeout_ms=settings.KAFKA_SESSION_TIMEOUT_MS,
        heartbeat_interval_ms=settings.KAFKA_HEARTBEAT_INTERVAL_MS,
    )
    await _consumer.start()
    _running = True
    logger.info(
        "audit.kafka_consumer_started",
        topics=[
            settings.KAFKA_IAM_AUDIT_EVENTS_TOPIC,
            settings.KAFKA_USER_EVENTS_TOPIC,
        ],
    )

    _consumer_task = asyncio.create_task(_consume_loop(write_event_fn))


async def stop_consumer() -> None:
    global _consumer, _dlq_producer, _consumer_task, _running
    _running = False
    if _consumer_task:
        _consumer_task.cancel()
        try:
            await _consumer_task
        except asyncio.CancelledError:
            logger.debug("audit.kafka_consumer_task_cancelled")
    if _consumer:
        await _consumer.stop()
    if _dlq_producer:
        await _dlq_producer.stop()
    logger.info("audit.kafka_consumer_stopped")


async def _consume_loop(write_event_fn: Any) -> None:
    assert _consumer is not None
    consecutive_dlq_failures = 0

    async for msg in _consumer:
        topic: str = msg.topic
        try:
            event_data = _parse_message(topic, msg.value)
        except Exception as exc:
            logger.error(
                "audit.kafka_schema_error",
                topic=topic,
                error=str(exc),
            )
            _consumed.labels(topic=topic, outcome="schema_error").inc()
            await _route_to_dlq(topic, msg.value, str(exc))
            await _consumer.commit()
            continue

        success = False
        last_exc: Exception | None = None
        for attempt in range(settings.KAFKA_RETRY_MAX_ATTEMPTS):
            try:
                await write_event_fn(event_data, source="kafka")
                success = True
                break
            except Exception as exc:
                last_exc = exc
                if attempt < settings.KAFKA_RETRY_MAX_ATTEMPTS - 1:
                    delay = settings.KAFKA_RETRY_BASE_DELAY_S * (2**attempt)
                    logger.warning(
                        "audit.kafka_write_retry",
                        topic=topic,
                        attempt=attempt + 1,
                        delay_s=delay,
                        error=str(exc),
                    )
                    await asyncio.sleep(delay)

        if success:
            _consumed.labels(topic=topic, outcome="success").inc()
            await _consumer.commit()
        else:
            logger.error(
                "audit.kafka_write_failed",
                topic=topic,
                retries=settings.KAFKA_RETRY_MAX_ATTEMPTS,
                error=str(last_exc),
            )
            _consumed.labels(topic=topic, outcome="dlq").inc()
            dlq_ok = await _route_to_dlq(topic, msg.value, str(last_exc))
            if dlq_ok:
                consecutive_dlq_failures = 0
                await _consumer.commit()
            else:
                consecutive_dlq_failures += 1
                logger.critical(
                    "audit.dlq_publish_failed",
                    topic=topic,
                    consecutive_failures=consecutive_dlq_failures,
                )
                if consecutive_dlq_failures > 5:
                    logger.critical(
                        "AuditDLQUnrecoverable — manual intervention required",
                        consecutive_dlq_failures=consecutive_dlq_failures,
                    )
                else:
                    await asyncio.sleep(30)


def _parse_message(topic: str, value: dict[str, Any]) -> dict[str, Any]:
    """Convert a Kafka message payload to a canonical audit event dict."""
    if topic == settings.KAFKA_USER_EVENTS_TOPIC:
        return user_registered_to_audit(value)

    # iam.audit.events messages are already AuditEventCreate-compatible
    # Validate required fields present; full Pydantic validation happens in write_event
    required = {
        "event_id",
        "event_type",
        "actor_type",
        "actor_id",
        "action",
        "resource_type",
        "outcome",
        "correlation_id",
        "service_name",
        "timestamp_utc",
    }
    missing = required - set(value.keys())
    if missing:
        raise ValueError(f"Missing required fields: {missing}")

    from datetime import datetime
    from uuid import UUID

    # Coerce string UUIDs and timestamps
    for field in ("event_id", "actor_id", "correlation_id"):
        if isinstance(value[field], str):
            value[field] = UUID(value[field])

    ts = value["timestamp_utc"]
    if isinstance(ts, str):
        parsed = datetime.fromisoformat(ts)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        value["timestamp_utc"] = parsed

    return value


async def _route_to_dlq(topic: str, original: Any, error: str) -> bool:
    """Publish to DLQ; return True on success."""
    if _dlq_producer is None:
        return False
    try:
        dlq_payload: dict[str, Any] = {
            "source_topic": topic,
            "error": error,
            "original": original if isinstance(original, dict) else str(original),
        }
        await _dlq_producer.send_and_wait(settings.KAFKA_DLQ_TOPIC, value=dlq_payload)
        _dlq_sent.labels(topic=topic).inc()
        logger.warning("audit.dlq_event_routed", source_topic=topic)
        return True
    except Exception as exc:
        logger.critical("audit.dlq_publish_error", error=str(exc))
        return False
