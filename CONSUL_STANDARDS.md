# Consul Standards — DAEP / RE-OS

**Authority:** WP-003-10 | LLD v2.0 §17.1 (`consul-agent` role) | LLD's worked health-check registration JSON example (literal source)

Consul is the VM-only replacement for what Kubernetes' internal DNS/Service
objects would otherwise provide — operationalizing ECR-001's resolution
beyond a documentation change.

## 1. Registration Schema (LLD-literal — every future service copies this)

```json
{
  "service": {
    "name": "{service-name}",
    "port": {service-port},
    "check": {
      "http": "http://localhost:{service-port}/health",
      "interval": "10s",
      "timeout": "3s",
      "deregister_critical_service_after": "60s"
    }
  }
}
```

`infra/consul/scaffold-service-registration.json` is the canonical,
copy-from reference — its field values were taken directly from the LLD's
own worked example. Deviating from it in a future service should require a
documented reason (§39).

## 2. Server Deployment

Single-node for Release 1 (`infra/consul/consul-server.hcl`,
`bootstrap_expect = 1`) — a documented single point of failure, explicitly
acceptable for now since no production service depends on it yet (§35).

**Multi-node upgrade path (Production):** `bootstrap_expect = 3` (or 5) with
`retry_join` listing all server addresses — standard Consul HA quorum
practice.

## 3. Agent Deployment

Every service VM runs a Consul agent in client mode
(`infra/consul/consul-agent-template.hcl` — the live Ansible-rendered
version is `infra/roles/consul-agent/templates/consul-agent.hcl.j2`,
WP-003-07), registering using the schema in §1.

## 4. Security

- Consul HTTP API bound to `127.0.0.1` — never public-internet-exposed.
- ACL tokens for agent-to-server communication are placeholders for this
  WP's own testing (`PLACEHOLDER-pending-WP-003-13-vault-integration`),
  explicitly flagged — sourced from Vault once WP-003-13 exists.

## 5. Health-Check Timing Rationale

`interval: 10s` / `timeout: 3s` / `deregister_critical_service_after: 60s`
— exact LLD values. A service transitions to `critical` after ~1-2 missed
checks and is deregistered from the catalog after 60 continuous seconds of
failure, giving enough grace for a transient blip while still removing a
genuinely dead instance from routing within a reasonable window.

## 6. Out of Scope

Consul Connect (service mesh / mTLS) — not evidenced in the captured LLD
excerpt and not assumed. If service-mesh-level mTLS becomes a real
requirement, raise a new ECR rather than building it speculatively (§9).

## 7. Verification (Runtime — requires the `consul` binary + a live agent/server)

```bash
consul agent -config-file=infra/consul/consul-server.hcl &
consul services register infra/consul/scaffold-service-registration.json
consul catalog services            # expect "scaffold" listed
consul health checks scaffold       # expect "passing"

# Simulated failure:
# kill the scaffold's /health endpoint, then:
consul health checks scaffold       # expect "critical" within interval/timeout
# after 60s of continued failure:
consul catalog services             # expect scaffold deregistered
```

**Status in this repository:** the `consul` binary is not installed in the
implementation environment — registration/health-transition/deregistration
verification is **Runtime PASS Deferred**. Registration JSON validated
(Structural PASS — `json.load` parses cleanly).

## 8. Traceability

| Requirement | Source |
|-------------|--------|
| `consul-agent` role reference | LLD v2.0 §17.1 |
| Registration schema, exact timing values | LLD v2.0 worked health-check JSON example (literal) |
