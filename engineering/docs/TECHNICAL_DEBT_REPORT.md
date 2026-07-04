# Repository Technical Debt Report
### Authority: EECR-CHG-071 | WP-005-04 CI Remediation Sprint | Date: 2026-07-04

> Prepared as a deliverable of the WP-005-04 CI Remediation Sprint.
> Scope: diep-lab monorepo — categorised by Lint, Security, Dependencies, Architecture, Governance.
> Status column reflects state **after** EECR-CHG-071 commit `889d3e3`.

---

## 1. Lint Debt

### 1.1 CLOSED — RE-OS Services (audit-service, identity-service, shared libs)

All Ruff, Black, and isort violations in `services/audit-service/`, `services/identity-service/`,
and `libs/` are now resolved. The following violation categories were closed:

| Category | Rule(s) | Count (approx) | Resolution |
|----------|---------|---------------|------------|
| Exception naming | N818 | 9 | Renamed with `Error` suffix; 11 downstream files updated |
| Exception chaining | B904 | ~8 | Added `from exc` / `from None` to all `raise` in `except` blocks |
| Unused loop variable | B007 | 2 | Renamed to `_` |
| Broad `pytest.raises` | B017 | 1 | Narrowed to `ValidationError` |
| `zip()` without `strict=` | B905 | 1 | Added `strict=False` |
| Undefined name (forward ref) | F821 | 4 | TYPE_CHECKING imports added; 1 genuine bug fixed (`remove_role_from_user`) |
| Line length | E501 | ~15 | Wrapped with black |
| Import order | various | ~20 | isort applied |
| Black formatting | various | 76 files | `black` applied |

### 1.2 SUPPRESSED — Justified `# noqa` annotations (production source, post-remediation)

All `# noqa` annotations carry a Ruff rule ID and a one-line justification per GOV-002.

| File | Rule | Justification |
|------|------|--------------|
| `audit-service/config.py` | S105 ×2 | Vault path strings, not credentials |
| `audit-service/domain/repositories.py` | C901 | Multi-filter query; inherent domain complexity |
| `identity-service/config.py` | S105 | File path string, not a credential |
| `identity-service/api/v1/auth.py` | S106 ×2 | MFA state token type names (`"mfa-pending"`, `"mfa-setup-required"`) |
| `identity-service/api/v1/auth.py` | S110 | Best-effort audit emission in revoke path; failure must not block |
| `identity-service/core/jwt.py` | S107, S105 | MFA state token type names in function default and comparison |
| `identity-service/core/mfa.py` | PLW0603 | Module-level `_fernet` Fernet instance; global-set in lifespan |
| `identity-service/schemas/auth.py` | S105 ×3 | OAuth2 grant type / token type constants, not credentials |
| `identity-service/schemas/mfa.py` | S105 | OAuth2 `"Bearer"` token type constant, not a credential |

### 1.3 OPEN — Legacy DIEP platform modules (pre-EPIC-004, non-RE-OS scope)

`drivers/`, `validation/`, `fastapi/`, `copilot/`, `services/cim/`, `services/opcua/`,
`services/mdm/` are excluded from RE-OS lint tooling. These modules are governed by `ci.yml`
(DIEP platform pipeline), not `service-ci-cd.yml`.

**Debt scope:** Unknown — legacy modules have not been audited against current Ruff rules.
**Risk:** LOW — these modules are not in the RE-OS service delivery path.
**Action:** Audit and remediate as part of a dedicated DIEP platform modernisation work package
(outside EPIC-005 scope).

---

## 2. Security Debt

### 2.1 CLOSED — Bandit B104 / Ruff S104 HOST binding

`HOST: str = "0.0.0.0"` changed to `HOST: str = "127.0.0.1"` in both:
- `services/audit-service/src/audit_service/config.py`
- `services/identity-service/src/identity_service/config.py`

Dockerfiles continue to pass `--host 0.0.0.0` explicitly to uvicorn `CMD` — container
networking is unchanged. The setting is **not consumed** by either `main.py`; the fix
applies the principle of least privilege to the Pydantic Settings default.

### 2.2 OPEN — `# type: ignore` annotations (~50 occurrences)

All `# type: ignore` annotations carry a mypy error code per GOV-002. The dominant patterns:

| Pattern | Count | Root cause |
|---------|-------|-----------|
| `aioredis.Redis` type parameter | ~20 | `redis.asyncio` generic type not fully exposed in stub; requires `# type: ignore[type-arg]` |
| `request.app.state.redis` | 2 | FastAPI `State` attribute access has no static type; `# type: ignore[no-any-return]` |
| `PostgresDsn` field assignment | 1 | Pydantic v2 validator return type mismatch; `# type: ignore[assignment]` |
| `dict[str, object]` narrow casts | ~15 | Kafka event dicts are `dict[str, Any]`; narrowed fields need `# type: ignore[assignment]` |
| `jwt.decode()` return | 2 | `python-jose` stubs return `dict` not `dict[str, object]`; `# type: ignore[return-value]` |
| `Fernet` / `webauthn` stubs | 3 | Incomplete stubs; `# type: ignore[arg-type]` |

**Action:** These are stub-quality issues, not logic errors. The correct long-term fix is:
- Upgrade to `types-redis` stubs when redis.asyncio generics are fully typed, OR
- Replace `aioredis.Redis` annotations with `redis.asyncio.Redis[bytes]` when stub coverage lands.
**Priority:** LOW (no correctness risk; mypy `--strict` currently passes with these suppressions).

### 2.3 OPEN — CodeQL Gate (WP-004-02 dependency)

`service-ci-cd.yml` Stage 2 runs CodeQL (`github/codeql-action`). CodeQL requires either
GitHub Advanced Security or a public repository. Availability on this private repository
has not been confirmed by the Project Owner.

**Risk:** If CodeQL is unavailable, Stage 2 CI step will fail on `codeql-action/analyze`.
**Action:** Project Owner to confirm GitHub Advanced Security availability or raise a new ECR
to fall back to Bandit-only for Stage 2. See `.github/README_EPIC004.md §Platform Lead Actions`.

### 2.4 OPEN — Gitleaks license (WP-004-09)

`service-ci-cd.yml` Secrets Scanning step requires `GITLEAKS_LICENSE` repository secret for
private repos. Secret not yet configured.

**Risk:** CI stage will fail on push until secret is provisioned.
**Action:** DevOps Lead to add `GITLEAKS_LICENSE` to GitHub repository secrets.

---

## 3. Dependency Debt

### 3.1 CLOSED — pydantic version conflict blocking pip-audit

`templates/python-service/requirements.txt` pinned `pydantic==2.7.4` / `pydantic-core==2.18.4`
while all services use `pydantic==2.8.2` / `pydantic-core==2.20.1`. pip resolver aborted when
pip-audit passed both `-r` flags together, preventing CVE scanning from executing.

**Fixed:** Template updated to `pydantic==2.8.2` / `pydantic-core==2.20.1`.

### 3.2 OPEN — requirements.txt manually pinned, not pip-compile generated

`services/audit-service/requirements.txt` and `templates/python-service/requirements.txt`
were pinned manually (no access to internal pip index during EPIC-005 CI bootstrap sprint).
DEPENDENCY_POLICY.md §2.4 requires `pip-compile requirements.in -o requirements.txt` with the
internal index URL before deployment.

**Risk:** Transitive dependency drift between manually pinned requirements and actual resolved
environment. The pins are internally consistent but have not been validated by a real solver run.
**Action:** Before Staging deployment, run:
```
pip-compile requirements.in -o requirements.txt --extra-index-url http://<internal-registry>/simple/
pip-audit -r requirements.txt --desc on
```
from each service directory. See ARTIFACT_REPOSITORY.md §3 and §6.

### 3.3 OPEN — reos-* internal packages not on PyPI

`reos-config==0.1.0`, `reos-logging==0.1.0`, `reos-exceptions==0.1.0`, `reos-common==0.1.0`
exist only in `libs/` and are not published externally. The CI bootstrap workaround (build wheels
+ local pypiserver) is documented in ARTIFACT_REPOSITORY.md §6. A persistent internal registry
(WP-003-post scope) will replace the CI bootstrap.

**Risk:** Any CI runner without the pypiserver bootstrap step cannot resolve or audit these packages.
**Action:** Post-EPIC-003 — promote pypiserver to a VM-hosted instance per ARTIFACT_REPOSITORY.md §2.

### 3.4 OPEN — pydantic-settings version gap in template

`templates/python-service/requirements.txt` pins `pydantic-settings==2.3.4`. Audit-service
and identity-service also use `2.3.4`. No immediate conflict, but the next service scaffold
should run `pip-compile` with the latest `pydantic-settings` patch to close any CVE exposure.

---

## 4. Architecture Debt

### 4.1 OPEN — Hash chain concurrent-write race condition (AR-052 F-AR052-01, C-AR052-03)

`services/audit-service/src/audit_service/domain/repositories.py` `create_event()` reads
the previous event's SHA-256 hash then inserts a new row without a serialisation guard. Under
concurrent REST writes for the same actor, a race condition can produce a broken chain link.

