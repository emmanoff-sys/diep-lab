# DIEP Phase 9 — Architecture Assessment, Gap Analysis & Implementation Plan

> **Status:** Planning artifact. **No production code has been modified.** This document
> is the assessment + gap analysis + plan that gates all Phase 9 implementation, per the
> program directive *"Do not implement blindly. First perform architecture assessment, gap
> analysis, and implementation planning before modifying production code."*
>
> Date: 2026-06-04 · Author: platform engineering · Scope: Phases 9A–9L + final report.

---

## 1. Executive summary

DIEP today is a **functionally complete simulation platform** — telemetry, MQTT/Kafka
messaging, digital twins, DERMS, AI analytics, and a unified operations portal all work
end-to-end. That is real, demonstrated capability. **However, it is a single-node lab
deployment, not a production system**, and it has **zero real-device integration surface**.

- **Current maturity:** *Late-stage functional prototype* — roughly **TRL 5** (validated in
  a representative lab environment with simulators).
- **Production readiness (real field devices, real sites):** **~30%.**
- **The gap is not features — it is the three pillars of production:** (1) field/device
  integration (protocols, edge, onboarding, certification), (2) security (no TLS, no API
  auth, hardcoded secrets), and (3) availability (everything single-node).

Phase 9 is correctly scoped to close exactly those three pillars. This plan sequences the
12 sub-phases into **4 delivery waves** with dependencies, effort, and risk.

---

## 2. Verified current-state snapshot

Facts confirmed by inspection of the running stack (not assumed):

| Domain | Current state | Evidence |
|--------|---------------|----------|
| Deployment | 22 single-instance services via `docker compose`, install-at-startup, bind-mounted code | `docker compose config` |
| Data plane | MQTT (Mosquitto) → telemetry ingestor → FastAPI → TimescaleDB + Redis; Kafka command bus → dispatcher → MQTT | Phases 3–5 |
| Apps | Digital twins, DERMS, AI analytics (forecast/anomaly/PdM/recommendations), Next.js portal on :3002 | Phases 6–8 |
| Devices | **Simulators only** — battery, solar, EV, microgrid, smart meter. No protocol adapters, no edge gateway | `simulator/` |
| **MQTT security** | Authenticated (passwd+ACL), `allow_anonymous false` ✅ — but **plaintext 1883 / ws 9001, no TLS, no client certs** | `mosquitto/config/mosquitto.conf` |
| **Kafka security** | `PLAINTEXT` listeners only; no SASL, no TLS; replication factor 1 | compose lines 23–28 |
| **API security** | FastAPI has **no auth, no CORS, no TLS, no rate limiting, no API keys, no audit log** | `grep` of `app.py` → none |
| **Secrets** | Hardcoded in plaintext: DB `diep123` (compose:63 + `app.py:28`), MinIO `admin/diep12345`, MQTT `nodered-pass-2026` | `grep` |
| **Availability** | Single node for FastAPI, Postgres/Timescale, Redis, Kafka, MinIO. No LB, no replicas, no failover | compose |
| Onboarding | `POST /assets` registers a device row; no validation/certification/approval workflow | `app.py` |

**Headline risks:** plaintext broker + no API auth + hardcoded secrets mean the platform
is **not safe to expose to a real field network or the public internet today.** Security
hardening (9J) is therefore a *prerequisite*, not a closing step.

---

## 3. Gap analysis by sub-phase

Effort key: **S** ≤1wk · **M** 1–3wk · **L** 1–2mo · **XL** 2mo+ (one engineer-equivalent).
Risk = delivery/technical risk.

