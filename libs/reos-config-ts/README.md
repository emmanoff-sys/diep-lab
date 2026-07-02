# @reos/config — Shared Configuration Framework (Next.js)

**Authority:** WP-002-02 | DRDP v1.0 §23.2 (Next.js `lib/` structure)

Zod-validated, typed environment configuration for the DAEP / RE-OS web portal.
Fails fast at startup on any missing or invalid value.

## Fields

| Field | Type | Env Var | Required | Notes |
|-------|------|---------|----------|-------|
| `apiBaseUrl` | `string` (URL) | `NEXT_PUBLIC_API_BASE_URL` | yes | Backend API root |
| `environment` | `"local" \| "shared_dev" \| "ci" \| "staging" \| "production"` | `NEXT_PUBLIC_ENVIRONMENT` | yes | Canonical set — synchronized with Python/Dart (see `src/config.ts` header) |
| `sentryDsn` | `string` (URL) | `NEXT_PUBLIC_SENTRY_DSN` | no | Explicitly optional; no default (WP-002-02 §25) |

## Usage

```ts
import { getConfig } from "@reos/config";

const config = getConfig(); // throws ZodError if invalid — fail fast
fetch(`${config.apiBaseUrl}/api/v1/health`);
```

## Example configuration

```dotenv
NEXT_PUBLIC_API_BASE_URL=https://api.reos.local
NEXT_PUBLIC_ENVIRONMENT=local
# NEXT_PUBLIC_SENTRY_DSN=   (optional — omit unless error tracking is wired)
```

## Build & test

```bash
npm ci          # never npm install — DEPENDENCY_POLICY.md §5
npm run build   # tsc → dist/
npm test        # jest
```

## Traceability

Environment enum mirrors `libs/reos-config` (Python, WP-002-01) and
`libs/reos_config` (Dart) — single-source-of-truth comment block in `src/config.ts`.
