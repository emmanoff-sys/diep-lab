# npm Audit Configuration — DAEP / RE-OS

**Authority:** WP-004-03 | Roadmap v1.0 §11.1 Stage 3 ("pip-audit, npm audit")

## Status: Ready to activate — not yet live (WP-004-03 §8)

No real frontend app scaffold exists in Release 1 (the TypeScript packages in
`libs/reos-*-ts` are libraries, not deployable apps with a lockfile in a fixed
location). The `npm audit` check below is documented and ready to wire into
`service-ci-cd.yml` the moment a real Next.js app scaffold is created.

## Activation Command

```yaml
- name: npm audit (frontend/mobile dependency CVE scan)
  working-directory: apps/{app-name}     # real app directory, once created
  run: |
    npm ci
    npm audit --audit-level=high
```

**Threshold:** `--audit-level=high` (blocks on HIGH and CRITICAL, matching the
Python track's Bandit/pip-audit policies).

## Policy

Same zero-tolerance policy as pip-audit: any HIGH or CRITICAL npm advisory
blocks the PR. `moderate` findings are reported but do not block.

## Activation Checklist

When the first real frontend app scaffold is created:

1. Replace `working-directory` with the real app path.
2. Remove the `#` comment from the step in `service-ci-cd.yml`.
3. Ensure `package-lock.json` is committed alongside `package.json`
   (DEPENDENCY_POLICY.md §5 — `npm ci`, not `npm install`).
4. Register `Stage 3 — Dependency Scanning` as a required check on
   `main`/`develop` if not already registered (Platform Lead action).

## Traceability

| Requirement | Source |
|-------------|--------|
| npm audit Stage 3 | Roadmap v1.0 §11.1 Stage 3 ("npm audit") |
| `npm ci` not `npm install` | DEPENDENCY_POLICY.md §5 |
| Activation note | WP-004-03 §39 (do not let this stay dormant past the first app) |
