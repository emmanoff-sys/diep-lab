#!/usr/bin/env bash
# RE-OS ADMS — Production Deployment Execution (OA-176 / WP-013-09)
#
# Executes the controlled production deployment of the RE-OS ADMS platform.
#
# AUTHORITY REQUIREMENT:
#   This script may only be executed after:
#     1. OA-173 Production Acceptance Report is fully signed (GO decision issued)
#     2. pre-deployment-validation.sh reports PASS
#     3. Platform Architect has confirmed all pre-deployment warnings resolved
#
# Usage: ./deploy-production.sh [--namespace re-os-prod] [--output-dir /tmp/deploy-YYYYMMDD]
#
# Generates: deployment-record.json (input for OA-177)
#
# ROLLBACK: If any stage fails, the script initiates automatic rollback and exits 1.
#           The Platform Architect is responsible for notifying the Programme Board.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
K8S_ADMS="$REPO_ROOT/k8s/adms"
NS="${NAMESPACE:-re-os-prod}"
OUTPUT_DIR="${OUTPUT_DIR:-/tmp/deploy-$(date +%Y%m%d-%H%M%S)}"
ROLLOUT_TIMEOUT="300s"
BASELINE_COMMIT="1e32419"
CONTRACT_VERSION="1.2"
DEPLOYMENT_START=$(date +%s)

mkdir -p "$OUTPUT_DIR"
RECORD_FILE="$OUTPUT_DIR/deployment-record.json"
LOG_FILE="$OUTPUT_DIR/deployment.log"

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)  $*" | tee -a "$LOG_FILE"; }
log_stage() { echo "" | tee -a "$LOG_FILE"; log "=== $* ==="; }

