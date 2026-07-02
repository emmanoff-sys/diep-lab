# Documentation Index — DAEP / RE-OS
### Canonical Repository: `github.com/emmanoff-sys/diep-lab` | Updated: 2026-07-02

> This index is the navigable entry point for all engineering documentation in this repository.
> Follow the section links to find the authoritative source for any architectural decision,
> design specification, operational procedure, or ADR.

---

## Architecture Baseline Documents

Pointer files for every frozen architecture baseline. Each file records document type, version,
status, classification, and a one-paragraph purpose summary. Full document text is maintained
externally; pointer files provide the stable in-repo anchor.

| Document | Pointer File | Version | Status |
|----------|-------------|---------|--------|
| Business Requirements Specification | [`architecture/brs.md`](architecture/brs.md) | v1.0 | CURRENT |
| Software Requirements Specification | [`architecture/srs.md`](architecture/srs.md) | v1.0 | CURRENT |
| High-Level Design | [`architecture/hld.md`](architecture/hld.md) | v2.0 | CURRENT |
| Low-Level Design | [`architecture/lld.md`](architecture/lld.md) | v2.0 | CURRENT |
| UI/UX Design Specification | [`architecture/uiux-spec.md`](architecture/uiux-spec.md) | v1.0 | CURRENT |
| Implementation Roadmap | [`architecture/roadmap.md`](architecture/roadmap.md) | v1.0 | CURRENT |
| Data Retention and Destruction Policy | [`architecture/drdp.md`](architecture/drdp.md) | v1.0 | CURRENT |

---

## Architecture Decision Records (ADRs)

ADRs record every binding architectural decision — motivation, alternatives considered, and
outcome. The formal ADR register is maintained in the EECR decision log. The `adr/` directory
holds the index and future individual ADR documents.

| Resource | Location |
|----------|----------|
| ADR Directory Index | [`adr/README.md`](adr/README.md) |
| EECR Decision Log (authoritative ADR register) | [`../engineering/governance/EECR/decision-log.md`](../engineering/governance/EECR/decision-log.md) |

---

## Operational Documentation

Operational guides, runbooks, and release notes produced during DIEP platform development and
deployment. These live directly in `docs/` alongside their subject-area subdirectories.

### Platform Architecture

| Document | Purpose |
|----------|---------|
| [`../DIEP_ADMS_ARCHITECTURE.md`](../DIEP_ADMS_ARCHITECTURE.md) | ADMS module design and integration status |
| [`../DIEP_DEPLOYMENT_ARCHITECTURE.md`](../DIEP_DEPLOYMENT_ARCHITECTURE.md) | Deployment topology and infrastructure layout |
| [`../DIEP_HA_ARCHITECTURE.md`](../DIEP_HA_ARCHITECTURE.md) | High-availability architecture |
| [`../DIEP_EDGE_GATEWAY_ARCHITECTURE.md`](../DIEP_EDGE_GATEWAY_ARCHITECTURE.md) | Edge gateway design |

### Operations & Runbooks

| Document | Purpose |
|----------|---------|
| [`../DIEP_OPERATIONS_MANUAL.md`](../DIEP_OPERATIONS_MANUAL.md) | Primary operations manual |
| [`../DIEP_PRODUCTION_OPERATIONS_RUNBOOK.md`](../DIEP_PRODUCTION_OPERATIONS_RUNBOOK.md) | Production operations runbook |
| [`../DIEP_PRODUCTION_CUTOVER_RUNBOOK.md`](../DIEP_PRODUCTION_CUTOVER_RUNBOOK.md) | Production cutover procedure |
| [`../MW2_READINESS_OPERATOR_RUNBOOK.md`](../MW2_READINESS_OPERATOR_RUNBOOK.md) | MW2 automated readiness verification |
| [`../DIEP_INSTALLATION_GUIDE.md`](../DIEP_INSTALLATION_GUIDE.md) | Installation guide |
| [`../ADMIN_GUIDE.md`](../ADMIN_GUIDE.md) | Administrator guide |

### OMS Module Documentation

| Module | Directory |
|--------|-----------|
| Automation | [`oms-automation/`](oms-automation/) |
| FLISR Planner | [`oms-flisr-planner/`](oms-flisr-planner/) |
| Grid Overlay | [`oms-grid-overlay/`](oms-grid-overlay/) |
| Operational Controls | [`oms-operational-controls/`](oms-operational-controls/) |
| Real Device Control | [`oms-realdevice-control/`](oms-realdevice-control/) |
| VoltVAR Advisory | [`oms-voltvar-advisory/`](oms-voltvar-advisory/) |
| OPC-UA Discovery | [`opcua-discovery.md`](opcua-discovery.md) |

### Release & Readiness

| Document | Purpose |
|----------|---------|
| [`production-readiness/`](production-readiness/) | Production readiness reports |
| [`readiness/`](readiness/) | Milestone readiness verification |

---

## Engineering Governance

| Resource | Location |
|----------|----------|
| Engineering Execution Control Register (EECR) | [`../engineering/governance/EECR/`](../engineering/governance/EECR/) |
| Engineering Standards | [`../STANDARDS.md`](../STANDARDS.md) |
| Repository Ownership | [`../CODEOWNERS`](../CODEOWNERS) |
| Risk Register | [`../engineering/governance/EECR/risk-register.md`](../engineering/governance/EECR/risk-register.md) |

---

## Navigation Rule

Every document referenced in this index must exist at its listed path. If a link is broken,
raise an Engineering Clarification Request (ECR) and update this index as part of the fix.
