# DIEP ADMS Reference Architecture

This document tracks the extension of DIEP from a SCADA + telemetry platform into
a fuller **ADMS-class** reference architecture (modeled on the unified-data-layer
approach of platforms like Survalent SurvalentONE): one network model and one
data layer shared by SCADA, OMS, DMS, and DERMS, surfaced through a common GUI.

It is built **incrementally on the existing platform** — reusing the FastAPI app,
MQTT/Kafka bus, TimescaleDB historian, and Redis — rather than introducing new
infrastructure. Each module is an isolated commit with live validation.

## Module status

| # | Module | Status | Key artifacts |
|---|--------|--------|---------------|
| 1 | Unified Network Model | ✅ implemented | `sql/013_network_model.sql`, `fastapi/routers/topology.py` |
| 2 | Outage Management (OMS) | ✅ implemented | `sql/014_oms.sql`, `fastapi/routers/oms.py`, `oms/outage_detector.py`, `portal/app/oms`, `portal/app/public/outages` |
| 3 | Distribution Management (DMS) | ✅ implemented | `sql/015_dms.sql`, `fastapi/routers/dms.py` |
| 4 | DERMS layer | ✅ implemented (extends `/derms`) | `sql/016_der_registry.sql`, `fastapi/routers/der.py`, `portal/app/derms` |
| 5 | Historian + forecasting | ✅ implemented | `fastapi/routers/historian.py`, `fastapi/routers/forecasting.py`, `HISTORIAN.md`, `portal/app/forecasting` |
| 6 | Common GUI / portal tabs | ✅ implemented | `portal/components/Sidebar.tsx` (grouped SCADA / ADMS / Analytics) |
| 7 | Integration/adapter (DNP3) | ✅ implemented | `drivers/dnp3/`, `ADAPTER.md`, `docker-compose-dnp3.yml`, `sql/017_dnp3_rtu.sql` |

## Conventions adopted

- **Backend modularity:** new endpoints live in `fastapi/routers/*.py` mounted via
  `app.include_router(...)`. Shared DB helpers are in `fastapi/common.py`
  (`get_conn`, `query_all`, `query_one`, `execute`) so routers never import `app.py`
  (which would be an import cycle). `app.py` imports `get_conn`/`DB_CONFIG` from
  `common.py`.
- **Schema:** additive, idempotent SQL migrations (`sql/0NN_*.sql`, `IF NOT EXISTS`
  / `ON CONFLICT DO NOTHING`), registered in `init-db.sh`. Tenant-scoped tables
  carry `tenant_id … REFERENCES tenants(tenant_id)`.
- **Auth:** reads gated at `viewer+`, structural writes at `engineer/admin`, live
  control ops at `operator+`, via `auth.require_role(...)`.
- **Tests:** lightweight integration smoke tests under `tests/`, run in a
  `python:3.12` container on the compose network against the live API.

---

## M1 — Unified Network Model

**Goal:** a canonical grid topology (single source of truth) that every other
module reads from, instead of re-deriving structure from the flat `devices` table.

### Data model (`sql/013_network_model.sql`)

A generic **directed graph** rather than one rigid table per asset class, so graph
queries and switching are uniform:

- **`grid_nodes`** — `node_id` PK, `node_type` ∈ {substation, feeder, transformer,
  switch, bus, meter, der, load}, `parent_id` (self-FK), `site_name` (→`sites`),
  `device_id` (nullable →`devices`, links a node to a live asset so telemetry/Redis
  state joins onto topology), `latitude/longitude`, `nominal_kv`, `attrs` JSONB,
  `tenant_id`, `model_version`.
- **`grid_edges`** — `edge_id` PK, `from_node`/`to_node` (→`grid_nodes`),
  `edge_type` ∈ {line, switch, transformer, tie}, `is_switchable`,
  `normally_closed`, **`is_closed`** (live state that FLISR/DMS mutates),
  `rating_kw`, `attrs`, `tenant_id`, `model_version`.
