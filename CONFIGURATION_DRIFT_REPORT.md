# DIEP v1.0 — Configuration Drift Report

**Date:** 2026-06-26
**Scope:** Phase 2 (source consistency classification) + Phase 5 (configuration
drift audit) of the Configuration & Deployment Audit. Every claim below was
checked against the live system (file diffs against both checkouts, live
Prometheus/API queries, live crontab) — none are assumed from prior reports.

---

## Part 1 — Source consistency classification (Phase 2)

**Category A — running from the Release 1.0 worktree (correct):**
`diep-cim`, `diep-fastapi`, `diep-ingestor`, `diep-mdm`, `diep-node-exporter`,
`diep-opcua-connector`. (6 services)

**Category B — running from the main checkout, content identical or
functionally inert difference:**
`diep-alertmanager`, `diep-caddy`, `diep-cadvisor`, `diep-dispatcher`,
`diep-ev-charger`, `diep-influxdb`, `diep-kafka`, `diep-kafka-exporter`,
`diep-kafka-ui`, `diep-minio`, `diep-mqtt`*, `diep-nodered`,
`diep-oms-detector`, `diep-portal`, `diep-postgres-exporter`,
`diep-redis`, `diep-redis-replica`, `diep-redis-sentinel-1/2/3`,
`diep-timescaledb`. (20 services — listed once each; sentinels counted
individually = 19 distinct compose services, 21 containers)

*`diep-mqtt`'s ACL content is correct only via an uncommitted edit — see
Part 3. Flagged here as B (content), but treated as a governance risk, not
"harmless."

**Category C — running from the main checkout with meaningful differences,
not yet remediated as of the start of this audit:**
`diep-prometheus`, `diep-wal-shipper`, `diep-grafana` (dashboard gap),
`diep-redis-exporter` (orphaned/unreproducible config). Plus, outside the
container model entirely: **the host cron jobs for `backup-db.sh` and
`backup-pg-basebackup.sh`**, which is the most severe finding in this audit
— see Part 2.4.

Do not assume any Category B classification above is permanent — it reflects
content as observed today; both checkouts are live working trees and can
change.

---

## Part 2 — Category C findings, in detail

### 2.1 `diep-prometheus` — 6 alert rules missing, confirmed not loaded live

`prometheus/alerts.yml` differs between checkouts. Confirmed via the live
`GET /api/v1/rules` API (not just file diff) that the running Prometheus has
only 4 rule groups loaded (`diep-ha-cluster-health`, `diep-infra`,
`diep-operational-controls`, `diep-slo`) — **the entire `diep-backup-dr`
group, and 3 rules from `diep-ha-cluster-health`'s sibling groups, do not
exist in the live instance**:

| Missing rule | Severity | What it would have caught |
|---|---|---|
| `BackupStale` | critical | No successful logical backup in >24h |
| `BaseBackupStale` | warning | No successful physical base backup in >8 days |
| `WalArchiveStalled` | critical | wal-shipper stuck/down >5min |
| `RedisReplicationBroken` | critical | Redis master has no connected replica |
| `KafkaUnderReplicatedPartitions` | warning | Inactive at current RF=1, harmless gap today |
| `DiskCapacityLow` | warning | Filesystem <15% free |

`diep-prometheus` was created 2026-06-23T11:54:43Z (initial stack start) and
has never been recreated since — consistent with it never having had a
chance to pick up `alerts.yml` content added on 2026-06-25 (Phase 22 MON-7),
since that content was committed only to the worktree's branch.

`prometheus.yml` also differs, but **only in comments** — the actual scrape
job list (`redis-exporter`, `diep-mdm`, `diep-opcua-connector`) is identical
between the live (main checkout, with an uncommitted edit — see Part 3) and
worktree versions. No functional gap here.

### 2.2 `diep-wal-shipper` — script and mount missing from main checkout's
current files, yet a fresh metric exists (unexplained anomaly)

Main checkout's `wal-shipper/ship-wal.sh`, as committed on
`feature/adms-topology-import`, has never (per `git log`) contained the
`diep_wal_last_cycle_timestamp_seconds` freshness-metric write — confirmed
absent in the current file via direct grep. Main checkout's current,
committed `docker-compose.yml` also does not define the `textfile_collector`
bind mount for this service at all.

