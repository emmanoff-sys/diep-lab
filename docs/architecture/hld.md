# High-Level Design — v2.0
### Architecture Baseline Pointer | DAEP / RE-OS

| Field | Value |
|-------|-------|
| Document Type | High-Level Design |
| Reference ID | HLD-002 |
| Version | v2.0 |
| Status | **CURRENT** |
| Classification | Internal — Confidential |
| Parent Documents | BRS v1.0, SRS v1.0 |
| Superseded By | N/A |

---

## Purpose

The Enterprise High-Level Design v2.0 defines the system architecture for the DAEP /
RE-OS platform at the component and integration level. It specifies the service topology,
data flows, message bus architecture, protocol adapter framework, identity and access
management model, and observability stack. HLD v2.0 is the primary input to LLD v2.0
(detailed design) and the UI/UX Design Specification. All architecture decisions recorded
in the EECR decision log (ADR-001 through ADR-007) are made within the architectural
frame established by this document.

## Source Location

Full document text is maintained externally. Request access from the Enterprise Architect
or consult the project document management system.

---

## Superseded Version

> **HLD v1.0 — SUPERSEDED**
>
> | Field | Value |
> |-------|-------|
> | Reference ID | HLD-001 |
> | Version | v1.0 |
> | Status | **SUPERSEDED** |
> | Superseded By | HLD v2.0 (this document) |
> | Supersession Record | ECR-005 |
>
> HLD v1.0 (also referred to as "High-Level Design v1.0") was the initial high-level
> design produced at program inception. It was superseded by HLD v2.0 following
> ECR-005, which incorporated revised service boundaries, updated protocol adapter
> architecture, and the ADMS extension scope. **Do not use HLD v1.0 as a design
> reference.** All current implementation work must trace to HLD v2.0.

---

## Cross-References

- [`brs.md`](brs.md) — Business requirements satisfied by this HLD
- [`srs.md`](srs.md) — Software requirements satisfied by this HLD
- [`lld.md`](lld.md) — Detailed design derived from HLD v2.0
- [`uiux-spec.md`](uiux-spec.md) — UI/UX design derived from HLD v2.0
- [`../../engineering/governance/EECR/decision-log.md`](../../engineering/governance/EECR/decision-log.md) — ECR-005 (HLD v1.0 → v2.0 supersession)

---

*Pointer only — authoritative source is external. Last updated: 2026-07-02 | WP-001-03*
