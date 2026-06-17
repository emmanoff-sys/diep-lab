# DIEP Production Security Checklist
## Phase 18 — Pre-Go-Live Security Validation

**Date:** 2026-06-17  
**Version:** 1.0  
**Classification:** Internal — Security and Operations  
**Scope:** Security validation required before DIEP HA production deployment  
**Input:** `DIEP_PRODUCTION_READINESS_CERTIFICATION.md` Section 6, `PHASE18_PRODUCTION_GAP_ANALYSIS.md` Section 2.1  

Mark each item [x] when verified. The "Verified by" column should be signed off by the operator completing each check. All items in Section 1 (Secrets) and Section 5 (Firewall) are mandatory blockers (SEC-1 and SEC-4 respectively) that must be complete before any maintenance window begins.

---

## 1. Secret Rotation

**Requirement:** SEC-1 and SEC-2. All default secrets must be rotated before production go-live.

**Why:** The `DIEP_FINAL_RELEASE_READINESS_REPORT.md` (2026-06-15) identified these as unrotated defaults from initial platform setup. A deployed system with default credentials is trivially compromised by any party with knowledge of the defaults.

### 1.1 Application Passwords

| # | Secret | Location | Check | Verified by |
|---|---|---|---|---|
| 1.1.1 | `DIEP_ADMIN_PASSWORD` | `.env` | [ ] Rotated from default; value is cryptographically random (≥ 16 chars) | |
| 1.1.2 | `DIEP_OPERATOR_PASSWORD` | `.env` | [ ] Rotated from default; value is cryptographically random | |
| 1.1.3 | `DIEP_VIEWER_PASSWORD` | `.env` | [ ] Rotated from default; value is cryptographically random | |
| 1.1.4 | `DIEP_ACME_PASSWORD` | `.env` | [ ] Rotated from default; value is cryptographically random | |
| 1.1.5 | `DIEP_GLOBEX_PASSWORD` | `.env` | [ ] Rotated from default; value is cryptographically random | |

**Verification command:**
```bash
# Confirm login fails with old default password (replace OLD_DEFAULT with the known default)
curl -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "OLD_DEFAULT"}'
# Expected: 401 Unauthorized
```

### 1.2 Database Credentials

| # | Secret | Location | Check | Verified by |
|---|---|---|---|---|
| 1.2.1 | `DB_PASSWORD` | `.env` | [ ] Rotated from default | |
| 1.2.2 | `POSTGRES_PASSWORD` | `.env` | [ ] Same value as `DB_PASSWORD` (must be in sync) | |

**Verification command:**
```bash
docker exec pg-ha-1 psql -U diep_user -d diep_db \
  -c "SELECT current_user, pg_postmaster_start_time();"
# Should succeed with new credential; confirm app connects via /readyz
```

### 1.3 Kafka SASL Credential

**Requirement:** SEC-2. Credential must be removed from source files and centralized in `.env`.

| # | Check | Verified by |
|---|---|---|
| 1.3.1 | `KAFKA_SASL_USERNAME` added to `.env` | |
| 1.3.2 | `KAFKA_SASL_PASSWORD` added to `.env` with non-default value | |
| 1.3.3 | `docker-compose.yml`: no hardcoded Kafka SASL credential | `grep -n "diep-kafka-pass" docker-compose.yml` → no results |
| 1.3.4 | `command_dispatcher.py`: uses `os.environ['KAFKA_SASL_PASSWORD']` (no hardcode) | |
| 1.3.5 | `fastapi/app.py`: uses `os.environ['KAFKA_SASL_PASSWORD']` (no hardcode) | |
| 1.3.6 | 4th location: Kafka SASL credential removed | |
| 1.3.7 | Kafka SASL rotation runbook written and reviewed | |

**Verification command:**
```bash
# No hardcoded credential in source
grep -rn "diep-kafka-pass" . --include="*.py" --include="*.yml" --include="*.yaml"
# Expected: zero matches
```

### 1.4 EMQX Admin Credential

**Requirement:** SEC-5. The validation throwaway password (`diep-emqx-admin-2026`) must not be used in production.

