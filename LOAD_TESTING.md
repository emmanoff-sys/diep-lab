# Load Testing — DAEP / RE-OS

**Authority:** WP-004-12 | Roadmap v1.0 §11.1 Stage 10 (trigger: Weekly+pre-release; tool: k6; budget: <45 minutes; policy: P95 ≤ 500ms @ 1,000 RPS; Alert + review)

## 1. Tool

**k6** (`loadtest/scaffold-load-test.js`) with a ramping-arrival-rate
executor — ramps to 1,000 RPS over 2 minutes, sustains for 35 minutes,
ramps down over 3 minutes (total ~40 minutes, inside the 45-minute budget).

## 2. Performance Target

**P95 ≤ 500ms @ 1,000 RPS** — exact Roadmap specification.

## 3. Policy — Alert + Review (NOT a hard block)

A P95 threshold breach sends a notification alert and must be reviewed
before the release proceeds. It does **not** hard-fail the pipeline
(unlike Stages 1–9's block policies). This is an intentional Roadmap
distinction (`load-test.yml` captures the k6 exit code but does not
propagate it as a workflow failure).

## 4. Trigger

| Trigger | Cadence |
|---------|---------|
| Scheduled | Weekly, Monday 2am UTC (off-peak default — revisit once real usage patterns exist, §39) |
| Manual (`workflow_dispatch`) | Pre-release, on-demand |

## 5. Target Safeguard

**Staging ONLY.** 1,000 RPS sustained load is a deliberate stress test —
running it against Production risks real customer impact. The `target_url`
input defaults to `https://api.staging.reos.internal` and there is no
Production option.

## 6. Release 1 Representativeness Note (WP-004-12 §35)

The scaffold's `/health` endpoint is trivially fast and does not represent
the load profile of a real, database-heavy business endpoint. The P95 number
from Release 1 load tests describes the **mechanism** (correct ramp, correct
threshold assertion, correct alert behavior), not a meaningful production
performance baseline. Extend `loadtest/scaffold-load-test.js` in the release
that ships the first real service.

## 7. Verification (Runtime — requires k6 binary + Staging environment)

```bash
k6 run loadtest/scaffold-load-test.js \
  --env TARGET_URL=https://api.staging.reos.internal \
  --summary-export=k6-summary.json
```

**Status in this repository:** k6 is not installed and no Staging
environment exists — **Runtime PASS Deferred**. Structural PASS: k6
script syntax reviewed; workflow YAML parses cleanly.
