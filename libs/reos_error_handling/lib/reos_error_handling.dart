/// reos_error_handling — DAEP / RE-OS shared error handling (Flutter).
///
/// Authority: WP-002-06 | DRDP v1.0 §21.3 (Standard Error Code Handling),
/// §22 (State Management — Error state).
///
/// Usage:
/// ```dart
/// import 'package:reos_error_handling/reos_error_handling.dart';
///
/// final state = mapErrorToUiState(rfc7807Body);
/// return ReosErrorWidget(state: state, onSignIn: goToSignIn);
/// ```
library reos_error_handling;

export 'error_widget.dart' show ReosErrorWidget;
export 'map_error.dart'
    show ErrorUiKind, ErrorUiState, mapErrorToUiState, userMessages;