| Phase | Requirement | Current | Gap | Effort | Risk |
|-------|-------------|---------|-----|--------|------|
| **9A** Edge Gateway | HW arch (Pi5/IPC/Jetson/IOT2050/Advantech), edge→TLS→DIEP | None | Full design + reference build | M (doc), L (build) | Med |
| **9B** Protocol framework | `drivers/` abstraction: connect/read/normalize/publish/cmd/ack | Sim publishes MQTT directly; no abstraction | New driver SDK + base class + registry | M | Med |
| **9C** Smart meters | DLMS/COSEM + Modbus; L+G/Itron/Hexing/EDMI/Huawei/Schneider | Sim only | 2 drivers + register maps + DLMS stack | L | **High** (DLMS/COSEM complexity, vendor obis maps) |
| **9D** Battery BMS | Modbus TCP/CAN/SunSpec; Huawei/BYD/Sungrow/Victron/Tesla | Sim only | 1–3 transport drivers + per-vendor maps | L | High (CAN + Tesla proprietary) |
| **9E** Solar inverter | Modbus TCP/SunSpec; Huawei/Sungrow/SMA/Fronius/Solis | Sim only | SunSpec driver (covers most) + vendor quirks | M | Med (SunSpec is standardized) |
| **9F** EV charger | OCPP 1.6 + 2.0.1; ABB/Schneider/ChargePoint/Delta/Autel | Sim only | OCPP **server** (CSMS) — chargers dial in via WebSocket | L | **High** (OCPP is a server role, not a poll driver) |
| **9G** Microgrid | IEC 60870-5-104 / IEC 61850 / Modbus; Schneider/Siemens/ABB/SEL | Sim only | IEC-104 client + 61850 MMS client | XL | **High** (61850 tooling, safety-critical) |
| **9H** Onboarding | register→site→twin→validate→certify→approve; 3 APIs | `POST /assets` only | Workflow state machine + 4 endpoints + status table | M | Low |
| **9I** Certification | 6 tests: connectivity/telemetry/command/ACK/failover/security | None | Automated test harness + report | M | Med |
| **9J** Security | JWT/OAuth2/RBAC, MQTT TLS+certs, Kafka SASL+TLS, rate limit, audit, secrets, Vault | None of it | **Foundational** — see §4 | L | **High** (touches every service) |
| **9K** High availability | LB + FastAPI cluster, PG/Redis/Kafka/MinIO HA | All single-node | Orchestration migration (likely k8s) + stateful HA | XL | High |
| **9L** Pilot | 1 of each device, 30–60d, 6 KPIs | No field site | Plan + instrumentation + runbook | M (plan), L (run) | Med |

---

## 4. Cross-cutting findings (must precede device rollout)

**Security (9J) is the critical path.** You cannot certify real devices (9I security test) or
run a pilot (9L) on an unsecured broker/API. Minimum viable security before any field device:
1. **MQTT TLS + per-device client certificates** (mutual TLS) — replaces shared `diep-device` password; each physical device gets its own identity and ACL.
2. **FastAPI auth** — JWT/OAuth2 + RBAC + API keys for machine clients; CORS already avoided via the portal BFF.
3. **Secrets out of source** — move DB/MinIO/MQTT creds to env/secret store; the portal already proves the env-injection pattern. Vault is a fast-follow, not day-one.
4. **Kafka SASL + TLS** — internal but required for a real multi-host deployment.
5. **Audit logging + rate limiting** on the command/DERMS paths (these actuate physical assets).

**Availability (9K) implies an orchestration change.** True PG/Redis/Kafka/MinIO HA is not
practical under single-host `docker compose`. The honest recommendation is **migrate to
Kubernetes (or Docker Swarm as a lighter step)** with operators (e.g. Patroni/CloudNativePG
for Postgres, Redis Sentinel, Strimzi for Kafka, MinIO distributed). This is the single
largest lift in Phase 9.

**The simulators are an asset, not throwaway.** They already speak the exact MQTT
topic/payload contract the platform expects. The protocol-adapter framework (9B) should
target **that same contract** as its normalized output, so real drivers and simulators are
interchangeable behind the edge gateway — and the existing certification tests can run
against both.

---

## 5. Production-readiness scorecard

