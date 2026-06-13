# DIEP End-to-End Test Scenarios (Phase 7)

**Mode:** Read-only / static analysis. No commands in this document have been executed against a
live system. Each scenario shows (a) the exact request an operator would issue, (b) the
**as-designed** expected MQTT/Kafka/DB/portal behavior if the platform were fully wired, and
(c) the **actual outcome given the current repository state** (per
`DATABASE_VALIDATION_REPORT.md`, `FASTAPI_VALIDATION_REPORT.md`, `MQTT_FLOW_VALIDATION_REPORT.md`,
`KAFKA_COMMAND_FLOW_REPORT.md`, `DERMS_VALIDATION_REPORT.md`, `PORTAL_VALIDATION_REPORT.md`),
assuming TimescaleDB has been restored and the rest of the stack has been started per
`DIEP_PLATFORM_ASSESSMENT.md` §C.4/D.

All 5 scenarios assume base URL `http://localhost:8000`, `DIEP_AUTH_ENFORCED=1`, and an
operator-role bearer token (`<DIEP_OPERATOR_KEY>` from `.env`).

---

## Scenario 1: Battery Dispatch (BAT001 → target SOC 80%)

### Command
```bash
curl -s -X POST http://localhost:8000/derms/battery_dispatch \
  -H "Authorization: Bearer <DIEP_OPERATOR_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"device_id":"BAT001","target_soc":80,"max_power_kw":10}'
```
(`fastapi/app.py:1397-1438`)

### As-designed expected flow

| Layer | Expected |
|---|---|
| **DB (immediate)** | `derms_requests`: new row, `request_type='battery_dispatch'`, `device_id='BAT001'`, `site_name='Abuja Site A'`, `params={"target_soc":80,"max_power_kw":10}`, `status='CREATED'` → `'EXECUTED'`. `commands`: new row, `command_type='charge'` or `'discharge'` (depends on current `battery_soc` vs 80), `status='PENDING'`→`'SENT'`, `dispatched_at` set. |
| **Kafka** | Producer sends to `diep.commands`, key=`BAT001`, value=`{"command_id":..., "device_id":"BAT001","device_type":"battery","command_type":"charge|discharge","params":{"target_soc":80,"max_power_kw":10},"issued_by":"...","issued_at":...}`. |
| **MQTT** | Dispatcher consumes, maps `battery`→domain `battery`, publishes `diep/battery/BAT001/cmd` (qos=1) with the Kafka message body. Device subscribes `diep/battery/BAT001/cmd`, executes, publishes `diep/battery/BAT001/ack` `{"command_id":...,"status":"ACKED"}`. |
| **Ack round-trip** | Dispatcher receives ack, `POST /commands/{command_id}/ack` (Bearer `DIEP_SERVICE_TOKEN`) → `commands.status='ACKED'`, `acked_at=now()`. |
| **Portal** | `/derms` page: new row appears in DERMS request table via `GET /derms/requests`, status `EXECUTED`. `/fleet` and `/twins/BAT001`: `battery_soc` in `state:BAT001` Redis mirror updates as the device telemetry reflects the new charge/discharge mode. |
| **Metrics** | `diep_derms_requests_total{request_type="battery_dispatch"}`++, `diep_derms_commands_total{request_type="battery_dispatch",command_type="charge|discharge"}`++, `diep_commands_issued_total`/`diep_commands_sent_total`/`diep_commands_acked_total`++. |

### Actual outcome (current repo state)

