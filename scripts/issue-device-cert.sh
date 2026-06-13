#!/usr/bin/env bash
# DIEP Phase 9J-S4 — issue a per-device X.509 client certificate from the platform CA.
# The cert CN = the device id; the broker uses it as the MQTT identity (mTLS), so each
# device has a unique, revocable credential instead of the shared 'diep-device' password.
# Usage: scripts/issue-device-cert.sh <device-id> [valid-days]
#
# Output (certs/devices/): <id>.key, <id>.crt, ca.crt (for server verification).
# The device gets ONLY its key+cert+ca.crt — never the CA private key.
# Revocation: delete the device's ACL block (and add to a CRL in production).
set -euo pipefail
cd "$(dirname "$0")/.."

CN="${1:?usage: issue-device-cert.sh <device-id> [valid-days]}"
DAYS="${2:-825}"
CA_DIR="mosquitto/config/certs"
OUT="certs/devices"
mkdir -p "$OUT"

[ -f "$CA_DIR/ca.crt" ] && [ -f "$CA_DIR/ca.key" ] || { echo "CA not found in $CA_DIR (run S3 first)"; exit 1; }

openssl genrsa -out "$OUT/$CN.key" 2048 2>/dev/null
openssl req -new -key "$OUT/$CN.key" -out "/tmp/$CN.csr" -subj "/O=DIEP/OU=devices/CN=$CN" 2>/dev/null
openssl x509 -req -in "/tmp/$CN.csr" -CA "$CA_DIR/ca.crt" -CAkey "$CA_DIR/ca.key" \
    -CAcreateserial -out "$OUT/$CN.crt" -days "$DAYS" 2>/dev/null
cp "$CA_DIR/ca.crt" "$OUT/ca.crt"
rm -f "/tmp/$CN.csr" "$CA_DIR/ca.srl"
chmod 644 "$OUT/$CN.crt" "$OUT/$CN.key" "$OUT/ca.crt"

echo "issued: $OUT/$CN.crt  (CN=$CN, valid ${DAYS}d)"
openssl x509 -in "$OUT/$CN.crt" -noout -subject -dates | sed 's/^/  /'
