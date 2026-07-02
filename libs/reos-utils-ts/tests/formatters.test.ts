/**
 * Unit tests for formatters/validators — WP-002-08 §29, §33.
 */

import {
  formatCurrency,
  formatDate,
  formatKwh,
  formatKwp,
} from "../src/formatters";
import { isValidEmail, isValidPhone } from "../src/validators";

describe("formatters", () => {
  const d = new Date("2026-07-02T14:30:00Z");

  it("formatDate renders day month year", () => {
    expect(formatDate(d)).toBe("2 Jul 2026");
  });

  it("formatCurrency renders EUR with symbol and grouping", () => {
    expect(formatCurrency(1234.5, "EUR")).toBe("€1,234.50");
  });

  it("formatKwp renders installed capacity", () => {
    expect(formatKwp(9.87)).toBe("9.87 kWp");
    expect(formatKwp(10, 1)).toBe("10.0 kWp");
  });

  it("formatKwh renders energy with grouping", () => {
    expect(formatKwh(1234.5)).toBe("1,234.5 kWh");
    expect(formatKwh(0.25, "en-GB", 2)).toBe("0.25 kWh");
  });
});

describe("validators", () => {
  it.each(["a@b.co", "user.name+tag@example.org"])(
    "accepts valid email %s",
    (email) => expect(isValidEmail(email)).toBe(true),
  );

  it.each(["", "plain", "a@b", "a b@c.de", "x@y.z"])(
    "rejects invalid email %s",
    (email) => expect(isValidEmail(email)).toBe(false),
  );

  it.each(["+491701234567", "0170 123 4567", "+44 20-7946-0958"])(
    "accepts valid phone %s",
    (phone) => expect(isValidPhone(phone)).toBe(true),
  );

  it.each(["", "123", "phone", "+12", "12345678901234567890"])(
    "rejects invalid phone %s",
    (phone) => expect(isValidPhone(phone)).toBe(false),
  );
});