1. `derms_requests` row created, `status='EXECUTED'` — **succeeds** (DB-only, no external dependency failure assuming Kafka reachable per recovery sequence).
2. `commands` row created, `status` transitions `PENDING`→`SENT` — **succeeds** if Kafka (root-compose SASL/9094) is up and on the same network as FastAPI (`KAFKA_COMMAND_FLOW_REPORT.md` §1/§7).
3. Kafka message produced and consumed by dispatcher — **succeeds** if network-name reconciliation is done (`diep-lab_diep-net`).
4. Dispatcher publishes `diep/battery/BAT001/cmd` to mosquitto:8883 (mTLS) — **succeeds** (dispatcher cert/config correct, `KAFKA_COMMAND_FLOW_REPORT.md` §3/§7).
5. **BREAK**: the running `battery_bms` edge driver (`docker-compose-battery-edge.yml`) subscribes as device **`BAT900`**, i.e. `diep/battery/BAT900/cmd` — **no subscriber for `diep/battery/BAT001/cmd`**. Command is published into the void.
6. No `/ack` is ever published → `commands.status` stuck at **`SENT`** forever; `acked_at` stays `NULL`.
7. `derms_requests.status` remains `'EXECUTED'` — **gives no indication of the failure**; `completed_at`/`'COMPLETED'` is never set by any code path (`DERMS_VALIDATION_REPORT.md` §5).
8. Portal `/derms` page shows the request as `EXECUTED` (looks "successful"); `/twins/BAT001` shows no change in `battery_soc`/mode because the device never received the command.
9. `diep_derms_commands_total{request_type="battery_dispatch"}` increments (Kafka produce succeeded); `diep_commands_acked_total` for `BAT001` never increments.

**Verdict: Partially works (DB + Kafka legs), broken at device delivery (`BAT001` vs `BAT900` topic mismatch).**

---

## Scenario 2: Peak Shaving (site-wide, reduce 5 kW)

### Command
```bash
curl -s -X POST http://localhost:8000/derms/peak_shaving \
  -H "Authorization: Bearer <DIEP_OPERATOR_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"site_name":"Abuja Site A","reduction_kw":5,"max_power_kw":10}'
```
(`fastapi/app.py:1441-1471`)

### As-designed expected flow

| Layer | Expected |
|---|---|
| **DB** | `_select_device("battery","Abuja Site A")` → `BAT001` (`status='ONLINE'`). If `battery_soc >= 25`: `derms_requests` row `request_type='peak_shaving'`, `device_id='BAT001'`, `params={"reduction_kw":5,"max_power_kw":10}`, `status='CREATED'`→`'EXECUTED'`. `commands` row: `command_type='discharge'`, `params={"max_power_kw":min(10,5)=5,"target_soc":max(soc-10,20)}`. |
| **Kafka/MQTT** | Same path as Scenario 1 — produce to `diep.commands`, dispatcher publishes `diep/battery/BAT001/cmd`. |
| **Portal** | `/derms` shows new `peak_shaving` request `EXECUTED`; dashboard `MetricCard`s reflecting reduced grid import would update once telemetry from `BAT001` reflects `discharge` mode. |

### Actual outcome (current repo state)

1. If `BAT001.battery_soc < 25` (e.g. fresh/restored DB seed has `soc=50`, so this branch is **not** hit by default — proceeds normally) → otherwise **409** "Battery state of charge too low for safe peak shaving" and no `commands`/Kafka/MQTT activity at all.
2. With seed `soc=50` (≥25): `derms_requests` + `commands` rows created exactly as Scenario 1 — same Kafka/MQTT path.
3. **Identical break point**: dispatcher publishes `diep/battery/BAT001/cmd`; `battery_bms` driver listens on `BAT900` → command never received, never acked.
4. `derms_requests.status='EXECUTED'`, `commands.status` stuck at `SENT`.
5. Portal `/derms` shows `EXECUTED` (apparently successful); no observable change in telemetry/`/fleet` `MetricCard`s for `BAT001`.

**Verdict: Same as Scenario 1 — broken at `BAT001`/`BAT900` device-ID mismatch.**

---

## Scenario 3: Demand Response (30-min event, reduce 5 kW)

### Command
```bash
curl -s -X POST http://localhost:8000/derms/demand_response \
  -H "Authorization: Bearer <DIEP_OPERATOR_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"site_name":"Abuja Site A","event_duration_minutes":30,"target_reduction_kw":5}'
```
(`fastapi/app.py:1474-1510`)

### As-designed expected flow

