/**
 * Structured client-side logger for the DAEP / RE-OS web portal — WP-002-04.
 *
 * Authority: DRDP v1.0 §22 (State Management — state transitions must be
 * observable), §23.2 (Next.js architecture).
 *
 * Event naming follows the backend's `noun.verb` convention (WP-002-03),
 * e.g. `auth.session_expired`, `error.mapped`.
 *
 * Security (WP-002-04 §25): this library provides the mechanism, not a
 * content filter — consuming feature teams must review context objects for
 * PII/credentials before logging. Documented limitation, not silently solved.
 */

import type { Environment } from "@reos/config";

import {
  ConsoleTransport,
  PendingRemoteTransport,
  type LogEntry,
  type LogLevel,
  type Transport,
} from "./transport";

let activeTransport: Transport = new ConsoleTransport();

/**
 * Select the transport for the given environment: console for `local`,
 * the pluggable remote transport otherwise (WP-002-04 §15).
 */
export function configureLogging(
  environment: Environment,
  remoteTransport?: Transport,
): void {
  activeTransport =
    environment === "local"
      ? new ConsoleTransport()
      : (remoteTransport ?? new PendingRemoteTransport());
}

/** Override the active transport directly (app wiring / tests). */
export function setTransport(transport: Transport): void {
  activeTransport = transport;
}

function emit(
  level: LogLevel,
  event: string,
  context?: Record<string, unknown>,
  error?: unknown,
): void {
  const entry: LogEntry = {
    level,
    event,
    context,
    error,
    timestamp: new Date().toISOString(),
  };
  activeTransport.send(entry);
}

export const log = {
  debug(event: string, context?: Record<string, unknown>): void {
    emit("debug", event, context);
  },
  info(event: string, context?: Record<string, unknown>): void {
    emit("info", event, context);
  },
  warn(event: string, context?: Record<string, unknown>): void {
    emit("warn", event, context);
  },
  error(event: string, context?: Record<string, unknown>, error?: unknown): void {
    emit("error", event, context, error);
  },
  /**
   * Log a UI state transition — directly supports DRDP v1.0 §22's
   * requirement that every state transition be predictable and observable.
   */
  stateTransition(component: string, fromState: string, toState: string): void {
    emit("info", "ui.state_transition", { component, fromState, toState });
  },
};
