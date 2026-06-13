# DERMS Flow Validation Report

**Scope:** Read-only validation of the 4 DERMS endpoints (`POST /derms/battery_dispatch`,
`/derms/peak_shaving`, `/derms/demand_response`, `/derms/load_optimization`) in
`fastapi/app.py`, their use of `_execute_derms_command`/`_dispatch_command` (the same
Kafka/MQTT path documented in `KAFKA_COMMAND_FLOW_REPORT.md`), the `derms_requests` table
(`sql/005_derms.sql`), the `/derms/requests*` GET endpoints, the `DERMS_REQUESTS`/
`DERMS_COMMANDS` Prometheus metrics, and the multi-tenancy gap flagged in
`FASTAPI_VALIDATION_REPORT.md` §6 item 8.

All 4 DERMS handlers funnel into the **same** command pipeline as `POST /commands`:
`_execute_derms_command()` (`fastapi/app.py:702-730`) builds a `CommandRequest` and calls
`_dispatch_command()` (`fastapi/app.py:1931-2037` — the exact function documented in
`KAFKA_COMMAND_FLOW_REPORT.md` §2), which inserts into `commands` (status `PENDING`→`SENT`)
and produces to Kafka topic `diep.commands`. **No separate command-generation path exists for
DERMS** — it is a thin wrapper that picks a `device_id`/`command_type`/`params` and reuses
`/commands`'s machinery verbatim.

---

## 1. Battery Dispatch — `POST /derms/battery_dispatch`

**Route:** `fastapi/app.py:1397-1438`, `status_code=202`.

**Auth:** `require_role("operator")` (operator or admin) + `rate_limit("derms", 60, 60)`
(`app.py:1398-1400`).

**Request body — `BatteryDispatchRequest`** (`app.py:1372-1376`):
| Field | Type | Constraints |
|---|---|---|
| `device_id` | `str \| None` | optional, e.g. `BAT001` |
| `site_name` | `str \| None` | optional, e.g. `Abuja Site A` |
| `target_soc` | `float` | required, `0 <= x <= 100` |
| `max_power_kw` | `float \| None` | optional |

**Handler logic** (`app.py:1401-1438`):
1. `DERMS_REQUESTS.labels("battery_dispatch").inc()` — incremented unconditionally, before any validation (`app.py:1401`).
2. `auth.audit(principal, "derms_battery_dispatch", device_id or site_name or "auto", "ok", {...})` (`app.py:1402-1403`) — audited as "ok" even though later steps may still 404/422.
3. Device selection (`app.py:1404-1414`):
   - If `device_id` given: `_device_row(device_id)`; 404 if unknown; 422 if `device_type != "battery"`.
   - Else: `_select_device("battery", site_name)` (`app.py:683-699`) — `SELECT ... FROM devices WHERE device_type='battery' AND status='ONLINE' [AND site_name=%s] ORDER BY created_at DESC LIMIT 1`; 404 if none.
4. Reads cached/DB state (`_get_cached_state` / `_state_from_db`) for `battery_soc`; defaults to 50.0 if absent.
5. Decides `command_type`: `charge` if `current_soc < target_soc`, `discharge` if `>`, else `idle`.
6. `params = {"target_soc": ...}` (+ `max_power_kw` if provided).
7. `_insert_derms_request("battery_dispatch", {...}, site_name, device_id)` (`app.py:1432-1437`).
8. `_execute_derms_command("battery_dispatch", request_id, device_id, command_type, params)` (`app.py:1438`).

**Target device:** `BAT001` (the only seeded `battery` device, `sql/002_seed_battery_solar.sql:6`, status `ONLINE`, `site_name='Abuja Site A'`). `ALLOWED_COMMANDS["battery"]` includes `charge`, `discharge`, `idle` (`app.py:81`) — all three possible `command_type` values are valid.

**DB recording:** `derms_requests` row inserted with `request_type='battery_dispatch'`, `site_name=device['site_name']` (`'Abuja Site A'`), `device_id='BAT001'`, `params={"target_soc":..., "max_power_kw":...}`, `status='CREATED'` (table default, `sql/005_derms.sql:9`). On success, `_update_derms_request_status(request_id, "EXECUTED", executed_at=now)` (`app.py:712-716`); on `HTTPException` from `_dispatch_command`, `status='FAILED'`, `executed_at=now`, `error_message=str(exc.detail)` (`app.py:723-730`). **`completed_at` is never set by any code path** (grep confirms `completed_at` only appears in the `_update_derms_request_status` signature and the SELECTs — no caller passes it). So the lifecycle stops at `CREATED` → `EXECUTED`/`FAILED`, never `COMPLETED`.

