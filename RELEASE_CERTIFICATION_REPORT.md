# DIEP Release Certification Report — v1.0.0-rc1

**Date:** 2026-06-13
**Scope:** Certification review of the v1.0 pilot baseline document set
(`RELEASE_NOTES_v1.0.md`, `SYSTEM_INVENTORY.md`, `CONFIGURATION_BASELINE.md`,
`DEPLOYMENT_BOM.md`, `PILOT_RELEASE_CHECKLIST.md`) plus a verification pass against the
working tree and `git status`, ahead of tagging `v1.0.0-rc1`.
Documentation and certification only — no code, configuration, or infrastructure was
modified to produce this report.

---

## 1. Documentation review

All five v1.0 baseline documents were re-read for this certification and are internally
consistent (cross-references resolve, readiness score matches across documents):

| Document | Status |
|---|---|
| `RELEASE_NOTES_v1.0.md` | ✅ Complete — capabilities, DERMS functions, security/monitoring features, 10 known limitations, roadmap, 88/100 score |
| `SYSTEM_INVENTORY.md` | ✅ Complete — 25 services, ports, databases, brokers, certs, secrets table, volumes |
| `CONFIGURATION_BASELINE.md` | ✅ Complete — compose files, env vars, backup schedule, monitoring config |
| `DEPLOYMENT_BOM.md` | ✅ Complete — host OS, image versions/digests, dependency pins |
| `PILOT_RELEASE_CHECKLIST.md` | ✅ Complete — pre/deployment/post-deployment, rollback, 88/100 breakdown |

---

## 2. Verification results

### 2.1 No secrets in Git — ❌ **FAIL (release-blocking)**

The repository has **no commits yet** (`git log` → "does not have any commits yet"),
and the working tree currently has **2,812 files staged for the first commit**. This
staged set includes real secrets and private key material:

| Item | Git status | Risk |
|---|---|---|
| `.env` | `AM` (staged) | Contains live values for `DB_PASSWORD`, `DIEP_JWT_SECRET`, `DIEP_ADMIN_KEY`/`DIEP_OPERATOR_KEY`, `MQTT_PASS`, `REDIS_PASSWORD`, `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`, `DIEP_SERVICE_TOKEN`, `DIEP_PORTAL_TOKEN` (40 vars) — would be committed to history permanently |
| `mosquitto/config/certs/ca.key` | `A` (staged) | **CA private key** — compromises the entire mTLS device fleet if exposed |
| `mosquitto/config/certs/server.key` | `A` (staged) | MQTT broker TLS private key |
| `caddy/certs/api.key` | `A` (staged) | Reverse-proxy TLS private key |
| `certs/devices/{BAT900,INV900,MGC900,MTR900,csms,dispatcher,ingestor}.key` | `A` (staged) | 7 device/service mTLS private keys |
| `certs/devices/{BAT001,EV001,INV001,METER001,MG001}.key` | `??` (untracked) | 5 more device private keys — would be added by `git add -A` |
| `.venv/` (2,812 files: Python interpreter, pip, pytest, site-packages) | `A` (staged) | Not secrets, but ~2,800-file repo bloat that should never be versioned |
| `.coverage`, `.docker-compose.yml.swp` | `A` (staged) | Editor/test-run artifacts |
| `.env.bak.1781164048`, `.env.pre-phase15a.bak`, `mosquitto/config/passwd.pre-phase15a.bak` | `??` (untracked) | Pre-rotation secret backups — would be added by `git add -A` |
| `backups/diep_20260613T042427Z.dump`, `.dump.sha256` | `??` (untracked) | Live DB dump — should never be committed |
| `mosquitto/config/passwd` | `AM` (staged) | Mosquitto password hash file — lower risk (hashed) but still credential material |

**Because no commit has been made yet, none of this is in Git history yet** — this is
fully remediable by unstaging before the first commit. See `GIT_RELEASE_CHECKLIST.md`
§1 for the exact remediation steps. **Do not run `git commit` or create the
`v1.0.0-rc1` tag until this is resolved.**

### 2.2 `.env` ignored — ❌ **FAIL**

No `.gitignore` file exists anywhere in the repository root. This is the root cause of
2.1: `.env`, `.venv/`, `.coverage`, editor swap files, `.bak` files, and the DB dump are
all eligible to be committed because nothing excludes them. `.env.example` (placeholder
values only) is correctly present and **should** be tracked.

### 2.3 Backup scripts present — ✅ **PASS**

All 5 scripts present and executable in `scripts/`:
`backup-db.sh`, `backup-config.sh`, `verify-backup.sh`, `install-backup-cron.sh`,
`dr-test.sh`. Matches `CONFIGURATION_BASELINE.md` §3.

### 2.4 Monitoring exporters present — ✅ **PASS**

`docker-compose.yml` defines `diep-cadvisor`, `diep-node-exporter`,
`diep-postgres-exporter`, and `diep-kafka-exporter`, matching
`CONFIGURATION_BASELINE.md` §4.1 and `SYSTEM_INVENTORY.md` §1.

### 2.5 UAT documents complete — ✅ **PASS**

`DIEP_UAT_TEST_PLAN.md` (241 lines) covers all 5 DERMS scenarios with explicit
pass/fail criteria, referenced from `RELEASE_NOTES_v1.0.md` §2 and §7.

---

## 3. Readiness score

**Platform readiness: 88 / 100** — unchanged from `PILOT_RELEASE_CHECKLIST.md` §5 and
`DIEP_PILOT_DEPLOYMENT_READINESS_REPORT.md`. The platform itself (DERMS functions,
security posture, monitoring, operations, deployment hygiene, documentation) has not
changed since that baseline; see the category breakdown there.

