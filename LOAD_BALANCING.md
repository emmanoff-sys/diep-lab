# Load Balancing — DAEP / RE-OS

**Authority:** WP-003-09 | LLD v2.0 Ch. 17 introduction (tool division) | LLD v2.0 §17.2 (Nginx/Keepalived — literal source) | DRDP v1.0 §21.3 (429 handling contract)

## 1. Tool Division (LLD v2.0 Ch. 17, verbatim)

> "Nginx handles HTTP load balancing. HAProxy handles TCP (Kafka, MQTT).
> Keepalived provides VRRP virtual IP failover for Nginx."

This replaces Kubernetes Services/Ingress under the VM-only model (ECR-001)
— no ingress controller, no Kubernetes-native load balancer exists anywhere
in this stack.

## 2. Nginx (`nginx.conf`) — literal LLD excerpt

- `upstream reos_scaffold`: `least_conn`, `max_fails=3 fail_timeout=30s`,
  `keepalive 32` connection pooling.
- TLS 1.3 only, HSTS/X-Content-Type-Options/X-Frame-Options headers on
  every response.
- `X-Request-ID` propagation — correlates Nginx access logs with backend
  structured logs (WP-002-03's request-ID contextvars binding).
- Rate limiting: `zone=auth_strict burst=10` (auth endpoints) vs.
  `zone=api_standard burst=200` (general API) — breach returns **HTTP
  429**, matching DRDP v1.0 §21.3's documented UI behavior exactly.

## 3. Keepalived (`keepalived.conf` / `keepalived-backup.conf`) — literal LLD excerpt

VRRP primary/backup pair. `vrrp_script chk_nginx` health-checks Nginx's own
`/health` endpoint every 2s (`fall 3`/`rise 2` — 6s to mark down, 4s to mark
back up). A bad Nginx config is caught by this health check, which
triggers automatic failover to BACKUP — a useful safety property (§36).

`auth_pass` is a placeholder for this WP's own testing (§24) — sourced from
Vault once WP-003-13 exists, explicitly flagged rather than presented as
production-ready.

## 4. HAProxy (`haproxy.cfg`) — ⚠️ this WP's own construction, not an LLD excerpt

The captured LLD v2.0 §17.2 excerpt confirmed HAProxy's role but did not
include a worked config example (unlike Nginx/Keepalived, both literal).
Built from standard HAProxy TCP-mode practice: `mode tcp`, `balance
leastconn`, TCP health checks, for Kafka (9092) and MQTT (1883).

**Flagged for extra review scrutiny (§35/§39)** — re-verify against the
complete LLD v2.0 document if more of it becomes available beyond this
package's initial document-reconciliation extraction.

## 5. Failover Test Procedure

1. Load-test the scaffold behind the LB pair (continuous traffic).
2. Kill the active (MASTER) node's Nginx process.
3. Confirm the VRRP virtual IP fails over to BACKUP within the
   `vrrp_script`'s configured interval/fall/rise thresholds (6s worst case).
4. Confirm zero dropped requests during the load test spanning the failover.

## 6. Rate-Limit Test Procedure

Exceed `limit_req` burst on a test endpoint; confirm HTTP 429 returned,
matching DRDP §21.3.

## 7. Out of Scope

Consul-based dynamic upstream discovery (WP-003-10 handles service
registration; wiring Nginx upstreams to Consul dynamically is a candidate
future enhancement) — upstreams are static IPs in this WP's scope, matching
the LLD's own worked example (§9).

## 8. Verification (Runtime — requires nginx/haproxy/keepalived binaries + LB VMs)

```bash
nginx -t -c infra/loadbalancer/nginx.conf
haproxy -c -f infra/loadbalancer/haproxy.cfg
# failover kill-test and rate-limit test per §5/§6
```

**Status in this repository:** nginx, haproxy, and keepalived binaries are
not installed in the implementation environment, and no LB VM pair exists —
config-syntax and failover/rate-limit verification are **Runtime PASS
Deferred**.

## 9. Traceability

| Requirement | Source |
|-------------|--------|
| Tool division | LLD v2.0 Ch. 17 introduction |
| Nginx/Keepalived config | LLD v2.0 §17.2 (literal) |
| HAProxy config | This WP's own construction (§9/§35 flagged) |
| 429 rate-limit contract | DRDP v1.0 §21.3 |
