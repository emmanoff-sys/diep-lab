# DIEP Platform Readiness Report (Phase 8 — Final Assessment)

**Scope:** Synthesis of `DATABASE_VALIDATION_REPORT.md`, `FASTAPI_VALIDATION_REPORT.md`,
`MQTT_FLOW_VALIDATION_REPORT.md`, `KAFKA_COMMAND_FLOW_REPORT.md`, `PORTAL_VALIDATION_REPORT.md`,
`DERMS_VALIDATION_REPORT.md`, and `END_TO_END_TEST_SCENARIOS.md`, assuming TimescaleDB restoration
has completed successfully and the rest of the stack is started per
`DIEP_PLATFORM_ASSESSMENT.md` §C.4/D. Static/code-level analysis only — no live execution, no DB
writes, no service restarts.

---

## 1. What Is Working

| Area | Evidence | Notes |
|---|---|---|
| **DB schema design** | `DATABASE_VALIDATION_REPORT.md` §1-6 | All required tables (`devices`, `telemetry`, `commands`, `audit_events`, `derms_requests`, `tenants`, `sites`, `ev_chargers`, etc.), hypertable on `telemetry`, indexes, FKs, continuous aggregates (`telemetry_5m`, `telemetry_1h` `WITH NO DATA`), retention/compression policies all present in SQL source. |
| **Seed data** | `DATABASE_VALIDATION_REPORT.md` §3 | BAT001, INV001, MG001, EV001, METER001 all present in `003_seed_microgrid.sql`/seed scripts with correct `tenant_id`, `site_name`. |
| **FastAPI route surface** | `FASTAPI_VALIDATION_REPORT.md` §2-3 | All 36 endpoints across 12 groups (Auth, Assets, State, Health, Onboarding, Fleet, Sites, DERMS, Analytics, Alarms, Reports, Commands) are implemented and route correctly; auth/role decorators applied consistently. |
| **Ingestor → DB leg** | `MQTT_FLOW_VALIDATION_REPORT.md` §4-5 | `ingestor` correctly subscribes `diep/+/+/telemetry`, parses payloads, calls `POST /telemetry`, which correctly inserts into the `telemetry` hypertable and updates Redis `state:<device_id>`. |
| **Dispatcher → MQTT leg** | `KAFKA_COMMAND_FLOW_REPORT.md` §3 | `dispatcher` correctly consumes `diep.commands`, maps `device_type`→domain, publishes to `diep/<domain>/<device_id>/cmd` over mTLS with valid certs. |
| **Portal page/endpoint mapping** | `PORTAL_VALIDATION_REPORT.md` §1-2 | All 9 portal pages (Dashboard, Fleet, Twins, DERMS, Reports, Admin, Alarms, AI Ops + login) call FastAPI endpoints that exist and match expected request/response shapes. |
| **Edge drivers (Phase 9C-9G) → mTLS broker leg** | `MQTT_FLOW_VALIDATION_REPORT.md` §6 | `BAT900`/`INV900`/`MGC900`/`MTR900`/`EVSE900` drivers correctly use mTLS 8883 with valid per-device certs and publish well-formed telemetry. |
| **Auth/authorization model** | `FASTAPI_VALIDATION_REPORT.md` §4 | JWT + API-key auth with viewer/operator/admin/service role tiers correctly enforced via decorators on all mutating endpoints. |
| **Observability scaffolding** | `FASTAPI_VALIDATION_REPORT.md` §3, §9 | Prometheus metrics (`diep_derms_requests_total`, `diep_commands_*_total`, etc.) instrumented at the right call sites. |

---

## 2. What Is Partially Working

