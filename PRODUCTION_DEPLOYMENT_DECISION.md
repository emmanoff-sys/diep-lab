# DIEP Phase 20 — Production Deployment Decision

**Date:** 2026-06-17
**Inputs:** `PRODUCTION_INSTALLATION_VALIDATION_REPORT.md` (Part A) and
`WEB_PORTAL_VALIDATION_REPORT.md` (Part B), both produced from real,
hands-on execution against a fresh, isolated clone of the codebase — not
documentation review and not the existing pilot deployment.

## Recommendation: **NO-GO**

DIEP v1.0 should **not** be deployed to a production environment with
real-world network exposure in its current state. This is not a judgment on
the platform's core engineering — the data path (MQTT → Kafka → TimescaleDB),
mTLS enforcement, DERMS command round-trip, and backup/restore mechanics all
demonstrated correct behavior under real testing. The blocker is that two
independent validation passes each surfaced at least one issue capable of
causing silent, undetected harm to the platform or its data (not just visible
breakage), and Part B surfaced a complete absence of access control on the
primary operator interface.

A **Go** decision is achievable, but only after the items in
"Required before Go" below are remediated and re-validated — not merely
acknowledged in a tracker.

## Installation readiness (Part A)

**CONDITIONAL** — 5 of 10 pass/fail criteria fully pass, 3 partial, 2 fail.
A fresh install does reach a fully running platform by following only the
installation guide, but only after three undocumented workarounds, one of
which (Alertmanager SMTP variables) is not optional — the install cannot
otherwise complete. Total time clone-to-running: ~18–20 minutes.

The two findings that matter most for this decision:

- **INSTALL-2 (Blocker/Security):** Grafana is reachable on the well-known
  default `admin`/`admin` credentials in every fresh install, because no
  Grafana admin password variable exists anywhere in `.env.example` or the
  installation guide. This is a real, externally-known attack vector, not a
  theoretical one.
- **INSTALL-3 (Blocker):** `backup-db.sh` and `backup-config.sh` report
  success (`exit 0`) while the off-site MinIO upload silently fails, due to a
  hardcoded network-name default plus a misplaced `|| true` that swallows
  failures from the entire upload chain. A production install whose
  directory/project name isn't exactly `diep-lab` would run its nightly
  backup cron for months with zero off-site copies and no indication
  anything is wrong. This is the most dangerous class of bug found in either
  report: it doesn't fail loudly, it fails quietly and looks healthy.

INSTALL-1 (Alertmanager), INSTALL-4 (rebuild_flows.py hardcoded path), and
INSTALL-5 (4 of 5 DERMS device types disabled by default, undocumented) are
real but lower-severity — they either have a workaround or a clear non-impact
on the functioning path that was tested.

## Portal readiness (Part B)

**NOT READY.** 2 of 10 areas are outright FAIL (Authentication,
Authorization), with a third (Audit logs) also FAIL. The functional surface —
Dashboard, Device inventory, DERMS controls, Reports — all work correctly
against a real backend, with sub-200ms response times and no data-integrity
issues observed.

The two findings that matter most for this decision:

- **PORTAL-1 / PORTAL-2 (Blocker/Security):** The portal has no login of any
  kind. Every page — including device registration under Administration —
  loads at HTTP 200 for a completely anonymous browser, because the portal's
  BFF proxy (`portal/app/api/diep/[...path]/route.ts`) attaches one fixed,
  admin-scoped API token to every request server-side regardless of who is
  browsing. The backend's real RBAC model (operator vs. admin roles,
  `require_role()`) is never exercised by the portal — it is bypassed
  entirely. The route's own source comment already documents this as a known
  gap: *"Production should replace this shared token with per-operator
  SSO/JWT via the /auth/token login flow."*
- **PORTAL-3 / PORTAL-4 (Major):** Because there is no login, the audit log
  cannot attribute any action to an individual human — only to the shared
  API-key identity — and there is no UI or API surface to read the audit log
  at all, despite the table being populated. **Anyone with network reach to
  the portal can issue DERMS commands or register devices, and there is no
  way, even after the fact, to determine who did it.**

This is a materially different and more severe risk category than anything
in Part A: Part A's issues are about installation correctness and backup
integrity; Part B's are about there being no barrier at all between an
anonymous network user and grid-control actions.

## Consolidated remaining issues

| ID | Source | Severity | Issue |
|---|---|---|---|
| INSTALL-2 | Part A | Blocker/Security | Grafana default admin/admin credentials |
| INSTALL-3 | Part A | Blocker | Backup scripts silently fail off-site upload, report success |
| PORTAL-1 | Part B | Blocker/Security | No authentication on the portal |
| PORTAL-2 | Part B | Blocker/Security | No authorization — all actions performed as one shared admin identity |
| PORTAL-3 | Part B | Major/Security | Audit log cannot attribute actions to a human |
| PORTAL-4 | Part B | Major | No audit log UI or API |
| INSTALL-1 | Part A | Blocker (has workaround) | Alertmanager requires 5 undocumented env vars to start at all |
| INSTALL-5 | Part A | Major | 4 of 5 documented DERMS device types disabled by default, undocumented |
| INSTALL-4 | Part A | Major | `rebuild_flows.py` hardcoded developer path |
| PORTAL-5/6/7 | Part B | Minor/UX | Inconsistent or unpolished error handling on backend-down/validation-failure |
| INSTALL-6/7/8/9/10 | Part A | Minor | Documentation accuracy gaps, container-naming collision risk, transient kafka-exporter restarts |

## Required before Go

1. Fix INSTALL-2: wire `GF_SECURITY_ADMIN_USER`/`GF_SECURITY_ADMIN_PASSWORD`
   from `.env`, document the variable, remove the default-credential exposure.
2. Fix INSTALL-3: correct the `DIEP_NET` default (or require it explicitly,
   failing loudly if unset) and fix the `|| true` placement so a failed
   upload causes a non-zero exit and an alertable failure.
3. Fix PORTAL-1/PORTAL-2: implement the per-operator authentication the
   route's own comment already calls for (the `/auth/token` login flow
   referenced in the code), and stop forwarding every browser session under
   one shared admin-scoped token.
4. Fix PORTAL-3/PORTAL-4: once individual login exists, ensure `audit_events`
   records the real principal, and add a minimal read surface (API endpoint
   at minimum; a UI screen ideally) so the log is actually usable.
5. Document INSTALL-1 (Alertmanager SMTP variables) and INSTALL-5 (DERMS
   device-vertical profiles) so a fresh install doesn't depend on
   undocumented tribal knowledge to reach the documented feature set.
6. Re-run both Part A and Part B validation passes against the fixes above,
   in a fresh isolated clone, before approving production deployment.

Items in the Minor category (INSTALL-4/6/7/8/9/10, PORTAL-5/6/7, PORTAL-9) do
not block Go but should be tracked and scheduled for cleanup.

## What does not need to change

The underlying platform mechanics validated correctly under real, adversarial
testing and do not need rework: mTLS enforcement (confirmed via broker-side
rejection of an uncertified client, not just client-side inference), the
DERMS command round-trip (operator API → Kafka → MQTT → device simulator →
ack → status update, fully observed end-to-end), TimescaleDB
initialization/hypertable/retention-policy setup, and the backup
verify/restore drill itself (`verify-backup.sh`) all passed without any
workaround.
