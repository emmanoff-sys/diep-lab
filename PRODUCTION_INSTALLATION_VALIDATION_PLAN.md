# DIEP Phase 20 — Production Installation Validation Plan

**Date:** 2026-06-17
**Phase:** 20 — Production Installation and Web Validation (Part A)
**Purpose:** Validate that DIEP can be installed and operated exactly as a customer/pilot site would, using only the published `DIEP_INSTALLATION_GUIDE.md` and a fresh clone from GitHub.
**Rules:** No production modifications. No infrastructure changes to the existing lab deployment. Validation only, in an isolated environment. Every issue discovered is recorded — none are silently worked around.

---

## 1. Validation Environment

| Item | Value |
|---|---|
| Host | Existing lab host (Ubuntu-based, `Linux 7.0.0-22-generic`), 4 vCPU / 7.2 GiB RAM / 48 GB disk — matches the documented pilot sizing in `DIEP_INSTALLATION_GUIDE.md` §1 |
| Isolation method | Fresh clone into `~/deploy-validation/phase20-fresh-install`, **separate from** the existing `~/projects/diep-lab` working tree and its running state |
| Source | `git clone https://github.com/emmanoff-sys/diep-lab.git` (real clone, real GitHub, no local file copy) |
| Credentials used | Throwaway validation-only values generated during this run; never copied from the existing `.env` |
| Teardown | `docker compose down -v` at the end of validation; cloned directory removed |

This mirrors the isolation discipline used in Phase 17 (K1–K6): a separate environment, separate volumes, separate network, and a clean teardown, so that the existing pilot deployment is never touched.

---

## 2. Validation Steps

Each step below is executed literally as documented in `DIEP_INSTALLATION_GUIDE.md` and `DIEP_OPERATIONS_MANUAL.md` — no undocumented workarounds are applied silently. If a step requires an undocumented action to succeed, that is recorded as a documentation gap, and the workaround is noted in the validation report.

### Step 1 — Fresh Host Simulation
Confirm the validation host's resources meet `DIEP_INSTALLATION_GUIDE.md` §1.1 minimums (4 vCPU / 8 GiB / 100 GB recommended for pilot). Record actual specs and any gap.

### Step 2 — Clone from GitHub
```
git clone https://github.com/emmanoff-sys/diep-lab.git
```
Record clone time and repository size.

### Step 3 — Follow Installation Guide Only
Work exclusively from `DIEP_INSTALLATION_GUIDE.md` §7 pre-install checklist, in order:
1. Verify Docker Engine ≥ 24.x and Compose V2 present
2. `cp .env.example .env`
3. Rotate all `change-me-*` defaults (validation-only throwaway values)
4. Confirm host packages (`git`, `curl`, `jq`, `bc`, `openssl`, `cron`, `tar`, `python3`)

No step from any other document (e.g., operations manual day-2 procedures) is used unless the installation guide explicitly references it.

### Step 4 — Generate PKI
```
./scripts/bootstrap-pki.sh
```
Confirm CA, broker cert, per-device client certs, and `mosquitto/config/passwd` are created per §6.1. Confirm idempotency by re-running once.

### Step 5 — Deploy All Services
```
./start-all-diep.sh
```
Record total deploy time, container count, and the health/state of every container against the documented 25-container topology.

### Step 6 — Initialize Database
Confirm `init-db.sh` runs as part of (or alongside) service startup; verify TimescaleDB schema, hypertables, and retention/compression policy are present per `DIEP_PHASE9SCHEMA_REPORT.md` baseline.

### Step 7 — Validate Monitoring
- Prometheus targets all `up`
- Grafana reachable and provisioned dashboards present
- Alertmanager reachable and configuration loaded
- cAdvisor and node-exporter metrics flowing

### Step 8 — Validate Backups
```
./scripts/backup-db.sh
./scripts/backup-config.sh
./scripts/verify-backup.sh
./scripts/install-backup-cron.sh
```
Confirm each script completes, output artifacts exist, and `verify-backup.sh` passes against the freshly created backup.

### Step 9 — Validate DERMS Functionality
Using the device simulators in `simulator/` and the scenarios in `END_TO_END_TEST_SCENARIOS.md`:
- Confirm `curl -sf http://localhost:8000/readyz` returns `{"ready": true, ...}`
- Run at least one round-trip per DERMS command type (EV charging, solar curtailment, battery control, smart meter, load, inverter) from simulator → MQTT → Kafka → dispatcher → database record
- Confirm mTLS is enforced (a simulator without a valid client cert is rejected)

---

## 3. Pass/Fail Criteria

| # | Criterion | Pass condition |
|---|---|---|
| 1 | Clean clone | Repository clones without error or missing submodules |
| 2 | PKI bootstrap | All certs/keys listed in §6.1 created; idempotent re-run produces no errors |
| 3 | Service deployment | All containers reach `Up`/`healthy` state using only documented commands |
| 4 | Database initialization | Schema and hypertables present; no manual SQL required beyond documented scripts |
| 5 | `/readyz` | Returns `{"ready": true, "checks": {"database": true, "redis": true}}` |
| 6 | Monitoring | Prometheus shows all expected targets `up`; Grafana and Alertmanager reachable |
| 7 | Backups | All 4 backup/verify scripts complete successfully against the fresh install |
| 8 | DERMS round-trip | At least one successful command delivery and database record per command type |
| 9 | mTLS enforcement | Certificateless/invalid-cert simulator connection rejected |
| 10 | Documentation completeness | No step required an action, parameter, or file not described in the installation guide |

**Overall PASS** requires all 10 criteria met. Any criterion not met is recorded as a finding with severity (Blocker / Major / Minor / Documentation) in `PRODUCTION_INSTALLATION_VALIDATION_REPORT.md`.

---

## 4. What Is Recorded

For every step: start/end timestamp, exact command run, exit code, and any deviation from the documented procedure. For every issue: which document was being followed, what was expected, what actually happened, and the workaround (if any) applied to proceed.

---

**Plan prepared by:** DIEP Platform Engineering
**Status:** Ready for execution