**Expected device action — end-to-end:**
- `_dispatch_command` writes a `commands` row for `BAT001`/`charge|discharge|idle`, produces to `diep.commands` keyed by `BAT001`, marks `status='SENT'`.
- Per `KAFKA_COMMAND_FLOW_REPORT.md` §6/§3: dispatcher consumes, maps `device_type='battery'` → domain `battery` (`DOMAIN_MAP`), publishes to `diep/battery/BAT001/cmd`.
- **Break point:** the running `battery_bms` edge driver (`docker-compose-battery-edge.yml`) subscribes as device **`BAT900`** (`drivers/battery_bms/devices.json`), i.e. `diep/battery/BAT900/cmd`. The command published to `diep/battery/BAT001/cmd` has **no subscriber** — never received, never executed, no `/ack` ever published. `commands.status` stays `SENT` forever; `derms_requests.status` stays `EXECUTED` (it only reflects that `_dispatch_command` returned 202, not that the device acted).
- **Conclusion: BROKEN** at `dispatcher → diep/battery/BAT001/cmd → no listener (driver listens on BAT900)`, identical to the generic `BAT001` finding in `KAFKA_COMMAND_FLOW_REPORT.md` §6.

---

## 2. Peak Shaving — `POST /derms/peak_shaving`

**Route:** `fastapi/app.py:1441-1471`, `status_code=202`.

**Auth:** `require_role("operator")` + `rate_limit("derms", 60, 60)` (`app.py:1442-1444`).

**Request body — `PeakShavingRequest`** (`app.py:1379-1382`):
| Field | Type | Constraints |
|---|---|---|
| `site_name` | `str \| None` | optional |
| `reduction_kw` | `float` | required, `>= 0` |
| `max_power_kw` | `float \| None` | optional |

**Handler logic** (`app.py:1445-1471`):
1. `DERMS_REQUESTS.labels("peak_shaving").inc()` (`app.py:1445`).
2. `auth.audit(principal, "derms_peak_shaving", site_name or "auto", "ok", {"reduction_kw": ...})` (`app.py:1446-1447`).
3. `device = _select_device("battery", site_name)` (`app.py:1448`) — **always a battery**, no `device_id` input option at all; 404 "No online battery available to support peak shaving" if none.
4. Reads `battery_soc` (cached/DB, default 50.0). If `current_soc < 25` → **409** "Battery state of charge too low for safe peak shaving" (`app.py:1456-1457`).
5. `max_power = max_power_kw or reduction_kw or 5.0`; `params = {"max_power_kw": min(max_power, reduction_kw if reduction_kw>0 else max_power), "target_soc": max(current_soc-10, 20)}` (`app.py:1459-1463`).
6. `_insert_derms_request("peak_shaving", {"reduction_kw":..., "max_power_kw":...}, site_name, device_id)` (`app.py:1465-1470`).
7. `_execute_derms_command("peak_shaving", request_id, device_id, "discharge", params)` (`app.py:1471`) — **command_type is always `"discharge"`**.

**Target device:** `BAT001` (the only `battery`, status `ONLINE`). `ALLOWED_COMMANDS["battery"]` includes `discharge` — valid.

**DB recording:** same shape as battery_dispatch — `request_type='peak_shaving'`, `site_name='Abuja Site A'`, `device_id='BAT001'`, `params={"reduction_kw":..., "max_power_kw":...}` (note: this is the **original request params**, not the computed `discharge` params sent to the device — the actual dispatched `params` (`max_power_kw`/`target_soc` computed at step 5) are only visible inside `commands.params`, not `derms_requests.params`). Status lifecycle identical: `CREATED` → `EXECUTED`/`FAILED` (no `COMPLETED`).

**Expected device action — end-to-end:**
- Same as Battery Dispatch: targets `BAT001` → `discharge` command → dispatcher publishes `diep/battery/BAT001/cmd`.
- **Break point: identical** — `battery_bms` edge driver listens as `BAT900`, command never received.
- **Conclusion: BROKEN** at the same point: `dispatcher → diep/battery/BAT001/cmd → no listener (driver listens on BAT900)`.

