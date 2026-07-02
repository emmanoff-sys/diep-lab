# DIEP — Distributed Intelligent Energy Platform

DIEP is a containerized utility-grid platform. Its core today is the **SCADA +
telemetry layer**: MQTT/Kafka ingestion, a FastAPI backend, a TimescaleDB
historian, Redis cache, Prometheus/Grafana monitoring, device simulators
(battery, solar, EV charger, microgrid, smart meter) and protocol drivers
(Modbus/SunSpec/OCPP/IEC-104), plus a Next.js operator portal.

It is being extended toward a fuller **ADMS reference architecture** (unified
network model + SCADA/OMS/DMS/DERMS on one data layer, common GUI) — see
[DIEP_ADMS_ARCHITECTURE.md](DIEP_ADMS_ARCHITECTURE.md).

## Architecture at a glance

```
Devices ──MQTT(diep/<domain>/<id>)──▶ ingestor ──POST /telemetry──▶ FastAPI
                                                                      │
                          TimescaleDB (historian) ◀── writes ────────┤
                          Redis (state/cmd cache) ◀── mirrors ───────┤
Operator ──▶ portal ──/api/diep──▶ FastAPI ──POST /commands──▶ Kafka(diep.commands)
                                                                      │
            device ◀──MQTT(.../cmd)── dispatcher ◀── consumes ───────┘
            device ──MQTT(.../ack)──▶ dispatcher ──POST /commands/{id}/ack──▶ FastAPI
```

- **Backend:** `fastapi/app.py` (+ `auth.py`, `common.py`, `routers/`). Raw
  `psycopg2`, JWT/RBAC (`viewer<operator<engineer<admin`, plus `service`),
  Prometheus `/metrics`, `/healthz` + `/readyz`.
- **Historian:** TimescaleDB `telemetry` hypertable + `telemetry_1m`/`telemetry_1h`
  continuous aggregates, compression + retention (`sql/010`).
- **Bus:** Mosquitto (mTLS, per-device cert identity) + Kafka (`diep.commands`).
- **Portal:** Next.js 14 App Router, Tailwind, SWR, Recharts + Leaflet, per-user
  BFF proxy at `/api/diep/*`.

## Running

```bash
# infra + app tiers
docker compose up -d                 # core services (incl. oms-detector)
./init-db.sh                         # apply sql/000..0NN schema + seeds
docker compose up -d fastapi portal  # app tier
```

`oms-detector` is a first-class service in the main stack: it polls
`POST /oms/detect` every 30s so outage detection runs continuously, with a
heartbeat healthcheck and `restart: unless-stopped`. It carries no local state —
detection is idempotent and re-derives from the DB, so it resumes automatically
after any restart.

Schema migrations are additive, idempotent SQL files under `sql/`, applied in
order by `init-db.sh`. New backend modules are FastAPI routers under
`fastapi/routers/` mounted in `app.py`.

## Tests

Integration smoke tests live under `tests/` and run against the live API on the
compose network:

```bash
docker run --rm --network diep-lab_diep-net -v "$PWD:/work" -w /work \
  -e DIEP_API_BASE=http://diep-fastapi:8000 \
  python:3.12 sh -c "pip install -q pytest -r fastapi/requirements.txt && python -m pytest tests/ -q"
```

## Key docs

- [DIEP_ADMS_ARCHITECTURE.md](DIEP_ADMS_ARCHITECTURE.md) — ADMS module design + status
- [DIEP_DEPLOYMENT_ARCHITECTURE.md](DIEP_DEPLOYMENT_ARCHITECTURE.md) — deployment topology
- [COMMAND_DISPATCHER.md](COMMAND_DISPATCHER.md) — command/ack flow
- [DIEP_OPERATIONS_MANUAL.md](DIEP_OPERATIONS_MANUAL.md) — ops runbook
- [MW2_READINESS_OPERATOR_RUNBOOK.md](MW2_READINESS_OPERATOR_RUNBOOK.md) — automated MW2 readiness verification

## Engineering Governance

This repository is the canonical engineering repository for DAEP / RE-OS per ADR-007 (2026-07-02).

| Resource | Location |
|----------|----------|
| Engineering Execution Control Register (EECR) | [`engineering/governance/EECR/`](engineering/governance/EECR/) |
| Engineering Standards | [`STANDARDS.md`](STANDARDS.md) |
| Repository Ownership | [`CODEOWNERS`](CODEOWNERS) |
| Architecture Decisions | [`engineering/governance/EECR/decision-log.md`](engineering/governance/EECR/decision-log.md) |
| Risk Register | [`engineering/governance/EECR/risk-register.md`](engineering/governance/EECR/risk-register.md) |

## Classification

**Internal — Confidential.** Access restricted to authorised engineers within the DAEP / RE-OS programme. Do not distribute outside the organisation.
