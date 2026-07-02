/**
 * Shared input validators — common shapes needed across every app.
 *
 * Authority: WP-002-08.
 */

// Pragmatic email shape: local@domain.tld — full RFC 5322 is deliberately
// not attempted; the backend remains the authority (client-side is UX only).
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

// E.164-ish: optional +, 8–15 digits, spaces/dashes tolerated in input.
const PHONE_RE = /^\+?[0-9][0-9 \-]{6,18}[0-9]$/;

/** Validate an email address shape (client-side UX check only). */
export function isValidEmail(value: string): boolean {
  return EMAIL_RE.test(value.trim());
}

/** Validate a phone number shape (client-side UX check only). */
export function isValidPhone(value: string): boolean {
  const trimmed = value.trim();
  if (!PHONE_RE.test(trimmed)) {
    return false;
  }
  const digits = trimmed.replace(/[^0-9]/g, "");
  return digits.length >= 8 && digits.length <= 15;
}
