# UI Message Specification — v1.0

### DAEP / RE-OS | Authoritative user-facing error message specification

| Field | Value |
|-------|-------|
| Document Type | UI Message Specification |
| Reference ID | UIMS-001 |
| Version | v1.0 |
| Status | **CURRENT — APPROVED** |
| Resolves | **ECR-002-06-01** |
| Parent Documents | DRDP v1.0 §21.3 (Standard Error Code Handling), §22 (State Management); LLD v2.0 §2.2 (Error Handling Standard) |
| Consumed By | `libs/reos-error-handling-ts` (`@reos/error-handling`), `libs/reos_error_handling` (WP-002-06) |
| Change Control | Any wording change requires UI/UX design sign-off and an EECR change record. Engineering must not edit copy ad hoc. |

---

## 1. Purpose

This document is the **single source of truth** for every user-facing message
shown for a standard platform error, in the web portal and the customer,
engineer, and installer Flutter apps. It formally closes ECR-002-06-01, which
was raised because the approved copy was previously maintained outside the
repository (and the in-repo `drdp.md` is the Data Retention and Destruction
Policy — an acronym collision with the design DRDP).

Copy rules applied throughout:

- Plain language; no HTTP jargon, stack traces, or internal system names.
- Never blame the user; always state what to do next.
- Never reveal security detail (which credential check failed, role structure).
- Support reference = the RFC 7807 `error_id` extension member only.

## 2. Summary Table

| HTTP | Internal Code | UI State (`ErrorUiState.kind`) | Localization Key | Severity |
|------|--------------|-------------------------------|------------------|----------|
| 400 | `BAD_REQUEST` | `form_validation` | `error.badRequest` | Warning |
| 401 | `AUTHENTICATION_REQUIRED` | `redirect_sign_in` | `error.sessionExpired` | Warning |
| 403 | `AUTHORIZATION_DENIED` | `permission_denied` | `error.permissionDenied` | Warning |
| 404 | `RESOURCE_NOT_FOUND` | `not_found` | `error.notFound` | Info |
| 409 | `RESOURCE_CONFLICT` | `conflict` | `error.conflict` | Warning |
| 422 | `VALIDATION_ERROR` | `form_validation` | `error.validation` | Warning |
| 429 | `RATE_LIMITED` | `rate_limited` | `error.rateLimited` | Warning |
| 500 | `INTERNAL_ERROR` | `server_error` | `error.serverError` | Critical |
| 502 | `EXTERNAL_SERVICE_ERROR` | `server_error` | `error.upstreamUnavailable` | Critical |
| 503 | `SERVICE_UNAVAILABLE` | `maintenance` | `error.maintenance` | Critical |
| — | (unknown) | `server_error` | `error.unknown` | Critical |

UI state kinds are unchanged from WP-002-06 — this specification supplies
copy only; behavior mapping remains as implemented and reviewed.

## 3. Message Definitions

### 3.1 — 400 Bad Request

| Field | Value |
|-------|-------|
| HTTP Status Code | 400 |
| Internal Error Code | `BAD_REQUEST` |
| User Message | **Some of the information provided needs attention. Please check the highlighted fields and try again.** |
| User Action | Correct the highlighted fields; resubmit. |
| Retry Behaviour | User-initiated resubmit; no automatic retry. |
| Severity | Warning |
| Logging Requirement | `error.mapped` at info with status (client); `request.error` at warning (backend). |
| Support Reference | Not shown. |
| Accessibility Notes | Field errors announced via `aria-live="polite"` / `Semantics(liveRegion:)`; each invalid field programmatically associated with its error text (`aria-describedby`). |
| Localization Key | `error.badRequest` |
| Developer Notes | Rendered inline per field via `fieldErrors`; the message above is the form-level banner when no field map is present. |

### 3.2 — 401 Authentication Required

| Field | Value |
|-------|-------|
| HTTP Status Code | 401 |
| Internal Error Code | `AUTHENTICATION_REQUIRED` |
| User Message | **Your session has ended. Please sign in again to continue.** |
| User Action | Sign in; the app returns the user to where they were. |
| Retry Behaviour | Automatic after successful sign-in (route preserved). No request retry before re-authentication. |
| Severity | Warning |
| Logging Requirement | `error.mapped` at info; never log credentials or tokens. |
| Support Reference | Not shown. |
| Accessibility Notes | Toast/redirect announced assertively; focus moved to the sign-in form on arrival. |
| Localization Key | `error.sessionExpired` |
| Developer Notes | Deliberately does not distinguish expired vs. missing vs. invalid credentials (security: LLD v2.0 §2.2, WP-002-05 §25). |

