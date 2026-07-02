/// ReosApiClient — the governed Dio API client for the Flutter apps.
///
/// Authority: WP-002-08 | DRDP v1.0 §23.1 (Dio with an auth interceptor
/// adding a Bearer token).
///
/// Every network call goes through this client: it attaches the Bearer token
/// (when a token source is wired), logs request metadata, and routes every
/// non-2xx response through mapErrorToUiState (WP-002-06) — no consuming
/// screen ever hand-parses an error response.
///
/// Security (WP-002-08 §25): token *retrieval/storage* is OUT OF SCOPE here —
/// [TokenSource] is a hook, not an auth implementation. The real auth feature
/// must supply tokens from secure storage (flutter_secure_storage or
/// equivalent).
/// TODO(auth-feature): wire the token source from the real auth feature when
/// it ships — this placeholder hook is a documented gap, not a finished
/// feature.
library api_client;

import 'package:dio/dio.dart';
import 'package:reos_error_handling/reos_error_handling.dart';
import 'package:reos_logging/reos_logging.dart';

/// Hook supplying the current Bearer token, or null when signed out.
typedef TokenSource = String? Function();

/// Thrown for every non-2xx response, carrying the mapped UI state.
class ReosApiException implements Exception {
  const ReosApiException(this.uiState, this.status);

  final ErrorUiState uiState;
  final int status;

  @override
  String toString() => 'ReosApiException(status: $status, kind: ${uiState.kind})';
}

/// Governed API client wrapping Dio per DRDP v1.0 §23.1.
class ReosApiClient {
  ReosApiClient({
    required String baseUrl,
    TokenSource? tokenSource,
    Dio? dio,
  })  : _tokenSource = tokenSource ?? (() => null),
        _dio = dio ?? Dio() {
    _dio.options.baseUrl = baseUrl;
    _dio.options.validateStatus = (_) => true; // errors mapped, not thrown raw
    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) {
          final token = _tokenSource();
          if (token != null) {
            options.headers['Authorization'] = 'Bearer $token';
          }
          options.extra['reos_started_at'] = DateTime.now();
          handler.next(options);
        },
        onResponse: (response, handler) {
          final startedAt =
              response.requestOptions.extra['reos_started_at'] as DateTime?;
          // Metadata only — never bodies (PII risk, WP-002-08 §26).
          log.debug('api.request', {
            'method': response.requestOptions.method,
            'url': response.requestOptions.uri.toString(),
            'status': response.statusCode,
            'durationMs': startedAt == null
                ? null
                : DateTime.now().difference(startedAt).inMilliseconds,
          });
          handler.next(response);
        },
      ),
    );
  }

  final Dio _dio;
  final TokenSource _tokenSource;

  Future<T> get<T>(String path) => _request<T>('GET', path);

  Future<T> post<T>(String path, {Object? body}) =>
      _request<T>('POST', path, body: body);

  Future<T> put<T>(String path, {Object? body}) =>
      _request<T>('PUT', path, body: body);

  Future<T> delete<T>(String path) => _request<T>('DELETE', path);

  Future<T> _request<T>(String method, String path, {Object? body}) async {
    final response = await _dio.request<Object?>(
      path,
      data: body,
      options: Options(method: method),
    );
    final status = response.statusCode ?? 500;
    if (status < 200 || status >= 300) {
      final data = response.data;
      final problem = data is Map<String, Object?>
          ? Map<String, Object?>.from(data)
          : <String, Object?>{'status': status};
      problem['status'] = problem['status'] ?? status;
      throw ReosApiException(mapErrorToUiState(problem), status);
    }
    return response.data as T;
  }
}
