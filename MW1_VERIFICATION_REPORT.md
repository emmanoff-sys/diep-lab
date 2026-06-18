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

## 9b. INFRA-2: closed (scoped and implemented, with explicit approval)

Implemented per `K4_REDIS_SENTINEL_IMPLEMENTATION_PLAN.md` §6 and the validated topology in `K4_REDIS_SENTINEL_VALIDATION_REPORT.md` — not designed fresh:

- Pinned `diep-net` to its already-auto-assigned subnet (`172.18.0.0/16`) explicitly in `docker-compose.yml`, so existing container addresses were unaffected.
- Assigned static IPs: `diep-redis` → `172.18.0.240`, new `diep-redis-replica` → `172.18.0.241` — exactly INFRA-2's literal ask, and exactly the validation report's recommended fix for the `+tilt` failure mode (hostname-based `sentinel monitor` re-entering `+tilt` after a container lifecycle event).
- Added `redis-replica` (streaming replication, `--replica-read-only yes`, `--appendonly yes`) and 3 `redis-sentinel-{1,2,3}` services (quorum 2 of 3), mirroring the validated design's topology exactly. New config: `redis-sentinel/sentinel.conf.template` (monitors `172.18.0.240` by IP, password placeholder) and `redis-sentinel/sentinel-entrypoint.sh` (substitutes the real password into a writable per-instance copy at `/data/sentinel.conf` — Sentinel rewrites this file at runtime, so it can't be the read-only mounted template directly).
- Applying a new network IPAM config requires recreating the network, so this was a brief full-stack `docker compose down && up` (not a per-service recreate) — confirmed zero containers left exited afterward, `/readyz` recovered.

