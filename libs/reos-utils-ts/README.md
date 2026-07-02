# @reos/utils — Shared Utilities (Next.js)

**Authority:** WP-002-08 | DRDP v1.0 §23.2 (`lib/api/`, `lib/utils/`) | UI/UX Design Spec v1.0 (unit conventions)

Formatters, validators, and the governed API client — one client for every
network call, one formatter for every displayed value.

## API client

```ts
import { ReosApiClient, ReosApiError } from "@reos/utils";

const client = new ReosApiClient(); // baseUrl from @reos/config

try {
  const projects = await client.get<Project[]>("/api/v1/projects");
} catch (err) {
  if (err instanceof ReosApiError) {
    render(err.uiState); // already mapped via @reos/error-handling (WP-002-06)
  }
}
```

- Bearer token attached via the `tokenSource` hook when present.
- Every non-2xx response arrives as a `ReosApiError` carrying the mapped
  `ErrorUiState` — screens never hand-parse error bodies.
- Request metadata (method/URL/status/duration) logged at `debug` via
  `@reos/logging`; bodies are never logged (PII, §26).

**⚠️ Auth is NOT implemented here (WP-002-08 §25):** `tokenSource` is a hook.
Token storage/retrieval (httpOnly cookie or equivalent secure mechanism) is
decided by the real auth feature — `TODO(auth-feature)` markers in
`src/apiClient.ts` track the gap explicitly.

## Formatters

| Function | Example |
|----------|---------|
| `formatDate(d)` | `"2 Jul 2026"` |
| `formatDateTime(d)` | `"2 Jul 2026, 14:30"` |
| `formatCurrency(1234.5, "EUR")` | `"€1,234.50"` |
| `formatKwp(9.87)` | `"9.87 kWp"` |
| `formatKwh(1234.5)` | `"1,234.5 kWh"` |

## Validators

`isValidEmail(value)`, `isValidPhone(value)` — client-side UX checks only;
the backend remains the validation authority.

## Build & test

```bash
npm ci && npm run build && npm test
```
