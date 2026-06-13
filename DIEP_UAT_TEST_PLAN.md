# DIEP Customer Acceptance Test (UAT) Plan (Phase 16, Task 4)

**Date:** 2026-06-13
**Scope:** Customer User Acceptance Test plan for the five core DERMS functions —
Battery Dispatch, Peak Shaving, Demand Response, EV Charging, and Microgrid Optimization.
Each scenario specifies preconditions, steps, expected results across all layers
(API → DB → Kafka → MQTT → device → ack), and explicit pass/fail criteria.

**Status reference:** the five-phase remediation documented in
`FINAL_DIEP_READINESS_REPORT.md` §8 exercised these scenarios live and observed full
`PENDING → SENT → ACKED` command lifecycles with sub-150ms round-trip latency. This plan
formalizes those same scenarios as repeatable, criteria-based acceptance tests for a
customer pilot sign-off.

---

## 0. General setup

### 0.1 Pre-requisites

- Full stack running and healthy: `docker compose ps` shows all services `Up`;
  `GET /healthz` and `GET /readyz` return 200 with `{"ready": true}`.
- Seed data present: `devices` table contains `BAT001` (battery, site "Abuja Site A",
  `status='ONLINE'`, `battery_soc>=25`), `EV001` (ev_charger), `MG001` (microgrid),
  `INV001` (solar), `METER001` (meter).
- Edge drivers running and subscribed to their matching device-ID topics
  (`diep-battery-edge`, `diep-ev-charger`, `diep-microgrid-edge`, `diep-sunspec-edge`,
  `diep-meter-edge`).
- Auth: an operator-role bearer token obtained via:
  ```bash
  curl -s -X POST http://localhost:8000/auth/token \
    -d "username=operator&password=<DIEP_OPERATOR_PASSWORD>" | jq -r .access_token
  ```
  (or use the static `DIEP_OPERATOR_KEY` as a Bearer token directly).

### 0.2 Common verification points (apply to every scenario)

| Layer | What to check |
|---|---|
| API response | HTTP status (200/202) and `request_id`/`command_id` in body |
| `derms_requests` (Postgres) | new row, `status` transitions `CREATED` → `EXECUTED` |
| `commands` (Postgres) | new row, `status` transitions `PENDING` → `SENT` → `ACKED`, `acked_at` set within a few seconds |
| Kafka (`diep.commands`) | message produced, key = `device_id` |
| MQTT | `diep/<domain>/<DEVICE_ID>/cmd` published, `diep/<domain>/<DEVICE_ID>/ack` received |
| Redis | `state:<DEVICE_ID>` updated with `last_command_id/status/acked_at` |
| `audit_events` | row with `principal`, `role=operator`, `result='ok'` |
| Portal | `/derms` shows the request `EXECUTED`; `/twins/<DEVICE_ID>` shows command `ACKED` |
| Metrics | `diep_commands_acked_total` incremented for the device |

A scenario is **PASS** only if **all** applicable rows above reach their expected
end-state within **10 seconds** of the API call. Any row stuck at `SENT`/`PENDING`/`CREATED`
past 10 seconds, or any 4xx/5xx unrelated to the documented business-rule responses (e.g.
the SOC-too-low 409 in Scenario 2), is a **FAIL**.

---

## 1. Scenario: Battery Dispatch (BAT001 → target SOC 80%)

**Objective:** Verify an operator can dispatch a battery to a target state of charge and
the command reaches the device and is acknowledged.

### Steps
1. `GET /assets/BAT001` — record current `battery_soc`.
2. ```bash
   curl -s -X POST http://localhost:8000/derms/battery_dispatch \
     -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" \
     -d '{"device_id":"BAT001","target_soc":80,"max_power_kw":10}'
   ```
3. Poll `GET /commands/{command_id}` until `status='ACKED'` (timeout 10s).
4. `GET /derms/requests/{request_id}` — confirm `status='EXECUTED'`.
5. `GET /state/BAT001` (or Redis `state:BAT001`) — confirm `last_command_status='ACKED'`.

### Expected result
- `commands` row: `command_type` = `charge` (if current SOC < 80) or `discharge` (if > 80),
  `status` reaches `ACKED`.
