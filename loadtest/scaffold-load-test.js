// DAEP / RE-OS — k6 load test (WP-004-12)
// Authority: Roadmap v1.0 §11.1 Stage 10 (1,000 RPS, P95 ≤ 500ms, Alert+Review)
//
// Target: Staging environment via Nginx VIP (WP-003-09).
// SAFEGUARD: ONLY Staging — never Production (same safeguard as DAST, WP-004-08).
//
// Release 1 note (WP-004-12 §35): the scaffold's trivial /health endpoint does
// not representatively stress-test database-heavy business endpoints. This script
// validates the *mechanism* (correct ramp, correct threshold assertion, correct
// non-blocking Alert+Review behavior). Extend with real business endpoints in the
// release that ships the first real service.

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

// ── Thresholds — Roadmap §11.1 Stage 10 exact performance target ──
// P95 ≤ 500ms @ 1,000 RPS.
// `abortOnFail: false` → threshold breach triggers an ALERT + REVIEW,
// not a hard pipeline halt (Roadmap's "Alert + review" policy, distinct
// from the hard-block policies of Stages 1–9).
export const options = {
  scenarios: {
    ramp_to_1000_rps: {
      executor: "ramping-arrival-rate",
      startRate: 0,
      timeUnit: "1s",
      preAllocatedVUs: 200,
      maxVUs: 500,
      stages: [
        { duration: "2m", target: 1000 },  // ramp to 1,000 RPS over 2 minutes
        { duration: "35m", target: 1000 }, // sustain at 1,000 RPS for 35 minutes
        { duration: "3m", target: 0 },     // ramp down over 3 minutes
        // Total scenario: 40 minutes < the 45-minute job timeout budget.
      ],
    },
  },
  thresholds: {
    // Roadmap exact target: P95 ≤ 500ms
    "http_req_duration": [{ threshold: "p(95)<500", abortOnFail: false }],
    // Error rate < 1% (a reasonable baseline, not in the Roadmap literal — flagged
    // as this WP's own reasonable addition; documented, not silent)
    "http_req_failed": [{ threshold: "rate<0.01", abortOnFail: false }],
  },
};

const BASE_URL = __ENV.TARGET_URL || "https://api.reos.internal";

export default function () {
  // Release 1: test the scaffold's /health endpoint — the only real endpoint.
  // Extend this function with real business endpoints once they exist.
  const res = http.get(`${BASE_URL}/health`, {
    tags: { endpoint: "health" },
  });

  check(res, {
    "status is 200": (r) => r.status === 200,
    "response has status:ok": (r) => {
      try {
        return JSON.parse(r.body).status === "ok";
      } catch {
        return false;
      }
    },
  });

  // No sleep — arrival-rate executor controls the request rate, not VU sleep.
}

export function handleSummary(data) {
  // Output a machine-readable summary for the DORA metrics script (WP-004-14).
  return {
    "k6-summary.json": JSON.stringify(data),
    stdout: JSON.stringify(
      {
        p95_ms: data.metrics.http_req_duration?.values?.["p(95)"] ?? null,
        p50_ms: data.metrics.http_req_duration?.values?.["p(50)"] ?? null,
        rps: data.metrics.http_reqs?.values?.rate ?? null,
        error_rate: data.metrics.http_req_failed?.values?.rate ?? null,
        threshold_breached:
          Object.values(data.metrics).some((m) =>
            m.thresholds
              ? Object.values(m.thresholds).some((t) => t.ok === false)
              : false,
          ),
      },
      null,
      2,
    ),
  };
}
