/// reos_utils — DAEP / RE-OS shared utilities (Flutter).
///
/// Authority: WP-002-08 | DRDP v1.0 §23.1 | UI/UX Design Spec v1.0.
///
/// Usage:
/// ```dart
/// import 'package:reos_utils/reos_utils.dart';
///
/// final client = ReosApiClient(baseUrl: config.apiBaseUrl);
/// Text(formatKwp(project.installedKwp));
/// ```
library reos_utils;

export 'api_client.dart' show ReosApiClient, ReosApiException, TokenSource;
export 'formatters.dart'
    show formatCurrency, formatDate, formatDateTime, formatKwh, formatKwp;
export 'validators.dart' show isValidEmail, isValidPhone;