| Area | Status | Evidence |
|---|---|---|
| **DB init for fresh deployments** | Schema is correct but **init order is broken**: `001_commands.sql` references `ev_chargers.site_name`/`sites` before `003_seed_microgrid.sql` creates them — fresh `init-db.sh` runs fail (R1, `DATABASE_VALIDATION_REPORT.md` §4). Restored DBs (already past init) are unaffected. | `DATABASE_VALIDATION_REPORT.md` R1 |
| **Continuous aggregates** | Created `WITH NO DATA` — structurally correct but require manual `CALL refresh_continuous_aggregate(...)` or a working refresh policy before they return data; not verified to auto-populate post-restore. | `DATABASE_VALIDATION_REPORT.md` §5 |
| **Backup currency** | Backups exist but are ~5.2 days stale as of 2026-06-11 — restoration would lose recent telemetry/command history. | `DATABASE_VALIDATION_REPORT.md` §9 |
| **`/readyz` health check** | Returns 200 based on DB+Redis only; does not check Kafka — a Kafka outage would not be reflected, giving false-positive readiness. | `FASTAPI_VALIDATION_REPORT.md` issue #5 |
| **Kafka producer construction** | `KafkaProducer` instantiated without exception handling around constructor (app.py:1986-1998) — if Kafka is briefly unreachable at first command-issue time, the request 500s instead of degrading gracefully. | `FASTAPI_VALIDATION_REPORT.md` issue #2 |
| **EV001 → Tier-1/Tier-2 demand response** | Endpoint logic is correct, but Tier 2 (EV fallback) is unreachable with current seed data (battery always selected first) — effectively dead code, not a hard bug but untestable as designed. | `DERMS_VALIDATION_REPORT.md` §3, `END_TO_END_TEST_SCENARIOS.md` Scenario 3 |
| **Node/portal build verification** | Portal source maps cleanly to the API, but TypeScript/build checks could not be executed (no `node`/`npm`/`npx` in shell) — unverified whether `npm run build` currently succeeds. | `PORTAL_VALIDATION_REPORT.md` (limitations note) |

---

## 3. What Is Broken

### 3.1 Platform-wide root cause: device-identity / transport mismatch

Every telemetry **and** command path for the 5 seeded devices (BAT001, INV001, MG001, EV001,
METER001) is broken at the same conceptual hop — **the device endpoint that owns each seeded
`device_id` either doesn't exist on the mTLS broker, or the component that *can* reach the mTLS
broker uses a different `device_id`.**

| Seeded device | Telemetry status | Command/ack status | Root cause |
|---|---|---|---|
| BAT001 | No telemetry arrives | Commands stuck `SENT` | Edge driver listens as `BAT900`, not `BAT001` |
| INV001 | No telemetry arrives | Commands stuck `SENT` | Edge driver listens as `INV900`, not `INV001` |
| MG001 | No telemetry arrives (simulator crash-looping) | Commands stuck `SENT` | `diep-microgrid` simulator hardcoded plaintext 1883 → `ConnectionRefusedError`; edge driver is `MGC900` |
| EV001 | No telemetry arrives | Commands stuck `SENT` | Simulator hardcoded plaintext 1883 vs mTLS-only 8883 broker (the one device whose topic IDs *would* match if connectivity worked) |
| METER001 | No telemetry arrives | Commands stuck `SENT` | Edge driver listens as `MTR900`, not `METER001` |

**Consequence:** None of the 5 Phase-7 end-to-end scenarios (Battery Dispatch, Peak Shaving,
Demand Response, EV Charger Control, Microgrid Optimization) can reach `ACKED`/`COMPLETED`
end-to-end today. `derms_requests.status` is set to `'EXECUTED'` immediately after the Kafka
produce succeeds — **this is misleading**, since `EXECUTED` gives no signal that the device never
received or executed the command. (`DERMS_VALIDATION_REPORT.md` §5, `END_TO_END_TEST_SCENARIOS.md`
Cross-Scenario Summary)

### 3.2 Infrastructure-level breaks (must be fixed before any of the above can even be tested)

| Issue | Detail | Evidence |
|---|---|---|
| **Docker network split** | Root `docker-compose.yml` references network `diep-net`, which does not exist; the actual network created by compose is `diep-lab_diep-net`. Per-service override files reference one or the other inconsistently. Containers on mismatched networks can't reach each other at all. | `DIEP_PLATFORM_ASSESSMENT.md` §C.4, confirmed across all 6 sub-reports |
| **Kafka listener config split** | Root `docker-compose.yml` configures Kafka with SASL_PLAINTEXT on 9094 (topic `diep.commands` auto-created); `docker-compose-kafka.yml` (legacy override, possibly still in use) configures PLAINTEXT-only with no 9094 listener at all. FastAPI/dispatcher are coded against the SASL/9094 config. If the legacy compose file is the one actually applied, **all Kafka produce/consume calls fail**. | `KAFKA_COMMAND_FLOW_REPORT.md` §1, §7 |
| **`diep-microgrid` crash loop** | Confirmed `Exited(255)` in the live environment at assessment time — `simulator/microgrid.py` cannot connect to mosquitto on 1883 (mTLS-only on 8883). | `DIEP_PLATFORM_ASSESSMENT.md` §C.1, `MQTT_FLOW_VALIDATION_REPORT.md` §6 |
| **`DIEP_SERVICE_TOKEN` mismatch** | `.env` sets `change-me-service-token`; dispatcher's default fallback (if env var unset in its container) is `diep-service-dev-token-CHANGE-ME`. If the dispatcher container doesn't actually receive `.env`'s value, every `POST /commands/{id}/ack` call gets **401**, so even a successfully-delivered command would never show as `ACKED` in the DB. | `KAFKA_COMMAND_FLOW_REPORT.md` §8 |
| **`DIEP_PORTAL_TOKEN` mismatch** | `.env.example` sets `change-me-admin-key`; BFF/portal default fallback is `diep-admin-dev-key-CHANGE-ME`. If portal env doesn't override this, **every admin/operator action from the Portal UI gets 401** even though the underlying FastAPI endpoints work fine via direct curl with the correct key. | `PORTAL_VALIDATION_REPORT.md` issue #1 |

