# MW1 Verification Report

**Date:** 2026-06-17
**Scope:** Verification of the 10 items gating Maintenance Window 1 (MW1 — K1 PITR + K4 Redis Sentinel) per `PRODUCTION_DEPLOYMENT_TRACKER.md`: SEC-1 through SEC-5, MON-1 through MON-4, INFRA-2.
**Baseline:** commit `267a7fe`, tag `v1.1.2-security-hardened`. **Working tree is NOT clean** — see §6.

## 0. Headline result

**MW1 is still NOT authorized**, but real progress was made this session: the Docker host issue from the first verification pass was resolved (by the user, between sessions) and the full stack is now up. Live verification of SEC-2, SEC-3, SEC-4, MON-1→4, and the Phase 21 portal/Grafana security claims is now complete — and it surfaced **four real, previously-unverified bugs**, all found and fixed in this session (detailed in §1). Two items remain genuinely open and need your decision, not more engineering: **SEC-1** (`DB_PASSWORD` still default) and **INFRA-2** (not started, by design).

## 1. Bugs found and fixed during live verification

Static/config review in the previous pass said SEC-3, Grafana's password, and Phase 21's portal auth were "done." Running them for real found four bugs — all are now fixed and re-verified:

1. **Caddy never attached to the Docker network.** `diep-caddy` was running but `docker inspect` showed `NetworkSettings.Networks: {}` — an artifact of the container recovery process. Fixed by `docker compose up -d --force-recreate --no-deps caddy`.
2. **Caddy's API HTTP-redirect port (8080) collided with `diep-cadvisor`**, which has owned host port 8080 since long before this work. Caddy's container was silently failing to bind it. Fixed by moving the API HTTP listener to **8082** in both `docker-compose.yml` and `caddy/Caddyfile` (8443 HTTPS, 3080/3443, 3081/3444 were unaffected and didn't need to change).
3. **Caddy's Portal health check used `/`, which 307-redirects to `/login`** (the portal's own auth-gate middleware) — Caddy's default health check expects 2xx, so it marked the upstream permanently unhealthy and returned 503 to all real traffic. Fixed by pointing `health_uri` at `/login` (a deliberately-public route per `portal/middleware.ts`), which always 200s.
4. **Grafana's `admin/admin` default still worked; the new `.env` password did not.** Same root cause as the `DB_PASSWORD` problem already known for Postgres: `GF_SECURITY_ADMIN_PASSWORD` only seeds the admin account on first creation, and `grafana-data` is a volume from 2026-06-08, predating this password rotation. Fixed by `docker exec diep-grafana grafana cli admin reset-admin-password <new-password>` against the live instance — this is the Grafana equivalent of Postgres's `ALTER ROLE` fix-up.
5. **Phase 21's entire portal-auth feature was non-functional**: `relation "portal_users" does not exist`. `sql/012_users_rbac.sql` (the migration that creates it) was never applied — `docker-compose.yml` doesn't mount `sql/` as Postgres `initdb.d` (confirmed: no such mount exists), and the project's own `init-db.sh` applies all `sql/*.sql` files only when run manually, which never happened against this volume after Phase 21 landed. Fixed by applying just that one (idempotent, additive) migration directly: `cat sql/012_users_rbac.sql | docker exec -i diep-timescaledb psql -U diep -d diep`.

None of these fixes touched any named volume's data; #5 only added a new table and additive columns to the existing `audit_events` table.

## 2. SEC-1 through SEC-5 — live-verified status