- `derms_requests.status = 'EXECUTED'`.
- Edge driver (`diep-battery-edge`, device ID `BAT001`) logs receipt of the command on
  `diep/battery/BAT001/cmd` and publishes `diep/battery/BAT001/ack`.

### Pass criteria
- All §0.2 common checks pass within 10s.
- `command_type` matches the SOC-vs-target direction (charge if soc<target, discharge if soc>target).

### Fail criteria
- `commands.status` stuck at `SENT` (no ack) — indicates a device-ID/topic mismatch
  between the dispatcher and the edge driver (historical issue, resolved per
  `FINAL_DIEP_READINESS_REPORT.md` §4/§8 — re-verify if regression suspected).

---

## 2. Scenario: Peak Shaving (site-wide, reduce 5 kW)

**Objective:** Verify a site-level peak-shaving request selects an appropriate battery
and dispatches a discharge command, with correct business-rule gating on SOC.

### Steps
1. Confirm `BAT001.battery_soc >= 25` (precondition for the non-rejection path).
2. ```bash
   curl -s -X POST http://localhost:8000/derms/peak_shaving \
     -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" \
     -d '{"site_name":"Abuja Site A","reduction_kw":5,"max_power_kw":10}'
   ```
3. Poll `GET /commands/{command_id}` until `status='ACKED'`.
4. Repeat with a battery whose `battery_soc < 25` (test data variant) and confirm the
   API returns **409** with message "Battery state of charge too low for safe peak shaving"
   and **no** `commands`/Kafka/MQTT activity occurs.

### Expected result
- Normal case (SOC ≥ 25): `commands` row `command_type='discharge'`,
  `params.max_power_kw = min(max_power_kw, reduction_kw)`, `params.target_soc = max(soc-10, 20)`;
  full lifecycle reaches `ACKED`.
- Low-SOC case (SOC < 25): HTTP 409, no side effects in `commands`/Kafka/MQTT.

### Pass criteria
- Normal case passes all §0.2 checks within 10s.
- Low-SOC case returns 409 and produces zero new `commands`/Kafka/MQTT/audit rows
  (other than the audit entry for the rejected request, if any).

### Fail criteria
- Normal case command stuck at `SENT`.
- Low-SOC case proceeds to dispatch a command anyway (safety-rule bypass).

---

## 3. Scenario: Demand Response (30-minute event, reduce 5 kW)

**Objective:** Verify a demand-response event is created against the site's battery
(Tier 1) and, where no battery is available, falls back to curtailing EV charging (Tier 2).

### Steps — Tier 1 (battery available)
1. Confirm `BAT001` exists, `status='ONLINE'`, `battery_soc >= 25`.
2. ```bash
   curl -s -X POST http://localhost:8000/derms/demand_response \
     -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" \
     -d '{"site_name":"Abuja Site A","event_duration_minutes":30,"target_reduction_kw":5}'
   ```
3. Confirm `commands` row: `device_id='BAT001'`, `command_type='discharge'`,
   `params={"max_power_kw":5,"event_duration_minutes":30}`, reaches `ACKED`.

### Steps — Tier 2 (no battery row for the site — test-data variant)
4. Using a site/device configuration with no battery, repeat step 2 against that site.
5. Confirm `commands` row: `device_id='EV001'`, `command_type='stop_charging'`,
   `params={"duration_minutes":30}`, publishes to `diep/charger/EV001/cmd`, reaches `ACKED`.

### Pass criteria
- Tier 1: full lifecycle to `ACKED` within 10s, correct `discharge` command on `BAT001`.
- Tier 2: full lifecycle to `ACKED` within 10s, correct `stop_charging` command on `EV001`,
  reachable only via `diep/charger/EV001/cmd` (mTLS 8883).

### Fail criteria
- Either tier's command stuck at `SENT`.
- Tier 2 device connects via plaintext MQTT (1883) instead of mTLS (8883) — connection
  refused by the broker (`allow_anonymous false`, Phase 9J-S4). This was a historical
  failure mode (`END_TO_END_TEST_SCENARIOS.md` Scenario 3/4) — confirm the EV charger
  edge driver (`docker-compose-ev-charger.yml`) uses `MQTT_PORT=8883`/`MQTT_TLS=1` with
  the `EV001` client cert before sign-off.

