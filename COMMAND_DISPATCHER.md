# DIEP Command Dispatcher — Python Implementation

## Overview
Replaced Node-RED with a lightweight Python Kafka→MQTT→FastAPI command dispatcher.

## Architecture

```
FastAPI (/commands)
    ↓ produces to Kafka
    ↓ (diep.commands topic)
    ↓
Command Dispatcher (Python)
    ├─ Kafka consumer (diep.commands)
    ├─ MQTT producer (diep/<domain>/<device_id>/cmd)
    └─ MQTT consumer (diep/+/+/ack)
    ↓ receives device ack
    ↓ POST to FastAPI (/commands/{id}/ack)
    ↓
TimescaleDB (audit update)
```

## Device Domain Mapping
```
ev_charger       → charger     (diep/charger/<device_id>/cmd)
battery          → battery     (diep/battery/<device_id>/cmd)
solar_inverter   → solar       (diep/solar/<device_id>/cmd)
microgrid        → microgrid   (diep/microgrid/<device_id>/cmd)
```

## Files

### [dispatcher/command_dispatcher.py](../../dispatcher/command_dispatcher.py)
- Consumes Kafka topic `diep.commands`
- Routes commands to MQTT based on device_type → domain mapping
- Subscribes to MQTT ack topics (`diep/+/+/ack`)
- POSTs device acks to FastAPI `/commands/{command_id}/ack`
- Includes retry logic for Kafka startup delays

### Docker Compose Service
```yaml
dispatcher:
  image: python:3.12
  environment:
    KAFKA_BOOTSTRAP: diep-kafka:9092
    MQTT_BROKER: diep-mqtt
    MQTT_USER: diep-nodered
    MQTT_PASS: nodered-pass-2026
    FASTAPI_BASE: http://diep-fastapi:8000
```

## End-to-End Flow Validation

✅ **Full command/ack path tested:**
1. FastAPI accepted command: `POST /commands` → status 202 SENT
2. FastAPI produced to Kafka: `diep.commands` topic
3. Dispatcher consumed from Kafka within 5 seconds
4. Dispatcher dispatched to MQTT: `diep/battery/BAT001/cmd`
5. Battery simulator received and published ack: `diep/battery/BAT001/ack`
6. Dispatcher consumed MQTT ack
7. Dispatcher POSTed to FastAPI: `/commands/{id}/ack`
8. FastAPI updated audit: status = ACKED

**Command audit trail (TimescaleDB):**
```
command_id: 9a32a6b7-1a55-43cf-a089-d71aa406b4e3
device_id: BAT001
command_type: charge
status: ACKED
created_at: 2026-06-02 07:08:15
acked_at: 2026-06-02 07:08:20 (5-second latency)
```

## Why This Replaces Node-RED

| Feature | Node-RED | Dispatcher | Status |
|---------|----------|-----------|--------|
| Kafka consumer | `node-red-contrib-kafkajs` (404 npm) | kafka-python | ✅ Working |
| MQTT producer | Built-in | paho-mqtt | ✅ Working |
| MQTT consumer (ack) | Built-in | paho-mqtt | ✅ Working |
| HTTP client | Built-in | requests | ✅ Working |
| Startup reliability | Blocked waiting for types | Retries on failure | ✅ Robust |
| Size/Complexity | ~2GB container, complex flow UI | ~100 lines, minimal deps | ✅ Lightweight |

## Benefits

1. **Operational**: Full command path validated end-to-end
2. **Lightweight**: Single Python script vs Node-RED ecosystem
3. **Maintainable**: Clear kafka→mqtt→http routing logic
4. **Reliable**: Integrated retry logic for startup delays
5. **Observable**: Detailed logging of each stage

## Dependencies

```
kafka-python==2.3.1
paho-mqtt==2.1.0
requests==2.34.2
```

## Deployment

```bash
# Included in docker-compose.yml
docker compose up -d dispatcher

# View logs
docker compose logs -f dispatcher

# Restart (if needed)
docker compose restart dispatcher
```

## Next Steps

- Telemetry ingestion path: ✅ Complete (MQTT→FastAPI→TimescaleDB)
- Command/control path: ✅ Complete (Kafka→Dispatcher→MQTT→Device)
- Phase 5E: Extend command vocabulary and add device-specific handlers
