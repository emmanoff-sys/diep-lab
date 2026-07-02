# reos_config — Shared Configuration Framework (Flutter)

**Authority:** WP-002-02 | DRDP v1.0 §23.1 (Flutter `core/` structure)

Typed, validated environment configuration shared by the customer, engineer,
and installer Flutter apps. Consumed via monorepo path import.

## Fields

| Field | Type | Source Key | Required | Notes |
|-------|------|-----------|----------|-------|
| `apiBaseUrl` | `String` | `REOS_API_BASE_URL` | yes | Backend API root |
| `environment` | `ReosEnvironment` | `REOS_ENVIRONMENT` | yes | `local`, `shared_dev`, `ci`, `staging`, `production` — synchronized with Python/TS (see `lib/reos_config.dart` header) |
| `sentryDsn` | `String?` | `REOS_SENTRY_DSN` | no | Explicitly optional; no default (WP-002-02 §25) |

## Usage

Local development (`.env` via `flutter_dotenv`):

```dart
await dotenv.load();
final config = ReosConfig.fromDotEnv(); // throws ArgumentError — fail fast
```

Release builds (compile-time `--dart-define`):

```bash
flutter build apk --release \
  --dart-define=REOS_API_BASE_URL=https://api.reos.example \
  --dart-define=REOS_ENVIRONMENT=production
```

```dart
final config = ReosConfig.fromDartDefine();
```

## Consume (monorepo path import)

```yaml
# apps/customer-app/pubspec.yaml
dependencies:
  reos_config:
    path: ../../libs/reos_config
```

## Test

```bash
flutter pub get
flutter test
```