---

## 4. Scenario: EV Charger Control (EV001 → start_charging, 7 kW limit)

**Objective:** Verify generic command issuance (`POST /commands`) for EV charger
start/stop/limit operations.

### Steps
1. ```bash
   curl -s -X POST http://localhost:8000/commands \
     -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" \
     -d '{"device_id":"EV001","command_type":"start_charging","params":{"limit_kw":7},"issued_by":"uat-operator"}'
   ```
2. Poll `GET /commands/{command_id}` until `status='ACKED'`.
3. `GET /devices/EV001` / `/twins/EV001` — confirm the device reflects `start_charging`
   state on next telemetry cycle (`power_kw` rises toward `limit_kw`).
4. Repeat with `command_type='set_limit'` (`params.limit_kw` changed) and
   `command_type='stop_charging'`; confirm each reaches `ACKED` and `power_kw` responds
   accordingly (drops to 0 on stop).

### Pass criteria
- All three command types (`start_charging`, `set_limit`, `stop_charging`) reach `ACKED`
  within 10s via `diep/charger/EV001/cmd` ↔ `diep/charger/EV001/ack` over mTLS 8883.
- `audit_events` contains an `issue_command` row with `resource='EV001:<command_type>'`
  for each call.
- Telemetry for `EV001` (`power_kw`, `session_energy_kwh`) reflects the commanded state
  within one telemetry interval (≤ 30s).

### Fail criteria
- `commands.status` stuck at `SENT` — historically caused by the EV charger simulator
  connecting via plaintext MQTT 1883 against the mTLS-only broker
  (`END_TO_END_TEST_SCENARIOS.md` Scenario 4/`MQTT_FLOW_VALIDATION_REPORT.md` §6). Confirm
  this has been corrected (per `FINAL_DIEP_READINESS_REPORT.md` §4/§8, `EV001` reached
  `ACKED` in ~80ms after remediation) before sign-off.

---

## 5. Scenario: Microgrid Optimization (MG001 → load optimization / setpoint)

**Objective:** Verify the load-optimization DERMS function issues a `set_setpoint`
command to the microgrid controller and/or battery, and the microgrid reflects the new
operating point.

### Steps
1. ```bash
   curl -s -X POST http://localhost:8000/derms/load_optimization \
     -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" \
     -d '{"site_name":"Abuja Site A"}'
   ```
2. Poll `GET /commands/{command_id}` until `status='ACKED'`.
3. Confirm `commands` row for `MG001`: `command_type='set_setpoint'`, includes a
   `params.setpoint` (or equivalent) value, reaches `ACKED`.
4. `GET /assets/MG001/health` and `/twins/MG001` — confirm telemetry (`frequency`,
   `power_kw`) reflects the new setpoint within one telemetry interval.
5. (Extended) issue a direct `island` / `grid_connect` command via `POST /commands`
   (`ALLOWED_COMMANDS["microgrid"] = {"island","grid_connect","set_setpoint"}`) and
   confirm each reaches `ACKED`.

### Pass criteria
- `load_optimization` request reaches `derms_requests.status='EXECUTED'` and its
  associated `commands` row reaches `ACKED` within 10s
  (per `FINAL_DIEP_READINESS_REPORT.md` §4, `MG001 set_setpoint` ACKED in ~108ms).
- `island`/`grid_connect`/`set_setpoint` direct commands each reach `ACKED` via
  `diep/microgrid/MG001/cmd` ↔ `.../ack` over mTLS 8883.

### Fail criteria
- Any of the three allowed microgrid command types fails to ack.
- `MG001` telemetry does not reflect a `set_setpoint` change within 30s.

---

## 6. Sign-off

| Scenario | Result (PASS/FAIL) | Tester | Date | Notes |
|---|---|---|---|---|
| 1. Battery Dispatch | | | | |
| 2. Peak Shaving | | | | |
| 3. Demand Response | | | | |
| 4. EV Charging | | | | |
| 5. Microgrid Optimization | | | | |

**Acceptance criteria:** all five scenarios PASS, with no `commands` rows stuck at
`PENDING`/`SENT` and no unexpected 4xx/5xx responses, for the platform to be accepted for
pilot go-live.
