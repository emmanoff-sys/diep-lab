# Devices `site_name` Backfill — Validation Report

Date: 2026-06-15
Related: [SITE_NAME_AUDIT_REPORT.md](SITE_NAME_AUDIT_REPORT.md)

## 1. Summary

`scripts/sql/site_name_backfill.sql` was executed against `diep-timescaledb`
inside a single transaction. It set `devices.site_name = 'Abuja Site A'` for
all 5 devices that previously had `site_name IS NULL`. No other tables were
modified. All three site-scoped DERMS request types (Peak Shaving, Demand
Response, Battery Dispatch) now resolve a device and execute successfully.

## 2. Backup

`backups/site-name-20260615051500/devices_before.csv` — full pre-fix export
of `devices` (8 columns, 5 rows), taken before running the backfill.

## 3. Before / after counts

| Metric | Before | After |
|---|---|---|
| Total devices | 5 | 5 |
| `site_name IS NULL` | 5 | **0** |
| `site_name = ''` | 0 | 0 |
| Rows updated by `UPDATE` | — | **5** (`UPDATE 5`) |

Post-fix `devices` table:

| device_id | device_type    | site_name    | location     | status |
|---|---|---|---|---|
| BAT001   | battery        | Abuja Site A | Abuja Site A | ONLINE |
| EV001    | ev_charger     | Abuja Site A | Abuja Site A | ONLINE |
| INV001   | solar_inverter | Abuja Site A | Abuja Site A | ONLINE |
| METER001 | smartmeter     | Abuja Site A | Abuja Site A | ONLINE |
| MG001    | microgrid      | Abuja Site A | Abuja Site A | ONLINE |

FK `devices_site_name_fkey -> sites(site_name)` satisfied (`sites` contains
`'Abuja Site A'`). Transaction committed (`COMMIT`).

## 4. DERMS validation (post-fix)

All requests sent as `operator` role to `http://localhost:8000/derms/*` with
`"site_name":"Abuja Site A"`:

| Request type | Result | device_id resolved | derms_requests status |
|---|---|---|---|
| `peak_shaving` | 200 OK, command dispatched (`discharge`) | BAT001 | EXECUTED |
| `demand_response` | 200 OK, command dispatched (`discharge`) | BAT001 | EXECUTED |
| `battery_dispatch` | 200 OK, command dispatched (`discharge`) | BAT001 | EXECUTED |

Each request's `site_name = 'Abuja Site A'` is now recorded on the
corresponding `derms_requests` row (previously this column was blank).

Dispatcher (`diep-dispatcher`) logs confirm end-to-end delivery for all
three commands:
```
Received command from Kafka: discharge for BAT001
Dispatched discharge for BAT001 to diep/battery/BAT001/cmd
Device ack: <command_id> = ACKED
Posted ack <command_id> to FastAPI
```

Before the fix, the same three requests all returned `404`:
- `peak_shaving` → "No online battery available to support peak shaving"
- `demand_response` → "No DERMS-capable asset available for demand response"
- `battery_dispatch` → "No online battery found for the requested site"

## 5. Outstanding items

None. Only `devices.site_name` was modified, for exactly the 5 rows that
were `NULL`. No unrelated tables touched. Backup retained at
`backups/site-name-20260615051500/`.
