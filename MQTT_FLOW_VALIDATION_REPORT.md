# MQTT Telemetry Flow Validation Report

**Scope:** Read-only validation of the telemetry data path
`Simulator/Edge-driver -> MQTT -> Ingestor -> FastAPI -> TimescaleDB`
for `BAT001`, `INV001`, `MG001`, `EV001`, `METER001`.

**Assumed live state** (per `DIEP_PLATFORM_ASSESSMENT.md`): only `diep-mqtt`
(mosquitto, mTLS-only on 8883) is running; `diep-microgrid` (legacy plaintext
simulator) is crash-looping; TimescaleDB/FastAPI assumed restored and started.

---

## 1. MQTT broker config

`mosquitto/config/mosquitto.conf`:
- `mosquitto/config/mosquitto.conf:1-5` — global auth: `allow_anonymous false`,
  `password_file /mosquitto/config/passwd`, `acl_file /mosquitto/config/acl`.
- `mosquitto/config/mosquitto.conf:7-12` — plaintext `listener 1883` and websocket
  `listener 9001` are **commented out / retired** (Phase 9J-S4).
- `mosquitto/config/mosquitto.conf:14-22` — **only active listener is 8883**
  (mTLS): `cafile`, `certfile`, `keyfile` under `mosquitto/config/certs/`,
  `require_certificate true`, `use_identity_as_username true` — i.e. the client
  cert's CN becomes the MQTT username, ACL-bound.

**Referenced files (paths/permissions only):**
- `/home/emmanoff_lab/projects/diep-lab/mosquitto/config/passwd` (`-rw-r--r--`, 397 bytes) — password file (legacy `diep-nodered`/`diep-device` users; unused by the active 8883 listener since `use_identity_as_username` overrides identity for cert-presenting clients, but still loaded globally).
- `/home/emmanoff_lab/projects/diep-lab/mosquitto/config/acl` (`-rw-r--r--`, 1906 bytes) — ACL rules, see below.
- `/home/emmanoff_lab/projects/diep-lab/mosquitto/config/certs/{ca.crt,ca.key,server.crt,server.key}` (`-rw-r--r--`, 1164/1704/1188/1704 bytes) — broker CA + server identity for the 8883 listener.

**ACL summary** (`mosquitto/config/acl:1-58`):
- Legacy shared identities `diep-nodered` and `diep-device` (password-based; topic patterns `diep/+/+`, `diep/+/+/cmd`, `diep/+/+/ack`).
- Per-device mTLS identities (CN = username), each scoped to its own topic only:
  - `INV900` -> `diep/solar/INV900[/cmd|/ack]` (`acl:25-28`)
  - `MTR900` -> `diep/smartmeter/MTR900[...]` (`acl:30-33`)
  - `BAT900` -> `diep/battery/BAT900[...]` (`acl:35-38`)
  - `MGC900` -> `diep/microgrid/MGC900[...]` (`acl:40-43`)
  - `csms` -> `diep/charger/+[...]` (`acl:45-48`, EVSE900 et al.)
  - `ingestor` -> `read diep/+/+` (`acl:51-52`)
  - `dispatcher` -> `read diep/+/+/ack`, `write diep/+/+/cmd` (`acl:54-56`)
- **No ACL entries exist for `BAT001`, `INV001`, `MG001`, `EV001`, or `METER001`** (or for any "smartmeter"/legacy device identity beyond the shared `diep-device` user).

---

## 2. Device sources

### Compose files identified
- Legacy/root: `docker-compose.yml` (services `smartmeter`, `battery`, `solar`, `microgrid`, `ev-charger`, lines ~314-388) and standalone split files `docker-compose-battery.yml`, `docker-compose-solar.yml`, `docker-compose-microgrid.yml`, `docker-compose-ev-charger.yml` — all build context `./simulator`, all on network `diep-net` (not `diep-lab_diep-net`).
- Phase 9C-9G edge drivers: `docker-compose-sunspec.yml` (INV900), `docker-compose-meter.yml` (MTR900), `docker-compose-battery-edge.yml` (BAT900), `docker-compose-microgrid-edge.yml` (MGC900), `docker-compose-ocpp.yml` (EVSE900 via `ocpp-csms`) — all build context `./drivers`, network `diep-lab_diep-net` (external).

