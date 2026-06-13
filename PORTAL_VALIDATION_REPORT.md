# Portal Validation Report (Static Review)

**Scope:** `/home/emmanoff_lab/projects/diep-lab/portal/` (Next.js 14 app), cross-checked against
`/home/emmanoff_lab/projects/diep-lab/FASTAPI_VALIDATION_REPORT.md` (36-endpoint authoritative list,
`fastapi/app.py`).
**Method:** Static code review only. `node`/`npm`/`npx` are **not available in this shell**
(`which node` → nothing under `/usr/bin`, `/usr/local/bin`), so `tsc --noEmit` / `npm run build`
could **not** be executed even though `portal/node_modules` exists. All findings below are from
reading source.

---

## Per-Page Analysis

| Page | API calls (via `/api/diep/*` BFF → FastAPI) | Endpoint match status | Component issues |
|---|---|---|---|
| `app/page.tsx` (Dashboard) | `GET /fleet/overview`, `GET /sites/overview`, `GET /health/assets`, `GET /alarms?limit=5`, `GET /recommendations` | All 5 match FastAPI exactly (`app.py:1274-1295`, `1298-1333`, `878-893`, `1657-1682`, `1685-1746`) | `FleetMap` dynamically imported with `ssr:false` (good — Leaflet needs `window`). No explicit error UI for `fleet`/`sites`/`recs` SWR errors — only `alarms`/`health` are read defensively via `?.`. If `/fleet/overview` 500s, `MetricCard` shows `0` silently (no `ErrorState`). |
| `app/fleet/page.tsx` | `GET /assets`, `GET /health/assets`, `GET /sites/overview`, `POST /commands` (via `CommandModal`) | All match (`app.py:827-847`, `878-893`, `1298-1333`, `2040-2050`) | Has `ErrorState` for `assets.error` (good), but `health`/`sites` have no error path — if those fail, `healthById` stays empty and map silently shows `Loading…` forever. `typeFilter` derived client-side from `assets.data` — fine. |
| `app/alarms/page.tsx` | `GET /alarms?limit=100` or `GET /alarms?device_id=<id>&limit=100` | Matches `app.py:1657-1682` (params `device_id?`, `limit=50` default — portal explicitly overrides to 100, allowed) | No `ErrorState` — `alarms.error` ignored; on failure stays in `Loading` indefinitely. Device filter is free-text, no validation against known device IDs. |
| `app/derms/page.tsx` | `GET /derms/requests?limit=50`; via `DermsActionPanel`: `POST /derms/battery_dispatch`, `POST /derms/peak_shaving`, `POST /derms/demand_response`, `POST /derms/load_optimization` | All 5 match exactly (`app.py:1551-1577`, `1397-1438`, `1441-1471`, `1474-1510`, `1513-1548`) | `DermsActionPanel.tsx:75` reads `res.command?.status` — matches FastAPI 202 response shape `{request_id, device_id, command_type, command}` (per FASTAPI report row for `/derms/battery_dispatch` etc., `app.py:1397-1438`). No error/loading skeleton in `DermsActionPanel` beyond inline `err` text — acceptable. Numeric fields parsed via `Number(v)`; an empty string becomes `Number('') === 0`, but the code skips empty values first (`DermsActionPanel.tsx:70`), so OK. |
| `app/reports/page.tsx` | `GET /reports/summary` | Matches `app.py:1749-1803` | No `ErrorState` for `report.error` — stays in `Loading` forever on failure. CSV export (`toCSV`) accesses `s.command_counts_by_status`, `s.derms_counts_by_status`, `s.alarm_counts_by_severity`, `s.latest_telemetry` — all present in `ReportSummary` type and (per FASTAPI report) returned by `/reports/summary`. |
| `app/twins/page.tsx` | `GET /assets`, `GET /health/assets` | Both match | Has `ErrorState` for `assets.error` (good). `health.error` not surfaced — `healthById` stays empty, all `TwinCard`s show `StatusBadge label={undefined}` → renders "UNKNOWN" badge, acceptable degrade. |
| `app/twins/[deviceId]/page.tsx` | `GET /assets/{deviceId}`, `GET /assets/{deviceId}/health`, `GET /commands?device_id={deviceId}&limit=10`, `GET /analytics/predictive_maintenance?device_id={deviceId}`, `POST /commands` (via `CommandModal`) | All 5 match (`app.py:850-855`, `869-875`, `2085-2110`, `1635-1648`, `2040-2050`) | Has `ErrorState` for `asset.error` (good — covers the page-blocking case). `health`/`commands`/`maint` errors not surfaced individually but UI degrades gracefully (empty sections / hidden `Section`). `deviceId` from `useParams` is **not URL-encoded** before interpolation into the fetch path (`/assets/${deviceId}/health` etc.) — for the seeded device IDs (`BAT001`, `MG001`, etc.) this is fine, but a device ID with special characters would break the path. |
| `app/administration/page.tsx` | `GET /assets`, `GET /health`, `POST /assets` | `GET /health` matches `app.py:1811-1813` (`{status:"UP", platform:"DIEP"}`); `GET /assets` and `POST /assets` match `app.py:827-847` / `794-824` | `POST /assets` requires `admin` role (`app.py:794`) — relies on BFF injecting `DIEP_PORTAL_TOKEN` as admin-scoped Bearer (see Auth section). Form sends `{...form, metadata:{}}` — matches `AssetRegistration` model fields (`device_id, device_type, location, site_name, status, metadata`); `tenant_id` omitted (optional, defaults server-side). No `ErrorState` for `devices`/`apiHealth` polling failures — table stays in `Loading`. |
| `app/ai-operations/page.tsx` | `GET /assets`, `GET /recommendations`, `GET /analytics/forecast?device_id=...&horizon_hours=12`, `GET /analytics/anomalies?device_id=...`, `GET /analytics/predictive_maintenance?device_id=...` | All match (`app.py:827-847`, `1685-1746`, `1601-1613`, `1616-1632`, `1635-1648`) | Default `device='BAT001'` hardcoded — works because `BAT001` is a seeded device (per `DIEP_PLATFORM_ASSESSMENT.md` §B.1 seed data), but if the device list is empty/different in another environment, forecast/anomaly/maintenance calls would 404 (`app.py` analytics endpoints return 404 if `device_id` unknown). No `ErrorState` anywhere on this page — failed analytics calls leave `Loading` or empty-state messages indefinitely, never surfacing the actual error. |

