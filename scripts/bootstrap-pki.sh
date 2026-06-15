#!/usr/bin/env bash
# DIEP PKI bootstrap (Phase 16 remediation, F2).
#
# Generates everything the MQTT mTLS listener (8883) and its clients need on a
# fresh clone, none of which is checked into git (see .gitignore):
#   - mosquitto/config/certs/ca.{crt,key}        platform CA
#   - mosquitto/config/certs/server.{crt,key}    broker identity (CN=diep-mqtt)
#   - certs/devices/<ID>.{crt,key} + ca.crt      per-device/service client identities,
#                                                 issued via scripts/issue-device-cert.sh
#   - mosquitto/config/passwd                    legacy password-auth users referenced
#                                                 by mosquitto/config/acl
#
# Idempotent: existing artifacts are left untouched and skipped. Safe to re-run to
# pick up newly added device IDs.
#
# Usage: scripts/bootstrap-pki.sh
set -euo pipefail
cd "$(dirname "$0")/.."

CA_DIR="mosquitto/config/certs"
DEV_DIR="certs/devices"
mkdir -p "$CA_DIR" "$DEV_DIR"

# --- 1. Platform CA ---
if [ -f "$CA_DIR/ca.crt" ] && [ -f "$CA_DIR/ca.key" ]; then
  echo "[skip] CA already present: $CA_DIR/ca.crt"
else
  openssl genrsa -out "$CA_DIR/ca.key" 4096 2>/dev/null
  openssl req -new -x509 -days 3650 -key "$CA_DIR/ca.key" -out "$CA_DIR/ca.crt" \
    -subj "/O=DIEP/CN=DIEP-Root-CA" 2>/dev/null
  chmod 600 "$CA_DIR/ca.key"
  chmod 644 "$CA_DIR/ca.crt"
  echo "[ok]   generated CA: $CA_DIR/ca.crt"
fi

# --- 2. Broker (server) cert, signed by the CA ---
if [ -f "$CA_DIR/server.crt" ] && [ -f "$CA_DIR/server.key" ]; then
  echo "[skip] broker cert already present: $CA_DIR/server.crt"
else
  openssl genrsa -out "$CA_DIR/server.key" 2048 2>/dev/null
  openssl req -new -key "$CA_DIR/server.key" -out /tmp/diep-mqtt-server.csr \
    -subj "/O=DIEP/CN=diep-mqtt" 2>/dev/null
  cat > /tmp/diep-mqtt-server.ext <<'EOF'
subjectAltName=DNS:diep-mqtt,DNS:localhost,IP:127.0.0.1
EOF
  openssl x509 -req -in /tmp/diep-mqtt-server.csr -CA "$CA_DIR/ca.crt" -CAkey "$CA_DIR/ca.key" \
    -CAcreateserial -out "$CA_DIR/server.crt" -days 3650 \
    -extfile /tmp/diep-mqtt-server.ext 2>/dev/null
  rm -f /tmp/diep-mqtt-server.csr /tmp/diep-mqtt-server.ext "$CA_DIR/ca.srl"
  # 644, not 600: the mosquitto container reads this as its non-root 'mosquitto'
  # user, which does not share a uid with the host user that generated it.
  chmod 644 "$CA_DIR/server.key"
  chmod 644 "$CA_DIR/server.crt"
  echo "[ok]   generated broker cert: $CA_DIR/server.crt (CN=diep-mqtt)"
fi

cp "$CA_DIR/ca.crt" "$DEV_DIR/ca.crt"

# --- 3. Per-device / service client certs (Installation Guide §6.1 fleet) ---
DEVICE_IDS="BAT001 EV001 INV001 MG001 METER001 ingestor dispatcher csms"
for CN in $DEVICE_IDS; do
  if [ -f "$DEV_DIR/$CN.crt" ] && [ -f "$DEV_DIR/$CN.key" ]; then
    echo "[skip] client cert already present: $DEV_DIR/$CN.crt"
    continue
  fi
  ./scripts/issue-device-cert.sh "$CN" >/dev/null
  echo "[ok]   issued client cert: $DEV_DIR/$CN.crt (CN=$CN)"
done

# --- 4. Mosquitto password file (legacy password-auth users in mosquitto/config/acl) ---
if [ -f mosquitto/config/passwd ]; then
  echo "[skip] mosquitto/config/passwd already present"
else
  if [ -f .env ]; then
    set -a; source .env; set +a
  fi
  MQTT_USER="${MQTT_USER:-diep-device}"
  MQTT_PASS="${MQTT_PASS:-change-me-device-password}"
  MQTT_NODERED_PASS="${MQTT_NODERED_PASS:-change-me-nodered-password}"
  docker run --rm -v "$(pwd)/mosquitto/config:/mosquitto/config" eclipse-mosquitto \
    sh -c "mosquitto_passwd -b -c /mosquitto/config/passwd '$MQTT_USER' '$MQTT_PASS' && \
           mosquitto_passwd -b /mosquitto/config/passwd diep-nodered '$MQTT_NODERED_PASS' && \
           chmod 644 /mosquitto/config/passwd"
  echo "[ok]   generated mosquitto/config/passwd (users: $MQTT_USER, diep-nodered)"
fi

echo
echo "PKI bootstrap complete. Restart the mqtt, ingestor, dispatcher and ev-charger"
echo "services to pick up the new certs:"
echo "  docker compose restart mqtt ingestor dispatcher ev-charger"
