# Release Dashboard — DAEP / RE-OS Program
### EECR v1.0 | Updated: 2026-07-05 (PCS-001)

---

## Program-Level Release Summary

| Release | Name | Epics | WPs (est.) | SP (est.) | Status | Target Quarter |
|---------|------|-------|-----------|----------|--------|---------------|
| R1 | Engineering Foundation | 6 | 47 | 240 | BASELINE PARTIAL — WP-005-04 FROZEN | Q3 2026 |
| R2 | Metering Data Acquisition | 4 | 96 | 480 | PLANNED | Q4 2026 |
| R3 | Customer Self-Service Portal | 4 | 96 | 480 | PLANNED | Q1 2027 |
| R4 | Field Engineer Mobile App | 4 | 96 | 480 | PLANNED | Q2 2027 |
| R5 | Real-time Grid Observability | 4 | 96 | 480 | PLANNED | Q3 2027 |
| R6 | Network Topology Management | 4 | 96 | 480 | PLANNED | Q4 2027 |
| R7 | Work Order & Dispatch Management | 4 | 96 | 480 | PLANNED | Q1 2028 |
| R8 | Billing & Tariff Engine | 4 | 96 | 480 | PLANNED | Q2 2028 |
| R9 | Fault Detection & Alerting | 4 | 96 | 480 | PLANNED | Q3 2028 |
| R10 | Advanced Analytics & Reporting | 4 | 96 | 480 | PLANNED | Q4 2028 |
| R11 | API Gateway & External Integrations | 4 | 96 | 480 | PLANNED | Q1 2029 |
| R12 | Enterprise Hardening & GA | 4 | 113 | 565 | PLANNED | Q2 2029 |

---

## ADMS Programme Extension — EPIC-007

| Field | Value |
|-------|-------|
| Work Package | WP-007 - ADMS Topology Services Foundation |
| Authorisation | PAO-006; PAO-007; PAO-008 |
| Branch | `feature/wp-007-adms-topology-services` |
| Final Engineering Commit | `089b498` |
| Status | COMPLETED / MERGED / BASELINE INTEGRATED |
| GOV-002 Status | PR #40 merged at `5d079bd` |
| Validation | PASS - compile, Ruff, Black, isort, Bandit, WP-007 tests, WP-006 regression, CIM/topology validation, Release 2 classification, `git diff --check` |
| Release Readiness | MERGED UNDER GOV-002 |

WP-007 is recorded as an ADMS programme extension following WP-006-08 baseline
integration. PR #40 merged into `develop/v1.1` at
`5d079bdefcbd41446d5ac3dde30177962b43c52a`. This entry does not alter the
historical R1/R2 roadmap rows that predate PAO-006.

---

## ADMS Programme Extension — EPIC-008

| Field | Value |
|-------|-------|
| Work Package | WP-008 - Operational Network State Foundation |
| Authorisation | WP-008 engineering authorisation (PAO-009 by programme sequence); PAO-011 governed release preparation |
| Branch | `feature/wp-008-operational-network-state` |
| Final Engineering Commit | `bb8682e` |
| Status | ENGINEERING COMPLETE / GOVERNANCE READY |
| GOV-002 Status | PR #41 open - pending governed review |
| Validation | PASS - compile, Ruff, Black, isort, Bandit, WP-008 tests (7), WP-006/WP-007 regression (191), CIM/topology validation (51 passed, 9 skipped), Release 2 classification (128 files), `git diff --check` |
| Release Readiness | READY FOR GOV-002 REVIEW |

WP-008 is recorded as an ADMS programme extension following WP-007 baseline
integration. This entry does not alter the historical R1/R2 roadmap rows that
predate PAO-006. The stacked `feature/wp-009-operations-foundation` branch
awaits WP-008 merge before its own governed release process.

---

## Release 1 — Engineering Foundation

### R1 Progress Summary

| Metric | Value |
|--------|-------|
| Total Work Packages | 47 |
| Approved / Closed | 26 (through WP-005-04 governance baseline) |
| Ready | 0 |
| In Progress | 0 |
| Blocked | 0 |
| Not Started | 21 |
| **Overall Completion** | **55.3% by WP count** |
| Total Story Points | 240 |
| Points Earned | 149 |
| Points Remaining | 91 |
| Sprint Range | S1 – S8 |
| Milestone Range | M1 – M6 |
| Target Release Date | Q3 2026 |

### R1 Epic Progress

| Epic | Title | WPs Total | Complete | In Progress | Remaining | % |
|------|-------|-----------|----------|-------------|-----------|---|
| EPIC-001 | Repository & Engineering Foundation | 9 | 1 | 0 | 8 | 11% |
| EPIC-002 | Core Infrastructure Stack | 8 | 0 | 0 | 8 | 0% |
| EPIC-003 | FastAPI Service Framework | 8 | 0 | 0 | 8 | 0% |
| EPIC-004 | CI/CD Pipeline Foundation | 6 | 0 | 0 | 6 | 0% |
| EPIC-005 | Identity & Access Management | 8 | 4 | 0 | 4 | 50% |
| EPIC-006 | Network Topology Foundation | 8 | 0 | 0 | 8 | 0% |
| **Total** | | **47** | **26** | **0** | **21** | **55%** |

