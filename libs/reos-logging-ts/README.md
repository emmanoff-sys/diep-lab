# @reos/logging — Shared Client-Side Logging (Next.js)

**Authority:** WP-002-04 | DRDP v1.0 §22 (State Management), §23.2 (Next.js architecture)

Structured client logger with severity levels and a pluggable transport:
console locally, remote sink in every other environment.

## Event naming convention

Mirror the backend's `noun.verb` pattern (WP-002-03): `auth.session_expired`,
`error.mapped`, `ui.state_transition`. Do not invent free-text messages.

## Usage

```ts
import { getConfig } from "@reos/config";
import { configureLogging, log } from "@reos/logging";

configureLogging(getConfig().environment);   // once, at app bootstrap

log.info("auth.signed_in", { method: "password" });
log.error("request.error", { status: 500 }, err);
log.stateTransition("ProjectList", "loading", "error"); // DRDP §22
```

## Transport interface

```ts
import type { LogEntry, Transport } from "@reos/logging";

class MyRemoteTransport implements Transport {
  send(entry: LogEntry): void { /* POST to error-tracking backend */ }
}
configureLogging(environment, new MyRemoteTransport());
```

**OPEN DECISION (WP-002-04 §35):** the remote error-tracking backend
(e.g. Sentry) is not selected. Until it is, non-local environments fall back
to the console via `PendingRemoteTransport`. This decision belongs to the
Project Owner — do not wire a vendor inside this library.

## Security

No PII or credentials in `context` objects — this library is the mechanism,
not a content filter (WP-002-04 §25). Feature teams review their own payloads.

## Build & test

```bash
npm ci && npm run build && npm test
```
