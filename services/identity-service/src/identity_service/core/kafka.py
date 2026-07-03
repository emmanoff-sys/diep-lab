"""Kafka producer for identity domain events.

Events published (SRS SEC-001 §user.registered):
  Topic: user.registered
  Schema: {event_type, user_id, email, timestamp, correlation_id}
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from aiokafka import AIOKafkaProducer

from identity_service.config import settings

logger = logging.getLogger(__name__)

_producer: AIOKafkaProducer | None = None


async def start_producer() -> None:
    global _producer
    _producer = AIOKafkaProducer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        acks="all",              # wait for all in-sync replicas (RF3 / min-ISR2)
        enable_idempotence=True,
        compression_type="gzip",
    )
    await _producer.start()
    logger.info("kafka.producer_started")


async def stop_producer() -> None:
    if _producer:
        await _producer.stop()


async def publish_user_registered(user_id: UUID, email: str) -> None:
    if not _producer:
        logger.warning("kafka.producer_unavailable — skipping user.registered event")
        return
    event = {
        "event_type": "user.registered",
        "user_id": str(user_id),
        "email": email,
        "timestamp": datetime.now(UTC).isoformat(),
        "correlation_id": str(uuid4()),
    }
    try:
        await _producer.send_and_wait(settings.KAFKA_USER_EVENTS_TOPIC, value=event)
        logger.info("kafka.event_published", topic=settings.KAFKA_USER_EVENTS_TOPIC,
                    user_id=str(user_id))
    except Exception:
        logger.exception("kafka.publish_failed", topic=settings.KAFKA_USER_EVENTS_TOPIC)
