/**
 * reos-config-ts — DAEP / RE-OS shared configuration framework (Next.js).
 *
 * Authority: WP-002-02 | DRDP v1.0 §23.2 (Next.js `lib/` structure).
 *
 * Environment enum single source of truth
 * ----------------------------------------
 * The environment values below are the platform-wide canonical set
 * (Roadmap v1.0 §11.2) and MUST stay synchronized with:
 *   - libs/reos-config/src/reos_config/settings.py   (Python — WP-002-01)
 *   - libs/reos_config/lib/reos_config.dart          (Dart — WP-002-02)
 * Any change requires updating all three files in one commit.
 */

import { z } from "zod";

export const ENVIRONMENTS = [
  "local",
  "shared_dev",
  "ci",
  "staging",
  "production",
] as const;

export type Environment = (typeof ENVIRONMENTS)[number];

/**
 * Typed, validated configuration for the DAEP / RE-OS web portal.
 *
 * Security (WP-002-02 §25): no sensitive field has a hardcoded default —
 * `apiBaseUrl` and `environment` are required-with-no-default; `sentryDsn`
 * is explicitly optional and undefined unless provided.
 */
export interface ReosConfig {
  apiBaseUrl: string;
  environment: Environment;
  sentryDsn?: string;
}

const configSchema = z.object({
  apiBaseUrl: z.string().url(),
  environment: z.enum(ENVIRONMENTS),
  sentryDsn: z.string().url().optional(),
});

/**
 * Raw environment source — defaults to `process.env`; injectable for tests
 * and non-Node runtimes (dependency-injection principle, EPIC-002).
 */
export type EnvSource = Record<string, string | undefined>;

let cachedConfig: ReosConfig | null = null;

/**
 * Read, validate, and cache the application configuration.
 *
 * Throws a `ZodError` describing every invalid/missing field if validation
 * fails — the app fails fast at startup rather than at first use.
 */
export function getConfig(env: EnvSource = process.env): ReosConfig {
  if (cachedConfig !== null) {
    return cachedConfig;
  }
  const parsed = configSchema.parse({
    apiBaseUrl: env.NEXT_PUBLIC_API_BASE_URL,
    environment: env.NEXT_PUBLIC_ENVIRONMENT,
    sentryDsn: env.NEXT_PUBLIC_SENTRY_DSN,
  });
  cachedConfig = parsed;
  return parsed;
}

/** Reset the cached config — test use only. */
export function resetConfigForTesting(): void {
  cachedConfig = null;
}
