/// Shared input validators — common shapes needed across every app.
///
/// Authority: WP-002-08. Client-side UX checks only — the backend remains
/// the validation authority.
library validators;

final RegExp _emailRe = RegExp(r'^[^\s@]+@[^\s@]+\.[^\s@]{2,}$');
final RegExp _phoneRe = RegExp(r'^\+?[0-9][0-9 \-]{6,18}[0-9]$');

/// Validate an email address shape.
bool isValidEmail(String value) => _emailRe.hasMatch(value.trim());

/// Validate a phone number shape (E.164-ish, 8–15 digits).
bool isValidPhone(String value) {
  final trimmed = value.trim();
  if (!_phoneRe.hasMatch(trimmed)) return false;
  final digits = trimmed.replaceAll(RegExp('[^0-9]'), '');
  return digits.length >= 8 && digits.length <= 15;
}