| Layer | Expected |
|---|---|
| **DB** | Tier 1: `_select_device("battery","Abuja Site A")` → `BAT001`. If `battery_soc >= 25`: `derms_requests` row `request_type='demand_response'`, `device_id='BAT001'`, `params={"target_reduction_kw":5,"event_duration_minutes":30}`, `status='CREATED'`→`'EXECUTED'`. `commands` row: `command_type='discharge'`, `params={"max_power_kw":5,"event_duration_minutes":30}`. |
| **Tier 2 fallback (only if no battery row exists at all)** | `_select_device("ev_charger", site_name)` → `EV001`; `command_type='stop_charging'`, `params={"duration_minutes":30}`, publishes `diep/charger/EV001/cmd`. |
| **Kafka/MQTT** | Battery path: `diep/battery/BAT001/cmd`. EV path: `diep/charger/EV001/cmd`. |
| **Portal** | `/derms` shows new `demand_response` request `EXECUTED`. |

### Actual outcome (current repo state)

1. With seed data, `BAT001` exists and is `ONLINE` with `soc=50` (≥25) → **Tier 1 (battery) is always taken**; Tier 2 (EV001) is effectively dead code with the current seed (`DERMS_VALIDATION_REPORT.md` §3).
2. `derms_requests` + `commands` rows created (`device_id='BAT001'`, `command_type='discharge'`) — same Kafka path as Scenarios 1-2.
3. **Same break point**: `diep/battery/BAT001/cmd` published, `battery_bms` driver listens on `BAT900` → never received, never acked.
4. **If Tier 2 were ever exercised** (e.g. `BAT001` removed/offline): `EV001`'s legacy simulator (`simulator/ev_charger.py`) **does** subscribe to the matching topic `diep/charger/EV001/cmd` (ID match — the one device where IDs align), but `client.connect(BROKER, 1883, 60)` is hardcoded **plaintext port 1883** against the mTLS-only (8883) broker — `ConnectionRefusedError`, identical failure mode to `diep-microgrid`. Command never received either way.
5. `derms_requests.status='EXECUTED'` either way — no visibility into the failure.

**Verdict: Broken regardless of which tier is taken — Tier 1 hits the `BAT001`/`BAT900` mismatch; Tier 2 (if reached) hits the EV001 plaintext-MQTT-vs-mTLS-broker break.**

---

## Scenario 4: EV Charger Control (EV001 → start_charging, 7 kW limit)

This flow is **not** a `/derms/*` endpoint — EV charger control is issued via the generic
`POST /commands` endpoint (no DERMS wrapper exists for `ev_charger` outside the demand-response
fallback in Scenario 3).

### Command
```bash
curl -s -X POST http://localhost:8000/commands \
  -H "Authorization: Bearer <DIEP_OPERATOR_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"device_id":"EV001","command_type":"start_charging","params":{"limit_kw":7},"issued_by":"operator-test"}'
```
(`fastapi/app.py:2040-2050`; `ALLOWED_COMMANDS["ev_charger"] = {"start_charging","stop_charging","set_limit"}`, `app.py:80`)

### As-designed expected flow

| Layer | Expected |
|---|---|
| **DB** | `commands` row: `device_id='EV001'`, `device_type='ev_charger'`, `command_type='start_charging'`, `params={"limit_kw":7}`, `status='PENDING'`→`'SENT'`. `audit_events` row: `action='issue_command'`, `resource='EV001:start_charging'`. |
| **Kafka** | Produce to `diep.commands`, key=`EV001`. |
| **MQTT** | Dispatcher: `device_type='ev_charger'` → `DOMAIN_MAP["ev_charger"]="charger"` → publishes `diep/charger/EV001/cmd`. `simulator/ev_charger.py` subscribes `CMD_TOPIC=diep/charger/EV001/cmd` (`ev_charger.py:68`) — **device IDs match**. Device starts charging, publishes `diep/charger/EV001/ack` `{"command_id":...,"status":"ACKED"}` (`ev_charger.py:89`). |
| **Ack** | Dispatcher → `POST /commands/{command_id}/ack` → `commands.status='ACKED'`, `acked_at=now()`. |
| **Portal** | `/twins/EV001`: `GET /commands?device_id=EV001` shows the command transitioning `SENT`→`ACKED`; `CommandModal` (if used) shows success. `/fleet`: EV001's `power_kw`/`session_energy_kwh` (via `extra`) update on next telemetry POST. |

