/// Shared formatters — dates, currency, energy units.
///
/// Authority: WP-002-08 | UI/UX Design Spec v1.0 (unit/format conventions:
/// kWp, kWh). Every screen must display these value types identically.
library formatters;

import 'package:intl/intl.dart';

const String _defaultLocale = 'en_GB';

/// Format a date for display, e.g. "2 Jul 2026".
String formatDate(DateTime date, {String locale = _defaultLocale}) =>
    DateFormat('d MMM yyyy', locale).format(date);

/// Format a date with time, e.g. "2 Jul 2026, 14:30".
String formatDateTime(DateTime date, {String locale = _defaultLocale}) =>
    DateFormat('d MMM yyyy, HH:mm', locale).format(date);

/// Format a monetary amount, e.g. formatCurrency(1234.5, 'EUR') → "€1,234.50".
String formatCurrency(
  num amount,
  String currency, {
  String locale = _defaultLocale,
}) =>
    NumberFormat.currency(locale: locale, name: currency).format(amount);

/// Format installed PV capacity, e.g. formatKwp(9.87) → "9.87 kWp".
String formatKwp(num kwp, {int fractionDigits = 2}) =>
    '${kwp.toStringAsFixed(fractionDigits)} kWp';

/// Format energy, e.g. formatKwh(1234.5) → "1,234.5 kWh".
String formatKwh(
  num kwh, {
  String locale = _defaultLocale,
  int fractionDigits = 1,
}) {
  final pattern = NumberFormat.decimalPatternDigits(
    locale: locale,
    decimalDigits: fractionDigits,
  );
  return '${pattern.format(kwh)} kWh';
}