| Capability area | Weight | Score | Notes |
|-----------------|:-----:|:-----:|-------|
| Functional data/control/analytics | 20% | 90% | Mature; works end-to-end |
| Field device integration | 20% | 5% | Simulators only |
| Edge architecture | 10% | 0% | None |
| Security | 20% | 20% | MQTT auth+ACL only; no TLS/API-auth/secrets-mgmt |
| High availability / resilience | 15% | 10% | All single-node |
| Onboarding & certification | 10% | 15% | Bare device registration only |
| Observability/ops | 5% | 70% | Prometheus/Grafana/cAdvisor present |
| **Weighted total** | **100%** | **≈30%** | **Functional prototype, not production** |

---

## 6. Recommended sequencing — 4 delivery waves

Dependencies drive the order; security is pulled forward because everything field-facing depends on it.

**Wave 1 — Foundations & design (docs + security baseline)**
- 9J security hardening **plan** + baseline implementation (MQTT TLS, FastAPI JWT/RBAC, secrets-to-env).
- 9A edge gateway architecture (doc).
- 9B protocol-adapter framework (doc + `drivers/` SDK skeleton: base class, registry, normalized contract).
- *Deliverables:* `DIEP_SECURITY_HARDENING_PLAN.md`, `DIEP_EDGE_GATEWAY_ARCHITECTURE.md`, `DIEP_PROTOCOL_ADAPTER_FRAMEWORK.md`.

**Wave 2 — First real protocol vertical (prove the framework)**
- 9E solar (SunSpec — most standardized, lowest risk) **or** 9C Modbus smart meter as the pilot driver.
- 9H onboarding workflow + APIs; 9I certification harness.
- Run the new driver through onboarding→certification against a **simulated Modbus/SunSpec endpoint** (no field hardware needed yet).
- *Deliverables:* one working driver, `DIEP_DEVICE_CERTIFICATION_FRAMEWORK.md`, onboarding APIs.

**Wave 3 — Remaining verticals**
- 9C DLMS, 9D battery BMS, 9F OCPP CSMS, 9G microgrid (IEC-104/61850). Highest-risk drivers; each is its own sub-project.

**Wave 4 — Scale & field**
- 9K HA architecture + orchestration migration.
- 9L pilot deployment plan + execution.
- Final `DIEP_PHASE9_PRODUCTION_READINESS_REPORT.md`.

---

## 7. Deployment-vertical roadmaps (for the final report)

**Utility-scale (DSO/genco):** prioritize 9G microgrid + 9D battery + 9E solar; IEC 61850/104
and DERMS grid-services are the differentiators; HA and security are non-negotiable
(regulatory). Longest path due to 61850 and HA.

**Telecom-energy (tower/site power):** prioritize 9D battery BMS + 9C smart meter + 9E solar
(rectifier/hybrid sites); edge gateway on Pi5/IPC per site; emphasis on remote-site
resilience, store-and-forward at the edge, and fleet onboarding at scale (thousands of sites).

**Smart city:** prioritize 9F EV charging (OCPP CSMS) + 9C metering + 9G district microgrid;
emphasis on multi-tenant RBAC, public-facing API security/rate-limiting, and BACnet for
building integration (note: BACnet is in the `drivers/` tree but unscoped in 9C–9G — flag).

---

## 8. Observations / corrections to the program spec

- **OCPP (9F) is a server role**, not a polling driver: chargers connect *inbound* over
  WebSocket to a Central System (CSMS). The `drivers/ocpp/` adapter is really a CSMS service —
  architecturally different from the Modbus/DLMS pollers. Plan accordingly.
- **`drivers/bacnet/`** appears in the 9B tree but no sub-phase (9C–9G) specifies BACnet
  devices. Recommend scoping it under smart-city/building integration or dropping for now.
- **`_predictive_maintenance_insight` writes an analytics_events row per call** (known from
  Phase 8) — certification/load tests must account for this write amplification.
- **Tesla Powerwall (9D)** has no open local protocol parity with Modbus/SunSpec; integration
  is via its (rate-limited, changing) local/cloud API — treat as best-effort, not guaranteed.

---

## 9. What I propose to do next (awaiting your direction)

Per the gate, I have **not** modified production code. The natural next step is **Wave 1**.
Because the full program spans multiple sessions, I'll confirm sequencing and how far to go
on code vs. design before proceeding — see the questions accompanying this document.
