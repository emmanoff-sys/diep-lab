# K4 — Redis High Availability via Redis Sentinel
## Implementation Plan

**Phase:** 17, Stage 2 (K4)
**Status:** Design + side-by-side validation (no production changes yet)
**Author:** Senior Platform Architect (DIEP)
**Date:** 2026-06-15

---

## 1. Objective

Eliminate the single-node Redis SPOF (`diep-redis`) by introducing a
primary + replica + 3-Sentinel topology, validated end-to-end in an isolated
side-by-side stack before any production change. This is Stage 2 (K4) of the
Phase 17 HA roadmap (`PHASE17_IMPLEMENTATION_PLAN.md`), building on the
primary+replica pattern already proven in `docker-compose-ha.yml`
(`diep-redis-replica`) and porting toward the drafted `k8s/redis.yaml`.

---

## 2. Current State Assessment

| Item | Current value | Source |
|---|---|---|
| Topology | Single instance, `diep-redis` (`redis:7-alpine`), container port 6379, host port 6379 | `docker-compose.yml` |
| Persistence | `--appendonly yes` (AOF) | `docker-compose.yml` |
| Auth | `requirepass` set from `${REDIS_PASSWORD}` | `docker-compose.yml`, `.env` |
| Replicas | None | — |
| Sentinel | None | — |
| Clients | `fastapi/app.py` (`REDIS = redis.Redis(host="diep-redis", port=6379, password=...)`), `fastapi/auth.py` (`_REDIS`, rate limiting), `copilot/cache/redis_cache.py` (response cache) — all use a **static host:port**, no Sentinel awareness | grep of `fastapi/`, `copilot/` |
| Used for | Digital-twin state mirror (`hset`/`hgetall`, 24h TTL), command-status mirror, auth rate limiting, Copilot response cache | `fastapi/app.py`, `fastapi/auth.py`, `copilot/cache/redis_cache.py` |
| k8s target (drafted, unused) | `k8s/redis.yaml` — Bitnami chart values: `architecture: replication`, 1 primary + 2 replicas, `sentinel.enabled: true`, `quorum: 2`, auth via `existingSecret` | `k8s/redis.yaml` |
| RTO today | Manual: detect failure → restart `diep-redis` container (same volume) → reconnect. Typically 5-30s depending on detection, **no automatic failover** | derived |
| RPO (cache data) | N/A — Redis here is a cache/mirror, not source of truth (Postgres/Influx are authoritative); acceptable to lose on restart, but losing it forces cache-miss storms and resets in-flight rate-limit counters | `fastapi/app.py` comment: "Redis is a cache mirror, not the source of truth" |

**Key finding:** Redis is **not** the system of record (Postgres/Timescale
and InfluxDB are), so the HA goal for K4 is *availability* (no SPOF, fast
automatic failover) rather than durability — AOF persistence is retained on
both primary and replica for warm-restart cache preservation, but the
correctness of the system never depends on Redis surviving a crash.

---

## 3. Target Design

### 3.1 Topology