---

## 3. Demand Response — `POST /derms/demand_response`

**Route:** `fastapi/app.py:1474-1510`, `status_code=202`.

**Auth:** `require_role("operator")` + `rate_limit("derms", 60, 60)` (`app.py:1475-1477`).

**Request body — `DemandResponseRequest`** (`app.py:1385-1388`):
| Field | Type | Constraints |
|---|---|---|
| `site_name` | `str \| None` | optional |
| `event_duration_minutes` | `int` | required, `>= 5` |
| `target_reduction_kw` | `float` | required, `>= 0` |

**Handler logic — two-tier device selection** (`app.py:1478-1510`):
1. `DERMS_REQUESTS.labels("demand_response").inc()` (`app.py:1478`).
2. `auth.audit(principal, "derms_demand_response", site_name or "auto", "ok", {"target_reduction_kw": ...})` (`app.py:1479-1480`).
3. **Tier 1 — battery** (`app.py:1481-1497`): `battery = _select_device("battery", site_name)`. If found:
   - Reads `battery_soc` (default 50.0); if `< 25` → **409** "Battery SOC too low for demand response discharge" (`app.py:1485-1486`).
   - `params = {"max_power_kw": target_reduction_kw, "event_duration_minutes": ...}` (`app.py:1487-1490`).
   - `_insert_derms_request("demand_response", {...}, battery_site, battery_device_id)` (`app.py:1491-1496`).
   - `_execute_derms_command("demand_response", request_id, battery_device_id, "discharge", params)` (`app.py:1497`).
4. **Tier 2 — EV charger** (`app.py:1499-1508`), only reached if **no battery found at all** (`_select_device` returned `None`, not just SOC-rejected — the SOC-too-low 409 at step 3 short-circuits the whole request and never falls through to Tier 2):
   - `charger = _select_device("ev_charger", site_name)`.
   - `_insert_derms_request("demand_response", {...}, charger_site, charger_device_id)` (`app.py:1501-1506`).
   - `params = {"duration_minutes": event_duration_minutes}` (`app.py:1507`).
   - `_execute_derms_command("demand_response", request_id, charger_device_id, "stop_charging", params)` (`app.py:1508`).
5. If neither tier finds a device → **404** "No DERMS-capable asset available for demand response" (`app.py:1510`).

**Target device(s):**
- **Primary:** `BAT001` (only seeded battery, `ONLINE`, `site_name='Abuja Site A'`) → `discharge`. `ALLOWED_COMMANDS["battery"]` includes `discharge` — valid.
- **Fallback (only if no battery exists in DB at all):** `EV001` (only seeded `ev_charger`, `status='ONLINE'` per `sql/001_commands.sql:27`, but **`devices.site_name` is NULL** for EV001 — never set by any seed script). `ALLOWED_COMMANDS["ev_charger"]` includes `stop_charging` — valid command_type.
  - Note: if a `site_name` filter is supplied and EV001's `site_name` is `NULL`, `_select_device("ev_charger", site_name)` would return no row (`AND site_name = %s` doesn't match `NULL`); only an unfiltered call (`site_name=None`) could select EV001. In practice this fallback is moot anyway since `BAT001` (a battery, `site_name='Abuja Site A'`) is always present and is checked first — Tier 2 is effectively dead code in the current seed data unless `BAT001`'s status is changed away from `ONLINE`.

**DB recording:** `request_type='demand_response'`, `site_name`/`device_id` = whichever device was selected, `params={"target_reduction_kw":..., "event_duration_minutes":...}` (original request params, same caveat as peak_shaving — the computed dispatch `params` differ slightly and are only in `commands.params`). Lifecycle: `CREATED` → `EXECUTED`/`FAILED`.

**Expected device action — end-to-end:**
- **Battery path (the realistic one given seed data):** targets `BAT001` → `discharge` → dispatcher publishes `diep/battery/BAT001/cmd` → **BROKEN**, same `BAT900` mismatch as flows 1 and 2.
- **EV charger path (theoretical fallback):** targets `EV001` → `stop_charging` → `_dispatch_command` produces to Kafka → dispatcher maps `device_type="ev_charger"` via `DOMAIN_MAP` → domain `charger` → publishes `diep/charger/EV001/cmd`. Per `KAFKA_COMMAND_FLOW_REPORT.md` §6, `EV001`'s legacy simulator (`simulator/ev_charger.py`) **does** subscribe to `diep/charger/EV001/cmd` (ID match), but `client.connect(BROKER, 1883, 60)` is hardcoded plaintext port 1883 against an mTLS-only (8883) broker — the simulator cannot connect at all, so it never receives the command and never acks.
- **Conclusion: BROKEN** in both cases — battery path breaks at `diep/battery/BAT001/cmd` (no `BAT900` listener); EV fallback path breaks earlier, at `EV001 simulator cannot connect to mosquitto:8883 (mTLS-only)`.

