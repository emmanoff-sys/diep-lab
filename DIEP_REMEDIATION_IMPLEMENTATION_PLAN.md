# DIEP Remediation Implementation Plan

**Status:** Planning document only. **No code, configuration, certificate, or database changes
have been made.** This document specifies the exact changes required to resolve the issues
identified in `DIEP_PLATFORM_READINESS_REPORT.md` and the six Phase 1-6 validation reports, in
the order required for a working end-to-end demo.

All file paths are relative to `~/projects/diep-lab`. All line numbers reference the file
contents as inspected during this assessment (2026-06-11) and should be re-verified against
`HEAD` immediately before editing, since line numbers shift as edits are applied.

---

## Phase Overview & Sequence

| Phase | Name | Why this order | Effort |
|---|---|---|---|
| 1 | Docker Network Split | Nothing else can be validated until containers can reach each other. | 0.5 day |
| 2 | MQTT TLS Alignment | Telemetry/command transport must work before device-ID remapping can be observed end-to-end. | 1 day |
| 3 | Device ID Mapping Alignment | Requires Phase 2 (mTLS working) to issue/test new certs against the broker. | 1–1.5 days |
| 4 | Kafka Listener Alignment | Independent of 1-3, but commands can't be tested end-to-end without it — sequenced after network fix (Phase 1) since it's a network-adjacent config issue. | 0.5 day |
| 5 | Token Alignment | Lowest blast radius, but should be last so that re-validation in Phases 1-4 isn't confused by simultaneous auth changes. | 0.5 day |

**Total estimated effort: 3.5–4.5 days**, executed strictly in the order above. Each phase ends
with its own validation step; do not proceed to the next phase until the current phase's
validation procedure passes.

---

# PHASE 1 — Docker Network Split

## Issue 1.1: Per-service compose files reference a network name that does not match the network root `docker-compose.yml` actually creates

### Root Cause

`docker-compose.yml` (root) declares:
```yaml
networks:
  diep-net:
    driver: bridge
```
This is **not** `external`, so Docker Compose creates a project-prefixed network named
**`diep-lab_diep-net`** (project name = directory name `diep-lab`).

The following compose files correctly reference this project-prefixed name as `external: true`
and work correctly:
- `docker-compose-ingestor.yml` (`default: name: diep-lab_diep-net external: true`)
- `docker-compose-battery-edge.yml`, `docker-compose-microgrid-edge.yml`,
  `docker-compose-meter.yml`, `docker-compose-sunspec.yml` (`diep-net: name: diep-lab_diep-net
  external: true`)

The following compose files instead reference a **literal, non-prefixed** network name
`diep-net` (`external: true`), which is a **different network** than the one root compose
creates — these containers end up isolated from `diep-timescaledb`, `diep-redis`,
`diep-mqtt`, `diep-kafka`, the edge drivers, and `diep-ingestor`:
- `docker-compose-kafka.yml` (`default: name: diep-net external: true`)
- `docker-compose-fastapi.yml` (`default: name: diep-net external: true`)
- `docker-compose-portal.yml` (`default: name: diep-net external: true`)
- `docker-compose-ev-charger.yml`, `docker-compose-microgrid.yml`, `docker-compose-battery.yml`,
  `docker-compose-solar.yml` (`default: name: diep-net external: true`)

### Affected Files

- `docker-compose-kafka.yml`
- `docker-compose-fastapi.yml`
- `docker-compose-portal.yml`
- `docker-compose-ev-charger.yml`
- `docker-compose-microgrid.yml`
- `docker-compose-battery.yml`
- `docker-compose-solar.yml`

### Exact Code Changes

None — this is a pure compose-file change (see below).

### Exact Docker Compose Changes

In **each** of the 7 affected files, change the trailing `networks:` block from:

```yaml
networks:
  default:
    name: diep-net
    external: true
```

to:

```yaml
networks:
  default:
    name: diep-lab_diep-net
    external: true
```

**Specific line references (current `HEAD`):**

| File | Line(s) to change |
|---|---|
| `docker-compose-kafka.yml` | line 38: `name: diep-net` → `name: diep-lab_diep-net` |
| `docker-compose-fastapi.yml` | last `networks.default.name` line: `diep-net` → `diep-lab_diep-net` |
| `docker-compose-portal.yml` | last `networks.default.name` line: `diep-net` → `diep-lab_diep-net` |
| `docker-compose-ev-charger.yml` | line 29: `name: diep-net` → `name: diep-lab_diep-net` |
| `docker-compose-microgrid.yml` | line 29: `name: diep-net` → `name: diep-lab_diep-net` |
| `docker-compose-battery.yml` | line 29: `name: diep-net` → `name: diep-lab_diep-net` |
| `docker-compose-solar.yml` | line 28: `name: diep-net` → `name: diep-lab_diep-net` |

Do **not** change `docker-compose-ingestor.yml`, `docker-compose-battery-edge.yml`,
`docker-compose-microgrid-edge.yml`, `docker-compose-meter.yml`, `docker-compose-sunspec.yml`, or
the root `docker-compose.yml` — these are already correct.

**Note on `docker-compose-kafka.yml`**: this file also defines a *second, conflicting* `kafka`
service definition (PLAINTEXT-only, no SASL/9094 listener). Do not bring this file up alongside
the root `docker-compose.yml` — see Phase 4 for the full resolution. The network-name fix above
is documented for completeness/consistency but this file should ultimately be retired (Phase 4).

### Exact Environment Variable Changes

None.

### Validation Procedure

1. Confirm the project-prefixed network exists (created when root `docker-compose.yml` is
   brought up):
   ```bash
   docker network ls | grep diep-lab_diep-net
   ```
