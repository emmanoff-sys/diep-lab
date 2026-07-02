// Unit tests for mapErrorToUiState (Dart) — WP-002-06 §29.
//
// All 9 DRDP §21.3 status codes produce the specified ErrorUiState shape.
// ECR-002-06-01 is resolved — message copy now asserted exactly against
// userMessages (which mirrors docs/architecture/UI_MESSAGE_SPEC.md §3).

import 'package:flutter_test/flutter_test.dart';
import 'package:reos_error_handling/reos_error_handling.dart';
import 'package:reos_logging/reos_logging.dart';

class MockTransport implements ReosLogTransport {
  final List<ReosLogEntry> entries = [];

  @override
  void send(ReosLogEntry entry) => entries.add(entry);
}

Map<String, Object?> rfc7807(int status, [Map<String, Object?> extra = const {}]) =>
    {'status': status, 'title': 't', 'detail': 'd', 'instance': '/x', ...extra};

void main() {
  late MockTransport transport;

  setUp(() {
    transport = MockTransport();
    ReosLogger.setTransport(transport);
  });

  group('all 9 DRDP §21.3 status codes', () {
    test('400 → formValidation with field errors', () {
      final state = mapErrorToUiState(rfc7807(400, {
        'errors': {'name': 'required'},
      }));
      expect(state.kind, ErrorUiKind.formValidation);
      expect(state.fieldErrors, {'name': 'required'});
    });

    test('422 → formValidation; falls back to detail', () {
      final state =
          mapErrorToUiState(rfc7807(422, {'detail': 'kwp must be positive'}));
      expect(state.kind, ErrorUiKind.formValidation);
      expect(state.fieldErrors, {'_form': 'kwp must be positive'});
    });

    test('401 → redirectSignIn preserving route', () {
      final state = mapErrorToUiState(rfc7807(401));
      expect(state.kind, ErrorUiKind.redirectSignIn);
      expect(state.preserveCurrentRoute, isTrue);
    });

    test('403 → permissionDenied, never blank, approved message', () {
      final state = mapErrorToUiState(rfc7807(403));
      expect(state.kind, ErrorUiKind.permissionDenied);
      expect(state.userMessage, userMessages[403]);
    });

    test('404 → notFound with illustration + breadcrumbs', () {
      final state = mapErrorToUiState(rfc7807(404));
      expect(state.kind, ErrorUiKind.notFound);
      expect(state.showIllustration, isTrue);
      expect(state.preserveBreadcrumbs, isTrue);
    });

    test('409 → conflict with context detail', () {
      final state =
          mapErrorToUiState(rfc7807(409, {'detail': 'version already published'}));
      expect(state.kind, ErrorUiKind.conflict);
      expect(state.contextDetail, 'version already published');
    });

    test('429 → rateLimited with countdown from retry_after', () {
      final state = mapErrorToUiState(rfc7807(429, {'retry_after': 12}));
      expect(state.kind, ErrorUiKind.rateLimited);
      expect(state.retryAfterSeconds, 12);
    });

    test('429 without retry_after uses default countdown', () {
      final state = mapErrorToUiState(rfc7807(429));
      expect(state.retryAfterSeconds, greaterThan(0));
    });

    test('500 → serverError surfacing only error_id', () {
      final state = mapErrorToUiState(rfc7807(500, {
        'error_id': 'err-abc-123',
        'stack': 'Traceback ...',
      }));
      expect(state.kind, ErrorUiKind.serverError);
      expect(state.errorId, 'err-abc-123');
      expect(state.userMessage, isNot(contains('Traceback')));
    });

    test('503 → maintenance descriptor', () {
      final state = mapErrorToUiState(rfc7807(503));
      expect(state.kind, ErrorUiKind.maintenance);
    });
  });

  group('resilience and observability', () {
    test('unknown status falls back to serverError — never blank (DRDP §22)', () {
      final state = mapErrorToUiState(rfc7807(418));
      expect(state.kind, ErrorUiKind.serverError);
      expect(state.userMessage, userMessages[500]);
    });

    test('502 (upstream) also falls back to serverError with the 500 message — unchanged behavior', () {
      final state = mapErrorToUiState(rfc7807(502, {'error_id': 'err-502'}));
      expect(state.kind, ErrorUiKind.serverError);
      expect(state.errorId, 'err-502');
      expect(state.userMessage, userMessages[500]);
    });

    test('every mapped error logs error.mapped with the original status', () {
      mapErrorToUiState(rfc7807(404));
      expect(transport.entries, hasLength(1));
      expect(transport.entries.single.event, 'error.mapped');
      expect(transport.entries.single.context?['status'], 404);
    });

    test('every state carries a non-empty userMessage', () {
      for (final status in [400, 401, 403, 404, 409, 422, 429, 500, 503]) {
        expect(mapErrorToUiState(rfc7807(status)).userMessage, isNotEmpty);
      }
    });

    test('every message exactly matches the approved UI_MESSAGE_SPEC copy — no placeholders remain', () {
      for (final status in [400, 401, 403, 404, 409, 422, 429, 500, 503]) {
        final message = mapErrorToUiState(rfc7807(status)).userMessage;
        expect(message, userMessages[status]);
        expect(message, isNot(contains('PLACEHOLDER')));
      }
    });
  });
}
