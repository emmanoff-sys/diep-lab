/**
 * Unit tests for @reos/config — WP-002-02 §29.
 *
 * Covers: Zod schema rejects invalid environment; typed config object shape;
 * missing required values rejected; optional sentryDsn handling.
 */

import { ZodError } from "zod";

import {
  ENVIRONMENTS,
  getConfig,
  resetConfigForTesting,
} from "../src/config";

const VALID_ENV = {
  NEXT_PUBLIC_API_BASE_URL: "https://api.reos.local",
  NEXT_PUBLIC_ENVIRONMENT: "local",
};

beforeEach(() => {
  resetConfigForTesting();
});

describe("getConfig", () => {
  it("returns a typed config object for valid env", () => {
    const config = getConfig(VALID_ENV);
    expect(config.apiBaseUrl).toBe("https://api.reos.local");
    expect(config.environment).toBe("local");
    expect(config.sentryDsn).toBeUndefined();
  });

  it.each(ENVIRONMENTS)("accepts canonical environment %s", (env) => {
    const config = getConfig({
      ...VALID_ENV,
      NEXT_PUBLIC_ENVIRONMENT: env,
    });
    expect(config.environment).toBe(env);
  });

  it("rejects an environment value outside the canonical set", () => {
    expect(() =>
      getConfig({ ...VALID_ENV, NEXT_PUBLIC_ENVIRONMENT: "prod" }),
    ).toThrow(ZodError);
  });

  it("rejects a missing apiBaseUrl", () => {
    expect(() =>
      getConfig({ NEXT_PUBLIC_ENVIRONMENT: "local" }),
    ).toThrow(ZodError);
  });

  it("rejects a non-URL apiBaseUrl", () => {
    expect(() =>
      getConfig({ ...VALID_ENV, NEXT_PUBLIC_API_BASE_URL: "not-a-url" }),
    ).toThrow(ZodError);
  });

  it("accepts an optional valid sentryDsn", () => {
    const config = getConfig({
      ...VALID_ENV,
      NEXT_PUBLIC_SENTRY_DSN: "https://key@sentry.reos.local/1",
    });
    expect(config.sentryDsn).toBe("https://key@sentry.reos.local/1");
  });

  it("caches the parsed config across calls", () => {
    const first = getConfig(VALID_ENV);
    const second = getConfig({
      ...VALID_ENV,
      NEXT_PUBLIC_ENVIRONMENT: "staging",
    });
    expect(second).toBe(first);
  });
});
