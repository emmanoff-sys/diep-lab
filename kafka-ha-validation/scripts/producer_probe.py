"""K3 Kafka HA validation — producer probe.

Mirrors fastapi/app.py's KafkaProducer pattern (acks="all", SASL_PLAINTEXT/
PLAIN, JSON values) and continuously sends numbered messages to
diep.commands.val, logging success/failure per send so a broker failure
shows up as a brief run of failures followed by resumed sends (possibly
against a different leader).
"""
import json
import time

from kafka import KafkaProducer
from kafka.errors import KafkaError

BOOTSTRAP = "kafka-val-1:9094,kafka-val-2:9094,kafka-val-3:9094"
PASSWORD = "kafka-ha-validation-only"
TOPIC = "diep.commands.val"

producer = KafkaProducer(
    bootstrap_servers=BOOTSTRAP,
    security_protocol="SASL_PLAINTEXT",
    sasl_mechanism="PLAIN",
    sasl_plain_username="diep",
    sasl_plain_password=PASSWORD,
    acks="all",
    retries=10,
    key_serializer=lambda k: k.encode("utf-8") if k is not None else None,
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
)

for i in range(180):
    t0 = time.monotonic()
    payload = {"seq": i, "command_type": "probe"}
    try:
        future = producer.send(TOPIC, key=f"probe-{i}", value=payload)
        meta = future.get(timeout=5)
        print(f"{time.strftime('%H:%M:%S')} seq={i:03d} OK   partition={meta.partition} offset={meta.offset} dt={time.monotonic()-t0:.3f}s")
    except KafkaError as exc:
        print(f"{time.strftime('%H:%M:%S')} seq={i:03d} FAIL err={exc!r} dt={time.monotonic()-t0:.3f}s")
    time.sleep(1)
