# DIEP Phase 9J-S4 — Per-Device Mutual TLS (mTLS)

> **Status:** Implemented and verified. Date: 2026-06-06. The INV900 vertical now runs over
> per-device mTLS with **no shared password**; the other four stay on plaintext 1883
> (additive migration). Builds on the S3 CA + 8883 TLS listener. Stack intact (5/5 PRODUCTION_READY).

---

## 1. Summary

Before S4, every device shared one MQTT identity (`diep-device`) and password over plaintext
1883 — no per-device identity, no revocation, sniffable credentials. S4 gives each device a
**unique X.509 client certificate** (CN = device id) issued from the platform CA; the broker
authenticates the cert (mutual TLS), uses the **CN as the MQTT identity**, and binds an ACL
that scopes the device to **its own topics only**. Migration is per-device and additive — a
device moves to 8883/mTLS by config alone, while un-migrated devices keep working on 1883.

---

## 2. What was built

### 2.1 Per-device certificate issuance — `scripts/issue-device-cert.sh`
Signs a client cert (`CN=<device-id>`, `O=DIEP/OU=devices`) from the platform CA
(`mosquitto/config/certs/ca.{crt,key}`) into `certs/devices/`. The device receives only its
key + cert + `ca.crt` — never the CA private key. Issued `INV900` (and a test cert);
chain-verified against the CA.

### 2.2 Broker mTLS — `mosquitto/config/mosquitto.conf` (8883 listener)
```
require_certificate true        # reject any client without a CA-signed cert
use_identity_as_username true   # the cert CN becomes the MQTT username (→ ACL identity)
```
1883 (plaintext, shared password) and 9001 (ws) are unchanged for migrating devices.

### 2.3 Per-device ACL — `mosquitto/config/acl`
```
user INV900
topic write diep/solar/INV900        # publish only its own telemetry
topic read  diep/solar/INV900/cmd    # receive only its own commands
topic write diep/solar/INV900/ack    # ack only its own commands
```
vs the broad shared `diep-device` (write `diep/+/+`). A compromised device can no longer
read or write another device's data. One block per migrated device.

### 2.4 Vertical migration — `docker-compose-sunspec.yml` (INV900)
The SDK already supports mTLS, so the cutover is config only: mount `certs/devices` read-only
and set `MQTT_TLS=1`, `MQTT_PORT=8883`, `MQTT_CA_CERTS`/`MQTT_CLIENT_CERT`/`MQTT_CLIENT_KEY`,
and **`MQTT_USER=""`** (no password — identity comes from the cert).

---

## 3. Verification

| # | Test | Result |
|---|------|--------|
| 1 | Connect to 8883 **without** a client cert | **rejected** (TLS handshake fails, exit 7) ✓ |
| 2 | Connect with valid `INV900` cert | accepted, publishes own topic (exit 0) ✓ |
| 3 | Identity = cert CN | broker log: `New client connected … u'INV900'` ✓ |
| 4 | **ACL isolation** — `INV900` cert subscribes to `diep/battery/BAT900` | **0 messages delivered** (denied), while an authorized identity received the real reading ✓ |
| 5 | **Real vertical over mTLS** — migrate INV900 | broker: `port 8883 … u'INV900' … TLSv1.3 TLS_AES_256_GCM_SHA384`; telemetry flowing (age 0 s), no shared password ✓ |
| 6 | **Command path over mTLS** | operator JWT → `/commands` (202) → INV900 received `curtail` over its 8883 link → `WMaxLimPct=40%` → **ACKED** ✓ |
| 7 | No breakage | 5/5 PRODUCTION_READY; other 4 verticals still publishing on 1883 ✓ |

---

## 4. Security improvement (before → after, for migrated devices)

| Property | Before (1883) | After (8883 mTLS) |
|----------|---------------|--------------------|
| Identity | shared `diep-device` | unique cert CN per device |
| Credential | shared static password (sniffable, plaintext) | X.509 client cert (mutual TLS, TLSv1.3) |
| Revocation | none (rotate one shared password = touch all) | per-device (delete ACL block / CRL) |
| Topic scope | any `diep/+/+` | only the device's own topics |
| Wire | plaintext | encrypted (TLS_AES_256_GCM_SHA384) |

---

## 5. Remaining / follow-ups

- **Migrate the other 4 verticals** (MTR900/BAT900/EVSE900/MGC900): issue a cert + ACL block
  each (same recipe), flip their compose env. Once all are on mTLS, **disable the plaintext
  1883 listener** (the final S4 step) and retire the shared `diep-device` password.
- **Certificate lifecycle**: issuance ties into onboarding (9H) — auto-issue a device cert at
  enrollment; add renewal + a CRL/OCSP for revocation. In production, the CA + issuance move
  to Vault PKI (9J-S7) and the cluster cert-manager.
- **9I certification `security` test**: now that a real mTLS path exists, the currently-SKIPPED
  security test can be implemented to assert the device uses mTLS (no plaintext fallback).
- **OCPP `wss://`** (9F) and **IEC-104 over TLS** (9G) are the per-vertical transport-TLS
  equivalents, to fold in here.

---

## 6. Result

Per-device mutual TLS is live and proven end-to-end on a real vertical: unique cert identity,
encrypted transport, per-device ACL isolation, telemetry **and** command/ack — with the
shared password retired for that device, and zero disruption to the rest of the fleet. This
is the security prerequisite for safe field-device actuation.

**Next per the roadmap:** S5 (Kafka SASL/TLS), S6 (TLS reverse proxy — the Caddy gateway from
9K already seams this), S7 (Vault PKI) — then Group B (10A/10B) to deploy on a real cluster.
