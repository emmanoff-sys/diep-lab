# Decision Log — DAEP / RE-OS Program
### EECR v1.0 | Updated: 2026-07-01

> Tracks architecture decisions (ADRs), scope decisions (ECRs), technical exceptions, and governance approvals.
> Format: ADR = Architecture Decision Record | ECR = Engineering Clarification Request | GOV = Governance Decision | TECH = Technical Exception

---

## Engineering Clarification Requests (ECRs)

### ECR-001 — VM-Only Deployment Model Confirmed

| Field | Value |
|-------|-------|
| ECR ID | ECR-001 |
| Type | Scope Clarification |
| Status | RESOLVED |
| Raised By | Enterprise Architect |
| Raised Date | Pre-program (baseline) |
| Resolved Date | Pre-program (baseline) |
| Resolution Owner | Enterprise Architect / PMO Lead |
| **Decision** | DAEP / RE-OS is deployed exclusively on on-premise virtual machines. Kubernetes and container orchestration platforms (ECS, GKE, AKS) are explicitly excluded from the architecture. The `infra/` directory in the monorepo is scoped for Ansible/Terraform/systemd VM configuration only. HLD volumes that reference Kubernetes-specific constructs are superseded by this ECR. |
| Architecture Impact | LLD v2.0 §3.1 `infra/` scope confirmed as VM-only. HLD Kubernetes references are non-binding for this program. |
| Affected WPs | WP-001-01, WP-002-01, EPIC-003, all infra WPs |
| Reference | LLD v2.0 Ch.3 §3.1; BRS v1.0 Vol.1 Executive Summary |

---

### ECR-006-GATE-01 — WP-006-04 Dependency Gate Interpretation After WP-006-03B Merge

| Field | Value |
|-------|-------|
| ECR ID | ECR-006-GATE-01 |
| Type | Dependency Gate Interpretation |
| Status | **OPEN — awaiting Programme Board decision** |
| Raised By | Release Manager / Engineering Defect Resolution Lead (AI-assisted) |
| Raised Date | 2026-07-07 |
| Resolution Owner | Programme Board |
| **Question** | The Engineering Execution Control Register gates WP-006-04 (Topology Publish-Version Endpoint) on "WP-006-02 or WP-006-03 APPROVED". WP-006-03 was delivered in slices: 03A merged under the Release 2 Sprint 1 authorized slice, and 03B (CIM XML import foundation) merged 2026-07-07 via PR #19 at `30b534d` (EECR-CHG-090). Does the merged 03A+03B slice set constitute "WP-006-03 APPROVED" for gate purposes, or does the gate require formal WP-level closure of WP-006-03 in full? |
| **Material facts for the decision** | (1) No Architecture Review is on record for WP-006-03B — the WP-005 series required one per WP (AR-048..052); the register's Arch_Review gate for WP-006-03 is unfilled. (2) The original register scope for WP-006-03 (8 SP, "CIM/IEC 61968 CIM-XML Parser") predates the 03A/03B split; no governance record defines whether 03A+03B exhausts the WP scope. (3) The alternative gate arm — WP-006-02 (GeoJSON Topology Importer) — is listed "Complete" in the Release 2 Platform Recovery Programme Sprint 1 slice but remains NOT STARTED in the register with no approval record, so it cannot currently satisfy the gate either. (4) Both merges carry GOV-002 human PR approval, which is merge authorisation, not WP-level closure. |
| **Options** | **A** — Programme Board declares the 03A+03B slice set sufficient: WP-006-03 marked APPROVED (optionally with a retrospective architecture review condition), WP-006-04 unlocks. **B** — WP-level closure required first: define residual WP-006-03 scope (if any), complete the missing Architecture Review, then re-evaluate the gate. **C** — Unlock WP-006-04 via the WP-006-02 arm after reconciling WP-006-02's register status and approval evidence. |
| Register Impact | WP-006-03 and WP-006-04 rows annotated pending this decision (EECR-CHG-091). WP-006-04 must not start until resolved. |
| Related Records | EECR-CHG-090; ADR-R2-07; RELEASE-2-PLATFORM-RECOVERY-PROGRAMME.md §6–7; PR #19 (`30b534d`) |

