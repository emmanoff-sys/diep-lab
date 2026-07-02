# DAST Standards — DAEP / RE-OS

**Authority:** WP-004-08 | Roadmap v1.0 §11.1 Stage 11 (trigger: Manual; tool: OWASP ZAP; budget: <60 minutes; policy: No High; Release blocked)

## 1. Purpose

Dynamic Application Security Testing (DAST) catches vulnerabilities only
exploitable at runtime — SSRF, injection flaws, auth bypasses — that SAST
(WP-004-02, Stage 2) cannot detect from source code alone.

## 2. Trigger

Manual (`workflow_dispatch`) — deliberately not automated on every merge.
Runs:
- Before every release candidate (pre-release gate).
- Weekly against Staging as a standing security posture check.

## 3. Target Safeguard

**This scan runs ONLY against Staging (NEVER Production).**

A full active DAST scan sends malformed/attack payloads to the target. Running
it against Production would risk real customer data mutation, service disruption,
and real security incident. The `workflow_dispatch` input is locked to the
`staging` option. Any change to allow Production as a target requires an
explicit Architecture Review (§25/§31).

## 4. Tool

OWASP ZAP `action-full-scan` — full active scan (not just passive/baseline),
matching the Roadmap's "full site scan" specification. The `.zap/rules.tsv`
file documents any scan-rule exceptions (reviewed exceptions only, same
discipline as `.trivyignore`).

## 5. Policy — "No High; Release blocked"

High (or Critical) severity alerts fail the workflow (`fail_action: true`).
A release candidate cannot proceed to Stage 12 Production Deployment
(WP-004-13) until this scan passes. Per Roadmap §11.1 Stage 11.

## 6. Relationship to WP-004-11 (Staging)

Stage 11 DAST requires a real, running Staging environment. WP-004-11 must
be done and Staging must be healthy before this workflow can produce meaningful
results. The Release 1 test surface is minimal (scaffold `/health` only) — this
validates the *mechanism*, not yet a full app surface.

## 7. Report Retention

ZAP scan reports (HTML, Markdown, JSON) are uploaded as workflow artifacts for
audit and remediation tracking per run. High-severity findings must be
remediated before the release can proceed.

## 8. Traceability

| Requirement | Source |
|-------------|--------|
| Manual trigger, ZAP full scan, <60 min, No High | Roadmap v1.0 §11.1 Stage 11 |
| Staging-only safeguard | WP-004-08 §25/§31 |
| Release-blocking policy | Roadmap §11.1 Stage 12 depends on Stage 11 ("No High") |