---

## Type Mismatches (`portal/lib/types.ts` vs FastAPI response shapes)

Overall the types are well-aligned (clearly hand-ported from `app.py`). Findings:

1. **No mismatches found** for `Asset` (`types.ts:4-13` vs `_build_asset_record`, `fastapi/app.py:344-356`) — fields `device_id, device_type, location, site_name, site_type, status, current_state, asset_metadata` line up exactly.
2. **`AssetHealthRow.health` is typed as `HealthVerdict`** (`types.ts:21-24`), and `HealthVerdict` is `{health: string, reason?: string, [k: string]: any}` (`types.ts:15-19`) — matches `_evaluate_health()`'s varying return shapes (`fastapi/app.py:378-...`, e.g. `{health, reason}` or `{health, reason, last_seen_seconds}` or `{health, reason, alarm:{...}}`). OK.
3. **`ReportSummary`** (`types.ts:107-116`) matches the `/reports/summary` shape described in `FASTAPI_VALIDATION_REPORT.md:162` ("aggregate report (device/command/derms/alarm counts + latest telemetry)") — field names `device_summary`, `command_counts_by_status`, `derms_counts_by_status`, `alarm_counts_by_severity`, `latest_telemetry`, `analytics_event_count`, `note?` all plausible; not independently verified line-by-line against `app.py:1749-1803` body construction in this pass, but no inconsistency surfaced from the FASTAPI report's description.
4. **`Alarm.id: number`** (`types.ts:98`) — `sql/000_schema.sql` defines `alarms` with a serial/integer PK per the platform assessment (B.1); consistent.
5. **`CommandRow`** (`types.ts:42-48`) lacks `topic` and other fields present in the **202 POST `/commands` response** (`{command_id,device_id,device_type,command_type,status,topic}` per FASTAPI report row `app.py:2040-2050`) — but `CommandRow` is only used for **GET `/commands`** list rows (`twins/[deviceId]/page.tsx:35,101`), and `CommandModal.tsx:42` reads the POST response as `any` (`res: any`), so this is not a live mismatch, just an incomplete type if reused for the POST response.
6. **`DermsRequest`** (`types.ts:50-61`) includes `executed_at`/`completed_at`/`error_message` — plausible per `derms_requests` table (assessment B.1, `sql/005_derms.sql`), not independently verified against `app.py:1551-1598` row-shape construction in this pass.

