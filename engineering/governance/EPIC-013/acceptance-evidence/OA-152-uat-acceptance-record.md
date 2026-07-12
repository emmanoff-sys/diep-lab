# OA-152 — Utility Partner UAT Acceptance Record

## Stage 2 Evidence — Utility Partner User Acceptance Testing

| Field | Value |
|-------|-------|
| OA Reference | OA-152 |
| UAT Scenario Document | `engineering/governance/EPIC-013/OA-152-uat-scenarios.md` |
| Baseline | `develop/v1.1 @ 1e32419` |

## UAT Scenario Completion Record

| Scenario | Description | Acceptance Criteria |
|----------|-------------|-------------------|
| UAT-01 | Normal Operations Dashboard | Operator confirms dashboard interpretable |
| UAT-02 | State Estimation Review | SE results consistent with network state |
| UAT-03 | Contingency Analysis | Top-N critical contingencies match operator knowledge |
| UAT-04 | Volt/VAR Optimisation Dispatch | Optimal dispatch is operationally feasible |
| UAT-05 | Network Loading Analytics | Loading report reflects actual network state |
| UAT-06 | Asset Criticality Assessment | Rankings match operator expectation |
| UAT-07 | Alert and Logging Verification | `SCADAIngestStale` fires and resolves correctly |
| UAT-08 | Operator Application Walkthrough | All dashboards load; data exports functional |

## Utility Partner Sign-Off

```
UAT SIGN-OFF

Work Package: WP-013-04 / WP-013-08
Baseline: develop/v1.1 @ 1e32419  CONTRACT_VERSION=1.2

Scenarios completed: UAT-01 through UAT-08

Utility partner sign-off:
  Name: ____________________
  Role: ____________________
  Organisation: DIEP Utility Partner
  Date: ____________________
  Signature: _______________

UAT result: [ ] PASS — AUTHORISE STAGING PROMOTION
            [ ] FAIL
```

**Note:** UAT execution is a live operational activity requiring the utility partner
to validate against a deployed DIEP network topology. This record template is
prepared; formal sign-off is obtained during live UAT execution in the staging environment.
