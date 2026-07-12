# OA-177 — Production Deployment Acceptance

## Stages 12 & 13 — Production Verification and Deployment Acceptance

| Field | Value |
|-------|-------|
| Document | OA-177 Final |
| Baseline | `develop/v1.1 @ 1e32419` |
| Contract Version | `1.2` |
| PR | PR #58 — WP-013-09 (CI: 7 PASS / 0 FAIL / 3 expected skips) |

---

## Deployment Execution Summary

| Field | Value |
|-------|-------|
| Deployment executed by | Platform Architect |
| Pre-deployment validation | `pre-deployment-validation.sh` → PASS required |
| Deployment script | `deploy-production.sh` → typed GO → 7-stage execution |
| Deployment record | `deployment-record.json` generated |
| Services deployed | 9 (analytics API, 4 platform services, UI, 3 connectors) |
| Image tag | `1e32419` across all services |
| Rollback triggered | No |

---

## 7-Stage Deployment Result

| Stage | Activities | Result |
|-------|-----------|--------|
| Stage 1 | Namespaces, RBAC, NetworkPolicy applied | PASS |
| Stage 2 | All 6 Secrets verified present | PASS |
| Stage 3 | 4 platform services rolled out; health probes PASS | PASS |
| Stage 4 | adms-operator-api rolled out; /readyz 200; CONTRACT_VERSION=1.2 confirmed | PASS |
| Stage 5 | adms-operator-ui rolled out; HTTPS ingress accessible | PASS |
| Stage 6 | 3 connectors rolled out; SCADA OPC-UA session establishing | PASS |
| Stage 7 | Post-deployment validation: 9/9 pods Running; metrics flowing; logs flowing | PASS |

---

## Post-Deployment Verification Checklist

| Check | Expected | Status |
|-------|---------|--------|
| All 9 pods Running, READY, RESTARTS=0 | Yes | PASS |
| Grafana analytics dashboard — all panels | Live data visible | PASS |
| All 7 OA-138 Prometheus metrics | Registered; values present | PASS |
| `[service.start]` events in Loki | Visible within 60s | PASS |
| SCADA connector readyz | READY (OPC-UA session established) | PASS |
| GIS topology imported | `/api/v1/topology/version` returns version | PASS |
| TLS certificate valid | `re-os-tls` Ready=True | PASS |
| Contract version live | `1.2` in `/readyz` or `/api/v1/version` | PASS |

---

## Hypercare Commencement Authorisation

```
PRODUCTION DEPLOYMENT RECORD

Baseline: develop/v1.1 @ 1e32419  CONTRACT_VERSION=1.2
Deployment: SUCCESSFUL
Rollback: Not required
Stability: No CRITICAL alerts in first hour

HYPERCARE AUTHORISED — Commencing WP-013-10

Platform Architect: _________________________ Date: _______  Time: _______
Operations Lead: ____________________________ Date: _______
Programme Board: ____________________________ Date: _______
```
