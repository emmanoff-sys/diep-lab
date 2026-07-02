# Architecture Decision Records — Index
### DAEP / RE-OS | `docs/adr/` | Updated: 2026-07-02

> Architecture Decision Records (ADRs) capture binding decisions about the architecture —
> the context that made a decision necessary, the alternatives considered, and the outcome.
> ADRs are immutable once accepted; a superseded ADR is replaced by a new one, never edited.

---

## Authoritative ADR Register

The formal ADR register for DAEP / RE-OS is maintained in the EECR:

**[`../../engineering/governance/EECR/decision-log.md`](../../engineering/governance/EECR/decision-log.md)**

That file is the single source of truth for all ADRs, ECRs, and governance decisions.
This directory (`docs/adr/`) holds individual ADR documents when they are sufficiently
complex to warrant a standalone file beyond the decision-log summary entry.

---

## Registered Decisions

| ID | Title | Status | EECR Entry |
|----|-------|--------|------------|
| ADR-001 | Monorepo Structure | ACTIVE | decision-log.md |
| ADR-002 | Git Branch Strategy | ACTIVE | decision-log.md |
| ADR-003 | Commit Message Convention | ACTIVE | decision-log.md |
| ADR-004 | CODEOWNERS and Branch Protection | ACTIVE | decision-log.md |
| ADR-005 | ECR-005 — HLD v1.0 Superseded by HLD v2.0 | ACTIVE | decision-log.md |
| ADR-006 | (reserved) | — | decision-log.md |
| ADR-007 | Canonical Engineering Repository | ACTIVE | decision-log.md |
| ECR-001 | VM-Only Deployment Model | ACTIVE | decision-log.md |
| GOV-001 | EECR Governance Framework | ACTIVE | decision-log.md |
| GOV-002 | AI Agent Governance | ACTIVE | decision-log.md |

> ADR-005 and ADR-006 numbering — refer to decision-log.md for current sequence.
> The table above reflects entries known at WP-001-03 implementation (2026-07-02).

---

## ADR Lifecycle

```
PROPOSED → ACCEPTED → ACTIVE
                    ↘
                     SUPERSEDED (replaced by a new ADR)
                    ↘
                     DEPRECATED (context no longer applies)
```

A decision in `ACTIVE` status is binding on all implementation work. A `SUPERSEDED`
decision remains in the register for audit traceability — do not delete it.

---

## ADR Template

When raising a new ADR, create a file in `docs/adr/` named `adr-{NNN}-{kebab-title}.md`
and register a summary entry in [`../../engineering/governance/EECR/decision-log.md`](../../engineering/governance/EECR/decision-log.md).

```markdown
# ADR-{NNN} — {Title}
### Status: PROPOSED | Date: YYYY-MM-DD | Author: {role}

## Context

{What situation or constraint made this decision necessary?}

## Decision

{The decision made, stated as a directive.}

## Alternatives Considered

| Alternative | Rejected Because |
|-------------|-----------------|
| {option A}  | {reason}         |
| {option B}  | {reason}         |

## Consequences

**Positive:** {benefits}
**Negative / Trade-offs:** {costs or constraints imposed}
**Neutral:** {things that change but are neither good nor bad}

## References

- {link to relevant EECR entry, WP, or external specification}
```

---

## ECR Log

Engineering Clarification Requests (ECRs) that escalate to architectural decisions are
promoted to ADR status and recorded in the decision log. Lower-level ECRs that are
resolved without architectural change are recorded in the EECR risk register or change
log as appropriate.

There is no standalone `ecr-log.md` in this repository. All ECRs are tracked via the
EECR change-log and risk-register in [`../../engineering/governance/EECR/`](../../engineering/governance/EECR/).
