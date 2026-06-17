# K4 — Redis Sentinel HA Validation Report

**Phase:** 17, Stage 2 (K4)
**Date:** 2026-06-15
**Environment:** Side-by-side validation stack
(`docker-compose-redis-sentinel-validation.yml`, project
`diep-redis-sentinel-val`), entirely separate containers/volumes/ports from
production.
**Production impact:** **None.** `diep-redis` was never stopped,
reconfigured, or restarted, and was reachable (`PING` → `NOAUTH Authentication
required`, i.e. auth still enforced) throughout and after the test.

---

## 1. Summary

| Check | Result |
|---|---|
| Replica synchronization | ✅ PASS |
| Sentinel quorum / discovery (3 sentinels, quorum 2) | ✅ PASS |
| Automatic failover on primary failure | ✅ PASS |
| Client reconnection (`redis.sentinel.Sentinel`) | ✅ PASS |
| Cache preservation across failover | ✅ PASS |
| Network-interruption failover | ✅ PASS |
| Replica re-promotion / topology recovery | ✅ PASS |
| Auth (`requirepass`) enforced post-failover | ✅ PASS |

**Overall: PASS.** The design in `K4_REDIS_SENTINEL_IMPLEMENTATION_PLAN.md` is
validated end-to-end, with one configuration finding (Section 5) to fold into
the production rollout (Section 6 of the plan).

---

## 2. Test Environment

- `diep-redis-val-primary` / `diep-redis-val-replica` — `redis:7-alpine`,
  fresh volumes, throwaway password `redis-sentinel-validation-only`,
  `--appendonly yes` on both, replica started with `--replicaof
  diep-redis-val-primary 6379 --replica-read-only yes`.
- `diep-redis-val-sentinel-1/2/3` — `redis:7-alpine` running
  `redis-sentinel`, `quorum 2`, `down-after-milliseconds 5000`,
  `failover-timeout 10000`, `parallel-syncs 1`, monitoring `diep-val-master`.
- All 5 containers attached to `diep-lab_diep-net` (same network as
  production `diep-redis`, which was never referenced by name or IP).
- A throwaway `python:3.12-slim` container ran
  `redis-sentinel-validation/scripts/client_reconnect_test.py`, which mirrors
  the target production pattern:
  `Sentinel([...]).master_for("diep-val-master", password=...)`, issuing one
  `SET`/`GET`/`discover_master` cycle per second.

---

## 3. Test Sequence and Results

### 3.1 Replica synchronization — ✅ PASS

- `diep-redis-val-replica` came up with `role:slave`,
  `master_link_status:up`.
- Wrote `copilot:cache:fleet_health`, `status:cmd:1234` (with `EXPIRE 86400`),
  `ratelimit:tenant:acme` on the primary — all three (and the TTL) appeared
  on the replica within 1s.

### 3.2 Sentinel quorum / discovery — ✅ PASS

- Each Sentinel discovered the other 2 (`num-other-sentinels: 2`) and the one
  replica (`num-slaves: 1`), with `quorum: 2` as configured.

### 3.3 Automatic failover on primary failure — ✅ PASS

- Seeded cache keys, started the client probe (steadily hitting
  `172.18.0.26`, the primary).
- `docker kill diep-redis-val-primary` at **15:35:08**.
- Sentinel timeline (from `diep-redis-val-sentinel-1` log):

  ```
  15:35:13.212  +sdown master diep-val-master 172.18.0.26 6379
  15:35:14.340  +odown  master diep-val-master 172.18.0.26 6379 #quorum 3/2
  15:35:14.376  +switch-master diep-val-master 172.18.0.26 6379 -> 172.18.0.27 6379
  ```

  → **down-detection ≈ 5.2s**, **odown → switch-master ≈ 36ms**,
  **total kill → switch-master ≈ 6.4s**.

### 3.4 Client reconnection — ✅ PASS

Client log around the failover:

```
15:35:07  iter=34 OK   master=(172.18.0.26, 6379) val=b'34' dt=0.008s
15:35:13  iter=35 FAIL master=?          err=network:TimeoutError dt=5.008s
15:35:14  iter=36 OK   master=(172.18.0.27, 6379) val=b'36' dt=0.006s
```

- The client's last successful write against the old primary was at
  `15:35:07`; the first against the newly promoted primary
  (`172.18.0.27`) was at `15:35:14` — **client-perceived outage ≈ 6-7s**,
  with **zero process restarts or code changes**: `master_for()` transparently
  re-resolved the new primary via Sentinel.
- From iter=36 onward, every subsequent command targeted `172.18.0.27`.

### 3.5 Cache preservation — ✅ PASS

After promotion, on the new primary (former replica, `172.18.0.27`):

```
MGET copilot:cache:fleet_health status:cmd:1234 ratelimit:tenant:acme client-reconnect-probe
-> {"answer":"ok"}
-> {"state":"ack"}
-> 7
-> 102
```

All pre-failover keys (including the live counter the client was writing)
were present and correct — the replica's `--appendonly yes` data became the
new primary's data with no loss.

### 3.6 Auth enforcement post-failover — ✅ PASS

```
docker exec diep-redis-val-replica redis-cli PING
-> NOAUTH Authentication required.
```

`requirepass` remained enforced on the promoted primary (it was started with
the same `--requirepass`/`--masterauth` as the original).

### 3.7 Replica re-promotion / topology recovery — ✅ PASS

- Restarted the original primary container (`docker start
  diep-redis-val-primary`) at **15:36:44**. It came back up with
  `role:master` (its own static config), i.e. **two masters existed
  transiently**.