- **`customers`** — `customer_id` PK, contact info, `priority` ∈ {standard, medical,
  critical} (drives OMS prioritization).
- **`service_points`** — maps `customer_id` ↔ `node_id` ↔ `meter_device_id`.
- **`network_model_versions`** — published-model registry; nodes/edges stamp
  `model_version` for future diff/rollback.

**Seeded pilot model (Abuja Site A):**
`SUB-ABUJA → FDR-01 → [switch E-SW-01] → TX-01 → BUS-01`, with `BUS-01` fanning out
to the meter node (`ND-METER001`) and DER/asset nodes for `BAT001`, `INV001`,
`EV001`, `MG001`. Three customers (one `medical`) sit behind `ND-METER001`.
`E-SW-01` is the sectionalizing switch FLISR operates.

### API (`fastapi/routers/topology.py`, prefix `/topology`)

| Method | Path | Role | Purpose |
|--------|------|------|---------|
| GET | `/topology/version` | viewer+ | current model version |
| GET | `/topology/nodes` (`?node_type`,`?site_name`) | viewer+ | list nodes |
| GET | `/topology/nodes/{id}` | viewer+ | get node |
| POST | `/topology/nodes` | engineer/admin | create node |
| PUT | `/topology/nodes/{id}` | engineer/admin | update node |
| DELETE | `/topology/nodes/{id}` | admin | delete node (409 if referenced) |
| GET | `/topology/edges` | viewer+ | list edges |
| POST | `/topology/edges` | engineer/admin | create edge |
| DELETE | `/topology/edges/{id}` | admin | delete edge |
| PATCH | `/topology/edges/{id}/switch` | operator+ | open/close a switchable edge |
| GET | `/topology/graph` | viewer+ | full {nodes, edges} |
| GET | `/topology/downstream/{id}` (`?energized_only`) | viewer+ | reachable nodes + affected meters/customers |
| GET | `/topology/customers`, POST | viewer+ / eng+ | customer registry |
| GET | `/topology/service-points`, POST | viewer+ / eng+ | service-point registry |

**`/topology/downstream/{id}`** is the key graph primitive other modules reuse: a
BFS over **closed** edges, so an open switch correctly severs the de-energized
subtree. OMS uses it for the affected-customer set; DMS/FLISR uses the same graph +
switch state. When `energized_only=false`, it traverses regardless of switch state
(the full physical reach).

### Validation

`tests/test_topology_smoke.py` (7 tests, all passing): RBAC rejection, version,
seeded graph counts, downstream affected-customer resolution, switch-open severs
downstream (FLISR primitive) + restore, node CRUD + duplicate conflict, and
non-switchable-edge rejection.

Live-verified: opening `E-SW-01` drops downstream of `FDR-01` from 8 nodes / 3
customers to 1 node / 0 customers; re-closing restores it. `/metrics` unaffected.

---

## M2 — Outage Management System (OMS)

**Goal:** detect and manage outages, resolving affected customers through the M1
network model rather than duplicating device/customer metadata.

### Detection signals
1. **Last gasp** — the smart-meter simulator publishes a final `state=LAST_GASP`
   message on power loss: on a `remote_disconnect` command, or as a SIGTERM
   dying-gasp on container stop / feeder loss. The ingestor stores `state`, so
   detection reads `telemetry.state = 'LAST_GASP'`.
2. **Heartbeat gap** — a meter that reported before but not within
   `OMS_HEARTBEAT_TIMEOUT_S` (default 180s).
3. **Manual reports** — customer calls via the Call Handler.

`fastapi/routers/oms.py::_run_detection()` groups out-meters by their **section
root** (nearest upstream switch-fed node, via the M1 graph), opens/extends one
`outage_case` per section, links new reports (corroboration → `CONFIRMED`), and
**auto-restores** cases whose meters are all back online.