```
┌──────────────────────────────────────────────────────────────────────┐
│                         diep-lab_diep-net                              │
│                                                                          │
│   ┌────────────┐  async repl   ┌────────────┐                          │
│   │ redis-      │ ────────────▶ │ redis-      │                         │
│   │ primary     │                │ replica     │                         │
│   │ (AOF on)    │                │ (AOF on,    │                         │
│   │ requirepass │                │  read-only) │                         │
│   └─────┬──────┘                └─────┬──────┘                         │
│         │  monitor/ping                │  monitor/ping                  │
│   ┌─────┴─────┬──────────────┬────────┴─────┐                          │
│   │ sentinel-1 │  sentinel-2  │  sentinel-3   │  quorum=2               │
│   └────────────┴──────────────┴───────────────┘                        │
│         ▲                                                               │
│         │ sentinel-aware client (redis.sentinel.Sentinel)              │
│   ┌─────┴──────┐                                                        │
│   │  fastapi /  │                                                       │
│   │  auth /     │                                                       │
│   │  copilot     │                                                      │
│   └─────────────┘                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

- **Primary** (`redis-primary`): `redis:7-alpine`, `--requirepass`,
  `--masterauth` (so it can re-sync from a promoted primary after its own
  failback), `--appendonly yes`.
- **Replica** (`redis-replica`): same image, `--replicaof <primary> 6379`,
  `--replica-read-only yes`, same `requirepass`/`masterauth`, `--appendonly
  yes` (so the replica can serve as a warm cache immediately upon
  promotion).
- **3x Sentinel** (`sentinel-1/2/3`): `redis:7-alpine` running
  `redis-sentinel`, each monitoring the primary with
  `sentinel auth-pass <name> <password>`, `quorum 2`,
  `down-after-milliseconds 5000`, `failover-timeout 10000`,
  `parallel-syncs 1`. Odd count (3) so a 2-of-3 quorum tolerates the loss of
  any single Sentinel without losing failover capability.
- **Clients**: switch from `redis.Redis(host="diep-redis", port=6379, ...)`
  to `redis.sentinel.Sentinel([(s1,26379),(s2,26379),(s3,26379)],
  sentinel_kwargs={"password": ...}).master_for("diep-master",
  password=..., decode_responses=True)` — `master_for()` returns a
  connection object that re-resolves the current primary on every command
  via Sentinel, so failover is transparent to callers.

### 3.2 Configuration Changes (target, applied to validation first)

| Setting | Current (`diep-redis`) | Target | Rationale |
|---|---|---|---|
| Topology | 1 node | 1 primary + 1 replica + 3 sentinels | remove SPOF |
| `requirepass` | set | set (same mechanism, new password for prod rollout via secret) | preserve auth |
| `masterauth` | n/a | same value as `requirepass` | replica/sentinel auth to primary |
| `appendonly` | `yes` | `yes` on primary **and** replica | cache preserved across failover/restart |
| Sentinel `quorum` | n/a | `2` (of 3) | tolerate 1 Sentinel loss |
| Sentinel `down-after-milliseconds` | n/a | `5000` | detect primary loss within 5s |
| Sentinel `failover-timeout` | n/a | `10000` | bound failover duration |
| Sentinel `parallel-syncs` | n/a | `1` | limit replica resync load during failover |
| Client connection | static `diep-redis:6379` | `redis.sentinel.Sentinel(...).master_for("diep-master")` | automatic reconnection to new primary |

### 3.3 Rollout Mechanics (validated here, applied to production later)

1. Add `redis-replica` (streaming replication from `diep-redis`) — purely
   additive, production primary unaffected.
2. Add 3 `sentinel-*` services monitoring `diep-redis`.
3. Update `fastapi/app.py`, `fastapi/auth.py`,
   `copilot/cache/redis_cache.py` to build their Redis client via
   `redis.sentinel.Sentinel(...)` instead of a static host/port — this is
   the **only** application-level change.
4. Roll FastAPI/Copilot to pick up the new client config (rolling restart,
   no downtime — `docker-compose-ha.yml` already runs 2 FastAPI replicas
   behind `api-gw`).
5. Drill: kill `diep-redis`, confirm Sentinel promotes `diep-redis-replica`
   within the configured `down-after-milliseconds` +
   `failover-timeout` window, confirm clients reconnect without restart.

---

## 4. Implementation Steps (this stage)

1. ✅ Assess current Redis deployment (Section 2).
2. ✅ Design primary/replica/Sentinel topology (Section 3).
3. Build a **side-by-side validation stack**
   (`docker-compose-redis-sentinel-validation.yml`): throwaway
   `redis-val-primary` + `redis-val-replica` + 3 `sentinel-val-*` containers,
   separate named volumes, separate ports, separate throwaway password —
   attached to `diep-lab_diep-net` only so Sentinel containers can resolve
   each other and the primary/replica by container name (production
   `diep-redis` is on the same network but never referenced).
4. Validate the full lifecycle end-to-end (Section 5 / see
   `K4_REDIS_SENTINEL_VALIDATION_REPORT.md`):
   - replica synchronization,
   - Sentinel quorum/discovery,
   - automatic failover on primary failure,
   - client reconnection via `redis.sentinel.Sentinel`,
   - cache preservation across failover,
   - network-interruption and replica-promotion drills.
5. **Only after validation passes**, schedule the production change
   (Section 6) as a follow-up maintenance task — **not executed in this
   stage**.

---

## 5. Validation Plan (side-by-side, isolated from production)

- New containers `diep-redis-val-primary` (port `6390`),
  `diep-redis-val-replica` (port `6391`), `diep-redis-val-sentinel-1/2/3`
  (ports `26390-26392`) — all `redis:7-alpine`, fresh named volumes,
  throwaway password, **completely separate from `diep-redis`**.
- Test sequence:
  1. Start the stack; confirm replica shows `master_link_status:up` and
     Sentinel reports `+slave` / `+sentinel` discovery for all 3 Sentinels.
  2. **Replica synchronization**: write keys to the primary, confirm they
     appear on the replica.
  3. **Sentinel quorum**: query each Sentinel's view of the master and
     confirm `num-other-sentinels: 2`, `quorum: 2`.
  4. **Cache preservation baseline**: seed a set of cache keys (mirroring
     `copilot`/`fastapi` key shapes), record their values.
  5. **Primary failure simulation**: stop `diep-redis-val-primary`. Time
     Sentinel's `+sdown`/`+odown`/`+switch-master` events and the replica's
     promotion to `role:master`.
  6. **Client reconnection**: a `redis.sentinel.Sentinel`-based Python
     client (mirroring the target `master_for()` pattern) continuously
     issues commands across the failover; confirm it transparently starts
     talking to the promoted primary with no process restart.
  7. **Cache preservation check**: confirm the keys seeded in step 4 are
     still present and correct on the promoted primary (former replica).
  8. **Network interruption simulation**: `docker network disconnect` the
     (restarted, now-replica) original primary from `diep-lab_diep-net` to
     simulate a partition; confirm Sentinel/quorum behavior and reconnection
     once the network is restored.
  9. **Replica re-promotion / topology recovery**: bring the original
     primary back as a replica of the newly promoted master, confirm
     `failover-timeout`-bounded stability.
  10. Tear down the entire validation stack and volumes; production
      (`diep-redis`, `REDIS_PASSWORD` auth) is untouched throughout.

Results, including measured failover duration and RTO, are recorded in
`K4_REDIS_SENTINEL_VALIDATION_REPORT.md`.

---

## 6. Production Rollout (deferred — not part of this stage)

Only after `K4_REDIS_SENTINEL_VALIDATION_REPORT.md` shows PASS for all
checks:

1. Add `redis-replica` + 3 `sentinel-*` services to `docker-compose.yml`,
   mirroring the validated config, sharing `${REDIS_PASSWORD}` via
   `masterauth`/`sentinel auth-pass`. `diep-redis` (primary) is unmodified.
2. Update `fastapi/app.py`, `fastapi/auth.py`, and
   `copilot/cache/redis_cache.py` to construct their Redis client via
   `redis.sentinel.Sentinel(...).master_for("diep-master")`, gated by an env
   var (`REDIS_SENTINELS`) so the static-URL path remains available as an
   instant rollback.
3. Rolling-restart FastAPI/Copilot (2 replicas behind `api-gw`, zero
   downtime) to pick up the new client.
4. Run the failover drill (Section 5, steps 5-7) against production off-peak,
   confirming `/readyz` (`redis: true`) recovers within the measured window
   and rate-limit counters survive.
5. Port the validated values into `k8s/redis.yaml` (already drafted with
   matching `quorum: 2`, `architecture: replication`) for the eventual
   cluster cutover.

---

## 7. Rollback Procedure

**Production is not modified in this stage**, so no rollback is required for
the validation work itself. For the deferred production rollout
(Section 6):

| Step | Rollback action |
|---|---|
| App client → Sentinel-aware | Unset `REDIS_SENTINELS` env var (or revert the code change) — clients fall back to the static `diep-redis:6379` connection, which is never removed |
| `redis-replica` service | Remove from `docker-compose.yml`; delete its volume once confirmed unneeded |
| `sentinel-1/2/3` services | Remove from `docker-compose.yml` |
| `REDIS_PASSWORD` / auth | Unchanged throughout — same secret used by primary, replica, and Sentinels |
| Original `diep-redis` | **Never stopped, reconfigured, or replaced** — remains the fallback primary at all times |

Because the existing single-node `diep-redis` is never removed or
reconfigured until after a successful soak period, the system can fall back
to the pre-K4 topology (manual restart, RTO ~5-30s, no auto-failover) at any
point with zero data-loss risk beyond what already exists today (Redis is a
cache, not a source of truth).

---

## 8. RTO / Failover Summary

| | Before (current) | After (K4 target) |
|---|---|---|
| **Failure detection** | Manual / external monitoring only | Automatic, Sentinel `down-after-milliseconds = 5000` |
| **Failover** | None — manual container restart, cache empty on restart | Automatic Sentinel-driven promotion, bounded by `failover-timeout = 10000` |
| **RTO** | ~5-30s (manual restart + reconnect), cache cold | Target: failover + client reconnection within **~5-15s**, cache **warm** (replica retains data) |

Measured values from the validation run are recorded in
`K4_REDIS_SENTINEL_VALIDATION_REPORT.md`.