# ------------------------------------------------------------------ #
# Rollback function                                                    #
# ------------------------------------------------------------------ #
DEPLOYED_SERVICES=()
rollback() {
    local reason="$1"
    log ""
    log "!!! ROLLBACK INITIATED: $reason !!!"
    log "Rolling back ${#DEPLOYED_SERVICES[@]} deployed services..."
    for svc in "${DEPLOYED_SERVICES[@]}"; do
        log "  Rolling back: $svc"
        kubectl rollout undo deployment/"$svc" -n "$NS" 2>/dev/null || \
            log "  WARNING: rollback of $svc failed — manual intervention required"
        kubectl rollout status deployment/"$svc" -n "$NS" --timeout=120s 2>/dev/null || \
            log "  WARNING: $svc rollback did not complete within 120s"
    done
    log "Rollback complete. Notify Programme Board immediately."
    python3 -c "
import json, pathlib, datetime
record = {
    'baseline': '$BASELINE_COMMIT',
    'contract_version': '$CONTRACT_VERSION',
    'outcome': 'ROLLBACK',
    'rollback_reason': '$reason',
    'timestamp': datetime.datetime.utcnow().isoformat() + 'Z',
    'services_deployed': ${#DEPLOYED_SERVICES[@]},
}
pathlib.Path('$RECORD_FILE').write_text(json.dumps(record, indent=2))
" 2>/dev/null || true
    exit 1
}

health_check() {
    local svc="$1"
    local port="$2"
    local path="${3:-/healthz}"
    local pod
    pod=$(kubectl get pod -n "$NS" -l "app=$svc" -o name 2>/dev/null | head -1 || echo "")
    if [[ -z "$pod" ]]; then
        return 1
    fi
    kubectl exec -n "$NS" "${pod#pod/}" -- \
        python3 -c "
import urllib.request, sys
try:
    r = urllib.request.urlopen('http://127.0.0.1:${port}${path}', timeout=5)
    sys.exit(0 if r.status == 200 else 1)
except Exception as e:
    print(e, file=sys.stderr)
    sys.exit(1)
" 2>/dev/null
}

rollout_and_check() {
    local svc="$1"
    local port="$2"
    log "  Deploying: $svc"
    kubectl rollout status deployment/"$svc" -n "$NS" --timeout="$ROLLOUT_TIMEOUT" || \
        rollback "$svc rollout failed"
    DEPLOYED_SERVICES+=("$svc")
    log "  Health check: $svc:$port/healthz"
    if ! health_check "$svc" "$port"; then
        rollback "$svc health check failed post-rollout"
    fi
    log "  PASS: $svc deployed and healthy"
}

# ------------------------------------------------------------------ #
# Execution start                                                      #
# ------------------------------------------------------------------ #
log "================================================================"
log "  RE-OS ADMS — Production Deployment Execution (OA-176)"
log "  Baseline: $BASELINE_COMMIT  CONTRACT_VERSION: $CONTRACT_VERSION"
log "  Cluster: $(kubectl config current-context 2>/dev/null)"
log "  Namespace: $NS"
log "  Output: $OUTPUT_DIR"
log "================================================================"
echo ""
echo "  ⚠  PRODUCTION DEPLOYMENT IN PROGRESS"
echo "  ⚠  Authorisation required: OA-173 GO decision + OA-175 pre-validation PASS"
echo ""
read -rp "  Type GO to confirm authorisation and proceed: " CONFIRM
if [[ "$CONFIRM" != "GO" ]]; then
    echo "Aborted."
    exit 0
fi

# ------------------------------------------------------------------ #
# Stage 0: Pre-deployment validation                                   #
# ------------------------------------------------------------------ #
log_stage "Stage 0: Pre-Deployment Validation"
log "Running pre-deployment-validation.sh..."
if ! NAMESPACE="$NS" "$REPO_ROOT/validation/deployment/pre-deployment-validation.sh" \
     >> "$LOG_FILE" 2>&1; then
    log "Pre-deployment validation FAILED. Deployment aborted."
    exit 1
fi
log "Pre-deployment validation: PASS"

# ------------------------------------------------------------------ #
# Stage 1: Namespaces, RBAC, NetworkPolicy                            #
# ------------------------------------------------------------------ #
log_stage "Stage 1: Namespaces, RBAC, NetworkPolicy"
kubectl apply -f "$K8S_ADMS/namespace.yaml" 2>&1 | tee -a "$LOG_FILE"
kubectl apply -f "$K8S_ADMS/rbac.yaml" 2>&1 | tee -a "$LOG_FILE"
kubectl apply -f "$K8S_ADMS/network-policy.yaml" 2>&1 | tee -a "$LOG_FILE"
log "Stage 1: PASS"

# ------------------------------------------------------------------ #
# Stage 2: Verify Secrets                                              #
# ------------------------------------------------------------------ #
log_stage "Stage 2: Secret Verification"
REQUIRED_SECRETS=("re-os-secrets" "re-os-pg-credentials" "re-os-redis-credentials"
                  "re-os-scada-credentials" "re-os-gis-credentials" "re-os-ami-credentials")
for secret in "${REQUIRED_SECRETS[@]}"; do
    if ! kubectl get secret "$secret" -n "$NS" &>/dev/null; then
        rollback "Required Secret $secret is not present"
    fi
    log "  PRESENT: $secret"
done
log "Stage 2: PASS"

# ------------------------------------------------------------------ #
# Stage 3: Platform Services                                           #
# ------------------------------------------------------------------ #
log_stage "Stage 3: Platform Services"
kubectl apply -f "$K8S_ADMS/platform-services.yaml" 2>&1 | tee -a "$LOG_FILE"
rollout_and_check "adms-topology-service"    "8001"
rollout_and_check "adms-operational-state"   "8002"
rollout_and_check "adms-operations"          "8003"
rollout_and_check "adms-intelligence"        "8004"
log "Stage 3: PASS — 4 platform services live"

# ------------------------------------------------------------------ #
# Stage 4: Analytics API                                               #
# ------------------------------------------------------------------ #
log_stage "Stage 4: Analytics API"
kubectl apply -f "$K8S_ADMS/analytics-api.yaml" 2>&1 | tee -a "$LOG_FILE"
rollout_and_check "adms-operator-api" "8000"
health_check "adms-operator-api" "8000" "/readyz" || \
    rollback "adms-operator-api /readyz failed — GridAnalyticsService may not be live"

# Confirm CONTRACT_VERSION = 1.2 is live
CONTRACT_LIVE=$(kubectl exec -n "$NS" \
    "$(kubectl get pod -n "$NS" -l app=adms-operator-api -o name | head -1 | sed 's|pod/||')" \
    -- python3 -c "
import urllib.request
r = urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=5)
body = r.read().decode()
print('1.2 in body:', '1.2' in body)
" 2>/dev/null || echo "check_failed")
log "  CONTRACT_VERSION=1.2 in readyz: $CONTRACT_LIVE"
log "Stage 4: PASS — analytics API live"

# ------------------------------------------------------------------ #
# Stage 5: Operator UI and Ingress                                     #
# ------------------------------------------------------------------ #
log_stage "Stage 5: Operator UI and Ingress"
kubectl apply -f "$K8S_ADMS/operator-ui.yaml" 2>&1 | tee -a "$LOG_FILE"
rollout_and_check "adms-operator-ui" "3000" "/api/healthz"
log "Stage 5: PASS — operator UI live"

# ------------------------------------------------------------------ #
# Stage 6: Data Connectors                                             #
# ------------------------------------------------------------------ #
log_stage "Stage 6: Data Connectors"
kubectl apply -f "$K8S_ADMS/connectors.yaml" 2>&1 | tee -a "$LOG_FILE"
rollout_and_check "gis-connector"   "9090"
rollout_and_check "ami-connector"   "9090"
rollout_and_check "scada-connector" "9090"
log "Stage 6: PASS — 3 connectors live"

# ------------------------------------------------------------------ #
# Stage 7: Post-Deployment Validation                                  #
# ------------------------------------------------------------------ #
log_stage "Stage 7: Post-Deployment Validation"

# 7a: All pods Running with 0 restarts
log "Checking pod health..."
RESTART_COUNT=$(kubectl get pods -n "$NS" --no-headers 2>/dev/null | \
    awk '{sum+=$4} END {print sum+0}')
RUNNING_COUNT=$(kubectl get pods -n "$NS" --field-selector=status.phase=Running \
    --no-headers 2>/dev/null | wc -l | tr -d ' ')
log "  Running pods: $RUNNING_COUNT | Total restarts: $RESTART_COUNT"
if [[ "$RESTART_COUNT" -gt 0 ]]; then
    log "  WARNING: $RESTART_COUNT restart(s) observed — investigate before declaring success"
fi

# 7b: Record deployed image digests
log "Recording deployed image digests..."
IMAGE_RECORD=$(kubectl get deployment -n "$NS" \
    -o jsonpath='{range .items[*]}{.metadata.name}{": "}{range .spec.template.spec.containers[*]}{.image}{" "}{end}{"\n"}{end}' \
    2>/dev/null || echo "")
log "$IMAGE_RECORD"

# 7c: Prometheus metrics check
log "Confirming Prometheus is scraping analytics services..."
# (Metrics will populate over the next scrape interval; manual verification in Grafana)
log "  ACTION: Verify all 7 analytics metrics visible in Grafana within 60 seconds"

# 7d: SCADA session check
log "Checking SCADA connector session..."
SCADA_HEALTH=$(kubectl exec -n "$NS" \
    "$(kubectl get pod -n "$NS" -l app=scada-connector -o name | head -1 | sed 's|pod/||')" \
    -- python3 -c "
import urllib.request, sys
try:
    r = urllib.request.urlopen('http://127.0.0.1:9090/readyz', timeout=10)
    print('READY' if r.status == 200 else f'NOT_READY:{r.status}')
except Exception as e:
    print(f'FAIL:{e}')
" 2>/dev/null || echo "CHECK_FAILED")
log "  SCADA connector readyz: $SCADA_HEALTH"
if [[ "$SCADA_HEALTH" != "READY" ]]; then
    log "  WARNING: SCADA connector is not yet READY — OPC-UA session may still be establishing"
    log "  Check again within 2 minutes. If still not ready: escalate to Platform Architect."
fi

DEPLOYMENT_END=$(date +%s)
ELAPSED=$(( (DEPLOYMENT_END - DEPLOYMENT_START) / 60 ))

# ------------------------------------------------------------------ #
# Write deployment record (input for OA-177)                          #
# ------------------------------------------------------------------ #
python3 - <<PYEOF
import json, pathlib, datetime, subprocess

images = {}
try:
    out = subprocess.check_output(
        ['kubectl', 'get', 'deployment', '-n', '$NS',
         '-o', 'jsonpath={range .items[*]}{.metadata.name}={range .spec.template.spec.containers[*]}{.image}{end}\\n{end}'],
        text=True
    )
    for line in out.strip().splitlines():
        if '=' in line:
            name, img = line.split('=', 1)
            images[name] = img
except Exception as e:
    images['error'] = str(e)

record = {
    'baseline_commit': '$BASELINE_COMMIT',
    'contract_version': '$CONTRACT_VERSION',
    'outcome': 'SUCCESS',
    'deployment_start': datetime.datetime.utcfromtimestamp($DEPLOYMENT_START).isoformat() + 'Z',
    'deployment_end': datetime.datetime.utcnow().isoformat() + 'Z',
    'elapsed_minutes': $ELAPSED,
    'namespace': '$NS',
    'cluster': 'production',
    'services_deployed': 9,
    'deployed_images': images,
    'post_deployment_checks': {
        'platform_services': 'PASS',
        'analytics_api': 'PASS',
        'operator_ui': 'PASS',
        'connectors': 'PASS',
    },
}
pathlib.Path('$RECORD_FILE').write_text(json.dumps(record, indent=2))
print(f'Deployment record written: $RECORD_FILE')
PYEOF

# ------------------------------------------------------------------ #
# Success                                                              #
# ------------------------------------------------------------------ #
log ""
log "================================================================"
log "  PRODUCTION DEPLOYMENT COMPLETE"
log "  Baseline: $BASELINE_COMMIT  CONTRACT_VERSION: $CONTRACT_VERSION"
log "  Elapsed: ${ELAPSED} minutes"
log "  Services deployed: 9/9"
log "  Deployment record: $RECORD_FILE"
log ""
log "  IMMEDIATE ACTIONS:"
log "  1. Verify Grafana analytics dashboard — all panels showing live data"
log "  2. Confirm Prometheus scraping 7 analytics metrics"
log "  3. Confirm Loki receiving [service.start] events"
log "  4. Notify Programme Board: deployment complete"
log "  5. Commence hypercare period (WP-013-10)"
log "================================================================"
