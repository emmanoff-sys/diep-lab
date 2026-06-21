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
| 2 | Outage Management (OMS) | ⏳ planned | — |
| 3 | Distribution Management (DMS) | ⏳ planned | — |
| 4 | DERMS layer | ⏳ planned (extends existing `/derms`) | — |
| 5 | Historian + forecasting | ⏳ planned | — |
| 6 | Common GUI / portal tabs | ⏳ planned | — |
| 7 | Integration/adapter (DNP3) | ⏳ planned | — |

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