### Data model (`sql/014_oms.sql`)
- **`outage_cases`** — status (DETECTED→CONFIRMED→RESTORED→CLOSED), cause
  (last_gasp/heartbeat/manual/mixed), `affected_node_id`→`grid_nodes`,
  `customers_affected`, lifecycle timestamps.
- **`outage_case_meters`** — meters attributed to a case.
- **`outage_reports`** — Call Handler records, linked to a case once correlated.

### API (`/oms`)
| Method | Path | Role | Purpose |
|--------|------|------|---------|
| POST | `/oms/detect` | operator+/service | run one detection sweep (idempotent) |
| POST | `/oms/call` | operator+ | Call Handler — record + correlate a report |
| GET | `/oms/cases` (`?status`) | viewer+ | list cases |
| GET | `/oms/cases/{id}` | viewer+ | case detail (meters + reports) |
| POST | `/oms/cases` | operator+ | manual case |
| PATCH | `/oms/cases/{id}` | operator+ | confirm / restore / close + notes |
| GET | `/oms/reports` | viewer+ | customer reports |
| GET | `/oms/outages` | viewer+ | active cases + coords for the map |
| GET | `/oms/kpis` | viewer+ | call volume, customers impacted, avg restoration, SAIDI/SAIFI (placeholders) |
| GET | `/oms/public/outages` | **none** | public outage status by area — no PII |

`oms/outage_detector.py` (+ `docker-compose-oms.yml`) drives `/oms/detect` on an
interval (`OMS_DETECT_INTERVAL`, default 30s) with the service token.

### Portal
- `portal/app/oms/page.tsx` — OMS Dashboard: KPI cards, active-outage Leaflet map
  (`components/OutageMap.tsx`), Call Handler form, and a case table with
  confirm/restore/close actions. Added to the sidebar nav.
- `portal/app/public/outages/page.tsx` — public Customer Outage Portal (server
  component, no auth, allow-listed in `middleware.ts`, fetches the open endpoint
  directly). `middleware.ts` now treats `/public` as a public prefix; the BFF
  proxy gained a `PATCH` method for case actions.

### Validation
`tests/test_oms_smoke.py` (5 tests) + topology (7) all pass. Live end-to-end
verified through the real bus: started `mqtt`+`ingestor`+meter sim over mTLS,
stopped the sim → dying-gasp `LAST_GASP` ingested → `/oms/detect` opened a case
at `TX-01` (3 customers) → `/oms/public/outages` and the portal `/oms` +
`/public/outages` pages showed it; fresh telemetry auto-restored it.

> **Note on the simulator:** the meter sim must run python as PID 1 (compose uses
> `exec python …`) — otherwise the wrapping shell holds PID 1 and SIGTERM never
> reaches python, so no dying-gasp fires. This was caught and fixed during M2.

---

## M3 — Distribution Management System (DMS) basics

**Goal:** lightweight, topology-driven distribution functions (all stubs — no
real power-flow solver), reading the M1 graph + live telemetry.

### Schema (`sql/015_dms.sql`)
Adds network **redundancy** so FLISR restoration is meaningful: a backup
transformer `TX-02` fed by a second switch `E-SW-02`, and a **normally-open tie**
`E-TIE-01` (TX-02→BUS-01) that can back-feed the LV bus when the primary path is
isolated. Plus `flisr_events` (run audit).

### API (`/dms`)
| Method | Path | Role | Purpose |
|--------|------|------|---------|
| GET | `/dms/state_estimation` | viewer+ | per-node voltage/load estimate |
| POST | `/dms/flisr/simulate` | operator+ | isolate fault + restore (plan or execute) |
| GET | `/dms/flisr/events` | viewer+ | FLISR run history |
| GET | `/dms/voltvar/recommendations` | viewer+ | rule-based Volt/VAR actions |

- **State estimation** — propagates measured load down the energized graph and
  estimates voltage as `1.0 pu` at the substation minus a drop proportional to
  downstream load; nodes with live telemetry are flagged `monitored` and show
  measured V/kW. Stub (`DMS_DROP_PU_PER_KW`), not a solver.
