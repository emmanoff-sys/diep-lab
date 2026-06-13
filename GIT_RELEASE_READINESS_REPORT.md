# DIEP Git Release Readiness Report — v1.0.0-rc1

**Date:** 2026-06-13
**Scope:** Final go/no-go assessment of the repository's first-commit contents for
`v1.0.0-rc1`, based on `GIT_SANITIZATION_INVENTORY.md` and the new `.gitignore`.
Documentation only — no files committed, pushed, or deleted.

---

## 1. Files safe to commit

After applying `.gitignore` and the unstage commands in
`GIT_SANITIZATION_INVENTORY.md` §3.1, the following categories make up the v1.0.0-rc1
first commit:

| Category | Examples | Notes |
|---|---|---|
| Application source | `fastapi/`, `ingestor/`, `dispatcher/`, `portal/`, `drivers/`, `digitaltwin/`, `copilot/`, `simulator/`, `nodered/*.py`, `nodered/flows.json`, `nodered/settings.js` | Core code for all services |
| SQL schema | `sql/000_schema.sql` … `sql/011_tenancy.sql` | Schema migrations |
| Compose / Helm / Terraform / k8s | `docker-compose*.yml` (active ones), `helm/`, `k8s/*.yaml` (incl. `k8s/secrets.example.yaml` — template only), `terraform/main.tf` | IaC definitions, no live secrets |
| Config templates | `.env.example`, `mosquitto/config/mosquitto.conf`, `mosquitto/config/acl`, `prometheus/prometheus.yml`, `prometheus/alerts.yml`, `alertmanager/alertmanager.yml`, `grafana/provisioning/**` | Placeholder values only |
| Scripts | `scripts/*.sh` (backup, restore, dr-test, install-backup-cron, issue-device-cert), `start-all-diep.sh`, `restart-diep.sh`, `init-db.sh`, `pin_network.py` | Operational tooling |
| Documentation | All `*.md` (release notes, system inventory, configuration baseline, BOM, checklists, certification report, phase reports, validation reports, architecture docs) | v1.0 baseline doc set |
| CI / editor config | `.github/workflows/ci.yml`, `.vscode/extensions.json` | No secrets present |
| New release-prep files | `.gitignore`, `GIT_SANITIZATION_INVENTORY.md`, `GIT_RELEASE_READINESS_REPORT.md`, `GIT_RELEASE_CHECKLIST.md`, `RELEASE_CERTIFICATION_REPORT.md` | This sanitization pass |
| Diagrams | `diagrams/` | Architecture diagrams from Phase 16 |
| Node-RED app config (non-secret) | `nodered/.config.nodes.json`, `nodered/.config.users.json`, `nodered/package.json` | UI/editor preferences and node registry — no secrets after `.config.runtime.json` is excluded |

---

## 2. Files unsafe to commit (must be excluded — see `.gitignore` + unstage commands)

| Category | Files | Why |
|---|---|---|
| Secrets | `.env`, `nodered/.config.runtime.json` (+ `.backup`), `nodered/flows_cred.json`, `mosquitto/config/passwd`, `.claude/settings.local.json`, `.env.bak.*`, `.env.pre-phase15a.bak`, `mosquitto/config/passwd.pre-phase15a.bak` | Live credentials / decryption keys |
| Private keys | All 13 `*.key` under `certs/`, `mosquitto/config/certs/`, `caddy/certs/` (CA key, device keys, service keys) | mTLS trust-chain compromise if committed |
| Virtual environment | `.venv/` (2,469 files) | Not source; massive bloat |
| Build artifacts | All `__pycache__/*.pyc` | Regenerated on run |
| Coverage | `.coverage` | Local test artifact |
| DB dumps | `backups/diep_*.dump`, `.dump.sha256`, `backups/config/` | Data, not source; may contain tenant data |
| Logs | `nodered/.npm/_logs/*`, `nodered/.npm/_update-notifier-last-checked` | Local tool logs |
| Temp/editor artifacts | `.docker-compose.yml.swp`, `500`, `*.bak`, `nodered/.config.*.backup`, `nodered/.flows.json.backup` | Stray/empty/duplicate files |
| Host-inventory snapshots | `inventory/*.txt` | Point-in-time lab output, not source |
| Public certs (`.crt`) | All `.crt` under `certs/`, `mosquitto/config/certs/`, `caddy/certs/` | Not secret, but excluded per `GIT_SANITIZATION_INVENTORY.md` §4.4 to avoid lab-cert reuse at pilot sites |

**Current staged-file count: 2,812.** After exclusion, the estimated first-commit size
is roughly **300-350 files** (application source, SQL, IaC, scripts, docs, configs,
diagrams) — a ~90% reduction.

---

## 3. Outstanding decisions (operator judgment, not blockers)

- `docker-compose-kafka.yml.deprecated`, `docker-compose-twins.yml.disabled` — currently
  excluded by the `*.deprecated`/`*.disabled` patterns. If these should be tracked for
  historical reference, add explicit `!` exceptions in `.gitignore`.
- `inventory/*.txt` — excluded as stale snapshots. If useful as a point-in-time
  baseline record, move into a dated `docs/` subfolder and add an explicit exception
  instead of relying on a one-off `git add -f`.
- Per-device `.crt` files — excluded entirely per §2. If the team prefers to track
  public certs for reference, add `!**/*.crt` exceptions for `certs/devices/*.crt`
  only (never for `*.key`).

---

## 4. Release recommendation

**Conditional GO for `v1.0.0-rc1`**, contingent on completing
`GIT_SANITIZATION_INVENTORY.md` §3 (unstage commands) before the first `git commit`.

- The application, configuration, and documentation are complete and ready (§1).
- The blocking issue identified in `RELEASE_CERTIFICATION_REPORT.md` §2.1/§2.2 — `.env`,
  the CA private key, and 12 other private keys staged for the first commit, with no
  `.gitignore` — is **fully remediable pre-commit** using the commands in
  `GIT_SANITIZATION_INVENTORY.md` §3. Nothing has been committed yet, so no history
  rewrite is needed.
- Once §3's verification step (no `.env`/`.key`/`.venv`/`.coverage` in
  `git diff --cached --name-only`) passes, proceed to
  `GIT_RELEASE_CHECKLIST.md` §2 (commit + tag).
- Independent of the Git-hygiene fix, the platform readiness score remains **88/100**
  (`PILOT_RELEASE_CHECKLIST.md` §5) — unrotated default secrets, missing operator TLS,
  and no Alertmanager receiver remain open items for the pilot site itself, tracked
  separately in `PILOT_RELEASE_CHECKLIST.md` §1.

**Do not tag `v1.0.0-rc1` until `GIT_SANITIZATION_INVENTORY.md` §3.3 verification
returns empty output for the secrets/keys/venv/coverage check.**

---

## 5. Related documents

- [`GIT_SANITIZATION_INVENTORY.md`](GIT_SANITIZATION_INVENTORY.md)
- [`.gitignore`](.gitignore)
- [`GIT_RELEASE_CHECKLIST.md`](GIT_RELEASE_CHECKLIST.md)
- [`RELEASE_CERTIFICATION_REPORT.md`](RELEASE_CERTIFICATION_REPORT.md)
- [`PILOT_RELEASE_CHECKLIST.md`](PILOT_RELEASE_CHECKLIST.md)