### 3.3 — 403 Permission Denied

| Field | Value |
|-------|-------|
| HTTP Status Code | 403 |
| Internal Error Code | `AUTHORIZATION_DENIED` |
| User Message | **You don't have permission to view or change this. If you believe you should, contact your administrator.** |
| User Action | Contact tenant administrator; navigate back. |
| Retry Behaviour | None — retrying cannot succeed without a permission change. |
| Severity | Warning |
| Logging Requirement | `error.mapped` at info; never log the required permission or role structure. |
| Support Reference | Not shown. |
| Accessibility Notes | Full-state descriptor (never blank space); lock icon is decorative (`aria-hidden`) with the message as the accessible text. |
| Localization Key | `error.permissionDenied` |
| Developer Notes | Must render a designed state, not blank space (DRDP §22). |

### 3.4 — 404 Not Found

| Field | Value |
|-------|-------|
| HTTP Status Code | 404 |
| Internal Error Code | `RESOURCE_NOT_FOUND` |
| User Message | **We couldn't find what you were looking for. It may have been moved or removed.** |
| User Action | Use the preserved breadcrumbs/navigation to continue. |
| Retry Behaviour | None automatic; user navigates away. |
| Severity | Info |
| Logging Requirement | `error.mapped` at info with the requested path. |
| Support Reference | Not shown. |
| Accessibility Notes | Illustration is decorative (`aria-hidden`); navigation options keyboard-reachable; breadcrumbs preserved so the user is never stranded. |
| Localization Key | `error.notFound` |
| Developer Notes | Also returned for soft-deleted resources (reos-common `is_deleted` filter) — do not word as "never existed". |

### 3.5 — 409 Conflict

| Field | Value |
|-------|-------|
| HTTP Status Code | 409 |
| Internal Error Code | `RESOURCE_CONFLICT` |
| User Message | **This item was changed by someone else while you were working. Please review the latest version and try again.** |
| User Action | Review current state; reapply intended change. |
| Retry Behaviour | User-initiated retry after review; no automatic retry. |
| Severity | Warning |
| Logging Requirement | `error.mapped` at info; backend `detail` carried as `contextDetail` for context-specific display. |
| Support Reference | Not shown. |
| Accessibility Notes | Announced via live region; the Retry control receives focus. |
| Localization Key | `error.conflict` |
| Developer Notes | The backend RFC 7807 `detail` (e.g. "version already published") may be shown beneath this message as context. |

### 3.6 — 422 Validation Error

| Field | Value |
|-------|-------|
| HTTP Status Code | 422 |
| Internal Error Code | `VALIDATION_ERROR` |
| User Message | **Some of the information provided needs attention. Please check the highlighted fields and try again.** |
| User Action | Correct the highlighted fields; resubmit. |
| Retry Behaviour | User-initiated resubmit; no automatic retry. |
| Severity | Warning |
| Logging Requirement | As 400. |
| Support Reference | Not shown. |
| Accessibility Notes | As 400. |
| Localization Key | `error.validation` |
| Developer Notes | Same copy as 400 by design — users do not distinguish syntactic vs. semantic validation; keys are kept separate for future divergence. |

### 3.7 — 429 Rate Limited

| Field | Value |
|-------|-------|
| HTTP Status Code | 429 |
| Internal Error Code | `RATE_LIMITED` |
| User Message | **You've made too many requests in a short time. Please wait a moment before trying again.** |
| User Action | Wait for the countdown; retry when enabled. |
| Retry Behaviour | Countdown from `retry_after` (default 30 s); retry control enabled at zero. No automatic retry. |
| Severity | Warning |
| Logging Requirement | `error.mapped` at info with `retry_after`. |
| Support Reference | Not shown. |
| Accessibility Notes | Countdown announced politely at start and on completion — not every second (screen-reader noise). |
| Localization Key | `error.rateLimited` |
| Developer Notes | Raised by infrastructure (rate limiter), not application code — see reos-exceptions "Not Covered by This Library". |