- **FLISR** — resolves the fault to a node, opens the nearest upstream switchable
  edge whose subtree contains it (isolation), then closes a normally-open tie
  that re-feeds the lost load **without re-energizing the faulted node**
  (restoration). Plans on an in-memory copy of the graph; persists switch changes
  only when `execute=true`. Every run is recorded in `flisr_events`.
- **Volt/VAR** — flags energized nodes outside band (measured LV volts
  216–253 V where available, else estimated 0.95–1.05 pu) and recommends
  raise/lower actions. Stub, open-loop (no actuation).

### Validation
`tests/test_dms_smoke.py` (4) + OMS (5) + topology (7) = 16 pass. Live-verified:
state estimation shows voltage dropping 0.9992→0.996 pu from substation to the
loaded meter; FLISR fault at `TX-01` isolates `E-SW-01` and restores 3 customers
via tie `E-TIE-01` in plan mode (switches untouched), and in `execute=true` mode
mutates switch state and correctly refuses to re-energize a faulted node;
Volt/VAR flags a 215 V meter as low → raise.

> DMS is API-first; not surfaced as its own portal tab (the portal scope is
> OMS / DERMS / forecasting). FLISR/state-estimation can be surfaced on the OMS
> map later if desired.

---

## M4 — DERMS layer (DER registry + aggregation + dispatch)

**Goal:** a formal Distributed Energy Resource registry layered on the existing
`/derms` endpoints and command path — not a new control plane.

### Schema (`sql/016_der_registry.sql`)
`der_assets` — `der_id`→`devices`, `der_type` (battery/solar/ev_charger/
microgrid), `node_id`→`grid_nodes` (M1 binding), `rated_kw`, `rated_kwh`,
`controllable`, `vpp_group`, `tenant_id`. Seeds the pilot fleet (BAT001, INV001,
EV001, MG001) into the `abuja-vpp` group.

### API (`/der`)
| Method | Path | Role | Purpose |
|--------|------|------|---------|
| GET | `/der/assets` (`?vpp_group`) | viewer+ | registry + live output, tenant-scoped |
| GET | `/der/fleet` (`?vpp_group`) | viewer+ | aggregate rated/storage/output, by type |
| POST | `/der/dispatch` | operator+ | dispatch a command to a DER |
| POST | `/der/curtailment` | operator+ | curtail (maps to per-type command) |

Dispatch/curtailment **reuse `_dispatch_command`** (via a lazy import to avoid the
app↔router cycle) → Kafka `diep.commands` → dispatcher → MQTT, so DER control
flows through the same validated, audited, metered pipeline as `/commands`.
Curtailment maps per type: solar/ev→`set_limit`, battery→`set_power_limit`,
microgrid→`set_setpoint`. Live output is the latest fresh telemetry per DER.

**Multi-tenancy fix:** `/der/dispatch` and `/der/curtailment` enforce
`_assert_tenant` — the gap the legacy `/derms` endpoints had. Verified: `acme-op`
(tenant=acme) dispatching `BAT001` (tenant=default) → 403.

### Portal
The existing `/derms` page gains a **DER fleet summary** (rated capacity,
storage, live output, online count) and a **DER registry table** (per-DER type,
bound node, rating, output, VPP group) above the existing action panel + request
log — kept as one DERMS tab.

### Validation
`tests/test_der_smoke.py` (5) + all prior = 21 pass. Live: `/der/fleet` reports 4
DERs / 582 kW rated; dispatch (BAT001 discharge) and curtailment (INV001→5 kW)
produce `SENT` commands to Kafka; cross-tenant dispatch is blocked (403). `/derms`
page recompiles and renders the fleet panel.

---

## M5 — Historian + forecasting

