/// ReosErrorWidget — renders DRDP §21.3 error states consistently.
///
/// Authority: WP-002-06 | DRDP v1.0 §22 (Error state — no blank screens,
/// no raw stack traces).
library error_widget;

import 'package:flutter/material.dart';

import 'map_error.dart';

/// Renders an [ErrorUiState] produced by [mapErrorToUiState].
///
/// Apps may pass builders to restyle states, but the default rendering
/// guarantees every state shows the user message — never blank space.
class ReosErrorWidget extends StatelessWidget {
  const ReosErrorWidget({
    required this.state,
    this.onSignIn,
    this.onRetry,
    super.key,
  });

  final ErrorUiState state;

  /// Invoked for the 401 redirect-to-sign-in action (route preserved by
  /// the caller per [ErrorUiState.preserveCurrentRoute]).
  final VoidCallback? onSignIn;

  /// Invoked by retryable states (409 conflict, 429 after countdown).
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      liveRegion: true,
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (state.kind == ErrorUiKind.notFound && state.showIllustration)
              const Icon(Icons.search_off, size: 64),
            if (state.kind == ErrorUiKind.serverError)
              const Icon(Icons.error_outline, size: 64),
            if (state.kind == ErrorUiKind.maintenance)
              const Icon(Icons.build_circle_outlined, size: 64),
            if (state.kind == ErrorUiKind.permissionDenied)
              const Icon(Icons.lock_outline, size: 64),
            const SizedBox(height: 16),
            Text(state.userMessage, textAlign: TextAlign.center),
            if (state.kind == ErrorUiKind.serverError && state.errorId != null)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(
                  'Reference: ${state.errorId}',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ),
            if (state.kind == ErrorUiKind.rateLimited &&
                state.retryAfterSeconds != null)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: _RetryCountdown(
                  seconds: state.retryAfterSeconds!,
                  onRetry: onRetry,
                ),
              ),
            if (state.kind == ErrorUiKind.redirectSignIn && onSignIn != null)
              Padding(
                padding: const EdgeInsets.only(top: 16),
                child: FilledButton(
                  onPressed: onSignIn,
                  child: const Text('Sign in'),
                ),
              ),
            if (state.kind == ErrorUiKind.conflict && onRetry != null)
              Padding(
                padding: const EdgeInsets.only(top: 16),
                child: OutlinedButton(
                  onPressed: onRetry,
                  child: const Text('Retry'),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// Countdown for the 429 rate-limited state (DRDP §21.3 countdown-timer
/// behavior); enables retry when the countdown reaches zero.
class _RetryCountdown extends StatefulWidget {
  const _RetryCountdown({required this.seconds, this.onRetry});

  final int seconds;
  final VoidCallback? onRetry;

  @override
  State<_RetryCountdown> createState() => _RetryCountdownState();
}

class _RetryCountdownState extends State<_RetryCountdown> {
  late int _remaining = widget.seconds;

  @override
  void initState() {
    super.initState();
    _tick();
  }

  Future<void> _tick() async {
    while (_remaining > 0 && mounted) {
      await Future<void>.delayed(const Duration(seconds: 1));
      if (!mounted) return;
      setState(() => _remaining -= 1);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_remaining > 0) {
      return Text('Try again in $_remaining s');
    }
    return OutlinedButton(
      onPressed: widget.onRetry,
      child: const Text('Try again'),
    );
  }
}
