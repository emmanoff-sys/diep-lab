# reos_error_handling — Shared Error Handling (Flutter)

**Authority:** WP-002-06 | DRDP v1.0 §21.3 (Standard Error Code Handling — source of truth), §22 (Error state) | consumes LLD v2.0 §2.2's RFC 7807 shape (WP-002-05)

`mapErrorToUiState()` + `ReosErrorWidget`: every backend error renders a
designed state in the customer, engineer, and installer apps — never a blank
screen, never a raw stack trace.

## User-facing copy (ECR-002-06-01 — RESOLVED)

Message copy in `lib/map_error.dart` is sourced from
[`docs/architecture/UI_MESSAGE_SPEC.md`](../../docs/architecture/UI_MESSAGE_SPEC.md)
§3, the approved specification that closed ECR-002-06-01. Copy changes go
through UI/UX design sign-off and an EECR change record — edit
`UI_MESSAGE_SPEC.md` first, then mirror the change here and in
`libs/reos-error-handling-ts/src/messages.ts`, never ad hoc.

## Status-code mapping (summary — DRDP v1.0 §21.3 is the source of truth)

| HTTP | `ErrorUiKind` | Behavior |
|------|--------------|----------|
| 400 / 422 | `formValidation` | Inline field-error map for forms |
| 401 | `redirectSignIn` | Redirect to sign-in, route preserved |
| 403 | `permissionDenied` | Permission descriptor — not blank |
| 404 | `notFound` | Illustration + breadcrumb-preserved navigation |
| 409 | `conflict` | Context-specific message from `detail` |
| 429 | `rateLimited` | Countdown timer (`retry_after` or 30 s default) |
| 500 | `serverError` | Generic message + `error_id` only (§25) |
| 503 | `maintenance` | Maintenance/degradation descriptor |
| *other* | `serverError` | Fallback — DRDP §22: no blank default |

## Usage

```dart
import 'package:reos_error_handling/reos_error_handling.dart';

final state = mapErrorToUiState(rfc7807Body);
return ReosErrorWidget(state: state, onSignIn: goToSignIn, onRetry: reload);
```

Every mapped error logs `error.mapped` via `reos_logging` (WP-002-04).

## Test

```bash
flutter pub get && flutter test
```