| Item | Status | Live evidence |
|---|---|---|
| SEC-1 | 🟡 **Partial — needs your decision** | `DIEP_ADMIN_PASSWORD`, `OPERATOR`, `ENGINEER`, `VIEWER`, `ACME`, `GLOBEX`, `GF_ADMIN_PASSWORD` all rotated and **live-confirmed**: full login→whoami→logout→revoked-token-rejected cycle tested for `admin`; wrong-password correctly 401s; RBAC confirmed (`viewer` → 403 on `/auth/users`, `admin` → 200); password-reset request→confirm→login cycle tested end-to-end on `viewer` and reverted back to its original value. **`DB_PASSWORD` is still `diep123`** (the lab default) — left as-is per your earlier explicit instruction. This is the one open piece of SEC-1: rotating it now requires `ALTER ROLE` against the live Postgres (same class of fix as the Grafana bug above), not just an `.env` edit. |
| SEC-2 | 🟢 **Closed** | Zero hardcoded-credential matches (re-confirmed by grep). `diep-dispatcher` logs show healthy, ongoing SASL-authenticated Kafka metadata refreshes against `diep-kafka:9094` — no auth errors. |
| SEC-3 | 🟢 **Closed** (after fixing bugs #1–3 above) | `https://localhost:8443/healthz` → 200, `https://localhost:3444/api/health` → 200, `https://localhost:3443/login` → 200, all three send `Strict-Transport-Security`. `http://localhost:8082`, `:3080`, `:3081` all 301-redirect to their HTTPS counterparts. |
| SEC-4 | 🟢 **Closed** | Live `docker ps` confirms Postgres/Redis/Kafka/MinIO bound to `127.0.0.1` only (not `0.0.0.0`); Kafka's SASL listener (9094) was never published to the host at all. |
| SEC-5 | 🟡 **Partial (expected)** | `EMQX_ADMIN_PASSWORD` issued in `.env`. Still can't be fully tested — production EMQX (K5/MW5) isn't deployed in `docker-compose.yml` yet, so there's no live `/api/v5/nodes` to test against. Matches the tracker's own sequencing intent. |

## 3. MON-1 through MON-4 — live-verified status

All four rules are loaded in Prometheus (`GET /api/v1/rules` confirms `diep-ha-cluster-health` group with all 4 rules present) and in the correct state:

| Rule | State | Why |
|---|---|---|
| `KafkaBrokerCountLow` (MON-2) | 🟠 **firing** | Correct and expected — 1 broker exists today, rule fires below 3. Resolves automatically once K3/MW3 ships 3 brokers. |
| `EMQXClusterNodesLow` (MON-1) | ⚪ inactive (no data) | No EMQX scrape target yet — EMQX itself isn't deployed (K5/MW5). |
| `MinioDiskOnlineLow` (MON-3) | ⚪ inactive (no data) | No MinIO Prometheus scrape job yet (needs `mc admin prometheus generate`). |
| `PatroniClusterDegraded` (MON-4) | ⚪ inactive (no data) | No Patroni exporter yet — Patroni isn't deployed (K2/MW4). |

**Unresolved cross-cutting gap (unchanged from last review):** all four rules' tracker acceptance text says "Route to `diep-oncall` receiver." **No such receiver exists** in `alertmanager/alertmanager.yml` (only `default`/`critical`/`warning`). Routing is correct and functional via the severity tree, but this needs a decision: build a literal `diep-oncall` receiver, or update the tracker's acceptance language to match reality.

## 4. INFRA-2 — unchanged, not started by design

🔴 **Not started — intentionally.** It's scoped by the tracker as an MW1 **pre-flight/execution-time** action (static IPAM for `diep-redis`/`redis-replica` ahead of the actual Sentinel cutover), not a pre-MW1 hardening item. Implementing it now would mean modifying network topology ahead of the runbook step that's supposed to do it. Still awaiting your explicit go-ahead.

## 5. Other live checks performed (not separately gating, but worth recording)

- **Portal authentication/RBAC/audit logging (Phase 21 claims):** fully exercised live — login, wrong-password rejection, JWT `whoami`, server-side logout/token-revocation, password-reset request→confirm cycle, and admin-vs-viewer RBAC enforcement on `/auth/users` all behave correctly (after the migration fix in §1.5).
- **Audit trail:** `GET /audit/events` shows `request_id` and user/role attribution populated correctly per event. **Minor, non-blocking gap noticed:** the `login` action's audit entry doesn't populate `source_ip` (visible as `null`) — `app.py`'s `/auth/token` handler builds its `Principal` without passing `source_ip`, unlike other authenticated-action paths in `auth.py`. Not gating MW1; flagging so it isn't lost.
- **Redis:** confirmed healthy and stable (`PING` → `PONG`, `RestartCount=0`, `StartedAt` 16+ minutes stable at time of check). Its container log history shows a real AOF-corruption-and-recovery cycle (`Bad file format reading the append only file ... use redis-check-aof --fix`) that resolved before this session's checks began — consistent with the incident described separately.

## 6. Git status and undocumented live changes

**Current, re-verified state (not the earlier "6 modified" count — 3 more files changed since, from updating the tracker/readiness docs themselves):**

```
Changes not staged for commit:
  modified:   .env.example
  modified:   GO_LIVE_AUTHORIZATION_PACKAGE.md
  modified:   PHASE22_GO_LIVE_READINESS_REPORT.md
  modified:   PRODUCTION_DEPLOYMENT_TRACKER.md
  modified:   caddy/Caddyfile
  modified:   dispatcher/command_dispatcher.py
  modified:   docker-compose.yml
  modified:   fastapi/app.py
  modified:   prometheus/alerts.yml

Untracked files:
  DIEP_v1.1.2_SECURITY_HARDENED_RELEASE_NOTES.md
  MW1_VERIFICATION_REPORT.md
  docker-containers-before-cleanup.txt
```

9 files changed, 174 insertions(+), 28 deletions(-). Nothing committed, nothing pushed.

**What's in each file:**

| File | What changed |
|---|---|
| `.env.example` | Documents the new/changed variables (`GF_ADMIN_PASSWORD`, `DIEP_ENGINEER_PASSWORD`, `KAFKA_SASL_PASSWORD`, `EMQX_ADMIN_PASSWORD`, removal of `DIEP_PORTAL_TOKEN`) — template only, no real secrets. |
| `caddy/Caddyfile` | SEC-3: HTTPS+redirect blocks for Portal/Grafana; the two bug fixes (port 8080→8082, health_uri `/`→`/login`). |
| `docker-compose.yml` | SEC-3: `caddy` service block; SEC-4: port bindings to `127.0.0.1`; the 8080→8082 port fix. |
| `dispatcher/command_dispatcher.py` | SEC-2: `KAFKA_SASL_PASSWORD` sourced from env, no hardcoded fallback credential. |
| `fastapi/app.py` | SEC-2: same, for the FastAPI side's Kafka producer config. |
| `prometheus/alerts.yml` | MON-1→4: the four new HA-cluster health rules. |
| `PRODUCTION_DEPLOYMENT_TRACKER.md`, `PHASE22_GO_LIVE_READINESS_REPORT.md`, `GO_LIVE_AUTHORIZATION_PACKAGE.md` | This session's live-evidence updates (§2–§3 above). |
| `MW1_VERIFICATION_REPORT.md` (untracked) | This report. |
| `DIEP_v1.1.2_SECURITY_HARDENED_RELEASE_NOTES.md` (untracked) | Unrelated, from an earlier session — release notes for the already-tagged `v1.1.2-security-hardened`. |
| `docker-containers-before-cleanup.txt` (untracked) | Leftover diagnostic capture from the Docker-host incident triage; not needed going forward, candidate for deletion rather than commit. |

**Live changes that exist nowhere in git** (run directly against running containers — these would not survive a fresh deployment from scratch the same way, and are tracked here so they aren't lost):

1. `docker exec diep-grafana grafana cli admin reset-admin-password <new-password>` — reset Grafana's admin password against the already-initialized `grafana-data` volume. **Not needed for a fresh deployment**: a new volume would correctly pick up `GF_ADMIN_PASSWORD` from `.env` on first init. This was strictly a one-time catch-up for this existing volume.
2. `cat sql/012_users_rbac.sql | docker exec -i diep-timescaledb psql -U diep -d diep` — applied the missing portal-auth migration. **Already correctly handled for fresh deployments** by the existing `init-db.sh` (which includes `012_users_rbac.sql` in its concatenation). This was a one-time catch-up because this volume's `init-db.sh` was last run before Phase 21 added that file.
3. `docker compose up -d --force-recreate --no-deps caddy` (×2, after each Caddyfile/compose fix) — already fully reflected in the committed-to-disk-but-not-git config files; no separate action needed once those files are committed.

## 7. SEC-1: `DB_PASSWORD` rotation plan (proposal — not yet executed)

Same root cause class as the Grafana fix: `POSTGRES_PASSWORD` only seeds the role on first `initdb`, and `timescale-data` is an existing volume (2026-06-08) — an `.env` edit alone won't change the live database. Three consumers read `DB_PASSWORD`: `fastapi/app.py` (DB_CONFIG dict, read once at process start), `docker-compose.yml`'s `timescaledb` service (`POSTGRES_PASSWORD`, init-only), and `postgres-exporter`'s `DATA_SOURCE_NAME`.

Proposed steps:
1. Generate a new random password (32-char, same convention as the other SEC-1 rotations).
2. Apply it live, in place, with zero DB downtime: `docker exec diep-timescaledb psql -U diep -d diep -c "ALTER ROLE diep WITH PASSWORD '<new>';"`.
3. Update `.env`: `DB_PASSWORD=<new>`.
4. Recreate only the two consumers that cache the password in process memory — **not** `timescaledb` itself (no need to restart the database; the live `ALTER ROLE` already took effect): `docker compose up -d --no-deps --force-recreate fastapi postgres-exporter`.
5. Verify: `curl http://localhost:8000/readyz` still shows `"database": true`; `curl http://localhost:9187/metrics | grep pg_up` shows `1`; confirm the *old* password is now rejected (`psql ... ` with the old value should fail authentication).

This is safe and reversible (a role password change, not a schema or data change) and I can execute it on your go-ahead.

## 8. INFRA-2: scope and evidence required

**What it is** (tracker definition, unchanged): add static IPAM entries in the compose network config for `diep-redis` (primary) and a not-yet-existing `redis-replica`, before the Redis Sentinel cutover (K4/MW1). Purpose: prevent Sentinel from seeing spurious `+tilt` events from DNS-resolution races after container lifecycle events — Sentinel needs stable IPs, not just stable hostnames, for its failover state machine to behave correctly.

**Why it's not done yet:** it's explicitly scoped by the tracker as an MW1 **pre-flight** action — i.e., part of the actual cutover runbook, executed immediately before Sentinel goes live, not part of this pre-MW1 hardening sprint. There is currently no `redis-replica` or Sentinel service in `docker-compose.yml` at all; adding static IPAM now, for a topology that doesn't exist yet, would be speculative configuration against an undeployed service.

**Evidence required to close it** (tracker's own bar): `docker network inspect` confirming static IPs are assigned to both Redis nodes; Sentinel logs showing `+reset-master` and `+slave` events with **no** `+tilt` entries; `redis-cli sentinel masters` showing an IP address (not a hostname) for the master.

**What I need from you:** confirm whether you want this scoped into the current session (i.e., stand up `redis-replica` + Sentinel now, ahead of the K4 runbook), or left for the actual MW1 execution runbook as originally planned. I have not made any network/topology changes pending that answer.

## 9. MON-1, MON-3, MON-4: closure plan

These three are blocked on different things — not the same blocker repeated three times:

| Item | Blocked on | Closure path |
|---|---|---|
| **MON-3** (MinIO disks) | A **missing scrape job only** — `diep-minio` already exists and is running today (single-node, pre-K6). `prometheus/prometheus.yml` has no `minio` job (confirmed: only `prometheus`, `node-exporter`, `cadvisor`, `diep-fastapi`, `postgres-exporter`, `kafka-exporter` jobs exist). **This can be closed now, independent of K6/MW2**: run `mc admin prometheus generate` against the live MinIO to get a scrape bearer token, add a `minio` job to `prometheus.yml` pointing at `:9000/minio/v2/metrics/cluster`, reload Prometheus. The rule itself (`< 4` disks) is already correct to leave firing/pending against single-node MinIO today, the same way `KafkaBrokerCountLow` correctly fires pre-K3. |
| **MON-1** (EMQX nodes) | EMQX itself isn't deployed (K5/MW5). No scrape target can exist until then — genuinely blocked on that milestone, not an oversight. |
| **MON-4** (Patroni) | Patroni isn't deployed (K2/MW4), and no metrics-exporter sidecar exists for it yet even at the design level. Genuinely blocked on K2/MW4 landing, plus an additional small piece of work (the exporter) that should be scoped into that milestone's implementation plan, not MW1's. |

Recommendation: close MON-3 now (it's actually achievable, unlike the other two), and explicitly re-classify MON-1/MON-4 in the tracker as "blocked on K5/K2 respectively" rather than "Pre-MW1" — they cannot be closed before those milestones no matter how much pre-MW1 effort is applied.

## 10. Final MW1 closure checklist — remaining blockers only

Everything else is done and live-verified. What's actually left:

- [x] **SEC-1**: **closed** — explicit approval received; rotated `DB_PASSWORD` live via `ALTER ROLE` (zero downtime), updated `.env`, recreated `fastapi`+`postgres-exporter`. Verified from a genuine network connection (a throwaway container on `diep-net`, not `localhost` inside the DB container, which is trust-authenticated and not a valid test): old password rejected, new password accepted.
- [ ] **SEC-5**: no action available until K5/MW5 deploys EMQX — not a blocker you can close early
- [ ] **SEC-6**: decision needed (adopt MinIO backup encryption, or formally accept the risk) — not started this session, out of scope of SEC-1→5/MON-1→4
- [ ] **MON-1**: blocked on K5/MW5 (EMQX deployment) — not closable now
- [x] **MON-3**: **closed** — explicit approval received; ran `mc admin prometheus generate`, stored the bearer token in `prometheus/secrets/minio_token` (gitignored, mounted read-only into the Prometheus container — not embedded inline in tracked config), added the `minio` scrape job. **Found a 6th bug while closing this**: the originally-tracked metric name `minio_cluster_disk_online_total` doesn't exist in this MinIO version — it renamed disk→drive. Fixed the rule to `minio_cluster_drive_online_total`. Target is `up`, rule is `pending` (correct: single-node MinIO is below the eventual 4-drive K6/MW2 target).
- [ ] **MON-4**: blocked on K2/MW4 (Patroni deployment + exporter) — not closable now
- [x] **MON-1→4 wording**: **resolved** — corrected the tracker to match reality (no `diep-oncall` receiver exists, no outbound notification integration exists anywhere in this stack; routing via `critical`/`warning` is correct as-is) rather than building a receiver that would just be a second name for the same no-op destination.
- [ ] **INFRA-2**: scope decision needed — implement now vs. defer to MW1 execution runbook (§8) — **the only remaining 🔴 Open gate item**
- [ ] **Commit**: now 11 modified + 4 untracked files (grew further from this turn's fixes) — explicit approval received, committing next.

Not blockers, already closed with live evidence: SEC-1, SEC-2, SEC-3, SEC-4, MON-2, MON-3, plus Phase 21's portal auth/RBAC/audit/Grafana-password claims (all independently re-verified live in this pass, after fixing 6 bugs total across §1 and this section).
