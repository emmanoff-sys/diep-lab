# RE-OS ADMS — Production Deployment Record

## OA-177 — Production Deployment Record

| Field | Value |
|-------|-------|
| Document ID | OA-177 |
| Work Package | WP-013-09 — Controlled Production Deployment |
| Authorisation | PAO-038 |
| Baseline | `develop/v1.1 @ 1e32419` |
| Contract Version | `1.2` |
| Status | **TEMPLATE — PENDING GO DECISION AND DEPLOYMENT** |

---

## 1. Deployment Authorisation

| Authorisation | Reference | Status |
|---------------|-----------|--------|
| Engineering baseline | `develop/v1.1 @ 1e32419` | CONFIRMED |
| Contract version | `1.2` | CONFIRMED |
| OA-173 Go decision | Programme Board sign-off | ___ |
| Pre-deployment validation | `pre-deployment-validation.sh` PASS | ___ |
| Deployment script | `deploy-production.sh` executed by Platform Architect | ___ |

---

## 2. Deployment Execution Summary

| Field | Value |
|-------|-------|
| Deployment date | _______________ |
| Window start | _______________ |
| Window end | _______________ |
| Total elapsed | ___ minutes |
| Cluster | production |
| Namespace | re-os-prod |
| Executing engineer | Platform Architect |

---

## 3. Deployed Services

| Service | Image Tag | Image Digest | Replicas | Status |
|---------|-----------|-------------|---------|--------|
| adms-operator-api | `1e32419` | ___ | 3 | ___ |
| adms-topology-service | `1e32419` | ___ | 2 | ___ |
| adms-operational-state | `1e32419` | ___ | 2 | ___ |
| adms-operations | `1e32419` | ___ | 2 | ___ |
| adms-intelligence | `1e32419` | ___ | 2 | ___ |
| adms-operator-ui | `1e32419` | ___ | 2 | ___ |
| scada-connector | `1e32419` | ___ | 1 | ___ |
| gis-connector | `1e32419` | ___ | 1 | ___ |
| ami-connector | `1e32419` | ___ | 1 | ___ |

---

## 4. Deployment Stage Results

| Stage | Description | Result | Time |
|-------|-------------|--------|------|
| Stage 0 | Pre-deployment validation | ___ | ___ |
| Stage 1 | Namespaces, RBAC, NetworkPolicy | ___ | ___ |
| Stage 2 | Secret verification | ___ | ___ |
| Stage 3 | Platform services (4 services) | ___ | ___ |
| Stage 4 | Analytics API | ___ | ___ |
| Stage 5 | Operator UI and Ingress | ___ | ___ |
| Stage 6 | Data connectors (3 services) | ___ | ___ |
| Stage 7 | Post-deployment validation | ___ | ___ |

**Rollback triggered:** [ ] NO (deployment successful)  [ ] YES — Reason: _______________

---

## 5. Post-Deployment Validation Evidence

| Check | Result | Evidence |
|-------|--------|---------|
| All 9 pods Running, READY | ___ | `deployment-record.json` |
| Pod restarts at T+60min | ___ | `kubectl get pods -n re-os-prod` |
| Grafana dashboard panels populated | ___ | Screenshot |
| All 7 OA-138 metrics in Prometheus | ___ | Prometheus query |
| `[service.start]` events in Loki | ___ | LogQL query |
| SCADA connector readyz | ___ | kubectl exec probe |
| GIS topology imported | ___ | `/api/v1/topology/version` |
| TLS certificate valid | ___ | `kubectl get certificate re-os-tls` |

---

## 6. Deployment Record Machine Output

*Paste contents of `$OUTPUT_DIR/deployment-record.json` here:*

```json
{
  "baseline_commit": "1e32419",
  "contract_version": "1.2",
  "outcome": "SUCCESS",
  "deployment_start": "YYYY-MM-DDTHH:MM:SSZ",
  "deployment_end": "YYYY-MM-DDTHH:MM:SSZ",
  "elapsed_minutes": 0,
  "namespace": "re-os-prod",
  "cluster": "production",
  "services_deployed": 9
}
```

---

## 7. Production Deployment Sign-Off

```
PRODUCTION DEPLOYMENT RECORD

Work Package: WP-013-09
Baseline: develop/v1.1 @ 1e32419  CONTRACT_VERSION=1.2
Deployment date: _______________
Outcome: [ ] SUCCESS  [ ] ROLLBACK (reason: _______________)

Post-deployment validation:
  All 9 services Running and healthy:        [ ] CONFIRMED
  Prometheus metrics flowing:                [ ] CONFIRMED
  Structured logs flowing:                   [ ] CONFIRMED
  SCADA connector connected:                 [ ] CONFIRMED
  Grafana dashboard live:                    [ ] CONFIRMED
  No CRITICAL alerts in first 30 minutes:    [ ] CONFIRMED

HYPERCARE COMMENCEMENT:
  Hypercare start time: _______________
  On-call engineer: _____________________

Platform Architect: _________________________ Date: _______  Time: _______
Operations Lead: ____________________________ Date: _______
Programme Board: ____________________________ Date: _______
```

---

## 8. Immediate Post-Go-Live Checklist

Within 15 minutes of deployment completion:

```bash
# 1. Verify all pods Running
kubectl get pods -n re-os-prod

# 2. Confirm health endpoints
for svc_port in adms-operator-api:8000 adms-topology-service:8001 \
  adms-operational-state:8002 adms-operations:8003 adms-intelligence:8004; do
  svc="${svc_port%%:*}"; port="${svc_port##*:}"
  POD=$(kubectl get pod -n re-os-prod -l app=$svc -o name | head -1 | sed 's|pod/||')
  STATUS=$(kubectl exec -n re-os-prod $POD -- \
    python3 -c "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:$port/healthz',timeout=5); print(r.status)")
  echo "$svc: $STATUS"
done

# 3. Verify Prometheus scraping
# Open Grafana → Analytics Platform dashboard
# Confirm all panels show data (not "No data")

# 4. Run a test analytics call
curl -X POST https://api.adms.re-os.internal/api/v1/analytics/estimate \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{}' | python3 -m json.tool | grep '"service"'
# Expected: "StateEstimationService"

# 5. Notify Programme Board — production is live
```

---

## 9. Forward to Hypercare

Upon completion of this record, commence WP-013-10 — Hypercare & Operational Transition.

```
HYPERCARE COMMENCEMENT AUTHORISATION

OA-177 signed by Platform Architect: [ ] YES
All post-go-live checks passed:       [ ] YES
No CRITICAL alerts in first hour:     [ ] YES

Platform Architect authorises hypercare commencement: _______________ Date: _______
```