Yet the live `diep-wal-shipper` container (created 2026-06-25T11:46:06Z)
**does** have that bind mount (confirmed via `docker inspect`), and a fresh
metric file (`diep_wal_shipper.prom`, updated within the last ~15s at time
of inspection) exists in the directory it's mounted to. This is internally
inconsistent with the on-disk script content and is not explained by this
audit's evidence — container-internal state was not inspected (`docker exec`
was not used; that boundary is intentional, see `DEPLOYMENT_INVENTORY.md`'s
Known Limitation). The most likely explanation, consistent with 3 other
confirmed instances in this same audit, is a since-discarded uncommitted
edit to `wal-shipper/ship-wal.sh` and `docker-compose.yml` in the main
checkout at container-creation time. Regardless of mechanism, this container
is **not reproducible** from any file currently on disk in either checkout —
recreating it from the worktree (Phase 4) resolves this unambiguously and
is the recommended fix independent of root cause.

### 2.3 `diep-grafana` — missing AMI/MDM pipeline dashboard

`grafana/provisioning/dashboards/ami-mdm-pipeline.json` exists only in the
worktree. Live confirmation via Grafana's own API was not performed — the
rotated admin credential was not extracted for this check, consistent with
this engagement's standing boundary against credential extraction. File-level
evidence (the dashboard file is simply absent from the directory Grafana's
container has mounted) is sufficient to confirm the gap: Grafana cannot
provision a dashboard from a file that isn't there.

### 2.4 Backup monitoring (`backup-db.sh` / `backup-pg-basebackup.sh`) — the
most severe finding, and a correction to this engagement's own prior evidence

**This is not a container bind-mount issue.** The real, scheduled backup
jobs run via the `emmanoff_lab` user's **host crontab**, confirmed live:

```
0 2 * * *  cd /home/emmanoff_lab/projects/diep-lab && ... ./scripts/backup-db.sh ...
30 2 * * * cd /home/emmanoff_lab/projects/diep-lab && ... ./scripts/backup-config.sh ...
0 3 * * 0  cd /home/emmanoff_lab/projects/diep-lab && ... ./scripts/verify-backup.sh ...
0 4 * * 0  cd /home/emmanoff_lab/projects/diep-lab && ... ./scripts/backup-pg-basebackup.sh ...
```

Every entry `cd`s into the **main checkout**, unconditionally. There is no
cron entry anywhere that touches the worktree.

Confirmed: main checkout's `scripts/backup-db.sh` (79 lines) and
`scripts/backup-pg-basebackup.sh` (63 lines) are **both missing** their
Phase 22 MON-5 freshness-metric-write blocks (present in the worktree's
90-line and 72-line versions respectively). `backup-config.sh`,
`verify-backup.sh`, and `lib-backup-alert.sh` (the failure-alert helper) are
identical between checkouts — so the **failure-path** alert
(`alert_backup_failure`, fired via an EXIT trap on non-zero exit) does work
correctly for real, cron-scheduled runs. The **success-path freshness
metric** does not, and never has, for any cron-scheduled run.

**This corrects `validation/evidence/rc2_backup_monitoring_correction.txt`
from the prior session**, which is accurate as far as it goes (the
worktree's script genuinely has the code, and the original qualification's
"never wired up" finding was indeed a wrong-checkout artifact) but did not
check which checkout the *actual scheduled* backup runs from, and so
overstated the conclusion. The evidence trail, reconstructed from file
timestamps during this audit:

1. The `diep_last_backup_timestamp_seconds` metric currently visible in live
   Prometheus (queried during this audit: ~2,198s / 36.6min old) traces to
   epoch `1782471979` = **2026-06-26T11:06:19Z** — which matches the prior
   session's *manual* test run (`diep_20260626T110607Z.dump`), executed by
   hand from the worktree, not a cron run.