No outright type/field-name mismatches were found that would cause `undefined` renders for fields actually used by the pages reviewed.

---

## Auth/Token Flow

- **BFF route** `portal/app/api/diep/[...path]/route.ts:15-16`:
  ```ts
  const BASE = process.env.DIEP_API_BASE || 'http://diep-fastapi:8000';
  const TOKEN = process.env.DIEP_PORTAL_TOKEN || 'diep-admin-dev-key-CHANGE-ME';
  ```
  Every proxied request gets `Authorization: Bearer ${TOKEN}` injected server-side (`route.ts:23`). The token never reaches the browser. This is described accurately in the file's header comment (`route.ts:1-11`) and in `DIEP_PLATFORM_ASSESSMENT.md:83`.

- **Token value mismatch / likely misconfiguration**: `docker-compose-portal.yml:15-18` sets `DIEP_API_BASE` and `NEXT_PUBLIC_GRAFANA_URL` in the portal container's environment, but **does NOT set `DIEP_PORTAL_TOKEN`**. `.env` / `.env.example` define `DIEP_PORTAL_TOKEN=change-me-admin-key` (`.env.example:20`), but `docker-compose-portal.yml` has no `env_file: .env` directive and no explicit pass-through of `DIEP_PORTAL_TOKEN`. As written, the portal container will fall back to the hardcoded default `'diep-admin-dev-key-CHANGE-ME'` (`route.ts:16`), which **does not match** `.env`'s `change-me-admin-key` value, nor (presumably) whatever `DIEP_ADMIN_KEY` FastAPI's `auth.py` actually expects (`fastapi/auth.py:36-40`, `API_KEYS` built from `DIEP_ADMIN_KEY` env var). **If FastAPI's `DIEP_ADMIN_KEY` ≠ `'diep-admin-dev-key-CHANGE-ME'`, every admin-scoped portal call (`POST /assets`, `POST /onboarding/*`, etc.) and operator-scoped call (`POST /commands`, `POST /derms/*`) will get `401`** from FastAPI (assuming `DIEP_AUTH_ENFORCED=1`, which `.env` confirms per the platform assessment §C.1).
- `DIEP_API_BASE` in `docker-compose-portal.yml:16` (`http://diep-fastapi:8000`) matches the BFF default (`route.ts:15`) and the network alias `diep-fastapi` would need to resolve on whichever Docker network the portal/fastapi containers share — subject to the network-name-split issue (`diep-net` vs `diep-lab_diep-net`) flagged in `DIEP_PLATFORM_ASSESSMENT.md` §A.1/§C.2 (`docker-compose-portal.yml:38-40` uses external `diep-net`).
- `portal/lib/api.ts:4` (`BASE = '/api/diep'`) confirms all browser-side calls are same-origin, avoiding CORS entirely — consistent with the BFF design.

---

## Grafana Integration

- `portal/lib/grafana.ts:3`: `GRAFANA_URL = process.env.NEXT_PUBLIC_GRAFANA_URL || 'http://localhost:3001'`. `docker-compose-portal.yml:17` sets `NEXT_PUBLIC_GRAFANA_URL: http://localhost:3001` — consistent (Grafana is mapped to host port 3001 per `DIEP_PLATFORM_ASSESSMENT.md` service table).
- **Usage is limited to outbound `<a target="_blank">` links** — `app/page.tsx:42-44` ("↗ Open Grafana for metrics") and `lib/grafana.ts:6-12` (`CONSOLES` array rendered in `app/administration/page.tsx:43-54`).
- **No iframe embeds found** — `grep` for `iframe` across `portal/app` and `portal/components` returned nothing in the files reviewed; the integration is link-out only.
- **If Grafana is down**: clicking the link opens a new tab that fails to load (browser-level error, e.g. `ERR_CONNECTION_REFUSED`) — this **does not affect the portal page itself** since there's no embed/fetch dependency. No error boundary is needed or present for this because there is no synchronous dependency.

