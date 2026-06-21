# DIEP Integration / Adapter Layer

How a real-world field protocol is bridged into the DIEP MQTT bus. DIEP already
ships **Modbus** as the reference (the `modbus_meter`, `sunspec`, and
`battery_bms` drivers are real Modbus-TCP adapters); ADMS M7 adds **DNP3** as a
second protocol, implemented as a mock so it runs with no field hardware.

## The bridge pattern (`drivers/`)

Every adapter is a `BaseDriver` subclass run by the shared `Runner`, which owns
the MQTT publish/subscribe/ack loop. A driver implements only the
protocol-specific parts:

```
connect()           open the protocol session (TCP/serial/WebSocket/DNP3 master)
read_telemetry()    read native points from the device
normalize()         map native -> canonical schema (voltage, power_kw, ...)
execute_command()   apply a command (controls/setpoints) and return ACK/FAIL
supported_commands()
```

The `Runner` then publishes canonical telemetry to **`diep/<domain>/<device_id>`**
and routes **`.../cmd` → `execute_command` → `.../ack`** — the *exact same MQTT
contract the simulators use*, so an adapter is a drop-in source for the existing
ingestor → TimescaleDB, digital-twin, DERMS, and OMS paths. Transport is
mTLS-secured (`diep_driver/mqtt_client.py`), per-device cert identity.

```
field device --DNP3/Modbus/...--> driver.read_telemetry() --normalize-->
  Runner --MQTT diep/<domain>/<id>--> ingestor --POST /telemetry--> TimescaleDB
operator --POST /commands--> Kafka --> dispatcher --MQTT .../cmd--> driver.execute_command()
```

## DNP3 adapter (M7, mock)

`drivers/dnp3/` — a microgrid/RTU vertical over DNP3:

- `models.py` — the outstation point map: Analog Inputs (g30) for V / Hz / PCC kW
  / load / solar, a Binary Input (g1) for breaker status, and controls (CROB g12
  breaker, AO g41 PCC setpoint).
- `sim.py` — `MockDnp3Outstation`: an in-process point database with microgrid
  physics (islanding droop) that honors control operations. Stands in for a real
  outstation (no `opendnp3`/`pydnp3` dependency).
- `driver.py` — `Dnp3Driver` (`@register("dnp3")`, `domain="microgrid"`): polls
  the outstation, normalizes PCC active power into `power_kw` + grid import/export,
  and maps `island`/`grid_connect` → breaker CROB and `set_setpoint` → analog
  output.
- `selftest.py` — end-to-end driver test against the mock (`python -m dnp3.selftest`).

**Going to real hardware:** replace `Dnp3Driver.connect()` with a real DNP3 master
(e.g. `opendnp3`) pointed at the outstation `host:port` and run integrity polls in
`read_telemetry()`. Nothing else changes — the MQTT/normalize/command contract is
identical.

## Deploy

```bash
# 1. issue the RTU's mTLS identity (gitignored, like all device certs)
scripts/issue-device-cert.sh MGD900
# 2. the ACL block (mosquitto/config/acl) and device row (sql/017_dnp3_rtu.sql)
#    are already in the repo; on a fresh DB they are applied by init-db.sh.
# 3. run the bridge
docker compose -f docker-compose-dnp3.yml up -d   # publishes diep/microgrid/MGD900
```

Validated live: the bridge published canonical microgrid telemetry for `MGD900`
through mTLS → ingestor → TimescaleDB, with store-and-forward buffering on
initial connect.