2. Bring up (or recreate) the affected services and confirm each attaches to
   `diep-lab_diep-net`:
   ```bash
   docker network inspect diep-lab_diep-net --format '{{range .Containers}}{{.Name}} {{end}}'
   ```
   Expected to include: `diep-fastapi`, `diep-portal`, `diep-kafka`, `diep-timescaledb`,
   `diep-redis`, `diep-mqtt`, `diep-ingestor`, `diep-dispatcher`, plus any running edge drivers.
3. Confirm cross-service reachability (read-only checks, no state change):
   ```bash
   docker exec diep-fastapi getent hosts diep-timescaledb diep-redis diep-kafka diep-mqtt
   docker exec diep-ingestor getent hosts diep-fastapi
   docker exec diep-portal getent hosts diep-fastapi
   ```
   All should resolve to IPs on `diep-lab_diep-net`.
4. Confirm no orphaned `diep-net` (literal) network remains with containers attached:
   ```bash
   docker network inspect diep-net 2>/dev/null
   ```
   (Expected: either the network doesn't exist, or exists with zero containers.)

### Rollback Procedure

1. `git diff` the 7 files to confirm only the `networks.default.name` / `networks.<name>.name`
   value changed (no other lines touched).
2. `git checkout -- docker-compose-kafka.yml docker-compose-fastapi.yml docker-compose-portal.yml
   docker-compose-ev-charger.yml docker-compose-microgrid.yml docker-compose-battery.yml
   docker-compose-solar.yml`
3. Recreate the affected containers (`docker compose -f <file> up -d --force-recreate`) to
   re-attach them to the original (broken) network reference.

---

# PHASE 2 — MQTT TLS Alignment

## Issue 2.1: Legacy device simulators (BAT001/INV001/MG001) hardcode plaintext MQTT 1883 against an mTLS-only (8883) broker

### Root Cause

`mosquitto/config/mosquitto.conf` retired the plaintext 1883/9001 listeners (Phase 9J-S4) and
now serves **only** `listener 8883` with `require_certificate true` and
`use_identity_as_username true`. However:

- `simulator/battery.py:100` — `client.connect(BROKER, 1883, 60)` (DEVICE_ID default `BAT001`)
- `simulator/solar_inverter.py:104` — `client.connect(BROKER, 1883, 60)` (DEVICE_ID default `INV001`)
- `simulator/microgrid.py:97` — `client.connect(BROKER, 1883, 60)` (DEVICE_ID default `MG001`)

all still attempt plaintext connections with `username_pw_set(MQTT_USER, MQTT_PASS)`. Mosquitto
rejects these connections (no plaintext listener exists), causing `ConnectionRefusedError` —
this is the confirmed cause of the `diep-microgrid` crash loop (`Exited(255)`), and the same
fate awaits `diep-battery`/`diep-solar` if started.

**Decision: do not migrate these three simulators to mTLS.** Phase 3 remaps the already-mTLS-
capable Phase 9C-9G edge drivers (`BAT900`→`BAT001`, `INV900`→`INV001`, `MGC900`→`MG001`) to own
these device identities. Running both the legacy simulator *and* the remapped edge driver for
the same device ID would create two MQTT clients publishing/competing for the same topics and
the same ACL identity — so the legacy simulators for these three devices must instead be
**disabled** (not migrated).

### Affected Files

- `docker-compose-battery.yml` (defines `diep-battery`, runs `simulator/battery.py`)
- `docker-compose-solar.yml` (defines `diep-solar`, runs `simulator/solar_inverter.py`)
- `docker-compose-microgrid.yml` (defines `diep-microgrid`, runs `simulator/microgrid.py`)

### Exact Code Changes

None — no source code changes to `simulator/battery.py`, `simulator/solar_inverter.py`, or
`simulator/microgrid.py`. (Optional cleanup, not required for the demo: add a top-of-file
comment in each noting the file is superseded by the corresponding edge driver under
`drivers/`.)

### Exact Docker Compose Changes

Do **not** start `diep-battery`, `diep-solar`, or `diep-microgrid` going forward. Concretely:

- If currently running, stop and remove them:
  ```bash
  docker compose -f docker-compose-battery.yml down
  docker compose -f docker-compose-solar.yml down
  docker compose -f docker-compose-microgrid.yml down
  ```
- Exclude `docker-compose-battery.yml`, `docker-compose-solar.yml`, and
  `docker-compose-microgrid.yml` from whatever startup script / `-f` file list is used to bring
  up the platform (e.g. `start.sh`, `Makefile`, or documented `docker compose -f ... -f ...`
  command chain — locate and edit that orchestration file to remove these three `-f` arguments).

No YAML content changes are required in these 3 files themselves (Phase 1's network-name fix
still applies to them for consistency, but they should not be deployed).

### Exact Environment Variable Changes

None.

### Validation Procedure

1. Confirm none of the three legacy containers are running:
   ```bash
   docker ps -a --filter "name=diep-battery" --filter "name=diep-solar" --filter "name=diep-microgrid"
   ```
2. Proceed to Phase 3 — validation of telemetry/command flow for `BAT001`/`INV001`/`MG001` is
   covered there (via the remapped edge drivers).

### Rollback Procedure

1. Re-add the 3 compose files to the startup script / `-f` file list.
2. `docker compose -f docker-compose-battery.yml -f docker-compose-solar.yml -f docker-compose-microgrid.yml up -d`
3. Note: this restores the original crash-loop / connection-refused behavior for these 3
   containers — only roll back if Phase 3 is also rolled back.

---

## Issue 2.2: EV001 simulator hardcodes plaintext MQTT 1883 against an mTLS-only (8883) broker, and has no edge-driver equivalent

### Root Cause

`simulator/ev_charger.py` (DEVICE_ID default `EV001`) is the **only** seeded device whose
device ID matches what the dispatcher would publish to (`diep/charger/EV001/cmd` —
`DOMAIN_MAP["ev_charger"] = "charger"` in `dispatcher/command_dispatcher.py:66-71`), and it has
no Phase 9C-9G edge-driver counterpart (the only EV-related edge component is the OCPP CSMS for
charge point `EVSE900`, a different protocol/architecture). Therefore, **this is the one
simulator that must be migrated to mTLS** rather than disabled.

Current code (`simulator/ev_charger.py`):
- Line 20: `BROKER = os.getenv("MQTT_BROKER", "mqtt")`
- Line 21-22: `MQTT_USER = os.getenv("MQTT_USER", "diep-device")` / `MQTT_PASS = os.getenv("MQTT_PASS", "device-pass-2026")`
- Line 97: `client.username_pw_set(MQTT_USER, MQTT_PASS)`
- Line 98: `client.connect(BROKER, 1883, 60)`

### Affected Files

- `simulator/ev_charger.py`
- `docker-compose-ev-charger.yml`
- `mosquitto/config/acl`
- `certs/devices/` (new files: `EV001.crt`, `EV001.key`)

### Exact Code Changes

**`simulator/ev_charger.py`**, replace the connection setup (lines ~95-99, exact context: just
before/at `client.username_pw_set(MQTT_USER, MQTT_PASS)` and `client.connect(BROKER, 1883, 60)`):

```python
# Before:
client.username_pw_set(MQTT_USER, MQTT_PASS)
client.connect(BROKER, 1883, 60)
```

```python
# After:
import ssl  # add to top-of-file imports if not already present

MQTT_TLS = os.getenv("MQTT_TLS", "0") == "1"
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

if MQTT_TLS:
    client.tls_set(
        ca_certs=os.getenv("MQTT_CA_CERTS"),
        certfile=os.getenv("MQTT_CLIENT_CERT"),
        keyfile=os.getenv("MQTT_CLIENT_KEY"),
        cert_reqs=ssl.CERT_REQUIRED,
    )
    # use_identity_as_username on the broker derives the MQTT identity from the
    # client cert CN (=EV001) — no username/password needed over mTLS.
else:
    client.username_pw_set(MQTT_USER, MQTT_PASS)

client.connect(BROKER, MQTT_PORT, 60)
```

This mirrors the pattern already used in `dispatcher/command_dispatcher.py:100-106` and the
Phase 9C-9G edge drivers (e.g. `drivers/battery_bms/edge_agent.py`) — confirm the exact
`tls_set`/import structure against `dispatcher/command_dispatcher.py` for consistency before
editing.

### Exact Docker Compose Changes

**`docker-compose-ev-charger.yml`** — add the cert volume mount and TLS environment variables
(mirroring `docker-compose-ingestor.yml`'s pattern):

```yaml
    volumes:
      - ./simulator:/app          # (or whatever the existing mount is — keep it)
      - ./certs/devices:/certs:ro # ADD this line

    environment:
      MQTT_BROKER: diep-mqtt
      MQTT_PORT: "8883"            # ADD / change from "1883"
      MQTT_TLS: "1"                # ADD
      MQTT_CA_CERTS: /certs/ca.crt          # ADD
      MQTT_CLIENT_CERT: /certs/EV001.crt    # ADD
      MQTT_CLIENT_KEY: /certs/EV001.key     # ADD
      MQTT_USER: ""                # ADD (unused under mTLS)
      MQTT_PASS: ""                # ADD (unused under mTLS)
      DEVICE_ID: EV001              # keep/confirm existing value
```

(Apply Phase 1's network-name fix to this same file in the same change set.)

### Exact Environment Variable Changes

No `.env` changes required — the new `MQTT_*` variables above are set directly in
`docker-compose-ev-charger.yml`'s `environment:` block (consistent with how
`docker-compose-ingestor.yml` and the edge-driver compose files already do it).

### Validation Procedure

1. Issue the new client certificate (read-only w.r.t. the platform; only adds a file under
   `certs/devices/`):
   ```bash
   ./scripts/issue-device-cert.sh EV001
   ```
   Confirm output: `issued: certs/devices/EV001.crt (CN=EV001, valid 825d)`.
2. Add an ACL block for `EV001` to `mosquitto/config/acl` (append, mirroring the `BAT900` block):
   ```
   user EV001
   topic write diep/charger/EV001
   topic read diep/charger/EV001/cmd
   topic write diep/charger/EV001/ack
   ```
3. Reload mosquitto's ACL (mosquitto supports `SIGHUP` for config reload without a full
   restart — confirm this satisfies "DO NOT restart services" per the user's constraint; if a
   full restart is required, flag this to the user before proceeding):
   ```bash
   docker kill -s HUP diep-mqtt
   ```
4. Recreate `diep-ev-charger` with the new compose env (`docker compose -f
   docker-compose-ev-charger.yml up -d --force-recreate`).
5. Tail logs for a successful TLS connection and subscription:
   ```bash
   docker logs -f diep-ev-charger
   ```
   Expected: `[EV001] connected to MQTT (Success), subscribing diep/charger/EV001/cmd` with no
   `ConnectionRefusedError`/TLS handshake errors.
6. Confirm telemetry arrives in the DB (read-only query):
   ```sql
   SELECT device_id, time, payload FROM telemetry WHERE device_id='EV001' ORDER BY time DESC LIMIT 1;
   ```
   Expect a row with `time` within the last `interval` (per `simulator/ev_charger.py`'s publish
   loop).

### Rollback Procedure

1. `git checkout -- simulator/ev_charger.py docker-compose-ev-charger.yml mosquitto/config/acl`
2. Remove the issued cert (only newly-added files):
   ```bash
   rm -f certs/devices/EV001.crt certs/devices/EV001.key
   ```
3. `docker kill -s HUP diep-mqtt` (reload ACL without the EV001 block)
4. `docker compose -f docker-compose-ev-charger.yml up -d --force-recreate`

---

# PHASE 3 — Device ID Mapping Alignment

## Issue 3.1: Phase 9C-9G edge drivers publish under `BAT900`/`INV900`/`MGC900`/`MTR900`, but the seeded DB devices and dispatcher command topics use `BAT001`/`INV001`/`MG001`/`METER001`

### Root Cause

- `drivers/battery_bms/devices.json`: `"device_id": "BAT900"`
- `drivers/devices.json` (sunspec/solar driver, used by `docker-compose-sunspec.yml`):
  `"device_id": "INV900"`
- `drivers/microgrid_iec104/devices.json`: `"device_id": "MGC900"`
- `drivers/modbus_meter/devices.json`: `"device_id": "MTR900"`
- `mosquitto/config/acl` has per-device mTLS blocks for `INV900`, `MTR900`, `BAT900`, `MGC900`
  (topics `diep/<domain>/<ID>`, `diep/<domain>/<ID>/cmd`, `diep/<domain>/<ID>/ack`)
- `certs/devices/` has `BAT900.{crt,key}`, `INV900.{crt,key}`, `MGC900.{crt,key}`,
  `MTR900.{crt,key}` (CN matches device ID, required by `use_identity_as_username`)

Meanwhile `devices` table seed rows (per `DATABASE_VALIDATION_REPORT.md` §3) use `BAT001`,
`INV001`, `MG001`, `METER001`, and the dispatcher constructs command topics as
`diep/{domain}/{device_id}/cmd` from the **DB/API** `device_id` (`BAT001`, etc.) — so telemetry
published to `diep/battery/BAT900` never reaches a `device_id='BAT001'` row's expectations, and
commands published to `diep/battery/BAT001/cmd` have no subscriber (the edge driver listens on
`BAT900`).

**Chosen approach:** remap the edge drivers (devices.json + certs + ACL) to the seeded IDs —
this requires zero DB schema/seed changes and zero portal/API changes, since the seeded IDs
(`BAT001`/`INV001`/`MG001`/`METER001`) are already what the FastAPI/Portal/DERMS layers expect.

### Affected Files

- `drivers/battery_bms/devices.json`
- `drivers/devices.json` (sunspec)
- `drivers/microgrid_iec104/devices.json`
- `drivers/modbus_meter/devices.json`
- `docker-compose-battery-edge.yml`
- `docker-compose-sunspec.yml`
- `docker-compose-microgrid-edge.yml`
- `docker-compose-meter.yml`
- `mosquitto/config/acl`
- `certs/devices/` (new files: `BAT001.{crt,key}`, `INV001.{crt,key}`, `MG001.{crt,key}`,
  `METER001.{crt,key}`)

### Exact Code Changes

No application source code changes — all changes are to JSON config files.

**`drivers/battery_bms/devices.json`**:
```json
[
  {
    "device_id": "BAT001",
    "protocol": "battery_bms",
    "interval": 5,
    "config": {
      "host": "127.0.0.1",
      "port": 1702,
      "unit": 1,
      "base": 4000,
      "default_power_kw": 50
    }
  }
]
```
(Only the `"device_id"` value changes from `"BAT900"` to `"BAT001"`.)

**`drivers/devices.json`** (sunspec/solar):
```json
[
  {
    "device_id": "INV001",
    "protocol": "sunspec",
    "interval": 5,
    "config": {
      "host": "127.0.0.1",
      "port": 1502,
      "unit": 1,
      "capacity_kw": 10
    }
  }
]
```
(Only `"device_id"`: `"INV900"` → `"INV001"`.)

**`drivers/microgrid_iec104/devices.json`**:
```json
[
  {
    "device_id": "MG001",
    "protocol": "microgrid_iec104",
    "interval": 5,
    "config": {
      "host": "127.0.0.1",
      "port": 2404,
      "common_address": 1
    }
  }
]
```
(Only `"device_id"`: `"MGC900"` → `"MG001"`.)

**`drivers/modbus_meter/devices.json`**:
```json
[
  {
    "device_id": "METER001",
    "protocol": "modbus_meter",
    "interval": 5,
    "config": {
      "host": "127.0.0.1",
      "port": 1602,
      "unit": 1,
      "base": 3000
    }
  }
]
```
(Only `"device_id"`: `"MTR900"` → `"METER001"`. **Verify against
`DATABASE_VALIDATION_REPORT.md` §3 that the seeded smart-meter device's `device_id` is exactly
`METER001`** — if the seed uses a different literal, e.g. `MTR001`, use that exact value
instead.)

### Exact Docker Compose Changes

Each edge-driver compose file passes `MQTT_CLIENT_CERT`/`MQTT_CLIENT_KEY` paths that must match
the new device IDs (cert filenames), and (where present) any `DEVICE_ID`/topic env vars.

**`docker-compose-battery-edge.yml`** (around line 20, alongside `MQTT_PORT: "8883"`):
```yaml
      MQTT_CLIENT_CERT: /certs/BAT001.crt   # was /certs/BAT900.crt
      MQTT_CLIENT_KEY: /certs/BAT001.key    # was /certs/BAT900.key
```

**`docker-compose-sunspec.yml`**:
```yaml
      MQTT_CLIENT_CERT: /certs/INV001.crt   # was /certs/INV900.crt
      MQTT_CLIENT_KEY: /certs/INV001.key    # was /certs/INV900.key
```

**`docker-compose-microgrid-edge.yml`**:
```yaml
      MQTT_CLIENT_CERT: /certs/MG001.crt    # was /certs/MGC900.crt
      MQTT_CLIENT_KEY: /certs/MG001.key     # was /certs/MGC900.key
```

**`docker-compose-meter.yml`**:
```yaml
      MQTT_CLIENT_CERT: /certs/METER001.crt # was /certs/MTR900.crt
      MQTT_CLIENT_KEY: /certs/METER001.key  # was /certs/MTR900.key
```

(Re-verify the exact current env var names/paths in each file before editing — grep for
`MQTT_CLIENT_CERT` in each file to get the precise line.)

**`mosquitto/config/acl`** — replace the 4 per-device blocks (currently `BAT900`, `INV900`,
`MGC900`, `MTR900`) with:

```
user BAT001
topic write diep/battery/BAT001
topic read diep/battery/BAT001/cmd
topic write diep/battery/BAT001/ack

user INV001
topic write diep/solar/INV001
topic read diep/solar/INV001/cmd
topic write diep/solar/INV001/ack

user MG001
topic write diep/microgrid/MG001
topic read diep/microgrid/MG001/cmd
topic write diep/microgrid/MG001/ack

user METER001
topic write diep/smartmeter/METER001
topic read diep/smartmeter/METER001/cmd
topic write diep/smartmeter/METER001/ack
```

Preserve the surrounding comments and the unrelated blocks (`diep-nodered`, `diep-device`,
`csms`, `ingestor`, `dispatcher`).

### Exact Environment Variable Changes

None in `.env`/`.env.example`.

### Validation Procedure

1. Issue the 4 new certs (additive only — does not remove old ones):
   ```bash
   ./scripts/issue-device-cert.sh BAT001
   ./scripts/issue-device-cert.sh INV001
   ./scripts/issue-device-cert.sh MG001
   ./scripts/issue-device-cert.sh METER001
   ```
2. Apply the ACL edit and reload mosquitto:
   ```bash
   docker kill -s HUP diep-mqtt
   ```
3. Recreate the 4 edge-driver containers with the updated `devices.json` + compose env:
   ```bash
   docker compose -f docker-compose-battery-edge.yml up -d --force-recreate
   docker compose -f docker-compose-sunspec.yml up -d --force-recreate
   docker compose -f docker-compose-microgrid-edge.yml up -d --force-recreate
   docker compose -f docker-compose-meter.yml up -d --force-recreate
   ```
4. Confirm each driver connects under its new identity (logs should show CN-based connection,
   no TLS/auth errors):
   ```bash
   docker logs --tail 20 diep-battery-edge
   docker logs --tail 20 diep-sunspec-edge
   docker logs --tail 20 diep-microgrid-edge
   docker logs --tail 20 diep-meter-edge
   ```
5. Confirm telemetry now arrives for all 4 seeded device IDs (read-only):
   ```sql
   SELECT device_id, max(time) FROM telemetry
   WHERE device_id IN ('BAT001','INV001','MG001','METER001')
   GROUP BY device_id;
   ```
   Expect all 4 rows with `max(time)` within the last `interval` window of each driver.
6. Issue a test command end-to-end (e.g. Scenario 1 from `END_TO_END_TEST_SCENARIOS.md`) and
   confirm `commands.status` reaches `ACKED`:
   ```sql
   SELECT command_id, device_id, command_type, status, dispatched_at, acked_at
   FROM commands WHERE device_id='BAT001' ORDER BY created_at DESC LIMIT 1;
   ```

### Rollback Procedure

1. `git checkout -- drivers/battery_bms/devices.json drivers/devices.json
   drivers/microgrid_iec104/devices.json drivers/modbus_meter/devices.json
   docker-compose-battery-edge.yml docker-compose-sunspec.yml
   docker-compose-microgrid-edge.yml docker-compose-meter.yml mosquitto/config/acl`
2. Remove the newly-issued certs (do **not** remove `BAT900.*`/`INV900.*`/`MGC900.*`/`MTR900.*`
   — those are untouched by this change):
   ```bash
   rm -f certs/devices/{BAT001,INV001,MG001,METER001}.{crt,key}
   ```
3. `docker kill -s HUP diep-mqtt`
4. Recreate the 4 edge-driver containers to revert to `*900` identities.

---

# PHASE 4 — Kafka Listener Alignment

## Issue 4.1: `docker-compose-kafka.yml` defines a conflicting, PLAINTEXT-only `kafka` service that does not match the SASL/9094 listener configuration the application code expects

### Root Cause

The root `docker-compose.yml` already defines a complete `kafka` service (lines ~14-30) with:
```yaml
KAFKA_LISTENERS: PLAINTEXT://:9092,CONTROLLER://:9093,SASL://:9094
KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://diep-kafka:9092,SASL://diep-kafka:9094
KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT,SASL:SASL_PLAINTEXT
KAFKA_SASL_ENABLED_MECHANISMS: PLAIN
KAFKA_LISTENER_NAME_SASL_PLAIN_SASL_JAAS_CONFIG: '...PlainLoginModule...user_diep="diep-kafka-pass-2026"...'
```
exposing `9092` (PLAINTEXT, internal) and `9094` (SASL_PLAINTEXT, app clients). Both
`fastapi/app.py` (Kafka producer) and `dispatcher/command_dispatcher.py:35-39` are coded against
`diep-kafka:9094` with `SASL_PLAINTEXT`/`PLAIN`/`diep`/`diep-kafka-pass-2026`.

`docker-compose-kafka.yml` is a **separate, older** standalone definition of the same `kafka`
service:
```yaml
KAFKA_LISTENERS: PLAINTEXT://:9092,CONTROLLER://:9093
KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://diep-kafka:9092
KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT
```
— **no `9094`/SASL listener at all**. If this file is ever applied (alone, or as an additional
`-f` after `docker-compose.yml` — Compose merges same-named services, and the *last* file's
scalar `environment` keys win), the resulting `kafka` service either has no `9094` listener, or
(if merged after root) has its `KAFKA_LISTENERS`/`KAFKA_ADVERTISED_LISTENERS`/
`KAFKA_LISTENER_SECURITY_PROTOCOL_MAP` overwritten to the PLAINTEXT-only values — in either case,
**every `diep-kafka:9094` SASL connection from FastAPI/dispatcher fails**, breaking the entire
command path (Phase 4/6/7 findings).

### Affected Files

- `docker-compose-kafka.yml` (to be retired)
- Whatever orchestration script/Makefile assembles the `-f` file list for `docker compose up`
  (must be located and confirmed not to include `docker-compose-kafka.yml` alongside
  `docker-compose.yml`)

### Exact Code Changes

None.

### Exact Docker Compose Changes

1. **Do not bring up `docker-compose-kafka.yml`** in combination with `docker-compose.yml`.
   The root `docker-compose.yml`'s `kafka` service (SASL/9094-enabled) is the canonical
   definition and is sufficient on its own — `docker-compose-kafka.yml` is redundant.
2. Locate the startup orchestration (search for `docker-compose-kafka.yml` references):
   ```bash
   grep -rn "docker-compose-kafka" --include="*.sh" --include="Makefile" --include="*.md" .
   ```
   Remove `-f docker-compose-kafka.yml` from any `docker compose -f ... up` command found.
3. **Recommended (not required for the demo, but prevents future accidental misuse):** rename
   `docker-compose-kafka.yml` to `docker-compose-kafka.yml.deprecated` or move it to an
   `archive/` subdirectory, with a comment at the top explaining it has been superseded by the
   `kafka` service in root `docker-compose.yml` (Phase 9J-S5 SASL/9094 listener). **This is a
   file rename only — confirm with the user before performing it**, since renaming is mildly
   destructive to anyone with local references to the old filename.
4. Apply Phase 1's network-name fix (`diep-net` → `diep-lab_diep-net`) to
   `docker-compose-kafka.yml` regardless, in case it's retained for reference/manual use —
   already covered in Phase 1's table.

### Exact Environment Variable Changes

None — `KAFKA_SASL_USERNAME`/`KAFKA_SASL_PASSWORD`/`KAFKA_BOOTSTRAP` are already correctly set
in the root `docker-compose.yml`'s `dispatcher` service (lines 159-162) and are read by
`fastapi/app.py` and `dispatcher/command_dispatcher.py:35-39` with matching defaults
(`diep-kafka:9094`, `SASL_PLAINTEXT`, `PLAIN`, `diep` / `diep-kafka-pass-2026`). Confirm
`fastapi`'s Kafka producer construction in `app.py` (~line 1986-1998 per
`FASTAPI_VALIDATION_REPORT.md` issue #2) uses the same `KAFKA_BOOTSTRAP`/SASL env-var names as
the dispatcher — if `fastapi`'s service definition in root `docker-compose.yml` does **not**
set these vars, it will fall back to `kafka-python`'s defaults (likely `localhost:9092`,
no SASL), which would also break Kafka produce calls from FastAPI. If so, add to the `fastapi`
service's `environment:` block in root `docker-compose.yml`:
```yaml
      KAFKA_BOOTSTRAP: diep-kafka:9094
      KAFKA_SECURITY_PROTOCOL: SASL_PLAINTEXT
      KAFKA_SASL_MECHANISM: PLAIN
      KAFKA_SASL_USERNAME: diep
      KAFKA_SASL_PASSWORD: diep-kafka-pass-2026
```
(Verify the exact env-var names expected by `fastapi/app.py`'s Kafka producer construction
before adding — they should match `dispatcher/command_dispatcher.py:35-39`'s names exactly.)

### Validation Procedure

1. Confirm only the root `docker-compose.yml`'s `kafka` service is running:
   ```bash
   docker compose -f docker-compose.yml config | grep -A8 "^  kafka:"
   ```
   Confirm `KAFKA_LISTENERS` includes `SASL://:9094`.
2. From inside `diep-fastapi` and `diep-dispatcher`, confirm SASL connectivity to 9094:
   ```bash
   docker exec diep-dispatcher python -c "
   from kafka import KafkaProducer
   p = KafkaProducer(bootstrap_servers='diep-kafka:9094', security_protocol='SASL_PLAINTEXT',
                      sasl_mechanism='PLAIN', sasl_plain_username='diep', sasl_plain_password='diep-kafka-pass-2026')
   print('connected:', p.bootstrap_connected())
   p.close()
   "
   ```
   Expected: `connected: True`.
3. Confirm topic `diep.commands` exists and is auto-created:
   ```bash
   docker exec diep-kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server diep-kafka:9094 \
     --command-config /dev/stdin --list <<< "
   security.protocol=SASL_PLAINTEXT
   sasl.mechanism=PLAIN
   sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username=\"diep\" password=\"diep-kafka-pass-2026\";
   "
   ```
   Expected output includes `diep.commands`.
4. Re-run a Phase-1-3-validated command (e.g. Scenario 1) and confirm the Kafka produce/consume
   leg succeeds (dispatcher log shows message consumed and published to MQTT).

### Rollback Procedure

1. If the orchestration script was edited, `git diff`/`git checkout` it to restore the
   `-f docker-compose-kafka.yml` reference.
2. If `docker-compose-kafka.yml` was renamed/moved, restore its original name/location:
   `git mv docker-compose-kafka.yml.deprecated docker-compose-kafka.yml` (or `git checkout` if
   tracked).
3. If `KAFKA_*` env vars were added to the `fastapi` service in root `docker-compose.yml`,
   `git checkout -- docker-compose.yml` to remove them (only if this introduced a regression —
   unlikely, since they match the dispatcher's already-working config).

---

# PHASE 5 — Token Alignment

## Issue 5.1: `.env` defines auth tokens/keys that no compose file actually passes into the `fastapi`, `dispatcher`, or `portal` containers — all three currently run on hardcoded source-code defaults

### Root Cause

- `fastapi/auth.py:36-39`:
  ```python
  API_KEYS = {
      os.getenv("DIEP_SERVICE_TOKEN", "diep-service-dev-token-CHANGE-ME"): ("svc-machine", "service"),
      os.getenv("DIEP_OPERATOR_KEY", "diep-operator-dev-key-CHANGE-ME"): ("api-operator", "operator"),
      os.getenv("DIEP_ADMIN_KEY", "diep-admin-dev-key-CHANGE-ME"): ("api-admin", "admin"),
  }
  ```
- `dispatcher/command_dispatcher.py:59`:
  ```python
  SERVICE_TOKEN = os.getenv("DIEP_SERVICE_TOKEN", "diep-service-dev-token-CHANGE-ME")
  ```
- `portal/app/api/diep/[...path]/route.ts`:
  ```typescript
  const TOKEN = process.env.DIEP_PORTAL_TOKEN || 'diep-admin-dev-key-CHANGE-ME';
  ```

**Verified against root `docker-compose.yml`:** the `fastapi` service (lines 107-129) defines
**no `environment:` block at all**; the `dispatcher` service (lines 150-181) sets Kafka/MQTT
vars but **not** `DIEP_SERVICE_TOKEN`; the `portal` service (lines 183-202) sets
`DIEP_API_BASE`/`NEXT_PUBLIC_GRAFANA_URL`/`NEXT_TELEMETRY_DISABLED` but **not**
`DIEP_PORTAL_TOKEN`. None of the three declare `env_file: .env`.

**Net effect today:** all three services fall back to their hardcoded `*-CHANGE-ME` defaults.
Because `diep-admin-dev-key-CHANGE-ME` (portal's fallback) happens to equal
`DIEP_ADMIN_KEY`'s fallback in `fastapi/auth.py:38`, and `diep-service-dev-token-CHANGE-ME`
(dispatcher's fallback) happens to equal `DIEP_SERVICE_TOKEN`'s fallback in
`fastapi/auth.py:37`, **auth currently "works" by coincidence of matching hardcoded defaults** —
but `.env`'s actual values (`change-me-service-token`, `change-me-admin-key`, etc., from
`.env.example`) are **never read by any of the three services**. Editing `.env` to rotate
secrets has **zero effect** on the running platform — a latent break for any operator who
follows the `.env.example` instructions to "OVERRIDE every value before any non-lab use."

### Affected Files

- `docker-compose.yml` (root) — `fastapi`, `dispatcher`, `portal` service definitions
- `docker-compose-fastapi.yml`, `docker-compose-portal.yml` (standalone equivalents, if used
  instead of/in addition to root compose)
- `.env` / `.env.example` (no value changes needed — only confirm consistency, see below)

### Exact Code Changes

None — `fastapi/auth.py`, `dispatcher/command_dispatcher.py`, and
`portal/app/api/diep/[...path]/route.ts` already correctly read from `os.getenv`/
`process.env` with sensible fallbacks. The fix is entirely in how environment variables are
*passed into* the containers.

### Exact Docker Compose Changes

Add `env_file: .env` to the `fastapi`, `dispatcher`, and `portal` service definitions in root
`docker-compose.yml` (and to `docker-compose-fastapi.yml`/`docker-compose-portal.yml` if those
are used standalone).

**`docker-compose.yml`, `fastapi` service (insert after `working_dir: /app`, ~line 112):**
```yaml
  fastapi:
    image: python:3.12
    container_name: diep-fastapi
    restart: unless-stopped
    working_dir: /app
    env_file:
      - .env
    volumes:
      - ./fastapi:/app
    ...
```

**`docker-compose.yml`, `dispatcher` service (insert after `working_dir: /app`, ~line 154):**
```yaml
  dispatcher:
    image: python:3.12
    container_name: diep-dispatcher
    restart: unless-stopped
    working_dir: /app
    env_file:
      - .env
    volumes:
      - ./dispatcher:/app
      - ./certs/devices:/certs:ro
    environment:
      KAFKA_BOOTSTRAP: diep-kafka:9094
      ...   # existing environment block unchanged — env_file values are overridden by
            # explicit `environment:` keys only for keys present in BOTH; DIEP_SERVICE_TOKEN
            # is not in this service's `environment:` block, so it will come from .env
```

**`docker-compose.yml`, `portal` service (insert after `working_dir: /app`, ~line 187):**
```yaml
  portal:
    image: node:20
    container_name: diep-portal
    restart: unless-stopped
    working_dir: /app
    env_file:
      - .env
    volumes:
      - ./portal:/app
    environment:
      DIEP_API_BASE: http://diep-fastapi:8000
      ...   # existing environment block unchanged
```

Apply the same `env_file: .env` addition to `docker-compose-fastapi.yml` and
`docker-compose-portal.yml` if they are used as standalone alternatives to root
`docker-compose.yml` (their `volumes:`/`working_dir:` blocks have the same shape).

### Exact Environment Variable Changes

**No new variables need to be added to `.env`** — `.env.example` already defines all the
required keys with mutually-consistent values:
```
DIEP_SERVICE_TOKEN=change-me-service-token
DIEP_OPERATOR_KEY=change-me-operator-key
DIEP_ADMIN_KEY=change-me-admin-key
DIEP_PORTAL_TOKEN=change-me-admin-key        # already equals DIEP_ADMIN_KEY — correct
```

**One verification step is required**: confirm the *actual* `.env` (gitignored, not
`.env.example`) preserves this invariant — `DIEP_PORTAL_TOKEN` **must equal** `DIEP_ADMIN_KEY`
(both are read by `fastapi/auth.py:38` vs. `portal/app/api/diep/[...path]/route.ts`'s `TOKEN`
respectively, and must match for the portal's admin-scoped requests to authenticate). If the
real `.env` has rotated these to *different* values, update `DIEP_PORTAL_TOKEN` to match
`DIEP_ADMIN_KEY` (or vice versa — pick one as the source of truth):
```
DIEP_ADMIN_KEY=<rotated-value>
DIEP_PORTAL_TOKEN=<same-rotated-value>
```

Similarly confirm `DIEP_SERVICE_TOKEN` in `.env` is the single value both `fastapi/auth.py:37`
(via the new `env_file`) and `dispatcher/command_dispatcher.py:59` (via the new `env_file`)
will now receive — no divergence possible once both services share `env_file: .env`, but worth
a final read-through of `.env` to confirm the key is actually set (not commented out).

### Validation Procedure

1. Recreate the 3 services with the new `env_file` directive:
   ```bash
   docker compose -f docker-compose.yml up -d --force-recreate fastapi dispatcher portal
   ```
2. Confirm each container actually receives the `.env` values:
   ```bash
   docker exec diep-fastapi printenv | grep -E "DIEP_(SERVICE_TOKEN|OPERATOR_KEY|ADMIN_KEY)"
   docker exec diep-dispatcher printenv | grep DIEP_SERVICE_TOKEN
   docker exec diep-portal printenv | grep DIEP_PORTAL_TOKEN
   ```
   All values should match the corresponding `.env` entries (not the `*-CHANGE-ME` source
   defaults, unless `.env` itself still contains `*-CHANGE-ME`-style placeholders — in which
   case they'll match `.env`'s placeholders, which is still correct/consistent).
3. Functional check — admin API key from `.env` (`DIEP_ADMIN_KEY`) authenticates directly
   against FastAPI:
   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/whoami \
     -H "Authorization: Bearer $(grep ^DIEP_ADMIN_KEY .env | cut -d= -f2)"
   ```
   Expected: `200`.
4. Functional check — Portal BFF proxy authenticates to FastAPI using `DIEP_PORTAL_TOKEN`:
   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3002/api/diep/whoami
   ```
   Expected: `200` (was `401` before this fix if `.env`'s `DIEP_PORTAL_TOKEN` had been rotated
   to differ from the hardcoded fallback; `200` either way once `env_file` is wired and the
   `DIEP_PORTAL_TOKEN`/`DIEP_ADMIN_KEY` invariant from above holds).
5. Functional check — dispatcher's ack call authenticates to FastAPI using
   `DIEP_SERVICE_TOKEN`:
   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/whoami \
     -H "Authorization: Bearer $(grep ^DIEP_SERVICE_TOKEN .env | cut -d= -f2)"
   ```
   Expected: `200` with `"role":"service"`.

### Rollback Procedure

1. `git checkout -- docker-compose.yml` (and `docker-compose-fastapi.yml`/
   `docker-compose-portal.yml` if edited) to remove the `env_file: .env` lines.
2. `docker compose -f docker-compose.yml up -d --force-recreate fastapi dispatcher portal`
3. If `.env` itself was edited (to align `DIEP_PORTAL_TOKEN`/`DIEP_ADMIN_KEY` or confirm
   `DIEP_SERVICE_TOKEN`), `git diff .env` (note: `.env` is gitignored per `.env.example`'s
   header comment, so there is no git history to revert to — keep a manual backup copy of
   `.env` before editing it: `cp .env .env.bak.$(date +%s)`).

---

## Cross-Phase Notes

- **Order dependency**: Phase 3's edge-driver cert reissuance (`scripts/issue-device-cert.sh`)
  requires the mosquitto container to be reachable on the correct network (Phase 1) and the
  8883 listener to be the only listener (already true, no change needed) — but the *validation*
  of Phase 3 (telemetry arriving in TimescaleDB) requires Phase 1's network fix to be in place
  first, since `diep-ingestor` and `diep-fastapi` must be able to reach each other and
  `diep-timescaledb`.
- **Phase 4 and Phase 5 are independent of Phases 1-3** and could be executed in parallel with
  them if desired — they are sequenced last here only to keep validation of each phase
  unambiguous (avoiding simultaneous changes to network, transport, identity, *and* auth that
  would make a failed validation harder to bisect).
- **`docker kill -s HUP diep-mqtt`** (used in Phases 2 and 3 to reload the mosquitto ACL without
  a full container restart) sends `SIGHUP` to the mosquitto process inside the container —
  mosquitto reloads `acl_file`/`password_file` on `SIGHUP` without dropping existing
  connections or requiring `docker compose restart`. If this is considered a "restart" under
  the user's constraints, **pause and confirm with the user** before running it; the
  alternative (`docker compose restart mqtt`) would drop all active mTLS sessions
  (ingestor, dispatcher, all edge drivers) and require them to reconnect.
- **No phase in this plan modifies `devices` table rows, any seed SQL, or any DB schema** — all
  Phase 3 changes are confined to `drivers/*/devices.json`, mosquitto ACL/certs, and edge-driver
  compose env vars, per the "DO NOT modify databases" constraint inherited from the prior
  validation phases.

---

## Effort Summary

| Phase | Effort | Cumulative |
|---|---|---|
| 1. Docker Network Split | 0.5 day | 0.5 day |
| 2. MQTT TLS Alignment | 1 day | 1.5 days |
| 3. Device ID Mapping Alignment | 1–1.5 days | 2.5–3 days |
| 4. Kafka Listener Alignment | 0.5 day | 3–3.5 days |
| 5. Token Alignment | 0.5 day | 3.5–4 days |

**Total: 3.5–4.5 working days**, assuming each phase's validation passes on the first attempt
and no additional issues are uncovered during live validation (e.g., a Phase 3 cert/ACL
mismatch surfacing only once mosquitto is reloaded). Add a 1-day contingency buffer for a
**total realistic estimate of 4.5–5.5 days**, consistent with the "bare-minimum demo" estimate
(workstreams A-D) in `DIEP_PLATFORM_READINESS_REPORT.md` §7.