---

## Architecture Decision Records (ADRs)

### ADR-001 — Monorepo Repository Layout (LLD v2.0 §3.1)

| Field | Value |
|-------|-------|
| ADR ID | ADR-001 |
| Status | ACCEPTED |
| Date | 2026-07-01 |
| Decided By | Enterprise Architect |
| **Context** | A single source repository is needed for a multi-language, multi-platform program (Flutter, React/Next.js, FastAPI, Ansible/Terraform). The alternative is polyrepo (one repo per service/app). |
| **Decision** | Adopt a monorepo structure as defined in LLD v2.0 Ch.3 §3.1: `apps/`, `services/`, `libs/`, `infra/`, `docs/`, `.github/`. All platform code lives in the `RE-OS` repository. |
| **Amendment (ADR-007, 2026-07-02)** | The canonical repository hosting this monorepo is `github.com/emmanoff-sys/diep-lab`. The directory layout defined by this ADR is unchanged. Repository identifier updated from `RE-OS` to `diep-lab` in all EECR fields. See ADR-007. |
| **Rationale** | (1) Atomic cross-service commits; (2) unified CI/CD configuration; (3) simplified dependency management for shared `libs/`; (4) single CODEOWNERS file for access governance; (5) aligned to LLD baseline — no architectural invention required. |
| **Consequences** | (Positive) Single clone, unified tooling, cross-team visibility. (Negative) Repository size grows over time; large monorepos require careful CI optimization (e.g., path-filtered pipelines). Mitigation: path-filtered GitHub Actions workflows in WP-004-01. |
| Linked WPs | WP-001-01, WP-001-04, WP-004-01 |
| Reference | LLD v2.0 Ch.3 §3.1 |

---

### ADR-002 — Proprietary License (Internal — Confidential)

| Field | Value |
|-------|-------|
| ADR ID | ADR-002 |
| Status | ACCEPTED |
| Date | 2026-07-01 |
| Decided By | PMO Lead |
| **Context** | The repository requires a `LICENSE` file. BRS v1.0 Vol.1 classifies all program artifacts as "Internal — Confidential." Choosing an OSS license (MIT, Apache 2.0) would contradict this classification. |
| **Decision** | The repository `LICENSE` file uses a proprietary/confidential notice with all-rights-reserved language. No open-source license is applied to the RE-OS codebase. |
| **Rationale** | Compliance with BRS v1.0 classification; prevents inadvertent public disclosure; satisfies legal review requirement for internally-classified software. |
| **Consequences** | (Positive) Clear IP ownership; compliance with BRS. (Negative) No OSS community contributions possible. Note: if specific legal boilerplate is mandated by the legal team's template library, replace `LICENSE` in a follow-on commit — this does not require a new WP, only a PR with legal team sign-off. |
| Linked WPs | WP-001-01 |
| Reference | BRS v1.0 Vol.1 (Classification field) |

---

### ADR-003 — .gitkeep for Empty Directory Placeholders

| Field | Value |
|-------|-------|
| ADR ID | ADR-003 |
| Status | ACCEPTED |
| Date | 2026-07-01 |
| Decided By | Platform Lead |
| **Context** | Git does not track empty directories. The LLD v2.0 §3.1 layout requires several directories (e.g., `services/`, `libs/`) to exist in the repository before any code is added. Options: (a) `.gitkeep` placeholder files; (b) `.gitignore` with exception rule; (c) README.md in each directory. |
| **Decision** | Use `.gitkeep` (empty file) as the placeholder in all directories that must exist before their content Work Packages begin. `.gitkeep` files are deleted by the first substantive commit into a given directory. |
| **Rationale** | `.gitkeep` is the lowest-noise option — it adds no content, requires no maintenance, and is universally understood. Per WP-001-01 §39: "Do not add placeholder code files." `.gitkeep` is not a code file. README placeholders were rejected because WP-001-03 owns documentation structure and should not be pre-empted. |
| **Consequences** | `.gitkeep` files accumulate until the owning WP is delivered. A CI structure-lint check (WP-001-04) should warn if a directory still contains only `.gitkeep` past its planned WP delivery date. |
| Linked WPs | WP-001-01 |
| Reference | WP-001-01 §39 Engineering Notes |

