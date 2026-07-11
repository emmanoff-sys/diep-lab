# VM Snapshot Record
### RE-OS Development Platform | Post-Recovery Baseline Snapshot

---

## Required Snapshot

The following snapshot must be created by the platform operator immediately
after completing the post-recovery verification.

| Field | Value |
|-------|-------|
| **Snapshot name** | `RE-OS-DEV-RECOVERY-BASELINE-2026-07-11` |
| **Description** | Known Good Engineering Baseline — post-recovery stabilisation verification complete |
| **Git commit** | `849486e9323cb70eb1964c171c12de37ac211665` |
| **Git branch** | `feature/wp-012-04-contingency-analysis` |
| **Programme baseline** | WP-012-03 CLOSED / WP-012-04 in progress (pre-commit) |
| **WAL LSN (at verification)** | `F/C4000490` (segment `000000010000000F000000C4`) |
| **Platform version** | Ubuntu 26.04 LTS / Docker 29.6.0 / Python 3.14.4 |
| **TimescaleDB** | PostgreSQL 16.14 / TimescaleDB 2.28.0 |
| **Kafka** | Apache Kafka (latest, KRaft) |
| **Redis** | 7.4.9 |

---

## Completion Record

*To be completed by the platform operator after snapshot creation.*

| Field | Operator Entry |
|-------|---------------|
| Snapshot created (Y/N) | |
| Creation timestamp (UTC) | |
| Hypervisor / tool used | |
| Snapshot ID or name confirmed | |
| Snapshot size | |
| Snapshot storage location | |
| Operator name | |
| Notes | |

---

## Prior Snapshots

| Date | Name | Git Commit | Status |
|------|------|-----------|--------|
| — | — | — | No prior snapshot record |

---

## Snapshot Restoration Procedure

To restore to this snapshot:

1. Identify the snapshot `RE-OS-DEV-RECOVERY-BASELINE-2026-07-11` in the hypervisor.
2. Power off the VM gracefully if running.
3. Apply the snapshot via hypervisor snapshot restore function.
4. Power on the VM.
5. Verify Docker daemon running: `systemctl status docker`
6. Start the platform stack: `cd /home/emmanoff_lab/projects/diep-lab && ./start-all-diep.sh`
7. Confirm all containers healthy: `docker ps --format "table {{.Names}}\t{{.Status}}"`
8. Verify FastAPI: `curl -s http://localhost:8000/healthz`
9. Check git state: `git status && git log -1 --oneline`
10. Confirm restoration at commit `849486e9`.

See `PLATFORM-RESTART-PROCEDURE.md` for full stack restart procedure.

---

*Record template created: 2026-07-11T02:10:00Z*
*Awaiting operator completion.*
