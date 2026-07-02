/// reos_config — DAEP / RE-OS shared configuration framework (Flutter).
///
/// Authority: WP-002-02 | DRDP v1.0 §23.1 (Flutter `core/` structure).
///
/// Environment enum single source of truth
/// ----------------------------------------
/// The [ReosEnvironment] values are the platform-wide canonical set
/// (Roadmap v1.0 §11.2) and MUST stay synchronized with:
///   - libs/reos-config/src/reos_config/settings.py  (Python — WP-002-01)
///   - libs/reos-config-ts/src/config.ts             (TypeScript — WP-002-02)
/// Any change requires updating all three files in one commit.
library reos_config;

import 'package:flutter_dotenv/flutter_dotenv.dart';

/// Canonical DAEP / RE-OS deployment environments (Roadmap v1.0 §11.2).
enum ReosEnvironment {
  local('local'),
  sharedDev('shared_dev'),
  ci('ci'),
  staging('staging'),
  production('production');

  const ReosEnvironment(this.value);

  /// Wire value — matches the Python Literal / TypeScript enum exactly.
  final String value;

  /// Parse a wire value; throws [ArgumentError] for anything outside the
  /// canonical set so a misconfigured app fails fast at startup.
  static ReosEnvironment parse(String raw) {
    for (final env in ReosEnvironment.values) {
      if (env.value == raw) return env;
    }
    throw ArgumentError.value(
      raw,
      'raw',
      'Unknown environment — must be one of: '
          '${ReosEnvironment.values.map((e) => e.value).join(", ")}',
    );
  }
}

/// Typed, validated configuration shared by the customer, engineer, and
/// installer Flutter apps.
///
/// Security (WP-002-02 §25): no sensitive field has a hardcoded default —
/// [apiBaseUrl] and [environment] are required; [sentryDsn] is explicitly
/// optional and null unless provided.
class ReosConfig {
  const ReosConfig({
    required this.apiBaseUrl,
    required this.environment,
    this.sentryDsn,
  });

  final String apiBaseUrl;
  final ReosEnvironment environment;
  final String? sentryDsn;

  /// Load from `--dart-define` compile-time flags (release builds).
  ///
  /// Release builds pass:
  /// `--dart-define=REOS_API_BASE_URL=... --dart-define=REOS_ENVIRONMENT=...`
  factory ReosConfig.fromDartDefine() {
    const apiBaseUrl = String.fromEnvironment('REOS_API_BASE_URL');
    const environment = String.fromEnvironment('REOS_ENVIRONMENT');
    const sentryDsn = String.fromEnvironment('REOS_SENTRY_DSN');
    return ReosConfig._validated(
      apiBaseUrl: apiBaseUrl,
      environmentRaw: environment,
      sentryDsn: sentryDsn.isEmpty ? null : sentryDsn,
    );
  }

  /// Load from a `.env` file via `flutter_dotenv` (local development).
  ///
  /// Call `await dotenv.load()` before this factory.
  factory ReosConfig.fromDotEnv({DotEnv? env}) {
    final source = env ?? dotenv;
    return ReosConfig._validated(
      apiBaseUrl: source.get('REOS_API_BASE_URL', fallback: ''),
      environmentRaw: source.get('REOS_ENVIRONMENT', fallback: ''),
      sentryDsn: source.maybeGet('REOS_SENTRY_DSN'),
    );
  }

  factory ReosConfig._validated({
    required String apiBaseUrl,
    required String environmentRaw,
    String? sentryDsn,
  }) {
    if (apiBaseUrl.isEmpty) {
      throw ArgumentError('REOS_API_BASE_URL is required and was not set.');
    }
    if (environmentRaw.isEmpty) {
      throw ArgumentError('REOS_ENVIRONMENT is required and was not set.');
    }
    return ReosConfig(
      apiBaseUrl: apiBaseUrl,
      environment: ReosEnvironment.parse(environmentRaw),
      sentryDsn: (sentryDsn == null || sentryDsn.isEmpty) ? null : sentryDsn,
    );
  }
}