### Per-device source detail

**BAT001 — `simulator/battery.py`**
- Topic: `diep/battery/BAT001` (`simulator/battery.py:27`)
- Payload fields (`simulator/battery.py:121-128`): `device_id, mode, power_kw, soc, soc_target, capacity_kwh`
- Connection: `client.connect(BROKER, 1883, 60)` (`simulator/battery.py:100`), `username_pw_set(MQTT_USER="diep-device", MQTT_PASS="device-pass-2026")` (`simulator/battery.py:99`) — **plaintext 1883, no TLS**.
- Cert under `certs/devices/`: none for `BAT001`. (`BAT900.crt/.key` exist for the edge driver, not this simulator.)

**INV001 — `simulator/solar_inverter.py`**
- Topic: `diep/solar/INV001` (`simulator/solar_inverter.py:28`)
- Payload fields (`simulator/solar_inverter.py:111-118`): `device_id, output_kw, available_kw, limit_kw, curtailed, capacity_kw`
- Connection: `client.connect(BROKER, 1883, 60)` (`simulator/solar_inverter.py:104`), `username_pw_set("diep-device","device-pass-2026")` — **plaintext 1883, no TLS**.
- Cert: none for `INV001` (only `INV900.crt/.key` for the sunspec edge driver).

**MG001 — `simulator/microgrid.py`**
- Topic: `diep/microgrid/MG001` (`simulator/microgrid.py:33`)
- Payload fields (`simulator/microgrid.py:115-125`): `device_id, mode, grid_connected, setpoint_kw, pcc_kw, frequency, load_kw, solar_kw, net_load_kw`
- Connection: `client.connect(BROKER, 1883, 60)` (`simulator/microgrid.py:97`), `username_pw_set("diep-device","device-pass-2026")` — **plaintext 1883, no TLS**. This is the container currently crash-looping (`ConnectionRefusedError`, per assessment C.1).
- Cert: none for `MG001` (only `MGC900.crt/.key` for the IEC-104 edge driver).

**EV001 — `simulator/ev_charger.py`**
- Topic: `diep/charger/EV001` (`simulator/ev_charger.py:27`)
- Payload fields (`simulator/ev_charger.py:118-125`): `device_id, charging, power_kw, power_limit_kw, session_energy_kwh, vehicle_soc`
- Connection: `client.connect(BROKER, 1883, 60)` (`simulator/ev_charger.py:98`), `username_pw_set("diep-device","device-pass-2026")` — **plaintext 1883, no TLS**.
- Cert: none for `EV001` (the OCPP edge path uses `csms.crt/.key` and publishes a different device, `EVSE900`, not `EV001`).

**METER001 — `simulator/smartmeter.py`**
- Topic: `diep/energy/meter1` (`simulator/smartmeter.py:8`) — note non-standard domain `energy` and device segment `meter1` (not `METER001`).
- Payload fields (`simulator/smartmeter.py:37-46`): `voltage, current, power_kw, frequency, solar_kw, battery_soc, grid_import_kw, grid_export_kw` — **all already CANONICAL_FIELDS**, no `device_id` key in the payload.
- Connection: `client = mqtt.Client()` (old/no callback-API-version arg, `smartmeter.py:10`), `client.connect(broker, 1883, 60)` (`smartmeter.py:15`), `username_pw_set("diep-device","device-pass-2026")` — **plaintext 1883, no TLS**.
- Cert: none for `METER001` (only `MTR900.crt/.key` for the modbus_meter edge driver).