### 3.8 — 500 Internal Error

| Field | Value |
|-------|-------|
| HTTP Status Code | 500 |
| Internal Error Code | `INTERNAL_ERROR` |
| User Message | **Something went wrong on our side. Your data is safe. Please try again, and contact support with the reference code if the problem continues.** |
| User Action | Retry; contact support quoting the reference code. |
| Retry Behaviour | User-initiated retry. |
| Severity | Critical |
| Logging Requirement | Client: `error.mapped`; backend logs the full failure at error/critical. Client must never receive or display stack traces. |
| Support Reference | **Shown** — the RFC 7807 `error_id` extension member, rendered as "Reference: {error_id}". The ONLY internal detail permitted on screen (WP-002-06 §25). |
| Accessibility Notes | Assertive announcement; reference code selectable/copyable as text. |
| Localization Key | `error.serverError` |
| Developer Notes | The mapper strips every field except `error_id`. |

### 3.9 — 502 Upstream Service Unavailable

| Field | Value |
|-------|-------|
| HTTP Status Code | 502 |
| Internal Error Code | `EXTERNAL_SERVICE_ERROR` |
| User Message | **A service we depend on isn't responding right now. Please try again in a few minutes.** |
| User Action | Wait briefly; retry. |
| Retry Behaviour | User-initiated retry after a short wait. |
| Severity | Critical |
| Logging Requirement | Client: `error.mapped`; backend `ExternalServiceError` names the failing dependency in logs only — never on screen. |
| Support Reference | Shown if `error_id` present (same rule as 500). |
| Accessibility Notes | As 500. |
| Localization Key | `error.upstreamUnavailable` |
| Developer Notes | UI state kind remains `server_error` (unchanged behavior); only the copy is 502-specific. The upstream service name must not appear in the message. |

### 3.10 — 503 Service Unavailable

| Field | Value |
|-------|-------|
| HTTP Status Code | 503 |
| Internal Error Code | `SERVICE_UNAVAILABLE` |
| User Message | **The service is temporarily unavailable, possibly for maintenance. Please try again shortly.** |
| User Action | Wait; retry shortly. |
| Retry Behaviour | User-initiated; apps may poll a status endpoint in a later release. |
| Severity | Critical |
| Logging Requirement | `error.mapped` at info. |
| Support Reference | Not shown. |
| Accessibility Notes | Maintenance icon decorative; message is the accessible text. |
| Localization Key | `error.maintenance` |
| Developer Notes | Raised by infrastructure (load balancer / HAProxy, WP-003-09), not application code. |

### 3.11 — Unknown Error

| Field | Value |
|-------|-------|
| HTTP Status Code | any unmapped value (or unparsable response) |
| Internal Error Code | — |
| User Message | **An unexpected error occurred. Please try again, and contact support with the reference code if the problem continues.** |
| User Action | Retry; contact support quoting the reference code if available. |
| Retry Behaviour | User-initiated retry. |
| Severity | Critical |
| Logging Requirement | `error.mapped` at info with the raw status for diagnostics. |
| Support Reference | Shown if `error_id` present. |
| Accessibility Notes | As 500. |
| Localization Key | `error.unknown` |
| Developer Notes | DRDP §22: there is no acceptable default that shows blank space — every unmapped status renders this state (`server_error` kind). |

## 4. Localization

Release 1 ships English only; the localization keys above are the stable
identifiers for the Release 2+ translation catalogue. Translations require
UI/UX design sign-off per the change-control rule in the header.

## 5. Traceability

| Requirement | Source | Implementation |
|-------------|--------|----------------|
| Status-to-behavior mapping | DRDP v1.0 §21.3 | `mapErrorToUiState` (TS + Dart) |
| No blank error states | DRDP v1.0 §22 | Unknown-error fallback |
| RFC 7807 input shape | LLD v2.0 §2.2 / WP-002-05 | `Rfc7807Response` |
| error_id-only disclosure | WP-002-06 §25 | 500/502/unknown states |
| This copy | ECR-002-06-01 resolution (this document) | `messages.ts`, `map_error.dart` |