**Goal:** formalize the TimescaleDB telemetry store as a named **Historian** with
a documented query API + retention introspection (M5a), and add a short-term load
forecaster (M5b). No new storage — see [HISTORIAN.md](HISTORIAN.md).

### M5a Historian (`fastapi/routers/historian.py`)
- `GET /historian/query` — `device_id`/`metric`/`bucket`(raw|1m|1h)/`hours`; raw
  reads the hypertable, `1m`/`1h` read the continuous aggregates (`avg_<metric>`).
  Metric names are whitelisted (column interpolated) to prevent injection.
- `GET /historian/retention` — hypertables, continuous aggregates, and
  compression/retention/refresh policy jobs (compress@7d, raw 90d, 1m 180d).

### M5b Forecasting (`fastapi/routers/forecasting.py`)
- `GET /forecast/load` — hour-of-day seasonal mean blended with a recent moving
  average when ≥ ~1 day of history exists, else a flat moving-average projection.
  Pure stdlib (no Prophet/ARIMA per the chosen lightweight approach). Portal
  **Load Forecasting** tab (`portal/app/forecasting`) renders it via the existing
  `TimeSeriesChart`.

### Validation
`tests/test_historian_forecast_smoke.py` (5) + prior = 26 pass. Live: historian
raw query returns the seeded series; `/historian/retention` lists all 7 policies
(after fixing a silent failure — a literal `%` in `LIKE 'policy%'` must be `%%`
because `query_all` passes params, so psycopg2 treated it as a placeholder);
forecast returns horizon points; `/forecasting` page compiles and renders.

---

## M7 — Integration / Adapter layer (DNP3)

**Goal:** show how a real field protocol bridges into the MQTT bus. Modbus is
already real (`modbus_meter`/`sunspec`/`battery_bms`); M7 adds **DNP3** as a mock
so it runs without hardware. Full detail in [ADAPTER.md](ADAPTER.md).

`drivers/dnp3/` implements the stub as a working adapter on the existing driver
SDK (`BaseDriver` + `Runner`): `models.py` (DNP3 point map — AI/BI + CROB/AO
controls), `sim.py` (`MockDnp3Outstation`, in-process, islanding droop physics),
`driver.py` (`Dnp3Driver`, `domain=microgrid`: polls the outstation, normalizes
PCC power → canonical, maps island/grid_connect→breaker CROB, set_setpoint→AO),
`selftest.py`. A real deployment only swaps `connect()` for an `opendnp3` master —
the MQTT/normalize/command contract is unchanged.

`docker-compose-dnp3.yml` runs it via the edge agent as RTU `MGD900` (mTLS);
`sql/017_dnp3_rtu.sql` registers the device + topology node so the ingestor
accepts it; an ACL block for `MGD900` was added to `mosquitto/config/acl`.

### Validation
`tests/test_dnp3_adapter.py` (driver selftest) + prior = 27 pass. Live-verified
end-to-end: the bridge published `diep/microgrid/MGD900` telemetry over mTLS →
ingestor → TimescaleDB (with store-and-forward buffering on connect).

---

## M6 — Common GUI / portal integration

The OMS, DERMS, and Forecasting surfaces were each integrated into the existing
Next.js portal as they were built (M2/M4/M5b), reusing the shared design system
(`Section`, `PageHeader`, `MetricCard`, `StatusBadge`, `TimeSeriesChart`, Leaflet)
and the per-user BFF — not separate apps. M6 is the consolidation pass:
`portal/components/Sidebar.tsx` now groups navigation into **SCADA**
(Dashboard / Fleet / Twins), **ADMS** (OMS / DERMS / Load Forecasting), and
**Analytics & Ops** (AI Operations / Alarms / Reports / Administration), with
role-filtered items and empty-group hiding — so the SCADA + OMS + DERMS +
analytics surfaces read as one platform. The public Customer Outage Portal
(`/public/outages`) sits outside the authenticated shell by design.

Validated: all tabs load 200 authenticated; portal recompiles cleanly.