| # | Check | Verified by |
|---|---|---|
| 1.4.1 | EMQX production admin password is stored in secrets manager or vault | |
| 1.4.2 | EMQX admin password is ≥ 16 chars, cryptographically random | |
| 1.4.3 | `diep-emqx-admin-2026` does not appear in any production compose or config file | `grep -rn "diep-emqx-admin-2026" . → zero matches` |
| 1.4.4 | `$EMQX_API_KEY` rotatable procedure documented | |

### 1.5 JWT / API Key Secrets

| # | Check | Verified by |
|---|---|---|
| 1.5.1 | `JWT_SECRET_KEY` is cryptographically random (≥ 32 bytes) | `grep JWT_SECRET_KEY .env` → confirm length |
| 1.5.2 | `JWT_SECRET_KEY` is not shared with any other environment (dev, staging) | |
| 1.5.3 | No expired or test API keys present in the database | `SELECT * FROM api_keys WHERE expires_at < now();` → no active rows |

---

## 2. TLS Certificates

### 2.1 Certificate Authority Health

| # | Check | Command / Verification | Verified by |
|---|---|---|---|
| 2.1.1 | DIEP Root CA present and readable | `openssl x509 -in certs/ca.crt -noout -subject -enddate` | |
| 2.1.2 | DIEP Root CA expiry > 90 days | Expected: Dec 2035 — no action needed | |
| 2.1.3 | Root CA private key is NOT in the git repository | `git log --all --full-history -- certs/ca.key` → no commits | |
| 2.1.4 | Root CA private key backed up to MinIO (encrypted) | `mc ls local/diep-config-backups/pki/` | |

### 2.2 EMQX TLS Configuration

**Requirement:** EMQX-1. SSL options must be set via environment variables, not only `emqx.conf`.

| # | Check | Verified by |
|---|---|---|
| 2.2.1 | `EMQX_LISTENERS__SSL__DEFAULT__SSL_OPTIONS__VERIFY=verify_peer` set on all 3 EMQX nodes | |
| 2.2.2 | `EMQX_LISTENERS__SSL__DEFAULT__SSL_OPTIONS__FAIL_IF_NO_PEER_CERT=true` set on all 3 EMQX nodes | |
| 2.2.3 | `EMQX_LISTENERS__SSL__DEFAULT__SSL_OPTIONS__CACERTFILE` points to production CA cert path | |
| 2.2.4 | EMQX server cert (`CERTFILE`) and key (`KEYFILE`) point to production-issued certs (not validation throwaway) | |
| 2.2.5 | EMQX node hostnames use `.local` (or other FQDN) suffix per EMQX-2 requirement | |

**Verification:**
```bash
# Confirm client without cert is rejected
echo | openssl s_client -connect localhost:8883 -CAfile certs/ca.crt 2>&1 | \
  grep -i "certificate required"
# Must return: "alert certificate required"

# Confirm client with valid cert connects
openssl s_client -connect localhost:8883 \
  -CAfile certs/ca.crt \
  -cert certs/INV001.crt -key certs/INV001.key \
  -brief 2>&1 | head -5
# Must show: CONNECTION ESTABLISHED
```

### 2.3 Service and Device Certificate Expiry

Run before go-live and on each monthly check:

```bash
# Check all certs in the certs/ directory
for cert in certs/*.crt; do
  expiry=$(openssl x509 -in "$cert" -noout -enddate 2>/dev/null | cut -d= -f2)
  days_left=$(( ($(date -d "$expiry" +%s) - $(date +%s)) / 86400 ))
  echo "$cert: expires $expiry ($days_left days)"
done
```

| # | Certificate | Min acceptable days remaining | Verified by |
|---|---|---|---|
| 2.3.1 | `certs/ca.crt` (Root CA) | > 3000 days (expires 2036) | |
| 2.3.2 | `certs/emqx-server.crt` | > 90 days | |
| 2.3.3 | `certs/ingestor.crt` | > 90 days | |
| 2.3.4 | `certs/dispatcher.crt` | > 90 days | |
| 2.3.5 | `certs/INV001.crt` | > 90 days | |
| 2.3.6 | `certs/BAT001.crt` | > 90 days | |
| 2.3.7 | `certs/EV001.crt` | > 90 days | |
| 2.3.8 | `certs/MG001.crt` | > 90 days | |
| 2.3.9 | `certs/METER001.crt` | > 90 days | |

