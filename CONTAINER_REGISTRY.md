# Container Registry — DAEP / RE-OS

**Authority:** WP-003-03 | Roadmap v1.0 §11.1 Stage 7 ("Push to Registry — Internal Docker registry — <2 minutes — Image pushed — Notification")

The durable, versioned home for every service's built image, between "CI
built it" (Stage 5, WP-004-05) and "a VM is running it" (Ansible pull,
WP-003-07).

## 1. Release 1 Deployment

Self-hosted via the official `registry:2` image, running under Docker
Compose locally/CI (`infra/container-registry/docker-compose.yml`).
Promoted to a properly provisioned VM once WP-003-05/06/07 exist — the same
follow-on pattern already established for the Python artifact repository
(WP-001-11 `ARTIFACT_REPOSITORY.md` §6).

## 2. Tagging Convention

| Tag | Applied | Example |
|-----|---------|---------|
| `{registry-host}/reos/{service-name}:{git-sha}` | Every build | `registry.internal:5000/reos/identity-service:a1b2c3d` |
| `{registry-host}/reos/{service-name}:{semver}` | Only on `release/*` → `main` merges (WP-001-10 versioning policy) | `registry.internal:5000/reos/identity-service:1.2.0` |

## 3. Authentication (Release 1 — basic auth)

```bash
cd infra/container-registry
mkdir -p data
htpasswd -Bbn <user> <password> > .htpasswd   # bcrypt, gitignored
docker compose up -d
```

**Upgrade path:** basic-auth credentials are replaced by Vault-issued
tokens once WP-003-13 (Vault) exists — documented here as a planned
follow-on, not silently deferred without a plan.

## 4. Push / Pull

```bash
# Login
docker login registry.internal:5000

# Tag and push
docker tag reos/scaffold:local registry.internal:5000/reos/scaffold:$(git rev-parse --short HEAD)
docker push registry.internal:5000/reos/scaffold:$(git rev-parse --short HEAD)

# Pull (from any other client with the same credentials)
docker pull registry.internal:5000/reos/scaffold:$(git rev-parse --short HEAD)
```

**Round-trip verification:** `docker inspect --format='{{.Id}}'` on the
pushed and pulled images must match (image digest identity).

No registry UI is in scope for Release 1 — `docker push`/`docker pull` are
the only supported interfaces.

## 5. Access Logs

```bash
docker compose logs -f registry
```

Retained for audit — who pushed/pulled what tag, when.

## 6. Push Notification

`REGISTRY_NOTIFICATIONS_ENDPOINTS` posts to a placeholder webhook
(`http://notify-placeholder.local/webhook`) for Release 1 — satisfies
Roadmap Stage 7's notification requirement structurally; wiring a real
alerting sink is EPIC-004's observability follow-on, flagged explicitly
rather than left silently unimplemented.

## 7. Security

- Never publicly internet-exposed — internal network only.
- Basic-auth credentials rotated per the same discipline as any other
  Internal-Confidential credential (BRS v1.0 data classification).
- CI push credentials supplied to the runner via a GitHub Actions secret,
  never hardcoded in a workflow file (WP-004-07 consumer requirement).

## 8. Verification (Runtime — requires a reachable Docker daemon)

```bash
docker compose up -d
docker push registry.internal:5000/reos/scaffold:test
docker pull registry.internal:5000/reos/scaffold:test  # on a separate client
# compare: docker inspect --format='{{.Id}}' both sides
```

**Status in this repository:** Docker daemon was not reachable in the
implementation environment — push/pull round-trip is **Runtime PASS
Deferred**.

## 9. Traceability

| Requirement | Source |
|-------------|--------|
| Registry role, timing, notification | Roadmap v1.0 §11.1 Stage 7 |
| Tagging convention (semver tag) | WP-001-10 `VERSIONING.md` |
| Basic-auth → Vault-token upgrade path | WP-003-13 (forward reference) |