**Release-packaging gate (this report): NOT PASSED.** The 88/100 platform score
describes the *running stack*; it does not cover the *Git release artifact*. The
finding in §2.1/§2.2 is an independent, release-blocking gate — a perfectly-scored
platform can still fail certification if its first commit ships private keys and
credentials. This gate must be closed (via `GIT_RELEASE_CHECKLIST.md` §1) before
`v1.0.0-rc1` is tagged.

---

## 4. Known limitations

Carried from `RELEASE_NOTES_v1.0.md` §5 (unchanged, all still open at this baseline):

1. RPO ≈ 24h — nightly `pg_dump` only, no PITR/WAL archiving.
2. Kafka single-broker (RF=1), no failover.
3. 5 secondary secrets not yet rotated (`DIEP_ADMIN_PASSWORD`, `DIEP_OPERATOR_PASSWORD`,
   `DIEP_VIEWER_PASSWORD`, `DIEP_ACME_PASSWORD`, `DIEP_GLOBEX_PASSWORD`).
4. No TLS on operator-facing endpoints (Portal, Grafana, API).
5. Alertmanager has no notification receiver configured.
6. Single-host deployment — multiple SPOFs.
7. Orphaned `diep-influxdb` container.
8. Legacy plaintext MQTT port mappings (1883/9001) remain in compose.
9. Backups unencrypted at rest.
10. Floating `latest`/`latest-pg16` image tags for 13/25 services.

**New finding from this certification pass (not in the original 10 — repo-packaging,
not platform):**

11. **First commit currently stages `.env`, all mTLS private keys (including the CA
    key), the Python virtualenv, and editor/coverage artifacts**, because no
    `.gitignore` exists. This is a packaging defect, not a running-platform defect —
    it does not change the 88/100 score but is an absolute blocker for tagging.

---

## 5. Release risks

| Risk | Severity | Likelihood | Notes |
|---|---|---|---|
| **CA private key (`mosquitto/config/certs/ca.key`) and all device/service private keys committed to a Git repo** | Critical | Certain if tagged as-is | Any clone, fork, or repo leak compromises the entire mTLS trust chain for every device and service in the fleet; keys would also live forever in history even if removed later |
| **`.env` with live secrets committed** | Critical | Certain if tagged as-is | DB, JWT, Redis, MinIO, service-token credentials exposed to anyone with repo access; rotation alone does not help once committed (history persists) |
| 5 unrotated default passwords (`change-me-*`) reach the pilot site | High | Medium | Mitigated by `PILOT_RELEASE_CHECKLIST.md` §1 pre-deployment item, but only if followed |
| Alertmanager has no real receiver — pilot outages produce no notification | High | Medium | Independent of the tag; must be configured per-site before go-live |
| Floating image tags drift on `docker compose pull` post-tag | Medium | Medium | Digests recorded in `DEPLOYMENT_BOM.md` mitigate detection, but tag should be pinned in compose for the release branch |
| Kafka single-broker crash-loop recurrence (Phase 15C issue) | Medium | Low | Fix procedure documented in `DIEP_OPERATIONS_MANUAL.md` §5.2 |
| `.venv/` (2,812 files) committed | Low | Certain if tagged as-is | Repo bloat / slow clones, not a security issue, but should be excluded |
| Live DB dump (`backups/diep_20260613T042427Z.dump`) committed | Medium | Certain if tagged as-is | May contain tenant/device data; should never be in source control |

---

## 6. Pilot deployment recommendation

**Conditional GO** for a controlled customer pilot, contingent on:

1. Resolving the release-blocking Git findings in §2.1/§2.2 (see
   `GIT_RELEASE_CHECKLIST.md` §1) before any commit/tag is created — this is the only
   item that blocks *tagging itself*.
2. Completing `PILOT_RELEASE_CHECKLIST.md` §1 pre-deployment checks at the pilot site —
   in particular rotating the 5 default secrets and issuing a fresh CA/device cert set
   for the pilot fleet (the currently-staged certs must be treated as compromised once
   they have touched Git history, even if removed before the first commit they were
   generated for lab use and should not be reused at a customer site).
3. Configuring real Alertmanager receivers for the pilot site.

With items 1-3 addressed, the platform's functional readiness (88/100, all 6 DERMS
functions verified end-to-end, full monitoring/backup/DR tooling in place) supports a
controlled pilot deployment.

## 7. Production recommendation

**NO-GO for production** at this baseline. In addition to the pilot conditions above,
production rollout requires the items in `RELEASE_NOTES_v1.0.md` §6 production roadmap:
Postgres/TimescaleDB HA + PITR (closes the 24h RPO gap), Kafka multi-broker (removes the
command-bus SPOF), Redis Sentinel, distributed MinIO/MQTT clustering, and operator-facing
TLS. None of these are present at v1.0.0-rc1, which is explicitly scoped as a
**single-host pilot baseline**, not a production-grade deployment.

---

## 8. Related documents

- [`RELEASE_NOTES_v1.0.md`](RELEASE_NOTES_v1.0.md)
- [`SYSTEM_INVENTORY.md`](SYSTEM_INVENTORY.md)
- [`CONFIGURATION_BASELINE.md`](CONFIGURATION_BASELINE.md)
- [`DEPLOYMENT_BOM.md`](DEPLOYMENT_BOM.md)
- [`PILOT_RELEASE_CHECKLIST.md`](PILOT_RELEASE_CHECKLIST.md)
- [`GIT_RELEASE_CHECKLIST.md`](GIT_RELEASE_CHECKLIST.md)
- [`DIEP_PILOT_DEPLOYMENT_READINESS_REPORT.md`](DIEP_PILOT_DEPLOYMENT_READINESS_REPORT.md)
