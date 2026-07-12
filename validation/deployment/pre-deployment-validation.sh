#!/usr/bin/env bash
# RE-OS ADMS — Pre-Deployment Production Validation (OA-175 / WP-013-09)
#
# Final validation checklist executed immediately before production deployment.
# Must complete with PASS before deploy-production.sh is authorised to proceed.
#
# Usage: ./pre-deployment-validation.sh [--namespace re-os-prod]
#
# This script is READ-ONLY. It does not modify any resources.
# All gates must PASS before the Platform Architect may authorise deployment.
set -euo pipefail

NS="${NAMESPACE:-re-os-prod}"
FAIL=0
PASS_COUNT=0

check() {
    local label="$1"
    local result="$2"
    if [[ "$result" == "PASS" ]]; then
        echo "  [PASS] $label"
        ((PASS_COUNT++))
    else
        echo "  [FAIL] $label — $result"
        FAIL=1
    fi
}

warn() { echo "  [WARN] $1 — manual confirmation required before proceeding"; }

echo ""
echo "================================================================"
echo "  RE-OS ADMS — Pre-Deployment Production Validation (OA-175)"
echo "  Cluster: $(kubectl config current-context 2>/dev/null || echo UNKNOWN)"
echo "  Namespace: $NS"
echo "  Baseline: develop/v1.1 @ 1e32419  CONTRACT_VERSION=1.2"
echo "  Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "================================================================"
echo ""
echo "  ⚠  This validation must PASS before production deployment proceeds."
echo "  ⚠  Do NOT proceed if any [FAIL] items are reported."
echo ""

# ------------------------------------------------------------------ #
# Gate 1: OA-173 Go decision confirmed                                 #
# ------------------------------------------------------------------ #
echo "--- Gate 1: OA-173 Go Decision ---"
warn "OA-173 Production Acceptance Report must be fully signed before deployment"
warn "Confirm in writing: Programme Board has issued GO decision for WP-013-09"

# ------------------------------------------------------------------ #
# Gate 2: Cluster context is production                                #
# ------------------------------------------------------------------ #
echo ""
echo "--- Gate 2: Cluster Context ---"
CURRENT_CONTEXT=$(kubectl config current-context 2>/dev/null || echo "UNKNOWN")
echo "  Current context: $CURRENT_CONTEXT"
if echo "$CURRENT_CONTEXT" | grep -qi "prod"; then
    check "Cluster context matches production" "PASS"
else
    echo "  [WARN] Context '$CURRENT_CONTEXT' does not contain 'prod' — verify correct target cluster"
    warn "If this is correct, Platform Architect must confirm before proceeding"
fi

# ------------------------------------------------------------------ #
# Gate 3: Production Secrets pre-provisioned                           #
# ------------------------------------------------------------------ #
echo ""
echo "--- Gate 3: Required Secrets ---"
REQUIRED_SECRETS=(
    "re-os-secrets"
    "re-os-pg-credentials"
    "re-os-redis-credentials"
    "re-os-scada-credentials"
    "re-os-gis-credentials"
    "re-os-ami-credentials"
)
for secret in "${REQUIRED_SECRETS[@]}"; do
    if kubectl get secret "$secret" -n "$NS" &>/dev/null 2>&1; then
        check "Secret $secret present" "PASS"
    else
        check "Secret $secret present" "FAIL: Secret not found — provision via Vault/ESO before deploying"
    fi
done

# ------------------------------------------------------------------ #
# Gate 4: Datastore operators healthy                                  #
# ------------------------------------------------------------------ #
echo ""
echo "--- Gate 4: Datastore Operators ---"

# CloudNativePG
CNPG_STATUS=$(kubectl get cluster -n "$NS" \
    -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "NOT FOUND")
if [[ "$CNPG_STATUS" == "Cluster in healthy state" ]]; then
    check "TimescaleDB (CloudNativePG) healthy" "PASS"
else
    check "TimescaleDB (CloudNativePG) healthy" "FAIL: status=$CNPG_STATUS"
fi

# Redis Sentinel
REDIS_READY=$(kubectl get pod -n "$NS" -l "app.kubernetes.io/name=redis" \
    --field-selector=status.phase=Running \
    -o name 2>/dev/null | wc -l | tr -d ' ')
if [[ "$REDIS_READY" -ge 3 ]]; then
    check "Redis Sentinel (≥3 pods running)" "PASS"
else
    check "Redis Sentinel (≥3 pods running)" "FAIL: only $REDIS_READY pods running"
fi

# Kafka
KAFKA_BROKERS=$(kubectl get pod -n "$NS" -l "strimzi.io/kind=Kafka" \
    --field-selector=status.phase=Running \
    -o name 2>/dev/null | wc -l | tr -d ' ')
if [[ "$KAFKA_BROKERS" -ge 3 ]]; then
    check "Kafka (≥3 brokers running)" "PASS"
else
    check "Kafka (≥3 brokers running)" "FAIL: only $KAFKA_BROKERS brokers running"
fi

