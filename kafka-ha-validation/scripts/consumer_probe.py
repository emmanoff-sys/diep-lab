"""K3 Kafka HA validation — consumer probe.

Mirrors dispatcher/command_dispatcher.py's KafkaConsumer pattern
(SASL_PLAINTEXT/PLAIN, consumer group, JSON values) and logs every message
read from diep.commands.val, so a broker failure / group-coordinator
rebalance shows up as a brief pause followed by resumed consumption with
no gaps or duplicates beyond normal at-least-once retries.
"""
import json
import time

from kafka import KafkaConsumer

BOOTSTRAP = "kafka-val-1:9094,kafka-val-2:9094,kafka-val-3:9094"
PASSWORD = "kafka-ha-validation-only"
TOPIC = "diep.commands.val"

consumer = KafkaConsumer(
    TOPIC,
    bootstrap_servers=BOOTSTRAP,
    security_protocol="SASL_PLAINTEXT",
    sasl_mechanism="PLAIN",
    sasl_plain_username="diep",
    sasl_plain_password=PASSWORD,
    group_id="diep-commands-val-consumer",
    auto_offset_reset="earliest",
    value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    consumer_timeout_ms=600000,
)

for message in consumer:
    print(f"{time.strftime('%H:%M:%S')} partition={message.partition} offset={message.offset} value={message.value}")