### 2.4 Caddy TLS Reverse Proxy

**Requirement:** SEC-3.

| # | Check | Verified by |
|---|---|---|
| 2.4.1 | Caddy TLS enabled in `docker-compose.yml` | |
| 2.4.2 | API (:443/8000) served over HTTPS | `curl -I https://<hostname>/healthz` → 200 |
| 2.4.3 | Portal (:443/3002) served over HTTPS | Browser navigation confirms HTTPS padlock |
| 2.4.4 | Grafana (:443/3001) served over HTTPS | |
| 2.4.5 | HTTP → HTTPS redirect enforced on port 80 | `curl -I http://<hostname>/healthz` → 301 or 308 to HTTPS |
| 2.4.6 | TLS certificate used by Caddy is valid and trusted | `openssl s_client -connect <hostname>:443 -brief` → no certificate errors |

---

## 3. CA Management

| # | Check | Verified by |
|---|---|---|
| 3.1 | `scripts/bootstrap-pki.sh` verified on a clean clone of the repository | `git clone ... && bash scripts/bootstrap-pki.sh` → exits 0 |
| 3.2 | Root CA private key is stored separately from the codebase (secrets manager, encrypted volume, or offline) | |
| 3.3 | Process for issuing a new device certificate is documented (procedure: run bootstrap-pki.sh with device CN as argument or equivalent) | |
| 3.4 | Process for revoking a device certificate is documented (procedure: remove cert from EMQX ACL; re-issue if device is redeployed) | |
| 3.5 | CA renewal reminder is scheduled for 2033 (3-year lead time before 2036 expiry) | |
| 3.6 | All device CNs match the `peer_cert_as_username` scheme enforced in EMQX ACL rules (`mqtt { peer_cert_as_username = cn }`) | |

---

## 4. RBAC

| # | Check | Verified by |
|---|---|---|
| 4.1 | JWT role hierarchy enforced: `viewer < operator < admin < service` | Test DERMS command with viewer token → 403 |
| 4.2 | All state-changing routes require at least `operator` role | `curl -X POST /api/v1/commands -H "Bearer viewer_token"` → 403 |
| 4.3 | Service accounts (`ingestor`, `dispatcher`) use `service` role only | Confirm token claims: `{"role": "service"}` |
| 4.4 | Admin accounts are held by named individuals (no shared admin credentials) | |
| 4.5 | API key rotation procedure documented and tested | |
| 4.6 | No test or expired API keys are active in the production database: | `SELECT username, expires_at FROM api_keys WHERE expires_at < NOW();` → 0 rows |
| 4.7 | RBAC enforcement on audit-sensitive routes (`/admin/*`) verified | |
| 4.8 | Tenant isolation verified: ACME tenant data not accessible by Globex credentials | |

---

## 5. Firewall Rules

**Requirement:** SEC-4. All infrastructure ports must be restricted to internal-only bindings.

### 5.1 Docker Compose Port Bindings

| # | Service | Port | Required binding | Check | Verified by |
|---|---|---|---|---|---|
| 5.1.1 | PostgreSQL | 5432 | Internal network only (no `0.0.0.0`) | `docker compose port pg-ha-haproxy 5432` → should NOT bind to 0.0.0.0 or host IP | |
| 5.1.2 | Redis | 6379 | Internal network only | `docker compose port diep-redis 6379` → internal only | |
| 5.1.3 | Kafka (plaintext) | 9092 | Internal only (if exposed) | Confirm 9092 not published to host | |
| 5.1.4 | Kafka (SASL) | 9094 | Internal only or application-tier only | `docker compose port diep-kafka 9094` → internal or 127.0.0.1 | |
| 5.1.5 | MinIO S3 API | 9000 | Internal network only | `docker compose port minio-ha-0 9000` → internal only | |
| 5.1.6 | MinIO Console | 9002 | Internal or admin-VLAN only | `docker compose port minio-ha-0 9002` → internal or 127.0.0.1 | |
| 5.1.7 | EMQX Management API | 18083 | Admin-only (VPN or 127.0.0.1) | `docker compose port emqx-ha-1 18083` → 127.0.0.1 or not published | |
| 5.1.8 | EMQX MQTT mTLS | 8883 | Device network accessible; host-published OK | `docker compose port emqx-ha-haproxy 8883` → confirms correct binding | |
| 5.1.9 | Prometheus | 9090 | Internal or admin-VLAN only | |
| 5.1.10 | Grafana | 3001 | Behind Caddy TLS only (not direct) | Port 3001 should NOT be published to 0.0.0.0 in production compose | |