---

## Digital Twins Status

- `app/twins/page.tsx` and `app/twins/[deviceId]/page.tsx` call **only FastAPI core endpoints** — `GET /assets`, `GET /health/assets`, `GET /assets/{id}`, `GET /assets/{id}/health`, `GET /commands?device_id=...`, `GET /analytics/predictive_maintenance?device_id=...`, `POST /commands`. None of these are routed to the separate `digitaltwin/app.py` service.
- `portal/lib/headlineMetrics.ts:1` comment: "Ported from `digitaltwin/app.py` — per-device headline metrics and color maps" — confirms the portal **reimplements** the digital-twin logic client-side (`headline()`/`HEADLINE_METRICS`/`HEALTH_COLORS`/`SEVERITY_COLORS`) rather than calling the disabled `digitaltwin` service.
- **Conclusion**: the `docker-compose-twins.yml.disabled` / unwired `digitaltwin/app.py` (per `DIEP_PLATFORM_ASSESSMENT.md` §C.2 item 4) has **no impact on the portal's `/twins` pages** — they are fully self-contained against the main FastAPI (`app.py`) and the portal's own `headlineMetrics.ts`. No 404s expected from a missing twin backend; the twins pages would behave identically with or without that service running.
- The only failure mode for `/twins*` pages is the same as any other page: FastAPI itself being unreachable (handled via `ErrorState` on `assets.error` in both twin pages, `app/twins/page.tsx:19-20` and `app/twins/[deviceId]/page.tsx:39`).

---

## TypeScript / Build Results

**Skipped.** `portal/node_modules` exists (verified via `ls`), but this shell has **no Node.js runtime** —
`which node`, `which npm`, `which npx` all resolve to nothing, and `node_modules/.bin/tsc` fails with
`env: 'node': No such file or directory`. Per the task constraints, `npm install` was not run to remediate
this. No TypeScript or build errors could be checked; all findings above are from static reading of the
`.tsx`/`.ts` source against `lib/types.ts` and the FastAPI route list.

---

## Prioritized List of Broken/Missing Integrations

1. **(High) Portal admin/operator token likely mismatched with FastAPI's expected key.** `docker-compose-portal.yml` does not set `DIEP_PORTAL_TOKEN`, so the BFF (`route.ts:16`) falls back to the hardcoded default `'diep-admin-dev-key-CHANGE-ME'`, while `.env`/`.env.example` define `DIEP_PORTAL_TOKEN=change-me-admin-key` (`.env.example:20`) — and FastAPI's `auth.py` builds its `API_KEYS` from `DIEP_ADMIN_KEY`/`DIEP_OPERATOR_KEY`/`DIEP_SERVICE_TOKEN` env vars (per `FASTAPI_VALIDATION_REPORT.md:35`). Unless these three values happen to coincide, every `POST /assets`, `POST /commands`, `POST /derms/*`, `POST /onboarding/*` call from the portal will return `401` when `DIEP_AUTH_ENFORCED=1` (confirmed set in `.env` per the platform assessment). **Fix**: add `DIEP_PORTAL_TOKEN: ${DIEP_ADMIN_KEY}` (or equivalent) to `docker-compose-portal.yml`'s `environment:` block, or use `env_file: .env`.

