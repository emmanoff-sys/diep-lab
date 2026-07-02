/// reos_logging — DAEP / RE-OS shared client-side logging (Flutter).
///
/// Authority: WP-002-04 | DRDP v1.0 §22 (state transitions must be
/// observable), §23.1 (Flutter architecture).
///
/// Event naming follows the backend `noun.verb` convention (WP-002-03),
/// e.g. `auth.session_expired`, `error.mapped`.
///
/// Security (WP-002-04 §25): this library provides the mechanism, not a
/// content filter — feature teams must review context maps for PII or
/// credentials before logging. Documented limitation, not silently solved.
///
/// The remote transport backend is an OPEN DECISION for the Project Owner
/// (WP-002-04 §35) — implement [ReosLogTransport] in the app layer once the
/// backend is selected; do not couple this library to a vendor.
library reos_logging;

import 'dart:developer' as developer;

import 'package:reos_config/reos_config.dart';

/// Severity levels, mirroring the backend Structlog levels.
enum ReosLogLevel { debug, info, warn, error }

/// A single structured log entry.
class ReosLogEntry {
  ReosLogEntry({
    required this.level,
    required this.event,
    this.context,
    this.error,
  }) : timestamp = DateTime.now().toUtc();

  final ReosLogLevel level;

  /// Event name in the `noun.verb` convention.
  final String event;
  final Map<String, Object?>? context;
  final Object? error;
  final DateTime timestamp;
}

/// Pluggable sink — console locally, remote service in other environments.
abstract interface class ReosLogTransport {
  void send(ReosLogEntry entry);
}

/// Local-development transport: renders via `dart:developer`.
class ConsoleTransport implements ReosLogTransport {
  const ConsoleTransport();

  @override
  void send(ReosLogEntry entry) {
    developer.log(
      '${entry.event} ${entry.context ?? {}}',
      time: entry.timestamp,
      level: switch (entry.level) {
        ReosLogLevel.debug => 500,
        ReosLogLevel.info => 800,
        ReosLogLevel.warn => 900,
        ReosLogLevel.error => 1000,
      },
      name: 'reos',
      error: entry.error,
    );
  }
}

/// Structured client-side logger shared by the customer, engineer, and
/// installer Flutter apps.
class ReosLogger {
  ReosLogger._(this._transport);

  static ReosLogger _instance = ReosLogger._(const ConsoleTransport());

  /// The process-wide logger instance.
  static ReosLogger get instance => _instance;

  final ReosLogTransport _transport;

  /// Select the transport for [environment]: console for `local`, the
  /// provided [remoteTransport] otherwise (WP-002-04 §15). Falls back to the
  /// console if no remote transport has been wired yet (open decision).
  static void configure(
    ReosEnvironment environment, {
    ReosLogTransport? remoteTransport,
  }) {
    _instance = ReosLogger._(
      environment == ReosEnvironment.local
          ? const ConsoleTransport()
          : (remoteTransport ?? const ConsoleTransport()),
    );
  }

  /// Override the active transport directly (app wiring / tests).
  static void setTransport(ReosLogTransport transport) {
    _instance = ReosLogger._(transport);
  }

  void _emit(
    ReosLogLevel level,
    String event, [
    Map<String, Object?>? context,
    Object? error,
  ]) {
    _transport.send(
      ReosLogEntry(level: level, event: event, context: context, error: error),
    );
  }

  void debug(String event, [Map<String, Object?>? context]) =>
      _emit(ReosLogLevel.debug, event, context);

  void info(String event, [Map<String, Object?>? context]) =>
      _emit(ReosLogLevel.info, event, context);

  void warn(String event, [Map<String, Object?>? context]) =>
      _emit(ReosLogLevel.warn, event, context);

  void error(String event, [Map<String, Object?>? context, Object? err]) =>
      _emit(ReosLogLevel.error, event, context, err);

  /// Log a UI state transition — directly supports DRDP v1.0 §22's
  /// requirement that every state transition be predictable and observable.
  void stateTransition(String component, String fromState, String toState) =>
      _emit(ReosLogLevel.info, 'ui.state_transition', {
        'component': component,
        'fromState': fromState,
        'toState': toState,
      });
}

/// Convenience accessor: `log.info('auth.signed_in')`.
ReosLogger get log => ReosLogger.instance;
