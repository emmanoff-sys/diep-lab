# DIEP Phase 9L — Field Pilot Plan

> Plan to validate DIEP with **real field devices** at a representative site, for 30–60
> days, before general deployment. Gated on the security + HA + certification work
> (9J/9K/9I — all done) and edge productization (9A).

---

## 1. Objective

Prove that the lab-certified platform operates against **physical** devices over real
networks: telemetry fidelity, command/actuation reliability, security in the field, edge
resilience (store-and-forward), and operability — and collect the KPIs that gate GA.

---

## 2. Scope — one of each certified vertical

| Vertical | Pilot device (example) | Protocol | DIEP driver |
|----------|------------------------|----------|-------------|
| Solar inverter | Huawei/Sungrow/SMA string inverter | SunSpec/Modbus TCP | `sunspec` |
| Smart meter | Landis+Gyr / Schneider PM | Modbus TCP | `modbus_meter` |
| Battery/BMS | Sungrow/BYD/Victron | Modbus/SunSpec | `battery_bms` |
| EV charger | ABB/Schneider/ChargePoint | OCPP 1.6J | `ocpp_csms` |
| Microgrid RTU | Schneider/SEL | IEC 60870-5-104 | `microgrid_iec104` |

**Site:** one microgrid site (e.g., Abuja Site A class) with PV + storage + a feeder meter +
an EV charger + the site controller. One **edge gateway** (Pi5/IPC) per site running the
edge agent with per-device mTLS.

---

## 3. Architecture for the pilot

- **Edge gateway** runs `drivers/` (production image, Phase 9A) with **store-and-forward**
  and **per-device mTLS** (cert issued from the platform CA / Vault PKI). Survives WAN drops.
- **Platform** runs on the HA Kubernetes cluster (Helm chart, `k8s/` operators) with the
  full 9J security baseline (mTLS broker, SASL Kafka, HTTPS API, JWT/RBAC, audit, rate-limit).
- Devices are taken through **onboarding → validation → certification (6/6) → PRODUCTION_READY**
  before being trusted for actuation.

---

## 4. KPIs (acceptance gates)

| # | KPI | Target |
|---|-----|--------|
| 1 | Telemetry delivery rate | ≥ 99.5% of expected samples persisted |
| 2 | Telemetry freshness (p95 edge→DB) | ≤ 10 s |
| 3 | Command success (ACKED / issued) | ≥ 99% |
| 4 | Command round-trip p95 (issue→ack) | ≤ 5 s (LAN) / ≤ 30 s (cellular) |
| 5 | Edge outage resilience | 100% of buffered readings replayed after a ≤ 1 h WAN outage |
| 6 | Security | 0 plaintext device connections; 0 unauthenticated API actuations; all devices unique-cert |
| 7 | Platform availability | ≥ 99.9% over the window |
| 8 | DERMS actuation | dispatch → device action → twin reflects, within SLA |

---

## 5. Test campaign (per device + site)

1. **Connectivity & onboarding** — device dials in (mTLS), enrolls, validates, certifies 6/6.
2. **Telemetry soak** — continuous capture; compare against the device's local display/meter.
3. **Command matrix** — exercise every command (curtail/charge/discharge/start/stop/island/
   set_setpoint/disconnect…); verify physical actuation + ACK + audit row.
4. **DERMS** — run battery dispatch / peak shaving / demand response against the real assets.
5. **Edge resilience** — induce WAN outages; verify store-and-forward replay (KPI 5).
6. **Failover** — kill platform components (DB primary, an API pod, a Kafka broker); verify
   recovery with no data loss (KPI 7) — the 9I failover test, live.
7. **Security** — attempt plaintext/unauth access; confirm rejection; rotate a device cert
   and confirm revocation.

---

## 6. Operations during the pilot

- **On-call** with the 10C SLO alerts (Alertmanager → PagerDuty); daily KPI dashboard review.
- **Backups** nightly + a mid-pilot restore drill (10E).
- **Runbooks** for device add/remove, cert rotation, failover, rollback (`DIEP_PHASE10_RUNBOOK.md`).
- **Change control** via CI/CD (signed images, `helm upgrade --atomic`).

---

## 7. Exit criteria → GA

All KPIs met for 2 consecutive weeks; zero Sev-1 security incidents; every device class
certified 6/6 against real hardware; DR drill passed; runbooks validated. Then proceed to
multi-site rollout (Group E — scale/commercial).

---

## 8. Risks & mitigations

| Risk | Mitigation |
|------|-----------|
| Vendor protocol quirks (register maps, OCPP profiles) | Data-driven maps; per-vendor test before soak; the SDK isolates protocol IO |
| Field connectivity (cellular drops) | Store-and-forward (9A); QoS; bounded buffer sizing per cadence |
| Safety-critical microgrid control | 9J security precondition met; staged enablement; manual override; IEC 61850 (9G-b) deferred until hardened |
| Cert lifecycle at scale | Vault PKI + auto-issue at onboarding; CRL/OCSP for revocation |
