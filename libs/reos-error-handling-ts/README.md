# @reos/error-handling — Shared Error Handling (Next.js)

**Authority:** WP-002-06 | DRDP v1.0 §21.3 (Standard Error Code Handling — source of truth), §22 (Error state) | consumes LLD v2.0 §2.2's RFC 7807 shape (WP-002-05)

`mapErrorToUiState()` + `<ReosErrorBoundary>`: every backend error renders a
designed state — never a blank screen, never a raw stack trace.

## ⚠️ OPEN ECR — user-facing copy (ECR-002-06-01)

DRDP v1.0 §21.3's approved "User Message" copy is maintained **externally**
and is not in this repository (`docs/architecture/drdp.md` is the *Data
Retention and Destruction Policy* — an acronym collision). All user-facing
strings in `src/messages.ts` are `[PLACEHOLDER ECR-002-06-01]`-prefixed and
**must be replaced verbatim from DRDP §21.3 before any app ships**. Copy
changes go through the UI/UX design process, never ad hoc edits here.

## Status-code mapping (summary — DRDP v1.0 §21.3 is the source of truth)

| HTTP | `ErrorUiState.kind` | Behavior |
|------|--------------------|----------|
| 400 / 422 | `form_validation` | Inline field-error map for forms |
| 401 | `redirect_sign_in` | Redirect to sign-in, current route preserved |
| 403 | `permission_denied` | Permission descriptor — not blank |
| 404 | `not_found` | Illustration + breadcrumb-preserved navigation |
| 409 | `conflict` | Context-specific message from `detail` |
| 429 | `rate_limited` | Countdown timer (`retry_after` or 30 s default) |
| 500 | `server_error` | Generic message + `error_id` only (§25) |
| 503 | `maintenance` | Maintenance/degradation descriptor |
| *other* | `server_error` | Fallback — DRDP §22: no blank default |

## Usage

```tsx
import { mapErrorToUiState, ReosErrorBoundary } from "@reos/error-handling";

const uiState = mapErrorToUiState(await response.json());
// switch (uiState.kind) { ... render designed state ... }

<ReosErrorBoundary>
  <App />
</ReosErrorBoundary>
```

Every mapped error logs `error.mapped` via `@reos/logging` (WP-002-04).

## Build & test

```bash
npm ci && npm run build && npm test
```
