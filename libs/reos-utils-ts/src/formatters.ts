/**
 * Shared formatters — dates, currency, energy units.
 *
 * Authority: WP-002-08 | UI/UX Design Spec v1.0 (unit/format conventions,
 * engineering-platform terminology: kWp, kWh).
 *
 * Every screen in the web portal and the three Flutter apps must display
 * these value types identically — do not hand-roll local formatting.
 */

const DEFAULT_LOCALE = "en-GB";

/** Format a date for display, e.g. "2 Jul 2026". */
export function formatDate(
  date: Date,
  locale: string = DEFAULT_LOCALE,
): string {
  return new Intl.DateTimeFormat(locale, {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(date);
}

/** Format a date with time, e.g. "2 Jul 2026, 14:30". */
export function formatDateTime(
  date: Date,
  locale: string = DEFAULT_LOCALE,
): string {
  return new Intl.DateTimeFormat(locale, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

/** Format a monetary amount, e.g. formatCurrency(1234.5, "EUR") → "€1,234.50". */
export function formatCurrency(
  amount: number,
  currency: string,
  locale: string = DEFAULT_LOCALE,
): string {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
  }).format(amount);
}

/** Format installed PV capacity, e.g. formatKwp(9.87) → "9.87 kWp". */
export function formatKwp(kwp: number, fractionDigits = 2): string {
  return `${kwp.toFixed(fractionDigits)} kWp`;
}

/** Format energy, e.g. formatKwh(1234.5) → "1,234.5 kWh". */
export function formatKwh(
  kwh: number,
  locale: string = DEFAULT_LOCALE,
  fractionDigits = 1,
): string {
  const value = new Intl.NumberFormat(locale, {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(kwh);
  return `${value} kWh`;
}
