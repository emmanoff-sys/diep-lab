# DIEP Edge Agent — production image (Phase 9A).
# Runs the protocol-adapter SDK + edge agent on a field gateway (Pi5/IPC/Jetson).
# Hardened: non-root, slim, pinned deps. Telemetry store-and-forward + re-subscribe
# on reconnect make it resilient to transient platform/broker outages.
FROM python:3.12-slim

# Protocol libs: paho (MQTT) always; pymodbus optional (SunSpec/Modbus/Battery —
# the drivers fall back to the built-in Modbus client if absent).
RUN pip install --no-cache-dir paho-mqtt==2.1.0 pymodbus==3.7.0

RUN groupadd -r diep && useradd -r -g diep -u 10001 diep
WORKDIR /app
COPY . /app
USER 10001:10001

# Config + per-device mTLS material are mounted at runtime:
#   -v ./certs/devices:/certs:ro  + MQTT_TLS=1 / MQTT_CLIENT_CERT/KEY (9J-S4)
#   --config <protocol>/devices.json
ENV EDGE_CONFIG=devices.json
ENTRYPOINT ["python", "edge_agent.py"]
CMD ["--config", "devices.json"]
