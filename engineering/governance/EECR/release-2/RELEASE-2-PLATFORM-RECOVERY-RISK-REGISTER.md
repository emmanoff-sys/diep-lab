# Release 2 Platform Recovery Risk Register
### DAEP / RE-OS | Platform Recovery Risks | Revision 1.0 | 2026-07-06

> Probability scale: 1 = Rare, 2 = Unlikely, 3 = Possible, 4 = Likely, 5 = Almost Certain.
> Impact scale: 1 = Negligible, 2 = Minor, 3 = Moderate, 4 = Major, 5 = Critical.

| Risk ID | Description | Probability | Impact | Score | Owner | Mitigation | Contingency |
|---------|-------------|-------------|--------|-------|-------|------------|-------------|
| R2-PLAT-RISK-001 | Pytest isolation work reveals deeper package-layout drift across service tests. | 3 | 4 | 12 HIGH | QA Lead | Start with invocation isolation before considering structural changes. | Raise a separate architecture review if package layout must change. |
| R2-PLAT-RISK-002 | Governed CI runner cannot provide both Docker and database services reliably. | 3 | 5 | 15 HIGH | DevSecOps Lead | Validate runner substrate before any profile fixes are merged. | Use GitHub-hosted runner or approved dedicated validation runner. |
| R2-PLAT-RISK-003 | DB environment variables remain inconsistent across Release 1 services and legacy modules. | 3 | 4 | 12 HIGH | Service Platform Engineer | Produce a mapping table and treat aliases as part of the environment contract. | Require residual acceptance for unsupported legacy aliases. |
| R2-PLAT-RISK-004 | Legacy Prometheus determinism requires application or test-harness code changes beyond current recovery authority. | 4 | 4 | 16 HIGH | Observability Lead | First attempt dependency-profile isolation; document any required code change as a separate approval. | Keep R2-RISK-017 mitigated and seek Programme Board decision. |
| R2-PLAT-RISK-005 | Security audit segmentation hides aggregate dependency conflicts that matter at deployment time. | 2 | 4 | 8 MEDIUM | Security Engineer | Record each product surface explicitly and add aggregate audit only where a real deployable environment combines them. | Block deployment claims until aggregate environment is defined. |
| R2-PLAT-RISK-006 | Recovery work expands into feature implementation under the cover of platform remediation. | 3 | 4 | 12 HIGH | PMO Lead | Apply GOV-002 scope checks and require each recovery PR to cite R2-PLAT WP only. | Reject out-of-scope changes and reopen recovery planning. |
| R2-PLAT-RISK-007 | Programme pressure leads to WP-006-03B authorization before release-gate evidence is green. | 3 | 5 | 15 HIGH | Programme Board | Keep WP-006-03B locked behind R2-PLAT-008. | Require formal residual-risk acceptance signed by PMO, EA, QA, DevSecOps, and Release Manager. |

## Recovery Risk Position

The highest residual risk is not application correctness. It is the possibility that platform
remediation exposes additional governance or validation-contract drift. The correct control is to
sequence recovery work through explicit platform WPs and keep feature implementation locked until
the evidence gate is restored.