---

## 4. Load Optimization — `POST /derms/load_optimization`

**Route:** `fastapi/app.py:1513-1548`, `status_code=202`.

**Auth:** `require_role("operator")` + `rate_limit("derms", 60, 60)` (`app.py:1514-1516`).

**Request body — `LoadOptimizationRequest`** (`app.py:1391-1394`):
| Field | Type | Constraints |
|---|---|---|
| `site_name` | `str \| None` | optional |
| `objective` | `str` | default `"maximize_solar"` |
| `optimization_horizon_hours` | `int` | default `1`, `>= 1` |

**Handler logic** (`app.py:1517-1548`):
1. `DERMS_REQUESTS.labels("load_optimization").inc()` (`app.py:1517`).
2. `auth.audit(principal, "derms_load_optimization", site_name or "auto", "ok", {"objective": ...})` (`app.py:1518-1519`).
3. `battery = _select_device("battery", site_name)` (`app.py:1520`); 404 "No battery asset available for load optimization" if none (`app.py:1521-1522`).
4. Reads `battery_soc` (default 50.0). Branches on `objective.lower()`:
   - `"maximize_solar"` → `command_type="charge"`, `target_soc = min(current_soc+20, 90)` (`app.py:1527-1529`).
   - `"min_cost"` → `charge` if `soc<50` else `discharge`; `target_soc = 50` or `max(soc-20,20)` (`app.py:1530-1532`).
   - else (default branch) → `charge` if `soc<60` else `discharge`; `target_soc = 60` or `max(soc-20,20)` (`app.py:1533-1535`).
5. `params = {"target_soc": ..., "max_power_kw": 10, "optimization_horizon_hours": ...}` (`app.py:1537-1541`) — note `max_power_kw` is **hardcoded to `10`**, not user-supplied (the request model has no `max_power_kw` field at all).
6. `_insert_derms_request("load_optimization", {"objective":..., "optimization_horizon_hours":...}, site_name, device_id)` (`app.py:1542-1547`).
7. `_execute_derms_command("load_optimization", request_id, device_id, command_type, params)` (`app.py:1548`).

**Target device:** `BAT001` (only seeded battery, `ONLINE`). `command_type` is always `charge` or `discharge` — both in `ALLOWED_COMMANDS["battery"]`.

**DB recording:** `request_type='load_optimization'`, `site_name='Abuja Site A'`, `device_id='BAT001'`, `params={"objective":..., "optimization_horizon_hours":...}`. Lifecycle: `CREATED` → `EXECUTED`/`FAILED` (no `COMPLETED`).

**Expected device action — end-to-end:**
- Targets `BAT001` → `charge`/`discharge` → dispatcher publishes `diep/battery/BAT001/cmd`.
- **Break point: identical to flows 1-3** — `battery_bms` edge driver listens as `BAT900`, command never received, never acked.
- **Conclusion: BROKEN**, same break point as Battery Dispatch and Peak Shaving.

---

## 5. Tracking a DERMS request — `GET /derms/requests` and `/derms/requests/{request_id}`

**`GET /derms/requests`** (`app.py:1551-1577`, no auth required):
- Query params: `limit: int = 50`, `request_type: str | None = None` (filter by `battery_dispatch`/`peak_shaving`/`demand_response`/`load_optimization`).
- Returns `{"requests": [...]}`, each row: `request_id, request_type, site_name, device_id, params, status, created_at, executed_at, completed_at, error_message` (timestamps ISO-formatted).

**`GET /derms/requests/{request_id}`** (`app.py:1580-1598`, no auth required):
- Same column set as above for a single row; **404** "Unknown DERMS request '{request_id}'" if not found.

