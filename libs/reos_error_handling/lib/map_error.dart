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

/// User-facing message copy — APPROVED (ECR-002-06-01 resolved).
///
/// Authority: `docs/architecture/UI_MESSAGE_SPEC.md` §3 — the single source
/// of truth for this copy (resolves ECR-002-06-01, which was raised when the
/// DRDP v1.0 §21.3 copy was unavailable in-repo).
///
/// Per WP-002-06 §39 this copy must not be paraphrased or edited ad hoc. Any
/// wording change requires UI/UX design sign-off and an EECR change record —
/// edit `UI_MESSAGE_SPEC.md` first, then mirror the change here and in
/// `libs/reos-error-handling-ts/src/messages.ts`.
///
/// Only the nine status codes routed by [mapErrorToUiState]'s switch are
/// keyed here (400/401/403/404/409/422/429/500/503). UI_MESSAGE_SPEC.md
/// §3.9 (502) and §3.11 (Unknown Error) are documented for completeness but
/// are, by design, not separately wired — 502 and any unmapped status fall
/// through to the 500 `serverError` state (see the `default` case below).
const Map<int, String> userMessages = {
  400:
      'Some of the information provided needs attention. Please check the highlighted fields and try again.',
  401: 'Your session has ended. Please sign in again to continue.',
  403:
      "You don't have permission to view or change this. If you believe you should, contact your administrator.",
  404: "We couldn't find what you were looking for. It may have been moved or removed.",
  409:
      'This item was changed by someone else while you were working. Please review the latest version and try again.',
  422:
      'Some of the information provided needs attention. Please check the highlighted fields and try again.',
  429:
      "You've made too many requests in a short time. Please wait a moment before trying again.",
  500:
      'Something went wrong on our side. Your data is safe. Please try again, and contact support with the reference code if the problem continues.',
  503:
      'The service is temporarily unavailable, possibly for maintenance. Please try again shortly.',
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