**Verification:**
```bash
# Confirm infra ports are NOT reachable from external networks
# Run from a machine outside the Docker host:
for port in 5432 6379 9092 9094 9000 9002; do
  nc -zv <production-host-ip> $port 2>&1 | grep -E "refused|timeout"
done
# All should show: Connection refused or timeout
```

### 5.2 Host Firewall Rules

| # | Check | Verified by |
|---|---|---|
| 5.2.1 | Host firewall (ufw, iptables, or nftables) is enabled and active | `ufw status` or `iptables -L -n` |
| 5.2.2 | Only ports 443 (HTTPS), 8883 (MQTT mTLS), and 22 (SSH) are published to external interface | |
| 5.2.3 | Docker daemon's default FORWARD rule does not bypass host firewall | `iptables -L DOCKER-USER` → confirm DROP default or explicit ACCEPT only for allowed ports |
| 5.2.4 | ICMP ping is allowed (for monitoring) but ICMP redirect is disabled | |

---

## 6. VPN / Access Control Requirements

| # | Check | Verified by |
|---|---|---|
| 6.1 | Admin access to infrastructure ports (5432, 6379, 9092, 9000, 18083) requires VPN or SSH tunnel | |
| 6.2 | EMQX Management API (18083) is VPN-gated or accessible only via 127.0.0.1 SSH forward | |
| 6.3 | Grafana admin panel is accessible over HTTPS but requires authentication | |
| 6.4 | SSH to production host uses key-based authentication only (password SSH disabled) | `grep PasswordAuthentication /etc/ssh/sshd_config` → `no` |
| 6.5 | Root login via SSH is disabled | `grep PermitRootLogin /etc/ssh/sshd_config` → `no` |
| 6.6 | Authorized SSH keys reviewed and contain only active team members | `cat ~/.ssh/authorized_keys` |
| 6.7 | VPN configuration documented in `DIEP_OPERATIONS_MANUAL.md` (or equivalent) | |

---

## 7. Alertmanager Routing

| # | Check | Verified by |
|---|---|---|
| 7.1 | Alertmanager email routing previously validated: `ALERTMANAGER_EMAIL_TEST_REPORT.md` | Reference existing test report |
| 7.2 | MON-1 alert active: `emqx_cluster_nodes_running < 3` fires and routes to on-call | Inject test: `curl -XPOST http://localhost:9093/api/v2/alerts -d '[{"labels":{"alertname":"EMQXClusterDegraded","severity":"critical"},"endsAt":"2099-01-01T00:00:00Z"}]'` → confirm email received |
| 7.3 | MON-2 alert active: Kafka broker count alert fires | |
| 7.4 | MON-3 alert active: MinIO disk count alert fires | |
| 7.5 | MON-4 alert active: Patroni primary health alert fires | |
| 7.6 | No unexpected silences active in Alertmanager | `curl http://localhost:9093/api/v2/silences` → review active silences; confirm all have known justification and expiry |
| 7.7 | Alert receiver email list includes all on-call contacts | Review `alertmanager.yml` `receivers:` section |
| 7.8 | `DiepApiDown` alert routes to P1 path | |
| 7.9 | `DatabaseOutage` alert routes to P1 path | |
| 7.10 | `KafkaOutage` alert routes to P1 path | |

---

## 8. MFA and Authentication Requirements

| # | Check | Verified by |
|---|---|---|
| 8.1 | DIEP portal admin login is protected by MFA or restricted to VPN-only access | |
| 8.2 | Grafana admin account has MFA configured or is accessible only via Caddy with additional auth | |
| 8.3 | All GitHub contributors to the diep-lab repository have 2FA enabled | GitHub → Repository → Settings → Security → Two-factor authentication required |
| 8.4 | SSH access to production host uses key-based auth (covered in Section 6) | See 6.4 |
| 8.5 | Password-based API authentication is disabled for service accounts (service accounts use API keys only) | |
| 8.6 | Admin API key (EMQX, Alertmanager) is stored in secrets manager — not in `~/.bashrc` or shell history | `history | grep -i api_key` → confirm no exposure |