### Phase 9C-9G edge drivers (publish DIFFERENT device IDs — BAT900/INV900/MGC900/MTR900/EVSE900, not the seeded BAT001/INV001/MG001/EV001/METER001)
All use `drivers/diep_driver/mqtt_client.py` (`MqttTransport`), which reads `MQTT_TLS`, `MQTT_CA_CERTS`, `MQTT_CLIENT_CERT`, `MQTT_CLIENT_KEY` env vars (`drivers/diep_driver/mqtt_client.py:44-55`) and auto-switches port 1883->8883 when TLS is enabled.
- `INV900` (sunspec, `docker-compose-sunspec.yml:16-27`): `MQTT_TLS=1`, certs `/certs/INV900.crt`/`.key` -> **valid cert exists** (`certs/devices/INV900.crt`/`.key`), publishes `diep/solar/INV900`, aliases `W_kw->power_kw, Hz->frequency, DCW_kw->solar_kw, ChaState->battery_soc` (`drivers/sunspec/driver.py:36`).
- `MTR900` (modbus_meter, `docker-compose-meter.yml:17-24`): `MQTT_TLS=1`, certs `MTR900.crt/.key` exist, publishes `diep/smartmeter/MTR900`.
- `BAT900` (battery_bms, `docker-compose-battery-edge.yml:20-26`): `MQTT_TLS=1`, certs `BAT900.crt/.key` exist, publishes `diep/battery/BAT900`.
- `MGC900` (microgrid_iec104, `docker-compose-microgrid-edge.yml:21-27`): `MQTT_TLS=1`, certs `MGC900.crt/.key` exist, publishes `diep/microgrid/MGC900`.
- `EVSE900` (ocpp_csms, `docker-compose-ocpp.yml:20-26`): `MQTT_TLS=1`, cert `csms.crt/.key` exists (CSMS identity), publishes `diep/charger/EVSE900`.

**None of these edge-driver device IDs (`INV900`, `MTR900`, `BAT900`, `MGC900`, `EVSE900`) are seeded in `devices` table** (seed data per assessment B.1 only has `BAT001/INV001/MG001/EV001/METER001`) — so even if these edge drivers connect successfully and publish, FastAPI `/telemetry` will return **404 Unknown device_id** for all of them.

---

## 3. Ingestor (`ingestor/telemetry_ingestor.py`)

- Subscribes `diep/+/+` (3-level topic, `telemetry_ingestor.py:39,120`) — excludes 4-level `/cmd` and `/ack` topics automatically.
- `resolve_device_id()` (`telemetry_ingestor.py:66-72`): prefers `payload["device_id"]`; else uses the topic's last segment, applying `TOPIC_ID_OVERRIDES = {"meter1": "METER001"}` (`telemetry_ingestor.py:42`).
- `normalize()` (`telemetry_ingestor.py:75-115`):
  - Initializes all `CANONICAL_FIELDS` to `0.0` (`:78`).
  - Step 1 (`:81-84`): copies any of `CANONICAL_FIELDS` present directly.
  - Step 2 device-native aliases (`:86-101`):
    - `soc -> battery_soc` (battery)
    - `output_kw -> solar_kw, power_kw, grid_export_kw=max(0,output_kw)` (solar)
    - `pcc_kw -> power_kw, grid_import_kw=max(0,pcc_kw), grid_export_kw=max(0,-pcc_kw)` (microgrid)
  - Step 3 (`:104-113`): forwards `EXTENDED_NUMERIC` fields (power_factor, energy_import_kwh, energy_export_kwh, temperature, soh), `state`, and packs `EXTRA_FIELDS` (`vehicle_soc, connector_status, session_energy_kwh, load_kw, setpoint_kw, grid_connected, mode`) into `extra` (-> `metadata` JSONB).
- POSTs to `FASTAPI_BASE/telemetry` with `Authorization: Bearer DIEP_SERVICE_TOKEN` (`:144`).

### Per-device mapping correctness check

