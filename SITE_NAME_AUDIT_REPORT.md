# Devices `site_name` — Audit & Remediation Report

Date: 2026-06-15
Scope: `devices` table, `diep-timescaledb` / database `diep`
Backup: `backups/site-name-20260615051500/devices_before.csv`

## 1. `devices` table inventory

| device_id | device_type    | site_name | location     | status | tenant_id |
|---|---|---|---|---|---|
| BAT001   | battery        | *(NULL)* | Abuja Site A | ONLINE | default |
| EV001    | ev_charger     | *(NULL)* | Abuja Site A | ONLINE | default |
| INV001   | solar_inverter | *(NULL)* | Abuja Site A | ONLINE | default |
| METER001 | smartmeter     | *(NULL)* | Abuja Site A | ONLINE | default |
| MG001    | microgrid      | *(NULL)* | Abuja Site A | ONLINE | default |

Schema (`\d devices`):
- `site_name character varying(100)`, nullable, FK `devices_site_name_fkey`
  → `sites(site_name)`.
- `location character varying(128)`, nullable, free-text (not FK-constrained).

## 2. Findings

| Check | Result |
|---|---|
| `site_name IS NULL` | **5 of 5 devices** (BAT001, EV001, INV001, METER001, MG001) |
| `site_name = ''` (empty string) | 0 |
| Duplicate site assignments | None — all 5 devices currently share the same (NULL) `site_name`; nothing to deduplicate, just a universal gap |

`sites` table contains exactly **one row**:

| site_name | site_type | latitude | longitude |
|---|---|---|---|
| Abuja Site A | microgrid | 9.0765 | 7.3986 |

Every device's `location` is `'Abuja Site A'`, identical to the sole `sites`
row and FK-compatible with `devices_site_name_fkey`.

`ev_chargers` and `solar_assets` (also FK'd to `sites`) are empty (0 rows) —
unaffected, out of scope.

## 3. Intended site structure

**Single-site deployment.** There is one site (`Abuja Site A`) and all 5
pilot devices belong to it (consistent with `location`). The correct,
FK-safe backfill is:

```sql
UPDATE devices SET site_name = 'Abuja Site A' WHERE site_name IS NULL;
```

No duplicate-assignment cleanup is needed — there is nothing to deduplicate;
this is a pure NULL-backfill to the one valid site.

## 4. Impact on DERMS (pre-fix validation)

All three DERMS endpoints in `fastapi/app.py` select the target device via
`_select_device()`, which filters `WHERE device_type = %s AND status =
'ONLINE' AND site_name = %s` when `site_name` is supplied in the request.
With `site_name IS NULL` on every device, a site-scoped request matches zero
rows:

```
POST /derms/peak_shaving     {"site_name":"Abuja Site A", ...} -> 404 "No online battery available to support peak shaving"
POST /derms/demand_response  {"site_name":"Abuja Site A", ...} -> 404 "No DERMS-capable asset available for demand response"
POST /derms/battery_dispatch {"site_name":"Abuja Site A", ...} -> 404 "No online battery found for the requested site"
```

This confirms the issue: `devices.site_name` must be backfilled to
`'Abuja Site A'` for site-scoped DERMS requests to resolve devices.

## 5. Backup taken (before any modification)

`backups/site-name-20260615051500/`:
- `TIMESTAMP.txt`
- `devices_before.csv` — full pre-fix export of `devices`
  (`id, device_id, device_type, site_name, location, status, tenant_id,
  created_at`) for all 5 rows.

No other tables were touched or exported (none needed modification).

## 6. Backfill script

[`scripts/sql/site_name_backfill.sql`](scripts/sql/site_name_backfill.sql) —
wraps the `UPDATE` in a transaction with before/after counts. Safe to run:
single target value, FK already satisfied by existing `sites` row, affects
only `devices.site_name` for the 5 NULL rows. No unrelated tables touched.

See [SITE_NAME_BACKFILL_VALIDATION_REPORT.md](SITE_NAME_BACKFILL_VALIDATION_REPORT.md)
for execution and post-fix DERMS validation.
