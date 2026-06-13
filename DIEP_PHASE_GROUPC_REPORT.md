# DIEP Group C — Field & Certification

> **Status:** 9I-full (real certification) and 9A (edge productization) complete & verified;
> 9L pilot planned; remaining drivers + compliance scoped. Date: 2026-06-06. Stack intact
> (5/5 PRODUCTION_READY). Builds on Group A (security/HA/data) + Group B (IaC/CI/observability).

---

## 1. 9I-full — real certification (security + failover now PASS, not SKIPPED)

The certification harness marked `security` and `failover` **SKIPPED** across all five
verticals because the underlying work didn't exist. With 9J-S4 (mTLS) and 9K (HA) done, those
tests are now **real and verifiable** (`fastapi/app.py` `_run_certification_tests`):

- **security** = API auth enforced **AND** plaintext MQTT retired. The harness **TCP-probes
  `diep-mqtt:1883`**; connection refused proves the broker is **mTLS-only**. Real, not a flag.
- **failover** = **telemetry continuity** (≥10 samples/3 min → resilient through reconnects)
  **AND** a **live datastore replica** (`REDIS.info().connected_slaves ≥ 1`, the 9K replica).

Re-certification of a PRODUCTION_READY device is now allowed (periodic re-cert) without
downgrading it.

**Result — all 5 verticals re-certified 6/6 PASS:**
```
INV900 / MTR900 / BAT900 / EVSE900 / MGC900:
  connectivity PASS · telemetry PASS · command PASS · ack PASS
  failover PASS  {telemetry_samples_3m: ~34, continuous: true, redis_connected_replicas: 1}
  security PASS  {api_auth_enforced: true, mqtt_plaintext_1883_open: false, mqtt_mtls_only: true}
```
The DIEP certification is now a meaningful gate: a device certifies only if secure transport,
auth, HA redundancy, and resilience are all actually true.

---

## 2. 9A — edge gateway productization

### Store-and-forward (`drivers/diep_driver/runner.py` + `mqtt_client.py`) — ✅ verified
- The Runner buffers **timestamped** telemetry in a bounded ring when the broker/platform is
  unreachable (tracked via the transport `connected` flag), and **replays it in order on
  reconnect** — a remote site survives WAN/broker outages with no lost readings.
- Telemetry now carries the **edge capture time**; the ingestor forwards it so replayed data
  keeps real timestamps (not replay time).
- **Validated:** `python -m diep_driver.selftest` — buffered-while-offline, replayed-in-order,
  buffer-drained, bounded ring drops oldest. Activated live on all 5 edge containers.

### Hardened edge image (`drivers/Dockerfile`)
Non-root, slim, pinned protocol libs (paho + optional pymodbus), runs the edge agent. Mounts
per-device mTLS material + config at runtime. The deployable form of the field gateway.

### Resilience stack now on the edge
re-subscribe on reconnect (9J) + store-and-forward (9A) + per-device mTLS (9J-S4) → the edge
agent tolerates broker restarts, WAN drops, and credential isolation.

---

## 3. 9L — field pilot

Planned in `DIEP_PHASE9L_PILOT_PLAN.md`: one of each certified vertical at a real microgrid
site, 30–60 days, 8 KPIs (telemetry delivery ≥99.5%, command success ≥99%, edge-outage replay
100%, 0 plaintext/unauth, availability ≥99.9%), full test campaign incl. live failover + edge
resilience, on-call with the 10C SLO alerts, exit criteria → GA.

---

## 4. Remaining (Group C tail) — scoped, not built

| Item | Status / note |
|------|---------------|
| **9G-b IEC 61850** (MMS/GOOSE) | Real-time/safety-critical; needs libiec61850; its own sub-project after the pilot |
| **DLMS/COSEM meters, DNP3, BACnet** | Additional drivers — same SDK pattern as the 5 built; data-driven maps |
| **OCPP 2.0.1 + `wss://`** | Charger protocol upgrade + transport TLS |
| **Compliance** | IEC 62443 (cyber), grid codes, GDPR/NDPR, safety sign-off for breaker/islanding |
| **Edge OTA + fleet onboarding at scale** | Image OTA, config management, thousands-of-sites enrollment via Vault PKI auto-issue |

---

## 5. Result

Group C makes the platform **field-ready**: certification is now real (6/6, security + HA
actually verified), the edge agent is productized (store-and-forward + hardened image + mTLS),
and the pilot is planned with measurable gates. Combined with Group A (secured, HA core) and
Group B (deployable via Helm/CI/CD), DIEP is ready for a real-hardware pilot.

**Next:** run the **9L pilot** (hardware), build the **remaining drivers** as demand dictates,
and start **Group D — the mobile app** (the API is HTTPS + JWT + versionable, so the PWA/native
track can begin on a stable contract).
