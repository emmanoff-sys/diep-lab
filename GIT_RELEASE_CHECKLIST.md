# DIEP Git Release Checklist — v1.0.0-rc1

**Date:** 2026-06-13
**Purpose:** Steps to take the working tree from its current (uncommitted) state to a
tagged `v1.0.0-rc1` release candidate, and how to roll the tag back if needed.
Documentation only — the commands below are **not executed by this report**; they are
to be run by an operator after reviewing `RELEASE_CERTIFICATION_REPORT.md`.

---

## 1. Pre-tag checks (must complete before the first commit)

`RELEASE_CERTIFICATION_REPORT.md` §2.1/§2.2 found that the repository has **no commits
yet** and the staged first commit currently includes `.env`, the CA and all device/
service mTLS private keys, the `.venv/` virtualenv, and several backup/coverage
artifacts. These must be removed from the index before committing.

- [ ] **Create `.gitignore`** at the repo root covering at minimum:
  ```
  .env
  .env.bak.*
  .env.pre-*.bak
  .venv/
  .coverage
  *.swp
  *.key
  backups/*.dump
  backups/*.dump.sha256
  mosquitto/config/passwd.pre-*.bak
  ```
  (Use a `*.key` pattern plus explicit `!.env.example` / `!**/*.crt` exceptions as
  needed — certs (`.crt`) are public and may be tracked if desired, but private keys
  (`.key`) must not be.)

- [ ] **Unstage and exclude `.env`** (keep `.env.example` tracked):
  `git restore --staged .env`

- [ ] **Unstage and exclude the virtualenv**:
  `git restore --staged .venv` (2,812 files)

- [ ] **Unstage and exclude all private keys** currently staged:
  `mosquitto/config/certs/ca.key`, `mosquitto/config/certs/server.key`,
  `caddy/certs/api.key`, and `certs/devices/{BAT900,INV900,MGC900,MTR900,csms,
  dispatcher,ingestor}.key` — `git restore --staged <path>` for each, or
  `git restore --staged $(git ls-files --cached | grep '\.key$')`

- [ ] **Unstage editor/coverage artifacts**: `.coverage`, `.docker-compose.yml.swp` —
  `git restore --staged .coverage .docker-compose.yml.swp` (then delete them from the
  working tree, they are not needed)

- [ ] **Do not `git add`** the following untracked files (already excluded if
  `.gitignore` above is in place before any further `git add -A`):
  `.env.bak.1781164048`, `.env.pre-phase15a.bak`,
  `mosquitto/config/passwd.pre-phase15a.bak`, `certs/devices/{BAT001,EV001,INV001,
  METER001,MG001}.key`, `backups/diep_20260613T042427Z.dump`,
  `backups/diep_20260613T042427Z.dump.sha256`

- [ ] **Re-issue the mTLS CA and all device/service certificates** before the pilot
  fleet is provisioned. Even though the keys above were caught before the first commit,
  they were generated for this lab environment — issue a fresh CA and cert set
  per `DIEP_INSTALLATION_GUIDE.md` §6.1 for any pilot or production deployment, and
  do not reuse the lab CA.

- [ ] **Verify the working tree after cleanup**:
  `git status --porcelain | grep -E '\.env$|\.key$|\.venv|\.coverage|\.swp'` should
  return nothing (other than `.env.example`).

- [ ] **Confirm the 5 v1.0 baseline docs + 2 certification docs are staged**:
  `RELEASE_NOTES_v1.0.md`, `SYSTEM_INVENTORY.md`, `CONFIGURATION_BASELINE.md`,
  `DEPLOYMENT_BOM.md`, `PILOT_RELEASE_CHECKLIST.md`, `RELEASE_CERTIFICATION_REPORT.md`,
  `GIT_RELEASE_CHECKLIST.md`

- [ ] **Confirm `RELEASE_CERTIFICATION_REPORT.md` §3 release-packaging gate is marked
  resolved** once the above is done (re-run this checklist's verification command and
  update the report if needed before tagging).

---

## 2. Tag creation steps

Once §1 is complete and the first commit has been made:

- [ ] `git add <reviewed files>` — stage only the intended release contents (code,
      configs excluding secrets, docs, `.env.example`, `.gitignore`)
- [ ] `git commit -m "DIEP v1.0.0-rc1: initial pilot release baseline"`
- [ ] Tag the commit: `git tag -a v1.0.0-rc1 -m "DIEP v1.0.0-rc1 - pilot release candidate"`
- [ ] Verify the tag: `git show v1.0.0-rc1 --stat | head -50` — confirm no `.env`,
      `.key`, or `.venv` paths appear in the tagged tree
- [ ] Record the resulting commit SHA in `RELEASE_CERTIFICATION_REPORT.md` (append a
      "Tagged as" line) for traceability
- [ ] Push the tag only after the above verification:
      `git push origin main --tags` (confirm with the team before pushing — this is a
      shared, hard-to-reverse action)

---

## 3. Rollback plan

If an issue is discovered with the `v1.0.0-rc1` tag **before it has been pushed**:

- [ ] Delete the local tag: `git tag -d v1.0.0-rc1`
- [ ] Amend or recreate the commit as needed, then re-tag

If the tag **has already been pushed** and must be retracted:

- [ ] Do **not** force-delete the remote tag without team agreement — other
      collaborators or CI may have already fetched it
- [ ] Communicate the retraction to the team first
- [ ] Delete the remote tag only with explicit approval: `git push origin :refs/tags/v1.0.0-rc1`
- [ ] Delete the local tag: `git tag -d v1.0.0-rc1`
- [ ] Fix the underlying issue, re-run §1 verification, create a new tag
      (e.g., `v1.0.0-rc2`) rather than reusing `v1.0.0-rc1`

If secrets or private keys are discovered **in history after a push** (i.e., §1 was
skipped):

- [ ] Treat all committed keys/secrets as compromised immediately — rotate
      `.env` secrets per `PILOT_RELEASE_CHECKLIST.md` §1 and re-issue the CA and all
      device/service certs per `DIEP_INSTALLATION_GUIDE.md` §6.1
- [ ] This is a history-rewrite situation (`git filter-repo` / BFG or a fresh repo) —
      do not attempt this without team agreement, as it rewrites shared history for
      all collaborators

---

## 4. Related documents

- [`RELEASE_CERTIFICATION_REPORT.md`](RELEASE_CERTIFICATION_REPORT.md)
- [`PILOT_RELEASE_CHECKLIST.md`](PILOT_RELEASE_CHECKLIST.md)
- [`DIEP_INSTALLATION_GUIDE.md`](DIEP_INSTALLATION_GUIDE.md)
- [`SYSTEM_INVENTORY.md`](SYSTEM_INVENTORY.md)
