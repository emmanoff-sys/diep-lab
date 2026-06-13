# DIEP Phase 11 (Group D) — Mobile App

> **Status:** The "app on a phone" is live — the portal is an **installable PWA** and the
> API is **mobile-ready** (CORS, versioning, refresh tokens) on top of the existing HTTPS +
> JWT/RBAC. Native app + push + store distribution designed. Date: 2026-06-06.

---

## 1. What shipped (live + verified)

### 11C — Installable PWA (the phone app)
The existing Next.js operator portal is now installable on a phone ("Add to Home Screen")
and launches standalone like a native app — reusing **all** existing screens (fleet, twins,
DERMS, alarms, onboarding) and the server-side auth BFF.
- `portal/public/manifest.webmanifest` (name, `display: standalone`, 192/512 + maskable icons,
  theme), `portal/public/sw.js` (app-shell cache + **API never cached** — live data stays
  fresh), generated PNG icons, and `layout.tsx` wiring (manifest link, theme-color,
  apple-web-app meta) + a service-worker registration component.
- **Verified:** `/manifest.webmanifest` 200 (`application/manifest+json`, valid, standalone,
  3 icons), `/sw.js` 200, icons 200, root HTML carries `rel="manifest"` + `theme-color` +
  `apple-mobile-web-app` → meets PWA installability criteria.

### 11A/11B — Mobile-ready API
- **CORS** middleware (origins via `DIEP_CORS_ORIGINS`) — token-based, credentials off.
- **Versioning:** `/version` → `{api_version: v1, app_version}`; OpenAPI at `/openapi.json`.
- **Refresh tokens:** `/auth/token` returns `access_token` (short) + `refresh_token` (30 d);
  `/auth/refresh` mints new access tokens. Refresh tokens are **rejected** as access tokens
  (`use` claim), so a stolen refresh token can't directly actuate.
- **Verified:** version, CORS preflight headers, login (access+refresh), refresh→new access
  (works on a protected route, 202), refresh-as-access (correctly 401).
- Already in place from earlier phases: **HTTPS** at the gateway (9J-S6), **JWT/RBAC + audit +
  rate-limit** (9J-S1/S2). The mobile contract is stable.

---

## 2. Two delivery tracks

| | PWA (shipped) | Native app (designed) |
|--|---------------|------------------------|
| Speed | days — reuses portal + auth | weeks — new codebase |
| Install | Add-to-Home-Screen; offline shell | App Store / Play Store |
| Push | Web Push (limited on iOS) | full FCM/APNs |
| Device APIs | limited | full (biometric, secure storage, camera) |
| Recommendation | **operators now** | **field/customer app next** (React Native or Flutter sharing the `/v1` API) |

---

## 3. 11D — Push notifications (design)

- **Backend:** a notification service subscribes to the event stream (command ACK/FAIL,
  alarms, certification/onboarding state) and fans out to **FCM** (Android) / **APNs** (iOS);
  Web Push (VAPID) for the PWA where supported.
- **Triggers:** Sev-1 alarms (from the 10C SLO alerts), command results, DERMS dispatch
  outcomes, device offline.
- **Delivery:** topic/role-scoped (operators see their site's events); per-user device-token
  registry; quiet hours + dedup.

## 4. 11E — Mobile hardening (design)

- **Transport:** TLS **certificate pinning** to the API gateway.
- **Token storage:** iOS Keychain / Android Keystore; never in JS-accessible storage; short
  access TTL + refresh rotation; logout revokes.
- **Step-up auth (MFA) for actuation:** issuing a command/DERMS action from a phone requires
  biometric re-auth (Face/Touch ID) → a short-lived elevated token; read-only views don't.
- **Device integrity:** jailbreak/root detection, screenshot/Recents masking on control
  screens; remote wipe via MDM; least-privilege per role (the existing RBAC maps to mobile scopes).

## 5. 11F — Distribution (design)

- **Operators (internal):** enterprise distribution / **MDM** (Intune, Jamf) — no public store;
  or the PWA via a managed browser.
- **Public/customer app:** Apple App Store + Google Play; staged rollout; crash/analytics
  (Sentry); accessibility + store-review compliance; semantic-versioned releases tied to the
  `/v1` API contract (breaking changes → `/v2`).

---

## 6. Result & next

The mobile requirement from the original ask ("deploy ... even as an app on a phone") is met
on the **fast path**: an installable PWA backed by a mobile-ready, secured, versioned API —
verifiable today. The **native app** (11C-native + 11D push + 11E hardening + 11F store) is
designed and unblocked because the API contract (HTTPS, JWT + refresh, CORS, `/v1`, OpenAPI)
is now stable.

**Remaining roadmap:** **Group E — scale & commercial** (multi-tenancy + SSO + billing,
analytics/ML productionization, GA with SLAs/SOC 2). And the field **9L pilot** + native app
build when hardware/customers are ready.