---

### ADR-004 — CODEOWNERS Team Slug Placeholders (Deferred to WP-001-04)

| Field | Value |
|-------|-------|
| ADR ID | ADR-004 |
| Status | ACCEPTED |
| Date | 2026-07-01 |
| Decided By | Platform Lead |
| **Context** | The `CODEOWNERS` file requires GitHub organization team slugs (e.g., `@RE-OS/platform-leads`). At WP-001-01 delivery time, the GitHub organization teams have not yet been created. Options: (a) Use real GitHub usernames; (b) Use logical team slugs as placeholders; (c) Omit CODEOWNERS until WP-001-04. |
| **Decision** | Use logical team slug placeholders (e.g., `@RE-OS/platform-leads`, `@RE-OS/backend-engineers`) matching the role taxonomy in DEF/BRS. These must be replaced with actual GitHub organization team slugs before WP-001-04 enables branch protection rules. CODEOWNERS with unresolved team slugs does not enforce access control but does not fail git either. |
| **Rationale** | Including CODEOWNERS in WP-001-01 documents governance intent immediately and provides the template for WP-001-04. Waiting until WP-001-04 to create CODEOWNERS would leave the repository without any ownership documentation during Sprints S1–S2. The lesson is recorded: CODEOWNERS team slugs are placeholders. |
| **Consequences** | CODEOWNERS is non-enforcing until GitHub teams are created and linked. WP-001-04 must include creating the GitHub organization teams matching the slugs defined here, or update CODEOWNERS with the actual team slugs. |
| Linked WPs | WP-001-01, WP-001-04 |
| Reference | WP-001-01 Lessons Learned; DEF Roadmap §Governance |

---

### ADR-007 — Canonical Engineering Repository

| Field | Value |
|-------|-------|
| ADR ID | ADR-007 |
| Status | ACCEPTED |
| Date | 2026-07-02 |
| Decided By | Enterprise Architect |
| **Context** | The DAEP / RE-OS engineering program was bootstrapped in a local repository at `/home/emmanoff_lab/projects/RE-OS` (WP-001-01, commits f69c194/f53fd38). The organization's canonical engineering platform is `github.com/emmanoff-sys/diep-lab`, which carries the full engineering history, CI/CD pipelines, and release history for the program. Maintaining two distinct repository identities creates governance fragmentation: branch strategies, PR workflows, CODEOWNERS enforcement, and CI/CD pipelines must all reference a single canonical location. Without a formal ADR, EECR fields, governance artefacts, and Work Package Engineering Packages would reference `RE-OS` indefinitely while actual implementation targets `diep-lab`. |
| **Decision** | The canonical engineering repository for DAEP / RE-OS shall be `github.com/emmanoff-sys/diep-lab`. All Work Packages across all Releases and Epics target `diep-lab` as their implementation repository. The EECR `Repository` field for all Release 1 Work Packages is updated from `RE-OS` to `diep-lab`. No DAEP / RE-OS engineering content shall be committed to any other repository location without a formal ADR superseding this decision. |
| **Rationale** | (1) Preserve engineering history — `diep-lab` carries existing commit history, CI/CD configuration, and release records that must not be abandoned. (2) Maintain one source of truth — a single repository eliminates branch strategy fragmentation and ensures CODEOWNERS, branch protection, and audit logging are unified. (3) Simplify governance — all governance artefacts, review records, and EECR fields reference a single canonical URL. (4) Avoid repository fragmentation — prevents future confusion about which repository is authoritative for production delivery. (5) No architectural change — the monorepo directory layout (LLD v2.0 Ch.3 §3.1: `apps/`, `services/`, `libs/`, `infra/`, `docs/`, `.github/`) is preserved exactly as defined by ADR-001; only the hosting location changes. |
| **Consequences** | (Positive) All governance artefacts, EECR fields, and Work Package Engineering Packages now reference a single canonical repository URL. CI/CD pipelines, branch protection rules, CODEOWNERS, and webhook configurations are unified under `diep-lab`. (Negative) Bootstrap commits in the temporary local repository (f69c194/f53fd38) are superseded — they remain in local git history but are not canonical. Note: DEF, MIB, and Claude Prompt Library repository examples reference `RE-OS` and require manual update by the respective document owners; these are external documents not tracked in this repository. |
| Linked WPs | All; applies to all Releases and Epics |
| Supersedes | None |
| Reference | ADR-001 (amended); EECR-CHG-007; LLD v2.0 Ch.3 §3.1; WP-001-01 |