**How a caller would track to "completion":**
- A caller polls `GET /derms/requests/{request_id}` and watches `status`.
- **In practice, `status` only ever reaches `EXECUTED` (success) or `FAILED` (an `HTTPException` raised inside `_dispatch_command`, e.g. unknown device/invalid command/Kafka error)** — these reflect only that `_dispatch_command` accepted/rejected the underlying `commands` row, **not** that the physical device executed anything.
- `status='COMPLETED'` is **never written by any code path** (confirmed via `grep -n "COMPLETED\|completed_at" fastapi/app.py` — `completed_at`/`'COMPLETED'` appear only in the `_update_derms_request_status` function signature/SQL template and the SELECTs in the GET endpoints; no call site passes `completed_at` or `status="COMPLETED"`). So `derms_requests.completed_at` is **always NULL** and `status` never progresses beyond `EXECUTED`/`FAILED` regardless of whether the device ever acks.
- The *only* way to observe whether the device actually acted is to separately track the underlying `commands` row via `GET /commands/{command_id}` (the `command_id` is returned in the DERMS response body's `command` sub-object, e.g. `{"request_id":..., "device_id":..., "command_type":..., "command": {"command_id":..., "device_id":..., ..., "status":"SENT", "topic":...}}` — see `_dispatch_command`'s return shape, mirrored from `POST /commands`). Given the `BAT900`/`BAT001` device-ID mismatch (§1-4 above), that `commands.status` will be stuck at `SENT` forever for all 4 DERMS flows in the current system state — and `derms_requests.status='EXECUTED'` gives **no indication** of this; it looks identical to a flow whose command was successfully delivered and acked.

---

## 6. Prometheus metrics — `DERMS_REQUESTS` / `DERMS_COMMANDS`

Defined at `app.py:192-197`:
```python
DERMS_REQUESTS = Counter(
    "diep_derms_requests_total", "DERMS requests accepted",
    ["request_type"])
DERMS_COMMANDS = Counter(
    "diep_derms_commands_total", "DERMS commands produced",
    ["request_type", "command_type"])
```

- **`DERMS_REQUESTS.labels(request_type).inc()`** is incremented at the **very top** of each handler, **before any validation/device-lookup** (`app.py:1401`, `1445`, `1478`, `1517`) — i.e. it increments even if the request subsequently 404s (no device found) or 409s (SOC too low) or 422s (wrong device type). It measures "DERMS endpoint was called", not "DERMS action succeeded".
- **`DERMS_COMMANDS.labels(request_type, command_type).inc()`** is incremented inside `_execute_derms_command()` at `app.py:711`, **only after** `_dispatch_command()` returns successfully (i.e. the `commands` row was inserted, Kafka produce succeeded, and `commands.status` was marked `SENT`). If `_dispatch_command` raises `HTTPException` (unknown device/invalid command/Kafka failure), `DERMS_COMMANDS` is **not** incremented (the `except HTTPException` branch at `app.py:723-730` only updates `derms_requests.status='FAILED'`).
- Neither metric reflects device-side ack/execution — there is no `DERMS_*_acked`/`completed` metric. Given the device-ID mismatches, `DERMS_COMMANDS` would increment normally (Kafka produce succeeds) for all 4 flows, but this says nothing about whether `BAT001`/`EV001` ever received the command.

---

## 7. Multi-tenancy — confirmed gap

`FASTAPI_VALIDATION_REPORT.md` §6 item 8 flagged that DERMS endpoints might lack the
`_assert_tenant_access()` check applied to `POST /commands`. **Confirmed by direct code reading:**

- `_assert_tenant_access(principal, device_id)` is defined at `app.py:778-791` and is called **exactly once** in the entire file: `app.py:2046`, inside `POST /commands`'s `create_command()` handler, immediately after `require_role("operator")`/`rate_limit` dependencies and before `_dispatch_command()` is invoked.
- Grepping the 4 DERMS handlers (`app.py:1397-1548`) for `_assert_tenant_access` returns **no matches**. None of `battery_dispatch` (1397-1438), `peak_shaving` (1441-1471), `demand_response` (1474-1510), or `load_optimization` (1513-1548) call it.
- `_execute_derms_command()` (`app.py:702-730`) — the shared dispatch wrapper — also does not call it; it goes straight to `_dispatch_command(CommandRequest(...))` which itself has **no** `_assert_tenant_access` call (that check lives only in the `create_command` HTTP handler at line 2046, not in `_dispatch_command` itself, `app.py:1931-2037`).
- `_select_device()` (`app.py:683-699`) and `_device_row()` (referenced at `app.py:1406`) both query `devices` with **no `tenant_id` filter** — `SELECT device_id, device_type, location, status, site_name FROM devices WHERE device_type = %s AND status = 'ONLINE' [AND site_name = %s] ...`.

