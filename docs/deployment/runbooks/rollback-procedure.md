# OA-098 — Connector Rollback Procedure

## Status

APPROVED (PAO-026)

## Scope

Rollback from a failed or rejected connector deployment in a staging environment.
This procedure is limited to the three external-integration connectors introduced
under PAO-026 (SCADA, GIS, AMI). Production rollback requires separate governance
approval and is not authorised by this document.

## Rollback Decision Criteria

Initiate rollback if any of the following conditions are met during staging validation:

- Any connector fails to reach `status: UP` within 120 seconds of deployment.
- DLQ entries accumulate immediately after startup with no actionable root cause.
- Regression in an existing test suite confirmed against the candidate commit.
- A quality gate (ruff, bandit, black, regression suite) fails for the candidate.
- A governance finding blocks acceptance (e.g. GOV-002 violation, architecture
  baseline deviation).

Do not rollback for transient connectivity issues that self-resolve within the
exponential backoff window. Use the Connector Recovery Runbook for those cases.

## Rollback Procedure

### 1. Record the rollback decision

| Field | Value |
| --- | --- |
| Operator / automation identity | |
| Environment | |
| Candidate commit (being rolled back from) | |
| Target rollback commit | |
| Rollback trigger reason | |
| Decision timestamp | |

### 2. Stop the deployed connectors

Stop all three connector processes or containers in the affected environment.
Confirm the health endpoints are no longer responding.

### 3. Restore the prior connector deployment

Deploy the previous known-good connector image or source commit:

1. Confirm the rollback target commit against governance baseline.
2. Confirm the rollback target passes all quality gates on the rollback commit:
   ruff, black, bandit, and regression suite.
3. Deploy the rollback target using the Connector Startup Runbook.

### 4. Validate rollback

- All three connectors reach `status: UP`.
- `/ready` returns 200 for all three.
- DLQ count is zero.
- No regression in the PAO-026 test suite at the rollback commit level.

### 5. Record rollback completion

| Field | Value |
| --- | --- |
| Rollback completion timestamp | |
| Rollback commit confirmed healthy | |
| Validation outcome | PASS / FAIL |
| Follow-up engineering actions | |

## Post-Rollback Requirements

A rollback completes a staging validation cycle with a REJECT outcome. Before
re-attempting deployment of the candidate or any successor:

1. The rollback trigger cause must be identified and resolved.
2. A new quality gate run must be recorded against the corrected candidate.
3. The staging deployment procedure must be re-executed in full.
4. The rollback event shall be recorded in the EECR change log.
