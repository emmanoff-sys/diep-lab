// Unit tests for ReosApiClient (Dart) — WP-002-08 §29, §33.
//
// Auth header attached when token present; mock 404 routed through
// mapErrorToUiState; metadata logged without bodies.

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:reos_error_handling/reos_error_handling.dart';
import 'package:reos_logging/reos_logging.dart';
import 'package:reos_utils/reos_utils.dart';

class MockTransport implements ReosLogTransport {
  final List<ReosLogEntry> entries = [];

  @override
  void send(ReosLogEntry entry) => entries.add(entry);
}

/// Dio adapter stub returning a canned response and capturing the request.
class _StubAdapter implements HttpClientAdapter {
  _StubAdapter(this.statusCode, this.body);

  final int statusCode;
  final String body;
  RequestOptions? lastRequest;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<List<int>>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    lastRequest = options;
    return ResponseBody.fromString(
      body,
      statusCode,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

void main() {
  late MockTransport transport;

  setUp(() {
    transport = MockTransport();
    ReosLogger.setTransport(transport);
  });

  ReosApiClient clientWith(_StubAdapter adapter, {TokenSource? tokenSource}) {
    final dio = Dio();
    dio.httpClientAdapter = adapter;
    return ReosApiClient(
      baseUrl: 'https://api.test.local',
      tokenSource: tokenSource,
      dio: dio,
    );
  }

  test('attaches Bearer token when token source provides one', () async {
    final adapter = _StubAdapter(200, '{"ok": true}');
    final client = clientWith(adapter, tokenSource: () => 'tok-123');
    await client.get<Map<String, Object?>>('/api/v1/things');
    expect(adapter.lastRequest?.headers['Authorization'], 'Bearer tok-123');
  });

  test('omits Authorization header when signed out', () async {
    final adapter = _StubAdapter(200, '{"ok": true}');
    final client = clientWith(adapter);
    await client.get<Map<String, Object?>>('/x');
    expect(adapter.lastRequest?.headers.containsKey('Authorization'), isFalse);
  });

  test('routes a 404 through mapErrorToUiState (WP-002-06)', () async {
    final adapter = _StubAdapter(404, '''
      {"type": "https://errors.re-os.dev/resource_not_found",
       "title": "Customer was not found.",
       "status": 404,
       "detail": "Customer with id '7' was not found.",
       "instance": "/customers/7",
       "code": "RESOURCE_NOT_FOUND"}''');
    final client = clientWith(adapter);
    try {
      await client.get<Map<String, Object?>>('/customers/7');
      fail('expected ReosApiException');
    } on ReosApiException catch (e) {
      expect(e.status, 404);
      expect(e.uiState.kind, ErrorUiKind.notFound);
    }
  });

  test('returns parsed JSON on success', () async {
    final adapter = _StubAdapter(200, '{"id": 7, "name": "x"}');
    final client = clientWith(adapter);
    final result = await client.get<Map<String, Object?>>('/things/7');
    expect(result, {'id': 7, 'name': 'x'});
  });

  test('logs request metadata without bodies (§26)', () async {
    final adapter = _StubAdapter(200, '{"secretPayload": "do-not-log"}');
    final client = clientWith(adapter);
    await client.post<Map<String, Object?>>(
      '/things',
      body: {'secretBody': 'do-not-log-either'},
    );
    final apiLogs =
        transport.entries.where((e) => e.event == 'api.request').toList();
    expect(apiLogs, hasLength(1));
    final serialized = '${apiLogs.single.context}';
    expect(serialized, contains('200'));
    expect(serialized, isNot(contains('do-not-log')));
  });
}
