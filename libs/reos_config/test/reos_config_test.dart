// Unit tests for reos_config — WP-002-02 §29.
//
// Covers: config loads correctly from an in-memory dotenv source and from
// validated values; invalid/missing environment values are rejected.

import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:reos_config/reos_config.dart';

void main() {
  group('ReosEnvironment.parse', () {
    test('accepts every canonical environment value', () {
      expect(ReosEnvironment.parse('local'), ReosEnvironment.local);
      expect(ReosEnvironment.parse('shared_dev'), ReosEnvironment.sharedDev);
      expect(ReosEnvironment.parse('ci'), ReosEnvironment.ci);
      expect(ReosEnvironment.parse('staging'), ReosEnvironment.staging);
      expect(ReosEnvironment.parse('production'), ReosEnvironment.production);
    });

    test('rejects values outside the canonical set', () {
      expect(() => ReosEnvironment.parse('prod'), throwsArgumentError);
      expect(() => ReosEnvironment.parse('LOCAL'), throwsArgumentError);
      expect(() => ReosEnvironment.parse(''), throwsArgumentError);
    });
  });

  group('ReosConfig.fromDotEnv', () {
    DotEnv envWith(Map<String, String> values) {
      final env = DotEnv();
      env.testLoad(
        fileInput:
            values.entries.map((e) => '${e.key}=${e.value}').join('\n'),
      );
      return env;
    }

    test('loads a valid .env source', () {
      final config = ReosConfig.fromDotEnv(
        env: envWith({
          'REOS_API_BASE_URL': 'https://api.reos.local',
          'REOS_ENVIRONMENT': 'local',
        }),
      );
      expect(config.apiBaseUrl, 'https://api.reos.local');
      expect(config.environment, ReosEnvironment.local);
      expect(config.sentryDsn, isNull);
    });

    test('loads optional sentry DSN when present', () {
      final config = ReosConfig.fromDotEnv(
        env: envWith({
          'REOS_API_BASE_URL': 'https://api.reos.local',
          'REOS_ENVIRONMENT': 'staging',
          'REOS_SENTRY_DSN': 'https://key@sentry.reos.local/1',
        }),
      );
      expect(config.sentryDsn, 'https://key@sentry.reos.local/1');
    });

    test('missing REOS_API_BASE_URL is rejected', () {
      expect(
        () => ReosConfig.fromDotEnv(
          env: envWith({'REOS_ENVIRONMENT': 'local'}),
        ),
        throwsArgumentError,
      );
    });

    test('invalid environment value is rejected', () {
      expect(
        () => ReosConfig.fromDotEnv(
          env: envWith({
            'REOS_API_BASE_URL': 'https://api.reos.local',
            'REOS_ENVIRONMENT': 'dev',
          }),
        ),
        throwsArgumentError,
      );
    });
  });
}