**Live evidence (all of INFRA-2's tracker-specified evidence, collected after bringup):**
- `docker network inspect`: `diep-redis` → `172.18.0.240`, `diep-redis-replica` → `172.18.0.241`.
- Replica `INFO replication`: `role:slave`, `master_host:172.18.0.240`, `master_link_status:up`.
- Sentinel-1 log: `+monitor master diep-master 172.18.0.240 ...`, `+slave slave 172.18.0.241:6379 ...`, two `+sentinel` discovery lines (by IP) — zero `+tilt` lines across all 3 sentinels' full logs.
- `sentinel masters`: `ip: 172.18.0.240` (an IP, not `diep-redis`).
- `sentinel master diep-master`: `num-other-sentinels: 2`, `quorum: 2` — correct 3-node quorum view.

**Scope boundary, deliberately not crossed:** this closes the *network/topology* prerequisite only. The implementation plan's §6 production rollout also calls for switching `fastapi`/`auth`/`copilot`'s Redis client to `redis.sentinel.Sentinel(...).master_for(...)` (gated behind a `REDIS_SENTINELS` env var) and running the actual failover drill — that is the MW1 maintenance window itself, not a pre-flight item, and wasn't part of what was asked here. `diep-redis` (primary) is unmodified in its role; the application still talks to it directly, exactly as before.

## 9c. SEC-6: closed (adopted SSE-KMS, with explicit approval)

Decision: **adopt SSE-KMS**, using a generated static MinIO KMS secret key rather than wiring through the existing `docker-compose-vault.yml` Vault container — that Vault runs in `-dev` mode only (its own header comment: "Production runs Vault in HA (not -dev)"; dev mode auto-unseals and loses all data on restart). Routing real backup-encryption keys through a non-production Vault instance would have been a worse, more theatrical version of the same "looks closed but isn't" problem this whole session has been correcting — a generated static key is the honest choice for what's actually deployed here.

Implementation:
- `MINIO_KMS_SECRET_KEY` (name:base64-32-byte-key) added to `.env` (real key) and `.env.example` (placeholder + generation command), wired into the `minio` service's environment.
- Recreated `minio` (single-service, no network change this time).
- Created both backup buckets used by `scripts/backup-db.sh` (`diep-backups`) and `scripts/backup-config.sh` (`diep-config-backups`) and set `mc encrypt set sse-kms diep-backup-key` as the default on each — this is bucket metadata stored server-side (persists across container restarts, unlike the `mc` CLI's own alias config, which is container-local and had to be redone after the `minio` recreate).

**Live evidence (tracker's exact bar):** `mc admin kms key status` → `Key: diep-backup-key — Encryption ✔ Decryption ✔`. Uploaded a real test object to `diep-backups` and ran `mc stat`: `Encryption: SSE-KMS (arn:aws:kms:diep-backup-key)`. Test object removed after verification; the bucket-level default encryption config remains in place for all future uploads, including the next real `backup-db.sh`/`backup-config.sh` run.

## 10. Final MW1 closure checklist — remaining blockers only

Everything else is done and live-verified. What's actually left:

- [x] **SEC-1**: **closed** — explicit approval received; rotated `DB_PASSWORD` live via `ALTER ROLE` (zero downtime), updated `.env`, recreated `fastapi`+`postgres-exporter`. Verified from a genuine network connection (a throwaway container on `diep-net`, not `localhost` inside the DB container, which is trust-authenticated and not a valid test): old password rejected, new password accepted.
- [ ] **SEC-5**: no action available until K5/MW5 deploys EMQX — not a blocker you can close early
- [x] **SEC-6**: **closed** — explicit approval received; adopted SSE-KMS with a generated static key (§9c), set as default encryption on both backup buckets, verified live via `mc stat`.
- [ ] **MON-1**: blocked on K5/MW5 (EMQX deployment) — not closable now
- [x] **MON-3**: **closed** — explicit approval received; ran `mc admin prometheus generate`, stored the bearer token in `prometheus/secrets/minio_token` (gitignored, mounted read-only into the Prometheus container — not embedded inline in tracked config), added the `minio` scrape job. **Found a 6th bug while closing this**: the originally-tracked metric name `minio_cluster_disk_online_total` doesn't exist in this MinIO version — it renamed disk→drive. Fixed the rule to `minio_cluster_drive_online_total`. Target is `up`, rule is `pending` (correct: single-node MinIO is below the eventual 4-drive K6/MW2 target).
- [ ] **MON-4**: blocked on K2/MW4 (Patroni deployment + exporter) — not closable now
- [x] **MON-1→4 wording**: **resolved** — corrected the tracker to match reality (no `diep-oncall` receiver exists, no outbound notification integration exists anywhere in this stack; routing via `critical`/`warning` is correct as-is) rather than building a receiver that would just be a second name for the same no-op destination.
- [x] **INFRA-2**: **closed** — explicit approval received; redis-replica + 3-Sentinel topology stood up with static IPAM per §9b. All tracker-specified evidence collected and passing.
- [x] **Commit**: committed as `37683a3` (the SEC-1..4/MON-2..3 fix set, 13 files). INFRA-2's redis-sentinel work (this section) is a separate, later set of changes — not yet committed as of this writing.

**Gate status: 7 of 10 closed, 3 correctly partial (pending K5/MW5 ×2, K2/MW4 ×1), 0 open.** MW1's pre-flight prerequisites are clear. MW1 itself — the K1 PITR + K4 Sentinel cutover, including the application-level Sentinel client switch and failover drill — has not been executed and still requires explicit scheduling.

Not blockers, already closed with live evidence: SEC-1, SEC-2, SEC-3, SEC-4, MON-2, MON-3, INFRA-2, plus Phase 21's portal auth/RBAC/audit/Grafana-password claims (all independently re-verified live in this pass, after fixing 6 bugs total).

## 11. MW1 executed: K1 PITR + K4 Sentinel cutover (2026-06-17, explicit approval received)

With the gate clear (§10), the user approved executing MW1 itself — not just its pre-flight prerequisites. Both halves implemented per the already-validated plans (`K1_PITR_IMPLEMENTATION_PLAN.md` §6, `K4_REDIS_SENTINEL_IMPLEMENTATION_PLAN.md` §6) and verified live.

### 11a. K1 PITR

- Created MinIO buckets `diep-wal-archive` and `diep-pg-basebackups`; both default to SSE-KMS (extending SEC-6's policy, not a separate decision).
- Added a `wal-archive` named volume (INFRA-1: pre-created and `chown -R 70:70` — confirmed via `id postgres` inside `diep-timescaledb` that uid 70 is correct for this image — **before** anything mounted it, so `archive_command` would never hit a permissions error).
- Added a `wal-shipper` sidecar (`minio/mc`, mirrors `pitr-validation/scripts/ship-wal.sh`'s validated design) mirroring `/wal-archive` to `diep-wal-archive` every 15s.
- Applied `archive_mode=on`, `archive_command=test ! -f /wal-archive/%f && cp %p /wal-archive/%f`, `archive_timeout=60` to `diep-timescaledb` via its compose `command:` — this **required a Postgres restart** (the one piece of this whole effort that needed real downtime; `wal_level`/`max_wal_size` were left unchanged, already sufficient).
- Added `scripts/backup-pg-basebackup.sh` (weekly physical base backup, mirrors `backup-db.sh`'s conventions: alert-on-failure, positive upload-size verification, retention prune) and a new Sunday 04:00 cron entry in `scripts/install-backup-cron.sh`.

**Bug found and fixed:** the plan's literal command, `pg_basebackup -D - -Ft -z -Xs`, fails on this Postgres version — `pg_basebackup: error: cannot stream write-ahead logs in tar mode to stdout`. `-Xs` (stream) can't share stdout with the tar output; switched to `-Xfetch`, which is stdout-compatible and sufficient since continuous WAL archiving already covers the gap between base backups.

**Live evidence:**
- `show archive_mode` → `on`.
- Forced a WAL switch (`pg_switch_wal()`); segment `000000010000000000000008` appeared in `diep-wal-archive` within the shipper's 15s loop. `mc stat` confirms `Encryption: SSE-KMS (arn:aws:kms:diep-backup-key)`.
- Ran `backup-pg-basebackup.sh` live (not just installed the cron): produced an 8.0MB tarball, uploaded, size-verified, also SSE-KMS encrypted.
- RPO bound: `archive_timeout` (60s) + shipper interval (15s) ≈ 75s worst case — matches the implementation plan's own estimate.

### 11b. K4 Sentinel cutover

- Added `fastapi/redis_client.py`: a single `get_redis_client()` used by both `fastapi/app.py` and `fastapi/auth.py` (previously two separate direct `redis.Redis(host="diep-redis", ...)` construction sites — confirmed via repo-wide grep these were the *only* two live construction sites; `copilot/cache/redis_cache.py` takes an externally-supplied client and isn't actually wired into `app.py`, so it didn't need touching). Gated by `REDIS_SENTINELS` (comma-separated `host:port`): unset keeps the old direct-connection behavior (instant rollback, per the plan's own §7); set, it builds a `redis.sentinel.Sentinel(...).master_for("diep-master")` connection.
- Set `REDIS_SENTINELS=diep-redis-sentinel-1:26379,diep-redis-sentinel-2:26379,diep-redis-sentinel-3:26379` in `.env`/`.env.example`, recreated `fastapi`.
- **Verified the client is genuinely Sentinel-backed, not silently falling back**: `REDIS.connection_pool` inside the running container is `redis.sentinel.SentinelConnectionPool`, not a plain pool.

**Failover drill** (`docker kill diep-redis`, the primary):
- Sentinel log timeline: `+sdown` at 5.08s after the kill (matches `down-after-milliseconds=5000`), `+odown` (quorum 3/2) at 6.15s, `+switch-master` at 6.48s — consistent with the validation report's measured ~6-7s.
- `fastapi`'s `RestartCount` stayed `0` and `StartedAt` didn't change across the entire drill — the app reconnected to the new primary transparently, with no restart, confirmed via `/readyz` staying `{"ready": true, ..., "redis": true}` throughout.
- **Topology recovery**: the killed `diep-redis` did not auto-restart under `restart: unless-stopped` (exited 137, `RestartCount: 0` — Docker did not consider this an "unexpected" exit triggering its policy); manually `docker start`ed it. Sentinel had **already** reconfigured it as a replica of the new primary the moment it reappeared (`redis-cli replicaof ...` returned `Already connected to specified master`) — full self-healing, no manual `REPLICAOF` actually needed. Final state confirmed via `sentinel replicas diep-master`: exactly one replica, `172.18.0.240` (the original primary, now demoted) — correct 1-primary-1-replica-3-sentinel topology restored.

**Scope note:** the original primary's static compose `command:` has no `--replicaof` baked in — if it's ever recreated (not just restarted) from the compose file, it would come back as a standalone node, relying on Sentinel to redemote it again (which it has just been shown to do automatically). Persisting role assignment across a full container *recreation* (not just restart) wasn't part of what was asked and would need `CONFIG REWRITE`-based persistence or an entrypoint script querying Sentinel at boot — noted for awareness, not implemented.

**Result: both MW1 work-streams executed and verified live. MW1 is complete.** Per the tracker's own Maintenance Window table, a 48-hour soak is the stated prerequisite before MW2 (K6 MinIO HA) can begin — that clock starts now, not before.

## 12. INCIDENT during soak — MW1 PITR WAL Staging Leak (2026-06-18)

**This supersedes §11's "MW1 is complete" as of the soak period: MW1 was found defective and the soak was invalidated.**

- **Incident:** the K1 wal-shipper (§11a) mirrored WAL to MinIO but never pruned the local staging copies — contrary to `K1_PITR_IMPLEMENTATION_PLAN.md` §3.1. At `archive_timeout=60` (~1 GB/hr) the `wal-archive` volume grew to 4.8 GB / 309 segments and filled the 48 GB root disk. PostgreSQL crash-looped (`No space left on device`, 26 restarts); FastAPI `/readyz` went `database:false`. Redis/Sentinel unaffected.
- **Why §11 missed it:** the cutover drill was point-in-time; this failure only appears under sustained runtime. The §11a verification confirmed a segment *shipped* but never watched staging-volume growth over hours.
- **Recovery (full detail + evidence in `MW1_OUTAGE_RECOVERY_REPORT.md`):** deleted only the 279 segments positively confirmed in MinIO (preserving 30 unshipped, since shipped); rewrote `ship-wal.sh` to upload→verify(`mc` exit codes)→prune with a 2 GiB staging alarm; restarted PostgreSQL (recovered clean, `RestartCount=0`); FastAPI `/readyz` back to `ready:true`. Validated live with PostgreSQL generating segments: staging now returns to 0 every cycle.
- **Soak:** INVALIDATED and restarted — new 48h window from 2026-06-18 10:25Z, earliest MW2 eligibility **2026-06-20 10:25Z**.

**Corrected status: MW1 functionally complete and recovered, but on a fresh soak — NOT yet soak-passed.**
