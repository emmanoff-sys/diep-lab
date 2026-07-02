/**
 * Transport interface for @reos/logging — WP-002-04.
 *
 * Backend-agnostic by design (WP-002-04 §9, §39): the remote error-tracking
 * backend is an OPEN DECISION for the Project Owner. Do not wire a specific
 * vendor (Sentry etc.) into this library — implement `Transport` in the app
 * layer once the backend decision is made.
 */

/** Severity levels, mirroring the backend Structlog levels (WP-002-03). */
export type LogLevel = "debug" | "info" | "warn" | "error";

/** A single structured log entry. */
export interface LogEntry {
  level: LogLevel;
  /** Event name in the backend's `noun.verb` convention, e.g. `auth.session_expired`. */
  event: string;
  context?: Record<string, unknown>;
  error?: unknown;
  timestamp: string;
}

/** Pluggable sink — console locally, remote service in other environments. */
export interface Transport {
  send(entry: LogEntry): void;
}

/** Local-development transport: renders to the browser/node console. */
export class ConsoleTransport implements Transport {
  send(entry: LogEntry): void {
    const line = `[${entry.timestamp}] ${entry.level.toUpperCase()} ${entry.event}`;
    switch (entry.level) {
      case "error":
        // eslint-disable-next-line no-console
        console.error(line, entry.context ?? "", entry.error ?? "");
        break;
      case "warn":
        // eslint-disable-next-line no-console
        console.warn(line, entry.context ?? "");
        break;
      default:
        // eslint-disable-next-line no-console
        console.log(line, entry.context ?? "");
    }
  }
}

/**
 * Placeholder for non-local environments until the remote error-tracking
 * backend is selected (open decision — WP-002-04 §35). Buffers nothing and
 * drops entries silently is NOT acceptable, so it falls back to the console;
 * replace via `setTransport()` when the real backend ships.
 */
export class PendingRemoteTransport extends ConsoleTransport {}