**Conclusion: GAP CONFIRMED.** A tenant-scoped `operator` principal (e.g. `acme-op`, `globex-op` per `fastapi/auth.py:44-52`) can call any of the 4 `/derms/*` endpoints with an arbitrary `device_id` (battery_dispatch only) or `site_name` belonging to a **different tenant's** site/device, and `_dispatch_command` will issue a real `commands` row + Kafka message against that device with no tenant ownership check at any point in the DERMS call chain. This is in contrast to `POST /commands`, which calls `_assert_tenant_access()` at `app.py:2046` and would raise `403 "device '<id>' belongs to another tenant"` for the same cross-tenant attempt. (In the current single-tenant seed data — all devices have `tenant_id` unset/`'default'` — this gap is latent rather than actively exploitable, but the code path is open.)

---

## Summary Table

| DERMS Flow | Endpoint | Target Device(s) | DB Recording | End-to-End Status | Break Point |
|---|---|---|---|---|---|
| Battery Dispatch | `POST /derms/battery_dispatch` (`app.py:1397`) | `BAT001` (explicit `device_id` or `_select_device("battery", site_name)`) — `charge`/`discharge`/`idle` | `derms_requests`: `request_type='battery_dispatch'`, `device_id='BAT001'`, `site_name='Abuja Site A'`, `status` CREATED→EXECUTED/FAILED (never COMPLETED) | **Broken** | Dispatcher publishes `diep/battery/BAT001/cmd`; `battery_bms` edge driver subscribes as `BAT900` → command never received, no ack |
| Peak Shaving | `POST /derms/peak_shaving` (`app.py:1441`) | `BAT001` (`_select_device("battery", site_name)`, SOC must be ≥25) — always `discharge` | `derms_requests`: `request_type='peak_shaving'`, `device_id='BAT001'`, `status` CREATED→EXECUTED/FAILED | **Broken** | Same `diep/battery/BAT001/cmd` vs `BAT900` mismatch |
| Demand Response | `POST /derms/demand_response` (`app.py:1474`) | Tier 1: `BAT001` (`discharge`, if SOC≥25); Tier 2 (only if no battery exists): `EV001` (`stop_charging`) | `derms_requests`: `request_type='demand_response'`, `device_id`=selected device, `status` CREATED→EXECUTED/FAILED | **Broken** | Battery path: `diep/battery/BAT001/cmd` vs `BAT900`. EV fallback path: `EV001` simulator hardcodes plaintext MQTT 1883 against mTLS-only 8883 broker — cannot connect at all |
| Load Optimization | `POST /derms/load_optimization` (`app.py:1513`) | `BAT001` (`_select_device("battery", site_name)`) — `charge`/`discharge` per objective, `max_power_kw` hardcoded to 10 | `derms_requests`: `request_type='load_optimization'`, `device_id='BAT001'`, `status` CREATED→EXECUTED/FAILED | **Broken** | Same `diep/battery/BAT001/cmd` vs `BAT900` mismatch |

**Cross-cutting findings:**
- All 4 flows reuse `_dispatch_command()` (`app.py:1931-2037`) verbatim — same Kafka topic `diep.commands`, same `commands` table, same dispatcher path documented in `KAFKA_COMMAND_FLOW_REPORT.md`.
- `derms_requests.status` never reaches `COMPLETED`/`completed_at` is never set (no call site passes it) — `EXECUTED` means "the `commands` row was created and produced to Kafka successfully," not "the device executed it."
- All 3 of `BAT001`'s flows hit the identical break point already documented in `KAFKA_COMMAND_FLOW_REPORT.md` §6 (BAT900 vs BAT001 topic mismatch).
- `DERMS_REQUESTS` increments on every call (even failed ones); `DERMS_COMMANDS` increments only after a successful `_dispatch_command()` (Kafka produce succeeded) — neither reflects device-side ack.
- **Multi-tenancy gap confirmed**: none of the 4 DERMS handlers, nor `_execute_derms_command`/`_dispatch_command`, call `_assert_tenant_access()` (only `POST /commands` at `app.py:2046` does); `_select_device`/`_device_row` queries are not tenant-filtered.
