# Outstanding Issues Register
### RE-OS Development Platform | Post-Recovery Verification
### Date: 2026-07-11

---

## Active Issues

| ID | Severity | Service | Description | Status | Action |
|----|----------|---------|-------------|--------|--------|
| OI-001 | MINOR | Prometheus | No auto-restart policy — requires manual start after graceful stop | OPEN | Add `restart: unless-stopped` to docker-compose.yml |
| OI-002 | MINOR | kafka-exporter | 11 startup restarts due to DNS race with Kafka | OPEN | Add startup delay or `depends_on` healthcheck condition |
| OI-003 | MINOR | Dispatcher | 1 restart at stack startup (cause unconfirmed) | OPEN | Monitor over 24h; investigate if recurs |
| OI-004 | INFORMATIONAL | Prometheus | 3 scrape targets expected-down: cadvisor, diep-mdm, diep-opcua-connector | ACCEPTED | Dev-env gaps; not deployed; no action required |
| OI-005 | INFORMATIONAL | VM Snapshot | Post-recovery snapshot not yet taken | PENDING | Operator action required — see VM Snapshot Record |
| OI-006 | INFORMATIONAL | 24h Observation | Observation period initiated but not yet complete | IN PROGRESS | Complete 4-hourly checks per observation report |

---

## Closed Issues (this event)

| ID | Severity | Service | Description | Resolution |
|----|----------|---------|-------------|-----------|
| OI-C01 | MINOR | Prometheus | Stopped during recovery, not running | Manually restarted 2026-07-11T01:48Z |
| OI-C02 | MINOR | WAL Shipper | Initial MinIO connection refused at 19:48Z | Self-recovered at 22:28Z |

---

## Issue Criteria

| Severity | Definition |
|----------|-----------|
| CRITICAL | Platform inoperable; data loss; security breach |
| MAJOR | Service down with impact on engineering or data integrity |
| MINOR | Service degraded; recoverable; no data loss |
| INFORMATIONAL | No impact; awareness only |

---

*Updated: 2026-07-11T02:10:00Z*
