# DIEP ADMS Extension — Release Notes

Branch: `feature/adms-network-model` → `main`
Scope: extend DIEP from a SCADA + telemetry platform toward a fuller **ADMS**
reference architecture (modeled on Survalent SurvalentONE): one unified network
model under SCADA + OMS + DMS + DERMS, surfaced through a common GUI, plus a
protocol adapter and a formalized historian.

All changes are **additive and backwards-compatible**: new FastAPI routers, new
idempotent SQL migrations, new portal routes/components, and one new background
service. No existing endpoint, schema object, or running service was removed or
repurposed.

---

## Highlights

- **Unified network model (M1):** canonical grid topology (`grid_nodes` +
  `grid_edges` directed graph, customers, service points, versioning) as the
  single source of truth, with a CRUD + graph-query API. Reused by OMS, DMS, and
  DERMS.
- **Outage Management (M2):** last-gasp + missing-heartbeat + manual-report
  detection, case management, Call Handler, KPIs (incl. SAIDI/SAIFI placeholders),
  an OMS dashboard, and a public (no-auth, no-PII) customer outage page.
- **Distribution Management (M3):** state estimation, FLISR (isolate + restore via
  tie), and Volt/VAR recommendations — topology-driven stubs, clearly labelled.
- **DERMS (M4):** formal DER registry, fleet aggregation, and dispatch/curtailment
  reusing the existing command path, with tenant isolation enforced.
- **Historian + forecasting (M5):** TimescaleDB formalized as the "Historian" with
  a documented query API and retention; a short-term load-forecasting stub.
- **Common GUI (M6):** OMS / DERMS / Forecasting integrated into the portal with
  grouped, role-filtered navigation (SCADA / ADMS / Analytics).
- **Protocol adapter (M7):** a DNP3 (mock) outstation bridged into the MQTT bus on
  the existing driver SDK — same MQTT/normalize/command contract as every driver.
- **OMS operating picture (read-only):** a grid + switch overlay, a FLISR planning
  panel, and a Volt/VAR advisory — added to the OMS page as decision support, with
  **no control/execution/mutation** (see "Read-only guarantees" below).
- **Ops:** the OMS outage detector is now a first-class platform service with a
  healthcheck and restart policy.

---

## New data model (idempotent migrations, applied by `init-db.sh`)

| Migration | Adds |
|---|---|
| `sql/013_network_model.sql` | `grid_nodes`, `grid_edges`, `customers`, `service_points`, `network_model_versions` (+ Abuja Site A seed) |
| `sql/014_oms.sql` | `outage_cases`, `outage_case_meters`, `outage_reports` |
| `sql/015_dms.sql` | TX-02 / second switch / normally-open tie for FLISR; `flisr_events` |
| `sql/016_der_registry.sql` | `der_assets` (+ VPP grouping seed) |
| `sql/017_dnp3_rtu.sql` | MGD900 device + `ND-MGD900` grid node |

## New API surface

- **Topology** `/topology/*` — nodes/edges CRUD, `/graph`, `/downstream/{id}`,
  edge switch, version.
- **OMS** `/oms/*` — `detect`, `call`, `cases`, `reports`, `outages`, `kpis`,
  `public/outages` (no auth).
- **DMS** `/dms/*` — `state_estimation`, `flisr/simulate` (+ `flisr/events`),
  `voltvar/recommendations`.
- **DERMS** `/der/*` — `assets`, `fleet`, `dispatch`, `curtailment`.
- **Historian** `/historian/*` — `query`, `retention`.
- **Forecasting** `/forecast/load`.

All mounted as `APIRouter`s in `fastapi/app.py` over a shared `fastapi/common.py`
(DB helpers + graph BFS), so `app.py` no longer grows per feature.

## Portal surfaces

- New routes: `/oms`, `/forecasting`, `/public/outages`; DERMS page extended.
- New components: `OutageMap` (with read-only grid overlay), `FlisrPlanner`,
  `VoltVarAdvisory`, grouped `Sidebar`.
- BFF proxy gained `PATCH`; `middleware.ts` treats `/public` as public.

## New / changed services

- **`oms-detector`** — promoted into the main `docker-compose.yml`:
  `restart: unless-stopped`, `depends_on` timescaledb/kafka/redis/mqtt/fastapi,
  heartbeat healthcheck, stateless restart-resume. (`docker-compose-oms.yml`
  retained as a deprecated standalone variant.)
- **DNP3 edge** — `docker-compose-dnp3.yml` runs the mock outstation bridge.

---

## Read-only guarantees (OMS operating-picture panels)

The three OMS decision-support panels are deliberately **observation-only** —
they establish the operating picture *before* any switching automation:

| Panel | Data source | Guarantee |
|---|---|---|
| Grid & switch overlay | `GET /topology/graph` | render-only; energization computed client-side |
| FLISR planner | `POST /dms/flisr/simulate` **`execute=false`** | plans on a server-side copy; `grid_edges` never changed; only writes its own `flisr_events` audit row (`executed=false`); operator-initiated, not polled |
| Volt/VAR advisory | `GET /dms/state_estimation`, `GET /dms/voltvar/recommendations` | GET-only; every recommendation tagged "Advisory"; no apply affordance |

No execute button, no switch operate, no Volt/VAR control is exposed anywhere in
these panels. Verified post-capture: live `grid_edges` remained at seed state.

---

## Validation

- **Regression:** 27/27 smoke tests pass (topology 7, OMS 5, DMS 4, DERMS 5,
  historian/forecast 5, DNP3 1), run in a container on the compose network.
- **Live end-to-end:** OMS dying-gasp → autonomous detection → public page →
  auto-restore; FLISR isolate + restore via tie (and refusal to re-energize a
  faulted node); DER dispatch → Kafka with cross-tenant 403; DNP3 mock → MQTT →
  TimescaleDB.
- **Read-only panels:** authenticated headless screenshots captured; no live
  state mutated; zero portal console errors. See `docs/oms-grid-overlay/`,
  `docs/oms-flisr-planner/`, `docs/oms-voltvar-advisory/`.

## Deployment / migration notes

- Apply migrations: `./init-db.sh` (additive `sql/013…017`).
- Bring up new services: `docker compose up -d` now includes `oms-detector`;
  DNP3 bridge via `docker-compose-dnp3.yml` (needs `scripts/issue-device-cert.sh
  MGD900`).
- No `.env` changes required for the read-only OMS panels. FLISR planning requires
  an operator/engineer/admin role.

## Backwards compatibility

Additive only. Existing SCADA/telemetry/command flows, schema, and services are
unchanged; the new model and panels layer on top.

---

## Commit list (11, on `main`)

```
9b7fbf5 OMS: read-only Volt/VAR advisory panel (ADMS step 3)
65f59f4 OMS: read-only FLISR restoration planner (ADMS step 2)
7cf8544 OMS: read-only grid & switch overlay on the outage map (ADMS step 1)
163fe93 ADMS: promote oms-detector to first-class platform service
3db588a ADMS M6: common GUI — grouped portal navigation
b23edfc ADMS M7: DNP3 (mock) protocol adapter bridged into MQTT
ac479e8 ADMS M5: Historian module + short-term load forecasting
fe7a0bf ADMS M4: DERMS layer (DER registry + aggregation + dispatch)
0e8d3bf ADMS M3: Distribution Management System (DMS) basics
9286854 ADMS M2: Outage Management System (OMS)
06caf18 ADMS M1: Unified Network Model (grid topology + API)
```
