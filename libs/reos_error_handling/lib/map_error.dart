/// mapErrorToUiState — DAEP / RE-OS shared error mapping (Flutter).
///
/// Authority: WP-002-06 | DRDP v1.0 §21.3 (status-to-behavior table),
/// §22 (Error state — no blank screens, ever).
/// Consumes the RFC 7807 shape produced by libs/reos-exceptions (WP-002-05).
///
/// Security (WP-002-06 §25): the 500 state surfaces ONLY the `error_id`
/// reference — fields outside the approved shape are stripped.
library map_error;

import 'package:reos_logging/reos_logging.dart';

/// User-facing message copy — ⚠️ PLACEHOLDER PENDING ECR-002-06-01 ⚠️
///
/// DRDP v1.0 §21.3's approved copy is maintained externally and is not
/// available in this repository (the in-repo `docs/architecture/drdp.md` is
/// the Data Retention and Destruction Policy — acronym collision). Per
/// WP-002-06 §39 this copy must not be paraphrased or invented; replace
/// these placeholders verbatim when ECR-002-06-01 is resolved. Do not ship
/// any app using these placeholders.
const Map<int, String> userMessages = {
  400: '[PLACEHOLDER ECR-002-06-01] Please check the highlighted fields and try again.',
  401: '[PLACEHOLDER ECR-002-06-01] Your session has ended. Please sign in again.',
  403: "[PLACEHOLDER ECR-002-06-01] You don't have permission to view this.",
  404: "[PLACEHOLDER ECR-002-06-01] We couldn't find what you were looking for.",
  409: '[PLACEHOLDER ECR-002-06-01] This item was changed elsewhere. Please review and retry.',
  422: '[PLACEHOLDER ECR-002-06-01] Please check the highlighted fields and try again.',
  429: '[PLACEHOLDER ECR-002-06-01] Too many requests. Please wait and try again.',
  500: '[PLACEHOLDER ECR-002-06-01] Something went wrong on our side.',
  503: '[PLACEHOLDER ECR-002-06-01] The service is temporarily unavailable.',
};

/// UI error-state kinds per DRDP v1.0 §21.3.
enum ErrorUiKind {
  formValidation, // 400 / 422 — inline field errors
  redirectSignIn, // 401 — preserve route, toast
  permissionDenied, // 403 — descriptor, never blank
  notFound, // 404 — illustration + breadcrumb-preserved nav
  conflict, // 409 — context-specific message
  rateLimited, // 429 — countdown timer
  serverError, // 500 — generic + error_id for support
  maintenance, // 503 — maintenance / degradation
}

/// Typed UI error-state descriptor consumed by [ReosErrorWidget].
class ErrorUiState {
  const ErrorUiState({
    required this.kind,
    required this.userMessage,
    this.fieldErrors = const {},
    this.contextDetail,
    this.retryAfterSeconds,
    this.errorId,
    this.preserveCurrentRoute = false,
    this.showIllustration = false,
    this.preserveBreadcrumbs = false,
  });

  final ErrorUiKind kind;
  final String userMessage;
  final Map<String, String> fieldErrors;
  final String? contextDetail;
  final int? retryAfterSeconds;
  final String? errorId;
  final bool preserveCurrentRoute;
  final bool showIllustration;
  final bool preserveBreadcrumbs;
}

const int _defaultRetryAfterSeconds = 30;

Map<String, String> _extractFieldErrors(Map<String, Object?> response) {
  final raw = response['errors'] ?? response['field_errors'];
  if (raw is Map) {
    return raw.map((key, value) => MapEntry('$key', '$value'));
  }
  final detail = response['detail'];
  return detail is String && detail.isNotEmpty ? {'_form': detail} : {};
}

/// Map a decoded RFC 7807 response body to the DRDP §21.3 UI state.
///
/// Unrecognized status codes fall back to the generic server-error state —
/// DRDP §22: there is no acceptable default that shows blank space.
/// Every mapped error logs `error.mapped` (WP-002-06 §26).
ErrorUiState mapErrorToUiState(Map<String, Object?> response) {
  final status = response['status'] is int ? response['status']! as int : 500;
  log.info('error.mapped', {'status': status, 'code': response['code']});

  String message(int code) => userMessages[code] ?? userMessages[500]!;

  switch (status) {
    case 400:
    case 422:
      return ErrorUiState(
        kind: ErrorUiKind.formValidation,
        userMessage: message(status),
        fieldErrors: _extractFieldErrors(response),
      );
    case 401:
      return ErrorUiState(
        kind: ErrorUiKind.redirectSignIn,
        userMessage: message(401),
        preserveCurrentRoute: true,
      );
    case 403:
      return ErrorUiState(
        kind: ErrorUiKind.permissionDenied,
        userMessage: message(403),
      );
    case 404:
      return ErrorUiState(
        kind: ErrorUiKind.notFound,
        userMessage: message(404),
        showIllustration: true,
        preserveBreadcrumbs: true,
      );
    case 409:
      return ErrorUiState(
        kind: ErrorUiKind.conflict,
        userMessage: message(409),
        contextDetail: response['detail'] is String ? response['detail']! as String : '',
      );
    case 429:
      final retryAfter = response['retry_after'];
      return ErrorUiState(
        kind: ErrorUiKind.rateLimited,
        userMessage: message(429),
        retryAfterSeconds: retryAfter is int && retryAfter > 0
            ? retryAfter
            : _defaultRetryAfterSeconds,
      );
    case 503:
      return ErrorUiState(
        kind: ErrorUiKind.maintenance,
        userMessage: message(503),
      );
    case 500:
    default:
      return ErrorUiState(
        kind: ErrorUiKind.serverError,
        userMessage: message(500),
        errorId: response['error_id'] is String ? response['error_id']! as String : null,
      );
  }
}
