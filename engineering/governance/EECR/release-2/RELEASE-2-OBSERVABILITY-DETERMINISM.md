# Release 2 Observability Dependency Determinism
### DAEP / RE-OS | R2-PLAT-006 | Revision 1.0 | 2026-07-06

## 1. Purpose

R2-PLAT-006 establishes deterministic legacy observability behavior for Release 2 validation. It
prevents optional `prometheus_client` availability and Prometheus default-registry state from
changing test outcomes across local execution, GitHub Actions, Docker builds, and integration
validation.

This is a Platform Engineering validation control. It does not change business functionality,
Release 1, EPIC-006 functionality, WP-006-03B authorization, EPIC-007, R2-PLAT-007, or R2-PLAT-008.

## 2. Root Cause

MDM and OPC UA metrics constructors registered collectors into Prometheus' default global registry
whenever `prometheus_client` was installed. Legacy tests instantiate metrics repeatedly, so test
outcomes differed depending on whether the dependency was present:

- if absent, no-op metrics were used and tests passed,
- if present, repeated construction raised duplicate-timeseries errors,
- legacy `/metrics` endpoints returned 200 when the dependency was present even when the validation
  profile expected absent-dependency behavior.

The underlying cause was dependency/profile ambiguity plus default `CollectorRegistry` reuse, not
application business logic.

## 3. Governed Profiles

| `PROMETHEUS_PROFILE` | Deterministic Behavior |
|----------------------|------------------------|
| `absent` | Force no-op metrics and 503 metrics endpoint behavior regardless of installed package |
| `isolated-registry` | Use a fresh private registry for each metrics object when real Prometheus classes are required |
| `present` | Preserve normal runtime default registry behavior |

## 4. Implementation Rule

Release 2 legacy validation uses `PROMETHEUS_PROFILE=absent`. Focused tests may use
`PROMETHEUS_PROFILE=isolated-registry` to prove real Prometheus classes can be constructed
repeatedly without default-registry collisions.

## 5. Evidence Requirements

R2-PLAT-006 evidence must include:

- MDM and OPC UA legacy tests passing under `PROMETHEUS_PROFILE=absent`,
- isolated-registry tests passing when `prometheus_client` is installed,
- no duplicate `CollectorRegistry` failures,
- classification validator passing,
- workflow YAML parse passing when workflow files are touched.