2. The night's actual 2026-06-25T02:00 UTC and any future cron-scheduled
   `backup-db.sh` runs execute in main checkout, which does not write this
   metric at all. The metric in the worktree's `textfile_collector` (the one
   `node-exporter` actually reads, since its bind mount was corrected last
   session) will therefore **never update again** from a real backup — it
   is frozen at the moment of that one manual test, and will read as
   increasingly stale until someone manually re-runs the script from the
   worktree again.
3. Separately, even if the metric did update, `BackupStale` is not a rule
   Prometheus has loaded at all (§2.1) — so this gap is currently
   **doubly silent**: the metric won't move, and nothing is watching it
   even if it did.
4. A third, orphaned data point exists in main checkout's own
   `prometheus/textfile_collector/diep_backup_db.prom` (epoch `1782388165` =
   2026-06-25T11:49:25Z) — neither a cron run (wrong time-of-day for the
   02:00 schedule) nor explained by main checkout's current script (which
   lacks the write code). This is consistent with the same pattern as §2.2's
   wal-shipper anomaly: an uncommitted, since-discarded edit was apparently
   live in main checkout at that moment. This file is now inert (node-exporter
   no longer reads from this checkout's `textfile_collector`) but could
   mislead a future operator who checks main checkout directly without
   knowing about the node-exporter mount correction.

**Why this isn't fixed in this audit's Phase 4:** Phase 4 is scoped to
container recreation. There is no container to recreate here — the fix
requires either changing a production cron schedule (a "modify shared
infrastructure" action, same class as prior actions this engagement that
required explicit authorization before proceeding) or changing which
checkout's branch content the main checkout's tracked files reflect (a git
branch-topology decision, squarely Phase 7's question, not Phase 4's). This
is carried into the Phase 7 recommendation as the most consequential open
item.

### 2.5 `diep-redis-exporter` — orphaned configuration

Already covered in `DEPLOYMENT_INVENTORY.md`. Functionally correct today
(env vars match the worktree's intended definition exactly), but main
checkout's current, committed `docker-compose.yml` does not define this
service at all — so this container's configuration cannot be regenerated
from any file on disk anywhere. Same remediation as wal-shipper/prometheus:
recreate from the worktree (Phase 4), which makes it match a real,
committed source.

---

## Part 3 — Uncommitted live edits in the main checkout

Three files are modified in the main checkout's working tree, none
committed to any branch reachable from that checkout:

| File | Live container | Content vs. worktree's committed version | Functional risk today |
|---|---|---|---|
| `mosquitto/config/acl` | diep-mqtt | **Identical** | None today. Silently lost on any `git checkout --`/reset of this working tree — the MDM→ingestor "trusted" topic write grant has no committed home on this checkout's branch. |
| `prometheus/prometheus.yml` | diep-prometheus | Functionally identical (comment text differs only) | None today, same reset risk as above. |
| `nodered/.config.users.json` | diep-nodered | Editor UI tour/sidebar state | None — not functional config. |

Both of the first two are safe today **only** because their content
happens to also be committed on the worktree's branch — a coincidence of
this engagement's history, not a durable guarantee. Anyone treating the
main checkout as the source of truth (which its branch name and the
crontab both imply it is) would not find this content anywhere if they
went looking in git history.

---

## Part 4 — Other configuration-drift checks (Phase 5, remaining items)

- **Environment variables / secrets:** `.env` (gitignored, never committed)
  was already reconciled with the live TimescaleDB password in the prior
  session (`DB_PASSWORD` updated to match the running container). No new
  drift found this audit. Carried-forward, still-open items from
  `GO_LIVE_CHECKLIST.md` P2 (dead `docker-compose-timescale.yml`'s
  hardcoded weak password, `DIEP_ADMIN_USER` literal default) are unrelated
  to deployment-source integrity and out of this audit's scope.
- **Redis Sentinel configuration:** `redis-sentinel/sentinel.conf.template`
  and `sentinel-entrypoint.sh` are byte-identical between checkouts for all
  3 sentinel instances. No drift.
- **Grafana dashboards/provisioning:** covered in §2.3. All non-dashboard
  provisioning (datasources, alerting) confirmed identical.
- **MQTT ACLs:** covered in Part 3.
- **WAL shipper:** covered in §2.2.
- **Backup scripts:** covered in §2.4.
