# RE-OS ADMS — Production Deployment Plan

## OA-174 — Controlled Production Deployment Plan

| Field | Value |
|-------|-------|
| Document ID | OA-174 |
| Work Package | WP-013-09 — Controlled Production Deployment |
| Authorisation | PAO-038 |
| Baseline | `develop/v1.1 @ 1e32419` |
| Contract Version | `1.2` |
| Status | **READY — AWAITING OA-173 GO DECISION** |

---

## 1. Go/No-Go Prerequisites

This deployment plan activates only after the Programme Board issues a formal GO
decision on OA-173 (Production Acceptance Review).

**Required before deployment window opens:**
- [ ] OA-173 Production Acceptance Report fully signed (6 signatories)
- [ ] `validation/acceptance/run-acceptance-tests.sh --env staging` → PASS
- [ ] UAT utility partner sign-off received (OA-152)
- [ ] DR rehearsal completed (OA-160)
- [ ] Runbook walkthrough accepted (OA-168)
- [ ] Pentest completed; all CRITICAL/HIGH findings resolved (OA-163/164)
- [ ] Operations team standing by
- [ ] Rollback procedure confirmed rehearsed
- [ ] Communication plan active

---

## 2. Deployment Architecture

**Target cluster:** Production Kubernetes cluster
**Target namespace:** `re-os-prod`
**Source baseline:** `develop/v1.1 @ 1e32419`
**Image tag:** `1e32419` (pinned digest in all manifests after OA-149 image governance)
**CONTRACT_VERSION:** `1.2`

**Production topology (from OA-144 Infrastructure Specification):**
- 3 replicas: `adms-operator-api` (HPA 3–10)
- 2 replicas each: `adms-topology-service`, `adms-operational-state`, `adms-operations`, `adms-intelligence`, `adms-operator-ui`
- 1 replica each: `scada-connector`, `gis-connector`, `ami-connector`
- Datastores: CloudNativePG (1+2), Redis Sentinel (1+2), Kafka (3 brokers)

---

## 3. Deployment Window

| Field | Value |
|-------|-------|
| Deployment date | TBD — set by Programme Board after GO decision |
| Window start | TBD (recommend 06:00 UTC on a non-Monday weekday) |
| Maximum duration | 4 hours (includes validation; if exceeded, rollback is triggered) |
| Pre-notification to stakeholders | 5 business days before window |
| Operational blackout | No switching operations during deployment window |
| Operations team on-call | Available for full deployment window + 2 hours post |
| Rollback authority | Platform Architect; notifies Programme Board within 30 minutes |

**Rationale for window timing:** Early morning UTC minimises operator impact while
keeping the European-based engineering and operations teams within normal working hours.
Avoid Mondays to reduce weekend backlog collision risk.

---

## 4. Deployment Sequence

The deployment follows dependency order: datastores → platform services → analytics
API → UI → connectors. Each stage has a validation gate before the next stage proceeds.

```
Stage 0: Final pre-deployment validation (OA-175)
         └─ pre-deployment-validation.sh → PASS required to proceed

Stage 1: Namespaces, RBAC, NetworkPolicy (idempotent apply)
         └─ k8s/adms/namespace.yaml
         └─ k8s/adms/rbac.yaml
         └─ k8s/adms/network-policy.yaml
         └─ Gate: namespaces present; policies applied

Stage 2: Secrets (verify pre-provisioned; no apply here)
         └─ Verify all 6 Secrets exist in re-os-prod
         └─ Gate: all Secrets present; none missing

Stage 3: Platform services
         └─ k8s/adms/platform-services.yaml
         └─ Rollout order: topology → operational-state → operations → intelligence
         └─ Gate: all 4 deployments rolled out; health probes 200 OK

Stage 4: Analytics API
         └─ k8s/adms/analytics-api.yaml
         └─ Gate: adms-operator-api rolled out; /healthz + /readyz → 200;
                  CONTRACT_VERSION=1.2 confirmed

Stage 5: Operator UI + Ingress
         └─ k8s/adms/operator-ui.yaml
         └─ Gate: adms-operator-ui rolled out; UI accessible via HTTPS ingress

Stage 6: Data connectors
         └─ k8s/adms/connectors.yaml
         └─ Rollout order: gis-connector → ami-connector → scada-connector
         └─ Gate: all 3 connectors rolled out; health probes 200 OK

Stage 7: Post-deployment validation
         └─ All 9 services Running, READY, RESTARTS=0
         └─ Prometheus scraping analytics metrics
         └─ Structured logs flowing to Loki
         └─ SCADA connector establishing OPC-UA session
         └─ GIS connector topology import confirmed
```

---

## 5. Rollback Criteria

Rollback is triggered automatically by `deploy-production.sh` if any stage gate fails,
or manually by the Platform Architect if post-deployment issues arise.

**Automatic rollback triggers:**
- Any deployment rollout fails to complete within 300 seconds
- Any health probe returns non-200 after rollout
- SCADA connector fails to establish OPC-UA session within 5 minutes of deployment
- Any pod enters CrashLoopBackOff during deployment window

**Manual rollback triggers (Platform Architect decision):**
- Operator reports analytical results are incorrect after go-live
- Any CRITICAL alert fires within 2 hours of go-live
- OT team reports SCADA telemetry is degraded

**Rollback procedure:**
```bash
# Revert all ADMS deployments to previous revision
for deploy in adms-operator-api adms-topology-service adms-operational-state \
              adms-operations adms-intelligence adms-operator-ui \
              scada-connector gis-connector ami-connector; do
  kubectl rollout undo deployment/$deploy -n re-os-prod
  kubectl rollout status deployment/$deploy -n re-os-prod --timeout=300s
done
# Notify Programme Board immediately
# Record in OA-177 deployment record
```

**Rollback decision window:** If any gate fails after Stage 3 and cannot be resolved
within 60 minutes, rollback is initiated. The deployment is considered failed. A
post-incident review occurs before the next deployment attempt.

---

## 6. Communication Plan

| Event | Who to Notify | Method | Timing |
|-------|--------------|--------|--------|
| Deployment window confirmed | All stakeholders | Email | 5 business days before |
| Window opens | Operations team | Slack/call | T-0 |
| Stage 3 complete (platform services live) | Platform Architect | Slack | T+~30 min |
| Stage 4 complete (API live) | Operations Lead | Slack | T+~45 min |
| Stage 6 complete (connectors live) | Operations Lead | Slack | T+~60 min |
| Deployment complete | Programme Board, utility partner | Email | T+~90 min |
| Rollback initiated | Programme Board immediately | Phone call | Immediately |
| Hypercare commenced | All stakeholders | Email | T+~120 min |

---

## 7. Checkpoint Validation Gates

For each stage, the deployment script confirms:

| Stage | Gate Check | Tool |
|-------|-----------|------|
| Stage 0 | OA-175 pre-deployment validation PASS | `pre-deployment-validation.sh` |
| Stage 1 | `kubectl get namespace re-os-prod` → Active | kubectl |
| Stage 2 | `kubectl get secret -n re-os-prod` → all 6 present | kubectl |
| Stage 3 | `kubectl rollout status` × 4 + `/healthz` × 4 | kubectl + health probe |
| Stage 4 | `kubectl rollout status` + `/readyz` → 200 | kubectl + health probe |
| Stage 5 | `kubectl rollout status` + HTTPS ingress → 200 | kubectl + curl |
| Stage 6 | `kubectl rollout status` × 3 + `/healthz` × 3 | kubectl + health probe |
| Stage 7 | Full post-deployment validation: metrics, logs, SCADA | `deploy-production.sh` §6 |