| Device | Native fields published | Ingestor mapping | Verdict |
|---|---|---|---|
| BAT001 (`battery.py`) | `device_id, mode, power_kw, soc, soc_target, capacity_kwh` | `power_kw` direct (CANONICAL); `soc -> battery_soc` (`:88-89`); `mode -> extra.mode` (EXTRA_FIELDS, `:53`); `soc_target`/`capacity_kwh` are dropped (not in any mapped set) | **Correct/complete for canonical+state fields.** `soc_target`/`capacity_kwh` silently dropped (minor, non-canonical, acceptable). |
| INV001 (`solar_inverter.py`) | `device_id, output_kw, available_kw, limit_kw, curtailed, capacity_kw` | `output_kw -> solar_kw, power_kw, grid_export_kw=max(0,output_kw)` (`:91-95`) | **Correct.** `available_kw, limit_kw, curtailed, capacity_kw` dropped (not in EXTRA_FIELDS/EXTENDED_NUMERIC) — acceptable, but means curtailment state isn't persisted. |
| MG001 (`microgrid.py`) | `device_id, mode, grid_connected, setpoint_kw, pcc_kw, frequency, load_kw, solar_kw, net_load_kw` | `frequency`, `solar_kw` direct (CANONICAL, `:81-84`); `pcc_kw -> power_kw, grid_import_kw=max(0,pcc_kw), grid_export_kw=max(0,-pcc_kw)` (`:97-101`); `mode -> extra.mode`, `grid_connected -> extra.grid_connected`, `setpoint_kw -> extra.setpoint_kw`, `load_kw -> extra.load_kw` (all in EXTRA_FIELDS, `:53-54`) | **Correct/complete.** `net_load_kw` dropped (acceptable). |
| EV001 (`ev_charger.py`) | `device_id, charging, power_kw, power_limit_kw, session_energy_kwh, vehicle_soc` | `power_kw` direct (CANONICAL); `session_energy_kwh -> extra.session_energy_kwh`, `vehicle_soc -> extra.vehicle_soc` (EXTRA_FIELDS, `:53-54`) | **Correct for power_kw + extras.** `charging` (bool) and `power_limit_kw` dropped — `charging` is not in `EXTRA_FIELDS` or mapped to `state`/`connector_status`, so charger on/off state is **not persisted** to `metadata` (minor mapping gap). |
| METER001 (`smartmeter.py`) | `voltage, current, power_kw, frequency, solar_kw, battery_soc, grid_import_kw, grid_export_kw` (no `device_id`) | All 8 fields are direct `CANONICAL_FIELDS` — copied as-is (`:81-84`). `device_id` resolved via topic fallback: topic `diep/energy/meter1` -> last segment `meter1` -> `TOPIC_ID_OVERRIDES["meter1"] = "METER001"` (`:42,71-72`) | **Correct.** Full direct 1:1 mapping; device-id resolution depends entirely on the topic-segment override, which matches `meter1` exactly. |

---

## 4. FastAPI `/telemetry` endpoint (`fastapi/app.py`)