- Sentinel detected this and issued `+convert-to-slave` at **15:37:05.798**
  (≈21s after restart, gated by Sentinel's `-sdown`/tilt-exit timing); the
  restarted node then showed `role:slave`, `master_host:172.18.0.27`,
  `master_link_status:up` — full 1-primary/1-replica topology restored
  automatically, **with no manual intervention**.

### 3.8 Network-interruption failover — ✅ PASS

With the topology now primary=`172.18.0.27`, replica=`172.18.0.26`:

- `docker network disconnect diep-lab_diep-net diep-redis-val-replica`
  (the current primary, `172.18.0.27`) at **15:37:57**, simulating a network
  partition (no process killed).
- Sentinel timeline:

  ```
  15:38:03.167  +failover-state-send-slaveof-noone (172.18.0.26)
  15:38:04.119  +promoted-slave 172.18.0.26
  15:38:04.200  +switch-master diep-val-master 172.18.0.27 -> 172.18.0.26
  ```

  → **partition → switch-master ≈ 7.2s**.
- `docker network connect diep-lab_diep-net diep-redis-val-replica`
  reconnected the partitioned node; Sentinel converted it back to a replica
  (`role:slave`, `master_host:172.18.0.26`, `master_link_status:up`) within
  ~1 minute, restoring the full 1-primary/1-replica/3-sentinel topology.
- Cache data (`copilot:cache:fleet_health`, `status:cmd:1234`,
  `ratelimit:tenant:acme`) remained correct on the new primary throughout.

---

## 4. RTO / Failover — Before vs. After

| | Before (current, single `diep-redis`) | After (K4, measured) |
|---|---|---|
| **Failure detection** | None (manual/external monitoring only) | Automatic, **~5.2s** (`down-after-milliseconds=5000`) |
| **Failover** | None — operator restarts `diep-redis` manually | Automatic, **~6.4-7.2s** kill/partition → `+switch-master` (both primary-kill and network-partition drills) |
| **Client reconnection** | Manual — app must reconnect to the same restarted endpoint, cache cold | Automatic via `redis.sentinel.Sentinel`/`master_for()`, **~6-7s** observed outage, **no restart** |
| **Cache state after recovery** | Empty (fresh container, fresh AOF) | **Preserved** — replica's AOF becomes the new primary's data |
| **Topology self-healing** | N/A | Restarted/reconnected node automatically reconfigured as a replica of the current primary (`+convert-to-slave`), ~21-60s |

These figures confirm the design assumptions in
`K4_REDIS_SENTINEL_IMPLEMENTATION_PLAN.md` Section 8 (target RTO ~5-15s).

---

## 5. Issues Found and Resolved

1. **`sentinel resolve-hostnames yes` + Docker container hostnames is
   unreliable across container lifecycle events.** Initial attempt
   configured `sentinel monitor diep-val-master diep-redis-val-primary 6379
   2` with `resolve-hostnames yes`/`announce-hostnames yes`. After
   `docker kill` on the monitored container, Docker's embedded DNS removed
   the container's hostname entry; Sentinel then logged
   `Failed to resolve hostname 'diep-redis-val-primary'` on every cron
   cycle and repeatedly re-entered `+tilt` mode, which **blocked failover
   indefinitely**.

   **Fix**: switched to the Sentinel default (`resolve-hostnames` unset/no)
   and seeded `sentinel monitor` with the **container's IP address**,
   resolved once at first startup (`redis-sentinel-validation/scripts/
   sentinel-entrypoint.sh`). After the initial bootstrap, Sentinel tracks
   the primary/replica purely by the IPs reported in `INFO replication`
   (`slave0:ip=...`), which is unaffected by hostname/DNS lifecycle —
   confirmed by both failover drills completing in ~6-7s.

   **Production implication**: for the `docker-compose.yml`-based
   production deployment, use **IP-based** `sentinel monitor` (resolved at
   deploy time, e.g. via the same entrypoint pattern), or assign **static
   IPs** to `redis`/`redis-replica` via the compose network's `ipam` config
   so the bootstrap IP remains stable across restarts. The drafted
   `k8s/redis.yaml` (Bitnami chart) is unaffected — it uses StatefulSet
   DNS, which the chart's Sentinel templates handle correctly — so this is
   purely a consideration for the interim docker-compose rollout, not the
   eventual k8s cutover.

No data loss occurred from this issue — it was caught and fixed entirely
within the isolated validation stack before any failover drill.

---

## 6. Recommendation

K4 design is **validated and ready for production scheduling**. Proceed with
`K4_REDIS_SENTINEL_IMPLEMENTATION_PLAN.md` Section 6 (Production Rollout),
with the added note from Section 5 above:

> When adding `sentinel monitor` for `diep-redis` in `docker-compose.yml`,
> seed it with `diep-redis`'s resolved IP at deploy time (or pin a static IP
> via the compose network `ipam` block), rather than relying on
> `resolve-hostnames` — this avoids the tilt/resolution-failure loop observed
> in validation if the primary container is ever recreated.

The application-level change (Sentinel-aware client in `fastapi/app.py`,
`fastapi/auth.py`, `copilot/cache/redis_cache.py`) should be gated behind an
env var (`REDIS_SENTINELS`) per the plan, so it can be enabled/rolled back
without a code change.

---

## 7. Cleanup Performed

- Removed containers `diep-redis-val-primary`, `diep-redis-val-replica`,
  `diep-redis-val-sentinel-1/2/3`, `diep-redis-val-client`.
- Removed volumes `diep-redis-sentinel-val_redis-val-primary-data`,
  `diep-redis-sentinel-val_redis-val-replica-data`,
  `diep-redis-sentinel-val_sentinel-val-{1,2,3}-data`.
- Removed throwaway `python:3.12-slim` image pulled for the client probe.
- Production `diep-redis` (container, volume `redis-data`, auth) confirmed
  unchanged: still running, still requires auth (`NOAUTH` on unauthenticated
  `PING`), never stopped or reconfigured.
- `docker-compose-redis-sentinel-validation.yml` and
  `redis-sentinel-validation/scripts/` (sentinel entrypoint, config template,
  client reconnection probe) are retained in the repo as the validated
  reference implementation for the production rollout.
