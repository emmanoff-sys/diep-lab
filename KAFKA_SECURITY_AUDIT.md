# Kafka Security Configuration Audit

**Date:** 2026-06-14
**Scope:** Kafka SASL credential configuration across `docker-compose.yml`,
`dispatcher/`, `fastapi/`, Helm charts, and Kubernetes manifests.
**Audit only — no files modified.**

This addresses Issue 4 from `DIEP_FULL_PLATFORM_VALIDATION_REPORT.md` /
`DIEP_POST_FIX_READINESS_REPORT.md`: a hardcoded Kafka SASL `PLAIN`
credential committed to `docker-compose.yml`.

---

## 1. Locations of Kafka SASL credentials

| # | File | Line(s) | Context | Value |
|---|---|---|---|---|
| 1 | `docker-compose.yml` | 30 | `diep-kafka` broker — `KAFKA_LISTENER_NAME_SASL_PLAIN_SASL_JAAS_CONFIG` | `username="diep" password="diep-kafka-pass-2026" user_diep="diep-kafka-pass-2026"` (username `diep` and password `diep-kafka-pass-2026` each appear **twice** in this one JAAS string) |
| 2 | `docker-compose.yml` | 165-166 | `dispatcher` service — `environment:` block | `KAFKA_SASL_USERNAME: diep`, `KAFKA_SASL_PASSWORD: diep-kafka-pass-2026` |
| 3 | `dispatcher/command_dispatcher.py` | 38-39 | Python module-level constants | `KAFKA_SASL_USERNAME = os.getenv("KAFKA_SASL_USERNAME", "diep")`, `KAFKA_SASL_PASSWORD = os.getenv("KAFKA_SASL_PASSWORD", "diep-kafka-pass-2026")` |
| 4 | `fastapi/app.py` | 58-59 | Python module-level constants | `KAFKA_SASL_USERNAME = os.getenv("KAFKA_SASL_USERNAME", "diep")`, `KAFKA_SASL_PASSWORD = os.getenv("KAFKA_SASL_PASSWORD", "diep-kafka-pass-2026")` |

Other Kafka-related files reference SASL **mode**, not credentials, and are
out of scope for the credential itself:

- `helm/diep/values.yaml:30`, `values-prod.yaml:15` — `kafkaSecurityProtocol: SASL_SSL` (no credential value)
- `helm/diep/values-dev.yaml:12` — `kafkaSecurityProtocol: SASL_PLAINTEXT` (no credential value)
- `k8s/kafka-strimzi.yaml:17` — `type: scram-sha-512` (Strimzi-managed `KafkaUser`; credential is generated into a K8s `Secret` by the Strimzi operator, not stored in this repo)
- `nodered/flows.json`, `nodered/rebuild_flows.py` — `saslssl`/`saslmechanism` flags only, no embedded username/password

**Total occurrences of the literal string `diep-kafka-pass-2026`: 4** (one of
which — line 30 — contains the password twice within a single JAAS config
string, for a total of **5 textual instances** of the password value).

---

## 2. Classification

### Hardcoded credentials (committed, plaintext, in version control)