---

## Governance Decisions

### GOV-001 — EECR as Single Source of Truth for WP Status

| Field | Value |
|-------|-------|
| Decision ID | GOV-001 |
| Type | Governance |
| Status | APPROVED |
| Date | 2026-07-01 |
| Decided By | PMO Lead |
| **Decision** | The EECR (this document set) is the authoritative source of record for Work Package status across the DAEP / RE-OS program. GitHub PR status, Jira tickets, and verbal updates are secondary. Any discrepancy between the EECR and another tool is resolved in favor of the EECR unless a change is formally logged in `change-log.md`. |
| **Rationale** | A single authoritative source prevents status conflicts between tooling layers and provides a stable audit trail for governance review. |
| Linked WPs | All |

---

### GOV-002 — AI Agents Cannot Self-Approve or Self-Merge

| Field | Value |
|-------|-------|
| Decision ID | GOV-002 |
| Type | Governance |
| Status | APPROVED |
| Date | 2026-07-01 |
| Decided By | PMO Lead / Enterprise Architect |
| **Decision** | AI engineering agents (Claude, ChatGPT, Codex, or any successor) are permitted to implement Work Package code and flag completion. They are explicitly prohibited from: (1) changing a WP status to APPROVED without a human review record; (2) merging PRs; (3) modifying architecture baseline documents; (4) closing or cancelling WPs. |
| **Rationale** | Maintains human oversight of production delivery. AI assistance accelerates implementation; human review validates correctness against architecture. |
| Linked WPs | All |

---

## Open Decisions

| Decision ID | Question | Owner | Raised | Blocking |
|-------------|----------|-------|--------|----------|
| ECR-006-GATE-01 | Does WP-006-03A+03B slice merge satisfy the "WP-006-03 APPROVED" gate for WP-006-04, or is formal WP-level closure required? | Programme Board | 2026-07-07 | WP-006-04 start |

---

## Decision Change Log

| Date | Decision ID | Change | Author |
|------|-------------|--------|--------|
| 2026-07-01 | All | Initial population from program baseline and WP-001-01 delivery | PMO Lead |
| 2026-07-07 | ECR-006-GATE-01 | Raised — WP-006-04 dependency gate interpretation after WP-006-03B merge; awaiting Programme Board | Release Manager (AI-assisted) |
| 2026-07-02 | ADR-001 | Amendment added: canonical repository hosting the RE-OS monorepo is `github.com/emmanoff-sys/diep-lab` per ADR-007 | Enterprise Architect (AI-assisted: claude-sonnet-4-6) |
| 2026-07-02 | ADR-007 | Added: Canonical Engineering Repository decision; all 47 R1 EECR Repository fields updated from `RE-OS` to `diep-lab` | Enterprise Architect (AI-assisted: claude-sonnet-4-6) |