- `TelemetryPayload` Pydantic model (`fastapi/app.py:745-765`): requires `device_id` (str), optional `time`, then **8 required floats** — `voltage, current, power_kw, frequency, solar_kw, battery_soc, grid_import_kw, grid_export_kw` — plus optional nullable extended fields (`power_factor, energy_import_kwh, energy_export_kwh, temperature, soh, state`) and `extra: dict = {}`.
- Handler `ingest_telemetry` (`fastapi/app.py:1845-1919`), requires role `service` (i.e. `DIEP_SERVICE_TOKEN`, matching ingestor's bearer token).
  - `:1851-1859` — `SELECT device_type, status, site_name, location FROM devices WHERE device_id = %s`. If no row -> **404 "Unknown device_id"**. This is the gate: only devices present in the `devices` table (seeded: `BAT001, INV001, MG001, EV001, METER001`, plus whatever `/assets` registers) succeed.
  - `:1862-1891` — on success, `INSERT INTO telemetry (time, device_id, voltage, current, power_kw, frequency, solar_kw, battery_soc, grid_import_kw, grid_export_kw, power_factor, energy_import_kwh, energy_export_kwh, temperature, soh, state, metadata)` with `metadata = json.dumps(payload.extra or {})`.
  - `:1893-1917` — mirrors a flattened `twin_state` dict (device_type/site/location/status/last_seen + all telemetry fields + `extra` merged in) to Redis key `state:<device_id>` via `_persist_state` (`_state_key` defined `fastapi/app.py:255-256`).
  - Returns `201` on success (decorator default `status_code=201`, `:1845`).

---

## 5. Database persistence cross-check

- `telemetry` base columns (`sql/000_schema.sql:86-98,102-105`): `time, device_id, voltage, current, power_kw, frequency, solar_kw, battery_soc, grid_import_kw, grid_export_kw, metadata jsonb`.
- Extended columns (`sql/009_schema_extension.sql:10-16`): `power_factor, energy_import_kwh, energy_export_kwh, temperature, soh (double precision), state varchar(30)`.
- The FastAPI INSERT (`fastapi/app.py:1864-1870`) lists exactly: `time, device_id, voltage, current, power_kw, frequency, solar_kw, battery_soc, grid_import_kw, grid_export_kw, power_factor, energy_import_kwh, energy_export_kwh, temperature, soh, state, metadata` — **17 columns, all present in the schema after both 000 and 009 are applied**. Column order/types align (floats -> REAL/double precision, `state` -> varchar(30), `extra` dict -> jsonb `metadata`).
- **Conclusion: schema/INSERT alignment is correct**, assuming `009_schema_extension.sql` has been applied (per `init-db.sh` numeric ordering, it should be).

---

## 6. Broken links given current mTLS-only broker state

**Ingestor itself** (`docker-compose-ingestor.yml:16-26`): `MQTT_PORT=8883`, `MQTT_TLS=1`, `MQTT_CA_CERTS=/certs/ca.crt`, `MQTT_CLIENT_CERT=/certs/ingestor.crt`, `MQTT_CLIENT_KEY=/certs/ingestor.key` (mounted from `./certs/devices:/certs:ro`). Cert files `certs/devices/ingestor.crt`/`.key` **exist**, ACL grants `ingestor` -> `read diep/+/+` (`acl:51-52`). **The ingestor would connect successfully** to the current mosquitto.conf.

**Per-device telemetry source status:**

| Device | Source script (current) | Topic published | TLS/cert status | Would connect to current 8883-mTLS broker? |
|---|---|---|---|---|
| BAT001 | `simulator/battery.py` (root/`-battery.yml`, `MQTT_BROKER` default `mqtt`, port hardcoded 1883) | `diep/battery/BAT001` | Plaintext only; `username_pw_set("diep-device", ...)`; **no client cert for BAT001** | **No** — plaintext 1883 connect fails (`ConnectionRefusedError`), same failure mode as `diep-microgrid` |
| INV001 | `simulator/solar_inverter.py` (`-solar.yml`) | `diep/solar/INV001` | Plaintext only, no cert | **No** — same ConnectionRefusedError |
| MG001 | `simulator/microgrid.py` (root/`-microgrid.yml`) | `diep/microgrid/MG001` | Plaintext only, no cert | **No** — this is the container *currently observed* crash-looping |
| EV001 | `simulator/ev_charger.py` (`-ev-charger.yml`) | `diep/charger/EV001` | Plaintext only, no cert | **No** — same ConnectionRefusedError |
| METER001 | `simulator/smartmeter.py` (root compose `smartmeter` service) | `diep/energy/meter1` | Plaintext only (old `mqtt.Client()` API), no cert | **No** — same ConnectionRefusedError |

The Phase 9C-9G **edge drivers** (`INV900`, `MTR900`, `BAT900`, `MGC900`, `EVSE900`) *would* connect (valid certs + `MQTT_TLS=1`, ACL entries present), but they publish telemetry for device IDs that are **not the 5 devices in scope** and **not seeded in `devices`**, so even a successful MQTT publish + ingestor forward would hit FastAPI's 404 (`fastapi/app.py:1856-1859`).

**Summary of broken link for each of the 5 in-scope devices:** the device source (legacy simulator) cannot reach the broker at all — TCP connection to port 1883 is refused because mosquitto only listens on 8883/mTLS and the simulators are hardcoded to plaintext 1883 with password auth and no client certificates. This is a **hard break at the very first hop** (device -> MQTT); the ingestor, FastAPI, and TimescaleDB legs are individually correct/functional but receive **zero messages** for BAT001/INV001/MG001/EV001/METER001 in the current state.

---

## 7. Per-device summary table

| Device | Source script | Topic | TLS/cert status | Ingestor mapping status | Expected DB outcome | Broken link |
|---|---|---|---|---|---|---|
| BAT001 | `simulator/battery.py` | `diep/battery/BAT001` | Plaintext 1883, password `diep-device`; **no client cert exists** | Correct (`soc->battery_soc`, `power_kw` direct, `mode->extra`) | None — no rows ingested | **Device -> MQTT**: `ConnectionRefusedError` on 1883 (mosquitto mTLS-only on 8883) |
| INV001 | `simulator/solar_inverter.py` | `diep/solar/INV001` | Plaintext 1883, password `diep-device`; **no client cert exists** | Correct (`output_kw -> solar_kw/power_kw/grid_export_kw`) | None — no rows ingested | **Device -> MQTT**: same ConnectionRefusedError |
| MG001 | `simulator/microgrid.py` | `diep/microgrid/MG001` | Plaintext 1883, password `diep-device`; **no client cert exists** | Correct (`pcc_kw -> power_kw/grid_import_kw/grid_export_kw`, `frequency`/`solar_kw` direct) | None — no rows ingested | **Device -> MQTT**: confirmed crash-loop (`diep-microgrid` `Exited(255)`) |
| EV001 | `simulator/ev_charger.py` | `diep/charger/EV001` | Plaintext 1883, password `diep-device`; **no client cert exists** | Mostly correct (`power_kw` direct, `session_energy_kwh`/`vehicle_soc -> extra`); `charging` bool dropped | None — no rows ingested | **Device -> MQTT**: same ConnectionRefusedError |
| METER001 | `simulator/smartmeter.py` | `diep/energy/meter1` (resolved to METER001 via `TOPIC_ID_OVERRIDES`) | Plaintext 1883 (legacy `mqtt.Client()` API), password `diep-device`; **no client cert exists** | Correct — payload already matches `CANONICAL_FIELDS` 1:1 | None — no rows ingested | **Device -> MQTT**: same ConnectionRefusedError |

**Ingestor leg (all 5 devices):** would connect successfully to 8883 (valid `ingestor.crt`/`.key`, ACL `read diep/+/+`) — **not the broken link**, but receives nothing because no device traffic arrives.

**FastAPI/TimescaleDB legs (all 5 devices):** schema, Pydantic model, and INSERT column list are all correctly aligned (Section 5) — **not the broken link**, would work correctly if telemetry arrived.

**Net conclusion:** The single broken link for all 5 in-scope devices is identical and is at the **device-simulator -> MQTT broker** hop: the legacy simulators (`simulator/*.py`, used by root `docker-compose.yml` and the `-battery.yml`/`-solar.yml`/`-microgrid.yml`/`-ev-charger.yml`/root-`smartmeter` definitions) are hardcoded to plaintext MQTT on port 1883 with password auth, while `mosquitto.conf` now serves only mTLS on 8883 and has no ACL/password entries or client certs for `BAT001/INV001/MG001/EV001/METER001`. Fixing this requires either (a) re-enabling 1883 in `mosquitto.conf` (security regression) or (b) issuing client certs for these 5 device identities, adding matching ACL entries, and updating the 5 simulator scripts/compose files to use `MQTT_TLS=1` + port 8883 + cert paths (mirroring the edge-driver pattern in `drivers/diep_driver/mqtt_client.py`).