**Risk:** MEDIUM — REST write concurrency is low in Release 1; Kafka consumer path is already
single-goroutine ordered. However, the chain is not cryptographically guaranteed under concurrent
REST load.
**Action:** C-AR052-03 (required before Staging deployment) — add a per-actor advisory lock or
serialise writes via a queue. Implementation scope: WP-005-06 or a dedicated fix.

### 4.2 OPEN — `audit_kafka_consumer_lag` metric never populated (AR-052 F-AR052-03, C-AR052-02)

`services/audit-service/src/audit_service/core/kafka.py` exposes a `Gauge` for consumer lag
but the Gauge is never `set()` during message processing.

**Risk:** LOW — operational observability gap; no functional impact.
**Action:** C-AR052-02 (required before Staging) — populate gauge after each `consumer.poll()`.

### 4.3 OPEN — SMS delivery stubbed (WP-005-05 dependency)

`services/identity-service/src/identity_service/api/v1/mfa.py` SMS send/verify endpoints
return stub responses. Real delivery requires WP-005-05 Notification Service.

**Risk:** LOW — explicitly documented in endpoint response; WP-005-05 is the delivery vehicle.

---

## 5. Governance Debt

### 5.1 OPEN — AR-052 Staging conditions (C-AR052-02/03/05/06)

Four conditions from AR-052 remain open. All are classified as "required before Staging deployment"
(not blocking merge to develop):

| Condition | Summary | Owner |
|-----------|---------|-------|
| C-AR052-02 | Populate `audit_kafka_consumer_lag` Gauge | Platform Lead |
| C-AR052-03 | Hash chain serialisation guard for concurrent REST writes | Platform Lead |
| C-AR052-05 | Confirm audit-service container port is 8004 (not 8001) | DevOps Lead |
| C-AR052-06 | Confirm `chain_state` table UPDATE permission for `audit_user` | DBA / DevOps |

### 5.2 OPEN — DAST ECR-004-DAST-01

DAST scanning (WP-004-08) requires `.zap/rules.tsv` for the ZAP baseline scan. File not yet
created. CI DAST job is skipped until this file exists.

### 5.3 OPEN — Staging VMs not provisioned (WP-003-08 dependency)

`service-ci-cd.yml` Stage 9 (Staging Deployment) requires real VMs, Vault/Consul, and Ansible
SSH keys provisioned as per WP-003-08. Staging VMs have not been provisioned; the Stage 9 job
will not succeed until this infrastructure is live.

### 5.4 OPEN — Registry push credentials not configured

`service-ci-cd.yml` Stage 7 requires `REGISTRY_USERNAME` and `REGISTRY_PASSWORD` secrets.
These are not yet configured.

---

## Summary Table

| ID | Category | Item | Status | Priority |
|----|----------|------|--------|----------|
| TD-01 | Lint | Legacy DIEP modules (drivers, cim, opcua, mdm) not Ruff-clean | OPEN | LOW |
| TD-02 | Security | `# type: ignore` annotations (~50) — stub quality issues | OPEN | LOW |
| TD-03 | Security | CodeQL GitHub Advanced Security availability unconfirmed | OPEN | HIGH |
| TD-04 | Security | Gitleaks licence secret not configured | OPEN | MEDIUM |
| TD-05 | Dependency | requirements.txt manually pinned (not pip-compile generated) | OPEN | MEDIUM (before Staging) |
| TD-06 | Dependency | reos-* internal packages require pypiserver bootstrap in CI | OPEN | MEDIUM |
| TD-07 | Architecture | Hash chain concurrent-write race (C-AR052-03) | OPEN | MEDIUM (before Staging) |
| TD-08 | Architecture | `audit_kafka_consumer_lag` Gauge never populated (C-AR052-02) | OPEN | LOW (before Staging) |
| TD-09 | Architecture | SMS delivery stubbed — WP-005-05 dependency | OPEN | LOW |
| TD-10 | Governance | AR-052 Staging conditions C-AR052-02/03/05/06 | OPEN | MEDIUM (before Staging) |
| TD-11 | Governance | DAST ECR-004-DAST-01 / `.zap/rules.tsv` missing | OPEN | MEDIUM |
| TD-12 | Governance | Staging VMs not provisioned (WP-003-08) | OPEN | HIGH (before Staging) |
| TD-13 | Governance | Registry push credentials not configured | OPEN | HIGH (before Staging) |

Items TD-07/08/10 are explicitly gated to Staging by AR-052 decision — they are **not merge blockers**.
Items TD-03/12/13 are infrastructure prerequisites outside EPIC-005 scope.
All Lint (Stage 1), Security SAST B104 (Stage 2), and Dependency pydantic conflict (Stage 3) items
from the CI remediation sprint are **CLOSED** as of commit `889d3e3`.