| File:line | Credential | Notes |
|---|---|---|
| `docker-compose.yml:30` | `diep:diep-kafka-pass-2026` (×2 in JAAS string) | Defines the broker-side SASL/PLAIN user table. This is the **source of truth** the credential must match. |
| `docker-compose.yml:165-166` | `diep:diep-kafka-pass-2026` | Hardcoded `environment:` override for `dispatcher`. Takes precedence over `env_file: .env` for this service, so even if `.env` defined `KAFKA_SASL_PASSWORD`, this hardcoded value would win. |
| `dispatcher/command_dispatcher.py:38-39` | `diep:diep-kafka-pass-2026` (as `os.getenv` defaults) | Code-level fallback. Currently the *effective* value for `dispatcher` is the docker-compose override (#2 above), not this default — but this default would become live the moment the compose override is removed without a `.env` replacement. |
| `fastapi/app.py:58-59` | `diep:diep-kafka-pass-2026` (as `os.getenv` defaults) | Code-level fallback. **This is currently the effective value for `fastapi`** — `fastapi`'s compose service has no `KAFKA_SASL_*` override and `.env` defines none, so the Python default is what's actually used at runtime. |

### Credentials already sourced from `.env`

**None.** `.env` (and `.env.example`) contain **no** `KAFKA_SASL_*` /
`KAFKA_BOOTSTRAP` / `KAFKA_SECURITY_PROTOCOL` keys at all (confirmed via
`grep -i kafka .env` → no matches). Both `fastapi` and `dispatcher` have
`env_file: .env`, so `.env` is already wired into both containers and is
ready to receive these values — it's just currently empty for Kafka.

Contrast: `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` (used by the `minio`
service, `docker-compose.yml:97-98`) **are** correctly sourced from `.env`
via `${MINIO_ROOT_USER}` / `${MINIO_ROOT_PASSWORD}` interpolation — this is
the existing pattern in the repo that the remediation below follows.

### Duplicate definitions

The pair `(username="diep", password="diep-kafka-pass-2026")` is defined
**4 separate times** in 4 different files, with the broker-side JAAS string
containing it twice over (5 literal occurrences of the password string
total):

1. `docker-compose.yml:30` (broker — authoritative)
2. `docker-compose.yml:165-166` (dispatcher override)
3. `dispatcher/command_dispatcher.py:39` (dispatcher code default)
4. `fastapi/app.py:59` (fastapi code default)

All 4 currently hold the **same** value, so the broker and both clients are
in sync today — but every future rotation requires editing all 4 locations
in lockstep, in 2 different file types (YAML + Python), or the broker and a
client will silently desync (client falls back to a stale default while the
broker's JAAS user table has been changed).

---

## 3. Remediation plan

**Goal:** single source of truth in `.env`, broker and both clients read
from it, no hardcoded plaintext credential left in `docker-compose.yml` or
Python source, zero deployment downtime/breakage.

### Step 1 — Add credential to `.env` (and `.env.example` placeholder)

Add to `.env`:
```
KAFKA_SASL_USERNAME=diep
KAFKA_SASL_PASSWORD=diep-kafka-pass-2026
```
(Same value as today — this step only *relocates* the credential, it does
not rotate it, so nothing breaks.)

Add to `.env.example` (placeholder, not the real secret):
```
KAFKA_SASL_USERNAME=diep
KAFKA_SASL_PASSWORD=changeme
```

### Step 2 — Broker: interpolate from `.env` instead of hardcoding

`docker-compose.yml:30` — replace the literal `diep` / `diep-kafka-pass-2026`
with `${KAFKA_SASL_USERNAME}` / `${KAFKA_SASL_PASSWORD}`:

```yaml
KAFKA_LISTENER_NAME_SASL_PLAIN_SASL_JAAS_CONFIG: >-
  org.apache.kafka.common.security.plain.PlainLoginModule required
  username="${KAFKA_SASL_USERNAME}" password="${KAFKA_SASL_PASSWORD}"
  user_${KAFKA_SASL_USERNAME}="${KAFKA_SASL_PASSWORD}";
```

The top-level `diep-kafka` service does not currently have `env_file: .env`
(only `fastapi`, `dispatcher`, and two other services do, per the earlier
grep). Compose `${VAR}` interpolation in the `environment:` section is
resolved from the shell/`.env`-at-project-root automatically by `docker
compose` regardless of a service's `env_file:` — so no `env_file:` addition
is needed for this interpolation to work. (Verify with `docker compose
config` before applying — see Step 5.)

### Step 3 — `dispatcher`: drop the hardcoded override, rely on `env_file`

`docker-compose.yml:165-166` — remove the two hardcoded lines entirely:
```yaml
      KAFKA_SASL_USERNAME: diep
      KAFKA_SASL_PASSWORD: diep-kafka-pass-2026
```
`dispatcher` already has `env_file: .env` (line 157-158), and
`dispatcher/command_dispatcher.py:38-39` already does
`os.getenv("KAFKA_SASL_USERNAME"/"KAFKA_SASL_PASSWORD", "diep"/...)`. Once
`.env` defines both keys (Step 1), `env_file` supplies them and the explicit
`environment:` override becomes redundant.

*(`KAFKA_BOOTSTRAP` and `KAFKA_SECURITY_PROTOCOL` on lines 163-164 are not
secrets — leave as-is, or optionally move to `.env` too for consistency, but
that is out of scope for this credential remediation.)*

### Step 4 — `fastapi` and `dispatcher` code: remove hardcoded fallback defaults

`fastapi/app.py:58-59` and `dispatcher/command_dispatcher.py:38-39` —
change:
```python
KAFKA_SASL_USERNAME = os.getenv("KAFKA_SASL_USERNAME", "diep")
KAFKA_SASL_PASSWORD = os.getenv("KAFKA_SASL_PASSWORD", "diep-kafka-pass-2026")
```
to:
```python
KAFKA_SASL_USERNAME = os.getenv("KAFKA_SASL_USERNAME", "")
KAFKA_SASL_PASSWORD = os.getenv("KAFKA_SASL_PASSWORD", "")
```
(or omit the default entirely / raise if `"SASL" in KAFKA_SECURITY_PROTOCOL`
and the value is empty). Both services have `env_file: .env`, so once Step 1
is done, `os.getenv(...)` returns the real value and the fallback is never
exercised in normal operation — the fallback is removed purely so a future
`.env` misconfiguration fails loudly (connection refused / auth error)
instead of silently reusing a stale committed password.

### Step 5 — Validation before commit (no live changes)

```bash
docker compose config | grep -A2 -i sasl   # confirm interpolation resolves correctly
```
Confirm the rendered config shows the real username/password from `.env`
(not literal `${KAFKA_SASL_USERNAME}`), and that no other service definition
references the now-removed Python/YAML defaults.

### Step 6 — Rollout (no breaking change, same credential value)

1. Commit `.env.example` placeholder + the 3 code/compose edits (Steps 2-4).
   `.env` itself is **not** committed (already gitignored — confirm).
2. `docker compose up -d` — recreates `diep-kafka`, `dispatcher`, `fastapi`
   with the same effective `diep` / `diep-kafka-pass-2026` credential
   (sourced from `.env` instead of hardcoded), so existing client
   connections re-authenticate successfully with no auth changes.
3. Tail logs of all three: `docker compose logs -f diep-kafka dispatcher
   fastapi` — confirm no `SaslAuthenticationException` / connection errors.
4. Smoke-test: re-run the DERMS dispatch validation
   (`POST /derms/battery_dispatch`) and confirm `commands.status` reaches
   `ACKED` as before.

### Step 7 — Rotation (optional follow-up, separate change)

Once the credential is centralized in `.env` (Steps 1-6 complete), rotating
it is a single-file change:

1. Update `KAFKA_SASL_PASSWORD` in `.env` to a new strong value.
2. `docker compose up -d diep-kafka` (broker picks up new JAAS user table).
3. `docker compose up -d dispatcher fastapi` (clients pick up new password
   from `.env` via `env_file`).
4. Validate as in Step 6.3-6.4.

### Rollback steps

If Steps 2-4 cause connection failures (e.g. interpolation not resolving as
expected in `docker compose config`):

1. `git revert <commit>` (or `git checkout -- docker-compose.yml
   dispatcher/command_dispatcher.py fastapi/app.py`) to restore the hardcoded
   values — these are byte-identical to the `.env` values added in Step 1, so
   the broker's JAAS user table and both clients' credentials remain
   consistent either way.
2. `docker compose up -d diep-kafka dispatcher fastapi` to recreate the 3
   containers with the reverted config.
3. No data migration, no credential rotation occurred, so rollback is a pure
   config revert with no further cleanup — `.env`'s new `KAFKA_SASL_*` keys
   can be left in place harmlessly (unused) or removed.

---

## 4. Summary

| Item | Finding |
|---|---|
| Hardcoded SASL credential | `diep` / `diep-kafka-pass-2026`, 4 definitions across `docker-compose.yml` (×2 sites, 1 containing the password twice) and 2 Python files |
| Sourced from `.env` today | None — `.env` has no `KAFKA_*` keys |
| Duplicate definitions | 4 (broker JAAS, dispatcher compose override, dispatcher code default, fastapi code default) — all currently consistent |
| Effective value for `fastapi` today | Python code default in `fastapi/app.py:59` (no compose override, `.env` empty) |
| Effective value for `dispatcher` today | Hardcoded compose override `docker-compose.yml:166` (wins over `env_file`) |
| Remediation | Add `KAFKA_SASL_USERNAME`/`KAFKA_SASL_PASSWORD` to `.env`; interpolate broker JAAS config from `.env`; drop dispatcher's hardcoded override; drop hardcoded Python fallbacks |
| Breaking change? | No — Step 1 preserves the existing credential value, so behavior is identical until an intentional rotation (Step 7) |
| Files to edit (when executed) | `.env`, `.env.example`, `docker-compose.yml` (2 spots), `dispatcher/command_dispatcher.py`, `fastapi/app.py` |

No files were modified during this audit.
