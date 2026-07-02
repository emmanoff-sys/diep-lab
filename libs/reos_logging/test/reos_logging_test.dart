// Unit tests for reos_logging — WP-002-04 §29.
//
// Covers: mock remote transport receives entries in non-local envs;
// severity levels; stateTransition helper shape.

import 'package:flutter_test/flutter_test.dart';
import 'package:reos_config/reos_config.dart';
import 'package:reos_logging/reos_logging.dart';

class MockTransport implements ReosLogTransport {
  final List<ReosLogEntry> entries = [];

  @override
  void send(ReosLogEntry entry) => entries.add(entry);
}

void main() {
  group('transport selection', () {
    test('remote transport used in non-local environment', () {
      final remote = MockTransport();
      ReosLogger.configure(ReosEnvironment.staging, remoteTransport: remote);
      log.info('auth.session_expired', {'userId': 'u-1'});
      expect(remote.entries, hasLength(1));
      expect(remote.entries.first.event, 'auth.session_expired');
    });

    test('remote transport ignored in local environment', () {
      final remote = MockTransport();
      ReosLogger.configure(ReosEnvironment.local, remoteTransport: remote);
      log.info('dev.event');
      expect(remote.entries, isEmpty);
    });
  });

  group('severity levels', () {
    late MockTransport transport;

    setUp(() {
      transport = MockTransport();
      ReosLogger.setTransport(transport);
    });

    test('debug/info/warn recorded with context', () {
      log.debug('a.b', {'x': 1});
      log.info('c.d', {'y': 2});
      log.warn('e.f');
      expect(
        transport.entries.map((e) => e.level),
        [ReosLogLevel.debug, ReosLogLevel.info, ReosLogLevel.warn],
      );
      expect(transport.entries.first.context, {'x': 1});
    });

    test('error recorded with error object', () {
      final boom = StateError('boom');
      log.error('request.error', {'status': 500}, boom);
      expect(transport.entries.single.level, ReosLogLevel.error);
      expect(transport.entries.single.error, boom);
    });

    test('entries carry a UTC timestamp', () {
      log.info('t.s');
      expect(transport.entries.single.timestamp.isUtc, isTrue);
    });
  });

  group('stateTransition helper (DRDP §22)', () {
    test('emits ui.state_transition with component and states', () {
      final transport = MockTransport();
      ReosLogger.setTransport(transport);
      log.stateTransition('ProjectList', 'loading', 'error');
      final entry = transport.entries.single;
      expect(entry.event, 'ui.state_transition');
      expect(entry.context, {
        'component': 'ProjectList',
        'fromState': 'loading',
        'toState': 'error',
      });
    });
  });
}
