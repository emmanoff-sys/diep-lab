# reos_utils — Shared Utilities (Flutter)

**Authority:** WP-002-08 | DRDP v1.0 §23.1 (Dio + auth interceptor) | UI/UX Design Spec v1.0 (unit conventions)

Formatters, validators, and the governed Dio API client for the customer,
engineer, and installer apps.

## API client

```dart
import 'package:reos_utils/reos_utils.dart';

final client = ReosApiClient(baseUrl: config.apiBaseUrl);

try {
  final projects = await client.get<List<Object?>>('/api/v1/projects');
} on ReosApiException catch (e) {
  return ReosErrorWidget(state: e.uiState); // mapped via WP-002-06
}
```

- Bearer token attached by the Dio interceptor via the `tokenSource` hook.
- Every non-2xx response arrives as `ReosApiException` carrying the mapped
  `ErrorUiState` — screens never hand-parse error bodies.
- Request metadata logged at `debug` via `reos_logging`; bodies never logged.

**⚠️ Auth is NOT implemented here (WP-002-08 §25):** `tokenSource` is a hook.
Token storage/retrieval (`flutter_secure_storage` or equivalent) is decided
by the real auth feature — `TODO(auth-feature)` markers in
`lib/api_client.dart` track the gap explicitly.

## Formatters

| Function | Example |
|----------|---------|
| `formatDate(d)` | `"2 Jul 2026"` |
| `formatDateTime(d)` | `"2 Jul 2026, 14:30"` |
| `formatCurrency(1234.5, 'EUR')` | `"€1,234.50"` |
| `formatKwp(9.87)` | `"9.87 kWp"` |
| `formatKwh(1234.5)` | `"1,234.5 kWh"` |

## Validators

`isValidEmail(value)`, `isValidPhone(value)` — client-side UX checks only.

## Test

```bash
flutter pub get && flutter test
```
