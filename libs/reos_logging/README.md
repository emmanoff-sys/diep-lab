# reos_logging — Shared Client-Side Logging (Flutter)

**Authority:** WP-002-04 | DRDP v1.0 §22 (State Management), §23.1 (Flutter architecture)

Structured client logger for the customer, engineer, and installer apps.
Console transport locally; pluggable remote transport elsewhere.

## Event naming convention

Mirror the backend's `noun.verb` pattern (WP-002-03): `auth.session_expired`,
`error.mapped`, `ui.state_transition`.

## Usage

```dart
import 'package:reos_config/reos_config.dart';
import 'package:reos_logging/reos_logging.dart';

ReosLogger.configure(config.environment);   // once, at app bootstrap

log.info('auth.signed_in', {'method': 'password'});
log.error('request.error', {'status': 500}, err);
log.stateTransition('ProjectList', 'loading', 'error'); // DRDP §22
```

## Transport interface

```dart
class MyRemoteTransport implements ReosLogTransport {
  @override
  void send(ReosLogEntry entry) { /* POST to error-tracking backend */ }
}
ReosLogger.configure(config.environment, remoteTransport: MyRemoteTransport());
```

**OPEN DECISION (WP-002-04 §35):** the remote error-tracking backend is not
selected — non-local environments fall back to the console until the Project
Owner decides. Do not wire a vendor inside this library.

## Security

No PII or credentials in context maps — this library is the mechanism, not a
content filter (WP-002-04 §25).

## Test

```bash
flutter pub get && flutter test
```
