# Container Security Scanning — DAEP / RE-OS

**Authority:** WP-003-04 | Roadmap v1.0 §11.1 Stage 6 ("Container Scan — Trivy (image scan) — <3 minutes — No CRITICAL — Image not [pushed]")

Trivy extends the source-code-level security gates already established by
Bandit/pip-audit (LLD v2.0 §2.1, WP-001-08) to the built container image
itself — OS packages, installed libraries, misconfigurations.

## 1. Scan Command

```bash
trivy image --severity CRITICAL,HIGH --exit-code 1 --ignore-unfixed reos/scaffold:local
```

`--exit-code 1` on any **CRITICAL** finding — matches Roadmap Stage 6's
exact policy ("No CRITICAL = build fails," cross-referenced against LLD
v2.0's testing-standards table for consistency). HIGH findings are reported
but do not fail the build in Release 1 (documented, not silent — CRITICAL is
the hard gate; HIGH-severity policy tightening is a candidate for a later
release once the finding baseline is established).

## 2. `.trivyignore` Exception Process

Empty by default — the scaffold, built on `python:3.12-slim` (WP-003-01),
should have zero CRITICAL findings out of the box. Every exception entry
requires:

1. The CVE ID
2. A justification comment (why it's a false positive or accepted risk)
3. A review-by date

Entries without both are rejected in review. **Never add a CVE "to unblock a
build"** — this defeats the entire point of the gate (§39).

## 3. Vulnerability Database Freshness

Trivy's local vulnerability DB must be refreshed before each scan run:

```bash
trivy image --download-db-only   # refresh cadence: every CI run (WP-004-06 automates this)
```

A stale DB gives false confidence — this is documented explicitly so the
refresh step is never silently skipped.

## 4. Fixture Test (deliberately vulnerable image)

```bash
trivy image --severity CRITICAL --exit-code 1 python:3.9-slim   # older base, known CVEs expected
```

Confirms Trivy correctly detects and fails on a genuinely vulnerable image —
the negative-path test companion to the scaffold's expected-clean scan.

## 5. Scope

This WP establishes the tool, policy, and `.trivyignore` process. CI workflow
automation (invoking this exact command on every build) is WP-004-06's job —
out of scope here (§9).

## 6. Logging & Audit

Scan results (image version scanned, timestamp, findings) are archived for
audit — WP-004-06 wires this into CI artifact retention.

## 7. Verification (Runtime — requires Trivy + a reachable Docker daemon)

```bash
docker build -t reos/scaffold:local templates/python-service/
trivy image --severity CRITICAL --exit-code 1 reos/scaffold:local   # expect exit 0, zero CRITICAL
trivy image --severity CRITICAL --exit-code 1 python:3.9-slim       # expect exit 1, CRITICAL detected
```

**Status in this repository:** neither Trivy nor a reachable Docker daemon
is available in the implementation environment — both scans are **Runtime
PASS Deferred**.

## 8. Traceability

| Requirement | Source |
|-------------|--------|
| Trivy, timing budget, CRITICAL-fail policy | Roadmap v1.0 §11.1 Stage 6 |
| Base image choice (`python:3.12-slim`) | WP-003-01 `DOCKER_STANDARDS.md` |
| Source-level equivalent (Bandit/pip-audit) | LLD v2.0 §2.1, `DEPENDENCY_POLICY.md` (WP-001-08) |