---

## 9. GitHub Security

| # | Check | Verified by |
|---|---|---|
| 9.1 | Branch protection on `main`: PRs required; at least 1 review required | GitHub → Settings → Branches → main |
| 9.2 | Direct pushes to `main` are disallowed | |
| 9.3 | GitHub secret scanning enabled for repository | GitHub → Security → Secret scanning → Active |
| 9.4 | Dependabot alerts enabled for Python and Docker dependencies | GitHub → Security → Dependabot |
| 9.5 | `.env` is in `.gitignore` | `cat .gitignore | grep .env` → confirmed |
| 9.6 | No secrets in git history: scan with git-secrets or truffleHog | `trufflehog git file://. --only-verified` → zero verified findings |
| 9.7 | No production `.env` file or private keys committed | `git log --all --full-history -- .env` → no commits; `git log --all -- certs/ca.key` → no commits |
| 9.8 | Validation throwaway credentials (`diep-emqx-admin-2026`, `diep-kafka-pass-2026`) visible in validation files are documented as throwaway and not reused in production | Confirmed: validation files only; production credentials not reproduced |
| 9.9 | Repository is private or access-controlled to authorized team members | GitHub → Settings → General → Visibility |
| 9.10 | GitHub Actions (if any) do not print secrets to logs | Review CI workflow files for `echo $SECRET` patterns |

---

## 10. Audit Logging

| # | Check | Verified by |
|---|---|---|
| 10.1 | `audit_events` table exists and is capturing events | `SELECT count(*) FROM audit_events WHERE created_at > now() - interval '1h';` → > 0 rows |
| 10.2 | All state-changing API calls (POST, PUT, PATCH, DELETE) appear in `audit_events` | Execute a test command; verify row in `audit_events` |
| 10.3 | Audit log includes: user identity, action, resource, timestamp, IP address | `SELECT user_id, action, resource, created_at, ip_address FROM audit_events LIMIT 3;` |
| 10.4 | Audit log retention policy defined and implemented (minimum: 1 year) | Review backup-db.sh retention config; confirm audit_events table is included |
| 10.5 | Audit log is included in nightly pg_dump (covers retention via backup) | `pg_dump` includes `audit_events` table by default (no exclusions) |
| 10.6 | Direct write access to `audit_events` is restricted (no application role has DELETE or UPDATE permissions) | `SELECT has_table_privilege('diep_user', 'audit_events', 'delete');` → false |
| 10.7 | Docker daemon log rotation is configured | `cat /etc/docker/daemon.json | grep log-opts` → `max-size` and `max-file` set |
| 10.8 | SIEM integration evaluated (not required for initial production; required for SOC2) | Document evaluation decision and timeline |

---

## 11. Completion Sign-Off

This checklist must be completed and signed off before any production maintenance window begins.

| Section | Complete | Verified by | Date |
|---|---|---|---|
| 1. Secret Rotation | [ ] | | |
| 2. TLS Certificates | [ ] | | |
| 3. CA Management | [ ] | | |
| 4. RBAC | [ ] | | |
| 5. Firewall Rules | [ ] | | |
| 6. VPN / Access Control | [ ] | | |
| 7. Alertmanager Routing | [ ] | | |
| 8. MFA Requirements | [ ] | | |
| 9. GitHub Security | [ ] | | |
| 10. Audit Logging | [ ] | | |

**All sections complete:** [ ] Yes  
**Any open items documented:** [ ] Yes / [ ] None  
**Approved for production go-live by:** ___________________________  
**Date:** ___________________________

---

## Security Constraints (Reproduced for Reference)

Do not expose passwords in logs, reports, screenshots, or output. Only throwaway credentials appear in validation files; production credentials from `.env` are never reproduced in any deliverable.

The validation credentials that appear in K1–K6 validation reports and Docker Compose files are throwaway credentials used in isolated validation environments only. They have never been and must never be used in production.