### R1 Sprint Plan

| Sprint | WPs Planned | SP Planned | Status | Target Dates |
|--------|------------|-----------|--------|-------------|
| S1 | WP-001-01 through WP-001-04 | 16 | IN PROGRESS | 2026-07-01 – 2026-07-14 |
| S2 | WP-001-05 through WP-001-09, WP-002-01 through WP-002-04 | 35 | PLANNED | 2026-07-15 – 2026-07-28 |
| S3 | WP-002-05 through WP-002-08, WP-003-01 through WP-003-03 | 33 | PLANNED | 2026-07-29 – 2026-08-11 |
| S4 | WP-003-04 through WP-003-08, WP-004-01 | 20 | PLANNED | 2026-08-12 – 2026-08-25 |
| S5 | WP-004-02 through WP-004-06, WP-005-01 | 28 | PLANNED | 2026-08-26 – 2026-09-08 |
| S6 | WP-005-02 through WP-005-06 | 31 | PLANNED | 2026-09-09 – 2026-09-22 |
| S7 | WP-005-07, WP-005-08, WP-006-01 through WP-006-03 | 31 | PLANNED | 2026-09-23 – 2026-10-06 |
| S8 | WP-006-04 through WP-006-08 | 33 | PLANNED | 2026-10-07 – 2026-10-20 |

### R1 Milestone Gates

| Milestone | Description | WPs Required | Target Date | Status |
|-----------|-------------|-------------|------------|--------|
| M1 — Repo Foundation Complete | All EPIC-001 WPs approved and merged | WP-001-01 through WP-001-09 | 2026-07-28 | IN PROGRESS |
| M2 — Dev Infrastructure Live | All EPIC-002 WPs approved and merged | WP-002-01 through WP-002-08 | 2026-08-11 | PLANNED |
| M3 — Service Framework Ready | All EPIC-003 WPs approved and merged | WP-003-01 through WP-003-08 | 2026-08-25 | PLANNED |
| M4 — CI/CD Pipeline Active | All EPIC-004 WPs approved and merged | WP-004-01 through WP-004-06 | 2026-09-08 | PLANNED |
| M5 — Auth Foundation Live | EPIC-005 tranche through WP-005-04 approved, merged, and baseline frozen; remaining WP-005-05..14 require future authorisation | WP-005-01 through WP-005-04 | 2026-07-05 | PARTIAL BASELINE FROZEN |
| M6 — Topology Foundation Live | All EPIC-006 WPs approved and merged | WP-006-01 through WP-006-08 | 2026-10-20 | IN PROGRESS — WP-006-08 complete and merged under GOV-002 PR #39 |
| **R1 Release Gate** | All milestones passed; release candidate approved | All 47 WPs | **2026-10-27** | **PLANNED** |

### R1 Readiness Gates

| Gate | Owner | Status | Notes |
|------|-------|--------|-------|
| Architecture Review Complete | Enterprise Architect | IN PROGRESS | WP-001-01 approved 98/100; 46 pending |
| Security Scan Clear | DevSecOps Lead | PENDING | No HIGH/CRITICAL findings required |
| All Tests Passing | QA Lead | PENDING | Unit + integration + UAT |
| Documentation Complete | Tech Lead | PENDING | README, ADRs, runbooks |
| CI/CD Pipeline Green | DevSecOps Lead | PASS FOR WP-005-04; PASS FOR WP-006-08 PR #39; PASS FOR WP-007 PR #40; LOCAL PASS FOR WP-008 PAO-011 VALIDATION | Release 2 Validation `28966762132` and Service CI/CD `28966758174` green for WP-006-08; WP-007 Release 2 Validation `28969663917` and Service CI/CD `28969660405` green; WP-008 PR CI pending governed PR creation |
| Operational Acceptance | SRE Lead | PENDING | Health checks, dashboards verified |
| Release Manager Sign-off | Release Manager | PENDING | |
| Product Owner Sign-off | RE-OS PO | PENDING | |

---

## Release 2 — Metering Data Acquisition (Preview)

| Field | Value |
|-------|-------|
| Status | PLANNED |
| Prerequisite | R1 complete |
| Epics | EPIC-007 through EPIC-010 |
| Estimated WPs | 96 |
| Estimated SP | 480 |
| Target | Q4 2026 |
| Key Dependency | DLMS/COSEM test environment (see RISK-002) |

Detailed WP breakdown for R2 will be created at R1 M6 gate.

---

## Release Burndown (Program)

```
Story Points Remaining

12000 |████████████████████████████████████████████████████████ R12
11000 |
10000 |████████████████████████████████████████████████████ R11
 9000 |
 8000 |████████████████████████████████████████████████ R10
 7000 |
 6000 |████████████████████████████████████████████ R9
 5000 |
 4000 |████████████████████████████████████████ R8
 3000 |
 2000 |████████████████████████████████████ R7
 1000 |
  500 |████████████████████████████████ R6
  240 |████████████████████████████ R1 (current)
    5 |▏ NOW (WP-001-01 complete)
      └─────────────────────────────────────────────────────────
       Q3'26  Q4'26  Q1'27  Q2'27  Q3'27  Q4'27  Q1'28  Q2'29
```