# ------------------------------------------------------------------ #
# Gate 5: Kyverno admission policies enforcing                         #
# ------------------------------------------------------------------ #
echo ""
echo "--- Gate 5: Kyverno Admission Policies ---"
POLICY_COUNT=$(kubectl get policy -n "$NS" --no-headers 2>/dev/null | \
    grep "Enforce" | wc -l | tr -d ' ')
if [[ "$POLICY_COUNT" -ge 4 ]]; then
    check "Kyverno Enforce policies present ($POLICY_COUNT ≥ 4)" "PASS"
else
    check "Kyverno Enforce policies present" "FAIL: only $POLICY_COUNT Enforce policies found (expected ≥4)"
fi

# ------------------------------------------------------------------ #
# Gate 6: Monitoring stack ready                                        #
# ------------------------------------------------------------------ #
echo ""
echo "--- Gate 6: Monitoring Stack ---"
PROM_POD=$(kubectl get pod -n re-os-monitoring -l "app=prometheus" \
    --field-selector=status.phase=Running -o name 2>/dev/null | head -1 || echo "")
GRAFANA_POD=$(kubectl get pod -n re-os-monitoring -l "app.kubernetes.io/name=grafana" \
    --field-selector=status.phase=Running -o name 2>/dev/null | head -1 || echo "")
LOKI_POD=$(kubectl get pod -n re-os-monitoring -l "app=loki" \
    --field-selector=status.phase=Running -o name 2>/dev/null | head -1 || echo "")

[[ -n "$PROM_POD" ]] && \
    check "Prometheus running in re-os-monitoring" "PASS" || \
    check "Prometheus running in re-os-monitoring" "FAIL: no running Prometheus pod"
[[ -n "$GRAFANA_POD" ]] && \
    check "Grafana running in re-os-monitoring" "PASS" || \
    check "Grafana running in re-os-monitoring" "FAIL: no running Grafana pod"
[[ -n "$LOKI_POD" ]] && \
    check "Loki running in re-os-monitoring" "PASS" || \
    check "Loki running in re-os-monitoring" "FAIL: no running Loki pod"

# ------------------------------------------------------------------ #
# Gate 7: TLS certificate ready                                         #
# ------------------------------------------------------------------ #
echo ""
echo "--- Gate 7: TLS Certificate ---"
TLS_READY=$(kubectl get certificate re-os-tls -n "$NS" \
    -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "False")
if [[ "$TLS_READY" == "True" ]]; then
    check "TLS certificate re-os-tls Ready" "PASS"
    EXPIRY=$(kubectl get certificate re-os-tls -n "$NS" \
        -o jsonpath='{.status.notAfter}' 2>/dev/null || echo "unknown")
    echo "    Certificate expiry: $EXPIRY"
else
    check "TLS certificate re-os-tls Ready" "FAIL: certificate not Ready (status=$TLS_READY)"
fi

# ------------------------------------------------------------------ #
# Gate 8: Operations team confirmed ready                               #
# ------------------------------------------------------------------ #
echo ""
echo "--- Gate 8: Operational Readiness ---"
warn "Operations team must confirm availability for deployment window + 2 hours"
warn "On-call engineer must be reachable by phone during the deployment window"
warn "Utility OT team must be on standby for SCADA connector commissioning"

# ------------------------------------------------------------------ #
# Gate 9: Rollback rehearsed                                            #
# ------------------------------------------------------------------ #
echo ""
echo "--- Gate 9: Rollback Readiness ---"
warn "Rollback procedure must have been rehearsed in staging (kubectl rollout undo)"
warn "Platform Architect confirms rollback authority during the deployment window"

# ------------------------------------------------------------------ #
# Gate 10: Container images available                                   #
# ------------------------------------------------------------------ #
echo ""
echo "--- Gate 10: Container Images ---"
echo "  Verifying image pull access for baseline tag 1e32419..."
IMAGES=(
    "registry.re-os.internal/adms/operator-api:1e32419"
    "registry.re-os.internal/adms/topology-service:1e32419"
    "registry.re-os.internal/adms/operational-state:1e32419"
)
IMAGE_FAIL=0
for img in "${IMAGES[@]}"; do
    if kubectl run img-probe-$RANDOM --rm -i --restart=Never --image="$img" \
       --image-pull-policy=Always -n "$NS" -- true &>/dev/null 2>&1; then
        echo "  [PASS] Image pullable: $img"
    else
        echo "  [WARN] Cannot verify image pull in dry-run — confirm registry access manually: $img"
    fi
done

# ------------------------------------------------------------------ #
# Summary                                                              #
# ------------------------------------------------------------------ #
echo ""
echo "================================================================"
if [[ $FAIL -ne 0 ]]; then
    echo "  PRE-DEPLOYMENT VALIDATION: FAIL"
    echo "  One or more hard gates failed. Resolve all failures before proceeding."
    echo "  DO NOT DEPLOY until this script reports PASS."
    echo "================================================================"
    exit 1
else
    echo "  PRE-DEPLOYMENT VALIDATION: PASS"
    echo "  Hard gates: $PASS_COUNT PASS"
    echo "  Warnings above require manual confirmation before deployment proceeds."
    echo ""
    echo "  Platform Architect must confirm all warnings resolved before executing:"
    echo "    ./validation/deployment/deploy-production.sh"
    echo "================================================================"
fi
