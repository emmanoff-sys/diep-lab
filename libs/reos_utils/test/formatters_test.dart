// Unit tests for formatters/validators — WP-002-08 §29, §33.

import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:reos_utils/reos_utils.dart';

Future<void> main() async {
  await initializeDateFormatting('en_GB');

  group('formatters', () {
    final d = DateTime.utc(2026, 7, 2, 14, 30);

    test('formatDate renders day month year', () {
      expect(formatDate(d), '2 Jul 2026');
    });

    test('formatDateTime includes time', () {
      expect(formatDateTime(d), '2 Jul 2026, 14:30');
    });

    test('formatCurrency renders EUR with grouping', () {
      expect(formatCurrency(1234.5, 'EUR'), contains('1,234.50'));
    });

    test('formatKwp renders installed capacity', () {
      expect(formatKwp(9.87), '9.87 kWp');
      expect(formatKwp(10, fractionDigits: 1), '10.0 kWp');
    });

    test('formatKwh renders energy with grouping', () {
      expect(formatKwh(1234.5), '1,234.5 kWh');
      expect(formatKwh(0.25, fractionDigits: 2), '0.25 kWh');
    });
  });

  group('validators', () {
    test('accepts valid emails', () {
      expect(isValidEmail('a@b.co'), isTrue);
      expect(isValidEmail('user.name+tag@example.org'), isTrue);
    });

    test('rejects invalid emails', () {
      for (final bad in ['', 'plain', 'a@b', 'a b@c.de', 'x@y.z']) {
        expect(isValidEmail(bad), isFalse, reason: bad);
      }
    });

    test('accepts valid phones', () {
      expect(isValidPhone('+491701234567'), isTrue);
      expect(isValidPhone('0170 123 4567'), isTrue);
    });

    test('rejects invalid phones', () {
      for (final bad in ['', '123', 'phone', '+12', '12345678901234567890']) {
        expect(isValidPhone(bad), isFalse, reason: bad);
      }
    });
  });
}
