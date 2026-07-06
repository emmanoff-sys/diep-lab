# Release 2 Observability Dependency Determinism
### DAEP / RE-OS | R2-PLAT-006 | Revision 1.0 | 2026-07-06

## 1. Purpose

R2-PLAT-006 identifies deterministic legacy observability behavior required for Release 2 validation.
The application behavior is deferred from EECR-CHG-089 because this Release Engineering PR may not
modify application source code.

This is a Platform Engineering validation control. It does not change business functionality,
Release 1, EPIC-006 functionality, WP-006-03B authorization, EPIC-007, R2-PLAT-007, or R2-PLAT-008.

## 2. Root Cause

MDM and OPC UA metrics constructors register collectors into Prometheus' default global registry
whenever `prometheus_client` was installed. Legacy tests instantiate metrics repeatedly, so test
outcomes differed depending on whether the dependency was present:

- if absent, no-op metrics were used and tests passed,
- if present, repeated construction raised duplicate-timeseries errors,
- legacy `/metrics` endpoints returned 200 when the dependency was present even when the validation
  profile expected absent-dependency behavior.

The underlying cause is dependency/profile ambiguity plus default `CollectorRegistry` reuse. Closing
this behavior requires a separately authorized application change.

## 3. Governed Profiles

| `PROMETHEUS_PROFILE` | Deterministic Behavior |
|----------------------|------------------------|
| `absent` | Target behavior: force no-op metrics and 503 metrics endpoint behavior regardless of installed package |
| `isolated-registry` | Target behavior: use a fresh private registry for each metrics object when real Prometheus classes are required |
| `present` | Preserve normal runtime default registry behavior |

## 4. Implementation Rule

Release 2 legacy validation may use `PROMETHEUS_PROFILE=absent` only after the corresponding
application behavior is separately authorized and implemented. EECR-CHG-089 excludes executable
observability determinism tests from the governed PR.

## 5. Evidence Requirements

Future R2-PLAT-006 application evidence must include:

- MDM and OPC UA legacy tests passing under `PROMETHEUS_PROFILE=absent`,
- isolated-registry tests passing when `prometheus_client` is installed,
- no duplicate `CollectorRegistry` failures,
- classification validator passing,
- workflow YAML parse passing when workflow files are touched.
