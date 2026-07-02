/**
 * @reos/logging public API — WP-002-04.
 *
 * Usage: `import { log } from "@reos/logging";`
 */

export { configureLogging, log, setTransport } from "./logger";
export { ConsoleTransport, PendingRemoteTransport } from "./transport";
export type { LogEntry, LogLevel, Transport } from "./transport";