### 3.3 Application-level issues (lower severity, don't block a basic demo but affect correctness)

| Issue | Detail | Evidence |
|---|---|---|
| Hardcoded Redis host | `app.py:91` hardcodes `redis` as hostname instead of reading from env — breaks if Redis service is renamed/relocated. | `FASTAPI_VALIDATION_REPORT.md` issue #1 |
| No DB connection pooling | Every request opens a new psycopg2 connection — fine for a demo, will not scale, adds latency under load. | `FASTAPI_VALIDATION_REPORT.md` issue #4 |
| Tenant-scoping gap in DERMS | `_assert_tenant_access` is called in most endpoints (`app.py:778-791`) but **not** in any of the 4 DERMS endpoints (`battery_dispatch`/`peak_shaving`/`demand_response`/`load_optimization`) or in `app.py:2046` (`/commands`) — an operator from Tenant A could issue commands against Tenant B's devices if they know the `device_id`. | `FASTAPI_VALIDATION_REPORT.md` issue #6, `DERMS_VALIDATION_REPORT.md` §6 |
| `derms_requests.status` semantics | `'EXECUTED'` is set as soon as the Kafka produce succeeds — never transitions to `'COMPLETED'`/`'FAILED'` based on actual device ack. Misleading for operators and for any automated reporting/SLA tracking. | `DERMS_VALIDATION_REPORT.md` §5 |

---

## 4. Security Gaps