### Actual outcome (current repo state)

1. `commands` row + `audit_events` row created, Kafka produce succeeds (assuming Kafka/network fixed) — **succeeds**, `status='SENT'`.
2. Dispatcher publishes `diep/charger/EV001/cmd` — **this is the one seeded device where the dispatcher's topic and the device's subscribed topic actually match** (`KAFKA_COMMAND_FLOW_REPORT.md` §6, `EV001` row).
3. **BREAK**: `simulator/ev_charger.py:98` does `client.connect(BROKER, 1883, 60)` with `username_pw_set("diep-device","device-pass-2026")` — **hardcoded plaintext MQTT on port 1883, no TLS, no client cert**. The active `mosquitto.conf` serves **only mTLS on 8883** (`require_certificate true`) — the simulator's `connect()` call fails with `ConnectionRefusedError` (the exact failure mode currently observed for `diep-microgrid`, `MQTT_FLOW_VALIDATION_REPORT.md` §6). The simulator never establishes an MQTT session at all, so it neither subscribes `diep/charger/EV001/cmd` nor could publish `diep/charger/EV001/ack`.
4. `commands.status` stuck at `SENT` forever; no `audit_events` row for the ack (ack handler doesn't audit anyway, `KAFKA_COMMAND_FLOW_REPORT.md` §5).
5. Portal `/twins/EV001` `GET /commands?device_id=EV001` shows `status: SENT` indefinitely; no telemetry updates for `EV001` either (Scenario applies to `MQTT_FLOW_VALIDATION_REPORT.md`'s finding that `EV001`'s telemetry path is also broken at the same plaintext-vs-mTLS hop).

**Verdict: Broken — the only seeded device with matching command/ack topic IDs, but its simulator cannot connect to the mTLS-only broker at all (neither for telemetry nor for commands/acks).**

---

## Scenario 5: Microgrid Optimization (MG001 → set_setpoint)

Like Scenario 4, microgrid control has no dedicated DERMS endpoint — `microgrid` commands go via
`POST /commands` directly. (`ALLOWED_COMMANDS["microgrid"] = {"island","grid_connect","set_setpoint"}`,
`app.py:83`.)

### Command
```bash
curl -s -X POST http://localhost:8000/commands \
  -H "Authorization: Bearer <DIEP_OPERATOR_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"device_id":"MG001","command_type":"set_setpoint","params":{"setpoint_kw":15},"issued_by":"operator-test"}'
```

### As-designed expected flow

| Layer | Expected |
|---|---|
| **DB** | `commands` row: `device_id='MG001'`, `device_type='microgrid'`, `command_type='set_setpoint'`, `params={"setpoint_kw":15}`, `status='PENDING'`→`'SENT'`. `audit_events`: `action='issue_command'`, `resource='MG001:set_setpoint'`. |
| **Kafka** | Produce to `diep.commands`, key=`MG001`. |
| **MQTT** | Dispatcher: `device_type='microgrid'` → `DOMAIN_MAP["microgrid"]="microgrid"` → publishes `diep/microgrid/MG001/cmd`. `simulator/microgrid.py` would need to subscribe `diep/microgrid/MG001/cmd` and publish `diep/microgrid/MG001/ack`. |
| **Portal** | `/twins/MG001`: command shows `SENT`→`ACKED`; telemetry `setpoint_kw` (in `extra`/metadata) reflects the new value on next ingest. |

### Actual outcome (current repo state)

1. `commands` row + `audit_events` created, Kafka produce succeeds (assuming Kafka/network fixed) — **succeeds**, `status='SENT'`.
2. Dispatcher publishes `diep/microgrid/MG001/cmd`.
3. **BREAK (double)**:
   - `simulator/microgrid.py` (the legacy simulator that owns device ID `MG001`) is **currently the observed crash-looping container** (`diep-microgrid`, `Exited(255)`, `ConnectionRefusedError` per `DIEP_PLATFORM_ASSESSMENT.md` §C.1) — it is hardcoded to plaintext MQTT 1883, `username_pw_set("diep-device",...)`, no TLS/cert, against the mTLS-only 8883 broker. It cannot connect, so it cannot subscribe `diep/microgrid/MG001/cmd` or publish an ack.
   - Even if it *could* connect, the running Phase-9G edge driver for microgrid (`docker-compose-microgrid-edge.yml`, `drivers/microgrid_iec104`) subscribes as device **`MGC900`**, i.e. `diep/microgrid/MGC900/cmd` — a **second, independent mismatch** if the edge driver were the intended target instead of the legacy simulator.
4. `commands.status` stuck at `SENT` forever.
5. Portal `/twins/MG001`: command list shows `SENT` indefinitely; no telemetry for `MG001` either (its simulator is the one in the observed crash loop, so `/state/MG001` would show stale/no data — `MQTT_FLOW_VALIDATION_REPORT.md` §6/§7).

**Verdict: Broken — `MG001`'s own simulator is the currently-crash-looping container (cannot connect to mTLS broker at all); the alternative edge driver (`MGC900`) has a device-ID mismatch with the dispatcher's topic, identical to the battery/solar/meter cases.**

---

## Cross-Scenario Summary

| # | Scenario | Endpoint | DB layer | Kafka layer | MQTT delivery to device | Device ack | Net result |
|---|---|---|---|---|---|---|---|
| 1 | Battery Dispatch | `/derms/battery_dispatch` | OK | OK* | **Broken** (`BAT001` vs `BAT900`) | Never | `derms_requests=EXECUTED`, `commands=SENT` forever |
| 2 | Peak Shaving | `/derms/peak_shaving` | OK | OK* | **Broken** (`BAT001` vs `BAT900`) | Never | Same as #1 |
| 3 | Demand Response | `/derms/demand_response` | OK | OK* | **Broken** (`BAT001` vs `BAT900`, or EV001 plaintext-vs-mTLS if Tier 2) | Never | Same as #1 |
| 4 | EV Charger Control | `/commands` (EV001) | OK | OK* | **Broken** (EV001 simulator can't reach mTLS broker; topic IDs *would* match) | Never | `commands=SENT` forever |
| 5 | Microgrid Optimization | `/commands` (MG001) | OK | OK* | **Broken** (MG001 simulator can't reach mTLS broker AND `MGC900` ID mismatch if edge driver used) | Never | `commands=SENT` forever |

\* "OK" for the Kafka layer assumes the network-name reconciliation (`diep-net` vs `diep-lab_diep-net`)
and Kafka-listener-config decision (root `docker-compose.yml`'s SASL/9094 vs `docker-compose-kafka.yml`'s
PLAINTEXT-only) from `DIEP_PLATFORM_ASSESSMENT.md` §C.4 have been resolved — neither is currently true
in the as-found state, so even the "OK" legs are conditional on those fixes.

**Common root cause across all 5 scenarios**: every command path terminates at a
`diep/<domain>/<device_id>/cmd` topic for which **no currently-runnable container both (a) uses the
seeded `device_id` and (b) can connect to the mTLS-only (8883) broker**. The five seeded devices
(`BAT001`, `INV001`, `MG001`, `EV001`, `METER001`) are owned by the legacy plaintext simulators
(none can reach 8883); the Phase 9C-9G edge drivers can reach 8883 but use different device IDs
(`BAT900`, `INV900`, `MGC900`, `MTR900`, `EVSE900`) that aren't seeded in `devices` and don't match
the dispatcher's topic construction. **No command issued today against a seeded device can reach
`ACKED` without either (a) re-pointing the edge drivers' `devices.json` to the seeded IDs and adding
matching DB seed rows, or (b) issuing mTLS certs + ACL entries for the seeded IDs and updating the
legacy simulators to use port 8883/TLS.** This mirrors the identical conclusion reached
independently for telemetry in `MQTT_FLOW_VALIDATION_REPORT.md`.