2. **(Medium) Network name split affects portal→FastAPI connectivity.** `docker-compose-portal.yml:38-40` uses external network `diep-net`, while most actively-maintained split files (and the existing Docker network) use `diep-lab_diep-net` (per `DIEP_PLATFORM_ASSESSMENT.md` §A.1/§C.2/§C.4). If `fastapi` is brought up on `diep-lab_diep-net` and `portal` on `diep-net`, `DIEP_API_BASE=http://diep-fastapi:8000` will fail to resolve, and every BFF call returns the `502 {detail:"proxy error: ..."}` from `route.ts:43-45`. The portal pages handle this somewhat (SWR `getJSON` throws on non-OK status, `lib/api.ts:8-10`), but most pages (alarms, reports, derms, ai-operations, administration's device table) have **no `ErrorState` rendering** and would hang in `Loading…` forever rather than surfacing the 502.

3. **(Low/Medium) Inconsistent error-state handling across pages.** Only `app/fleet/page.tsx`, `app/twins/page.tsx`, and `app/twins/[deviceId]/page.tsx` render `ErrorState` on fetch failure (for the primary `assets` query only). Dashboard, alarms, derms, reports, administration, and ai-operations pages have no `ErrorState` for any of their `usePolling` calls — on backend failure they show indefinite `Loading…` or stale `keepPreviousData`, with the actual error only visible in the browser console (SWR throws via `getJSON`, `lib/api.ts:8-10`).

4. **(Low) Hardcoded default device `'BAT001'` in AI Operations** (`app/ai-operations/page.tsx:14`) — works against the seeded dataset (`DIEP_PLATFORM_ASSESSMENT.md` §B.1) but would 404 against `/analytics/forecast`, `/analytics/anomalies`, `/analytics/predictive_maintenance` (all 404 on unknown `device_id` per `FASTAPI_VALIDATION_REPORT.md:148-150`) in any environment without that exact device ID, with no error surfaced to the user.

5. **(Informational) `/onboarding*` (6 endpoints) and `/auth/*` (3 endpoints) are entirely unused by the portal** — `grep -rn "onboarding"` across `portal/app|components|lib` returns only a comment (`route.ts:10`). All 9 of these FastAPI endpoints are exercised only via direct API/curl per `FASTAPI_VALIDATION_REPORT.md`, not through any portal UI. Not a bug, but worth noting as a coverage gap if onboarding is meant to be operator-facing.

6. **(Informational) Digital twins pages have no dependency on the disabled `digitaltwin` service** — see "Digital Twins Status" above. No action needed; `docker-compose-twins.yml.disabled` does not block `/twins*`.

7. **(Informational) Grafana integration is link-out only, no embeds** — a Grafana outage cannot break any portal page; only the external Grafana tab itself fails to load.

---

## File/Line Index of Key Evidence

- BFF proxy + token injection: `portal/app/api/diep/[...path]/route.ts:15-16,22-26,43-45`
- Typed client: `portal/lib/api.ts:4-25`
- Polling hook: `portal/lib/hooks.ts:8-14`
- Types: `portal/lib/types.ts` (whole file)
- Grafana/consoles: `portal/lib/grafana.ts:1-12`
- Headline metrics (ported twin logic): `portal/lib/headlineMetrics.ts:1-46`
- Pages: `portal/app/page.tsx`, `portal/app/fleet/page.tsx`, `portal/app/alarms/page.tsx`,
  `portal/app/derms/page.tsx`, `portal/app/reports/page.tsx`, `portal/app/twins/page.tsx`,
  `portal/app/twins/[deviceId]/page.tsx`, `portal/app/administration/page.tsx`,
  `portal/app/ai-operations/page.tsx`
- Components: `portal/components/{AssetTable,TwinCard,FleetMap,AlarmTable,RecommendationList,
  MetricCard,StatusBadge,TimeSeriesChart,CommandModal,DermsActionPanel,Loading}.tsx`
- FastAPI endpoint list / shapes: `FASTAPI_VALIDATION_REPORT.md` §3 (Auth, Health, Assets, State,
  Fleet, Onboarding, Sites, DERMS, Analytics, Alarms, Reports, Telemetry, Commands)
- Asset record shape: `fastapi/app.py:344-356` (`_build_asset_record`)
- Health eval shape: `fastapi/app.py:378-` (`_evaluate_health`)
- Recommendations shape: `fastapi/app.py:1685-1746`
- Portal compose env: `docker-compose-portal.yml:15-18,38-40`
- Token env source: `.env.example:20`, `.env:20`