| Gap | Severity | Detail |
|---|---|---|
| **CORS `*`** | High (for prod) | FastAPI CORS middleware allows all origins — acceptable for an isolated demo, unacceptable once the portal/API is internet-reachable. (`FASTAPI_VALIDATION_REPORT.md` issue #8) |
| **Hardcoded/default credential fallbacks in code** | High | `DIEP_SERVICE_TOKEN`/`DIEP_PORTAL_TOKEN` have hardcoded `*-CHANGE-ME` defaults baked into service code — if an operator forgets to override in any one environment, that environment silently runs with a publicly-known-from-source-code credential. |
| **`.env` tracked in git** | High | Per `DIEP_PLATFORM_ASSESSMENT.md`, `.env` (containing real-looking secrets, not just `.env.example`) is staged/committed to the repo — any clone of this repo leaks whatever credentials are in that file. |
| **Tenant-scoping bypass on DERMS/`/commands`** | Medium-High | See §3.3 — multi-tenant isolation is incomplete; a malicious or misconfigured tenant could issue commands to devices outside their tenant. |
| **Legacy device simulators use plaintext MQTT + shared username/password** | Medium | `simulator/ev_charger.py` and `simulator/microgrid.py` use `username_pw_set("diep-device","device-pass-2026")` over unencrypted 1883 — even disregarding the connectivity break, this is a shared static credential transmitted in cleartext, inconsistent with the per-device-cert mTLS model used elsewhere. |
| **`/readyz` doesn't check Kafka** | Low-Medium | Operationally a security/availability gap — orchestrators (k8s liveness/readiness) would route traffic to an instance that can't issue commands. |
| **No rate limiting observed on auth or command endpoints** | Medium | Not explicitly checked in sub-reports but no middleware for this was noted in the FastAPI validation — brute-force/DoS risk on `/auth/*` and `/commands`. |

---

## 5. Performance Concerns

| Concern | Detail | Evidence |
|---|---|---|
| **No DB connection pooling** | Per-request `psycopg2.connect()` — each API call pays full TCP+auth handshake cost to TimescaleDB; will not scale past low request volumes. | `FASTAPI_VALIDATION_REPORT.md` issue #4 |
| **No Kafka producer reuse guarantees** | Producer construction happens per call site without confirmed singleton/pool pattern and without exception isolation (§3.2/issue #2) — repeated construction under load adds latency and risk of connection exhaustion on the Kafka broker. | `FASTAPI_VALIDATION_REPORT.md` issue #2 |
| **Continuous aggregates require manual refresh** | `WITH NO DATA` aggregates won't auto-populate without a working refresh policy — dashboards/reports relying on `telemetry_5m`/`telemetry_1h` would show empty/stale data until refreshed, and a manual refresh over a large `telemetry` hypertable could be expensive post-restore. | `DATABASE_VALIDATION_REPORT.md` §5 |
| **Telemetry retention/compression unverified end-to-end** | Policies exist in SQL but were not verified to be active against the live (restored) instance — if not active, hypertable chunk count/size will grow unbounded over time. | `DATABASE_VALIDATION_REPORT.md` §6 |

---

## 6. Production Readiness Score

# **28 / 100**

### Justification

The score reflects a platform with **solid, largely-correct architecture and code** (DB schema,
API surface, ingestor, dispatcher, portal-to-API mapping all individually well-built) that is
**non-functional end-to-end** due to a small number of configuration/identity mismatches that
happen to sit on every critical path:

- **+40 baseline** for architectural completeness: every required component (DB schema, 36 API
  endpoints, MQTT ingest, Kafka command bus, dispatcher, portal pages, DERMS logic, auth/RBAC,
  metrics) exists and is individually implementable/correct in isolation.
- **−35** because **0 of the 5 Phase-7 end-to-end scenarios** can complete (no telemetry arrives
  for any seeded device; no command reaches `ACKED` for any seeded device) — for a platform whose
  entire value proposition is "observe devices and dispatch DERMS commands," this is a
  near-complete failure of the core demo.
- **−15** for security gaps that are not demo-blocking but would block any production
  consideration regardless of functional fixes (committed `.env`, hardcoded credential fallbacks,
  CORS `*`, tenant-scoping bypass).
- **−10** for unresolved infrastructure config drift (network name split, dual Kafka listener
  configs, stale backups) that makes "restore and demo" non-deterministic — the same repo could
  produce a working or non-working stack depending on which compose override is applied.
- **+8** for the fact that **all identified breaks are configuration/identity-mapping issues, not
  deep architectural flaws** — every fix in the remediation plan below is a config change, ID
  remap, or small targeted code fix, not a rewrite.

A platform at this score can run isolated component demos (e.g., "here's the schema," "here's a
curl call to `/derms/battery_dispatch` returning 200 and a DB row") but **cannot demonstrate a
single real device responding to a command or producing live telemetry** without the fixes below.

---

## 7. Estimated Effort to Production-Ready Demo

| Workstream | Effort | Depends on |
|---|---|---|
| **A. Infrastructure config reconciliation** (pick one network name and one Kafka listener config across all compose files; verify with `docker compose config`) | 0.5–1 day | None — do first |
| **B. Device-identity remediation** (choose: remap edge-driver `devices.json` to seeded IDs + add corresponding cert/ACL entries for `BAT001`/`INV001`/`MG001`/`METER001`, OR re-seed DB with `BAT900`/`INV900`/`MGC900`/`MTR900` and update portal/demo scripts to match) | 1–2 days | A |
| **C. EV001 + microgrid simulator mTLS migration** (port simulators from 1883/plaintext to 8883/mTLS with per-device certs, matching the edge-driver pattern) | 1 day | A |
| **D. Token alignment** (`DIEP_SERVICE_TOKEN`, `DIEP_PORTAL_TOKEN` — single source of truth in `.env`, verify all containers actually receive it) | 0.5 day | None — can run in parallel with A |
| **E. `derms_requests` status lifecycle** (add `COMPLETED`/`FAILED` transitions driven by command ack/timeout, so DERMS UI reflects real outcomes) | 1 day | B, C |
| **F. DB init-order fix (R1) + continuous-aggregate refresh verification** | 0.5 day | None — can run in parallel |
| **G. Security hardening pass** (remove `.env` from git + rotate secrets, restrict CORS, add tenant-scoping checks to DERMS/`/commands`, `/readyz` Kafka check) | 1–1.5 days | D |
| **H. End-to-end re-validation** (re-run the 5 Phase-7 scenarios live, confirm `ACKED`/`COMPLETED`, confirm telemetry arrives for all 5 devices, portal smoke test) | 0.5–1 day | A–G |

**Total estimated effort: ~6–8 working days** for one engineer familiar with the codebase to reach
a state where all 5 end-to-end scenarios complete successfully and core security gaps are closed.
A bare-minimum "demo works" milestone (workstreams A, B, C, D only — skipping E/F/G hardening)
could plausibly be reached in **~3–4 days**.

---

## 8. Prioritized Remediation Plan

1. **Reconcile Docker network naming** across `docker-compose.yml` and all `docker-compose-*.yml`
   overrides to a single network (`diep-lab_diep-net`). *Blocks everything else — without this,
   no two containers can reliably reach each other.*
2. **Reconcile Kafka listener configuration** — confirm which compose file is canonical (root
   SASL/9094 vs `docker-compose-kafka.yml` PLAINTEXT) and remove/align the other so FastAPI's and
   the dispatcher's `KAFKA_BOOTSTRAP_SERVERS`/SASL settings match the actual broker. *Blocks all
   command-flow scenarios.*
3. **Resolve device-identity mismatch (BAT001/INV001/MG001/METER001 vs BAT900/INV900/MGC900/MTR900)**
   — either remap edge drivers' `devices.json` + issue matching mTLS certs/ACLs for the seeded
   IDs, or re-seed the DB and all demo/portal references to the `*900` IDs. *This is the single
   highest-impact fix — it unblocks telemetry AND command-ack for 4 of 5 devices.*
4. **Migrate EV001 and microgrid simulators from plaintext 1883 to mTLS 8883** (issue device
   certs, update broker connection code) — fixes the 5th device and resolves the
   `diep-microgrid` crash loop simultaneously.
5. **Align `DIEP_SERVICE_TOKEN` and `DIEP_PORTAL_TOKEN`** between `.env` and the dispatcher/portal
   defaults; verify via container env inspection that the intended values are actually injected.
   *Without this, even a successfully-delivered command never shows `ACKED`, and the Portal UI
   can't issue any operator/admin action.*
6. **Fix DB init ordering (R1)** — move/reorder `001_commands.sql`'s FK-dependent statements
   after `003_seed_microgrid.sql` creates `sites`/`ev_chargers`, so fresh deployments (not just
   restores) succeed.
7. **Implement `derms_requests` status lifecycle** (`CREATED`→`EXECUTED`→`COMPLETED`/`FAILED`
   based on command ack/timeout) so the DERMS UI and reporting reflect real device outcomes
   instead of always showing `EXECUTED`.
8. **Security hardening**: remove `.env` from git history and rotate any exposed secrets,
   restrict CORS to known origins, add `_assert_tenant_access` checks to all 4 DERMS endpoints
   and `/commands`, add Kafka connectivity check to `/readyz`.
9. **Operational/perf cleanup** (lower priority, post-demo): connection pooling for
   TimescaleDB, exception-safe Kafka producer construction, hardcoded Redis host →
   env-configurable, verify continuous-aggregate refresh policies and retention/compression are
   active against the restored instance.
10. **Re-run all 5 Phase-7 end-to-end scenarios live** to confirm `ACKED`/`COMPLETED` status,
    telemetry arrival for all 5 devices, and portal end-to-end smoke test (login → dashboard →
    issue DERMS command → see status update) before declaring the platform demo-ready.

---

## 9. Summary

The DIEP platform's individual components — database schema, FastAPI service, MQTT ingest
pipeline, Kafka command bus, dispatcher, Next.js portal, and DERMS business logic — are each
**well-architected and largely correct in isolation**. However, **a small set of cross-cutting
configuration and device-identity mismatches** (Docker network naming, Kafka listener config,
seeded device IDs vs. edge-driver IDs, plaintext-vs-mTLS broker transport, and two auth-token
mismatches) sit on **every single end-to-end path**, with the result that **none of the 5
required demo scenarios (Battery Dispatch, Peak Shaving, Demand Response, EV Charger Control,
Microgrid Optimization) can currently complete**, and **no telemetry arrives in the database for
any of the 5 seeded devices**. All identified issues are configuration/mapping fixes or small,
well-scoped code changes rather than architectural rework, putting a working end-to-end demo
within an estimated **3–4 days** (bare minimum) to **6–8 days** (including security hardening) of
focused effort.
