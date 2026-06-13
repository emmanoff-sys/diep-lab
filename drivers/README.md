# DIEP Protocol Drivers (`drivers/`)

Edge protocol-adapter SDK for Phase 9. See **DIEP_PROTOCOL_ADAPTER_FRAMEWORK.md** for the
full design. **New code only — does not modify any running service.**

## Layout
- `diep_driver/` — shared SDK: `BaseDriver` (interface), `normalize` (canonical schema),
  `mqtt_client` (TLS/mTLS-ready transport), `registry` (factory), `runner` (telemetry+command loop).
- `sunspec/` — **implemented** (Phase 9E, first real vertical): SunSpec-over-Modbus PV
  inverter driver (`driver.py`), dependency-free model decoder (`models.py`), Modbus-TCP
  transport with pymodbus/built-in fallback (`transport.py`), a runnable Modbus-TCP
  inverter simulator (`sim.py`), and an end-to-end selftest (`selftest.py`).
- `modbus_meter/` — **implemented** (Phase 9C, first metering vertical): generic Modbus
  smart-meter driver (`driver.py`), float32 register map (`models.py`), simulator
  (`sim.py`), selftest, reusing the SunSpec Modbus `transport.py`. Commands:
  read_only / remote_disconnect / remote_connect via a control relay register.
- `battery_bms/` — **implemented** (Phase 9D, storage vertical): battery/BMS Modbus
  driver (`driver.py`), register map (`models.py`), simulator (`sim.py`), selftest,
  reusing the SunSpec Modbus `transport.py`. Commands: charge / discharge / standby /
  idle / set_power_limit / set_soc_target; **DERMS-dispatchable**.
- `ocpp_csms/` — **implemented** (Phase 9F, EV-charger vertical): an OCPP 1.6J **CSMS**
  (WebSocket *server*, not a poller) + MQTT bridge (`driver.py`), pure-python WebSocket
  transport (`transport.py`), OCPP-J message models (`models.py`), charge-point simulator
  (`sim.py`), selftest. Commands: start_charging / stop_charging / set_limit →
  RemoteStart / RemoteStop / SetChargingProfile. Runs as a **service** (see
  `docker-compose-ocpp.yml`), not via the per-device Runner.
- `microgrid_iec104/` — **implemented** (Phase 9G-a, microgrid vertical): microgrid
  controller over **IEC 60870-5-104** (pollable SCADA, runs via the standard Runner) —
  driver (`driver.py`), APCI/ASDU transport (`transport.py`), IOA models (`models.py`),
  RTU simulator with islanding droop physics (`sim.py`), selftest. Commands:
  island / grid_connect (C_SC breaker) / set_setpoint (C_SE).
- `modbus/ dlms/ ocpp/ iec104/ iec61850/ dnp3/ bacnet/` — per-protocol stubs (the `ocpp`
  and `iec104` stubs are superseded by `ocpp_csms/` and `microgrid_iec104/`). IEC 61850
  (9G-b), DLMS, DNP3, BACnet remain stubs.
- `edge_agent.py` — config-driven host that runs the **polling** drivers via the registry.

## Status
Phase 9 device integration **complete** — five real protocol verticals behind one SDK,
spanning poll (Modbus/SunSpec, IEC-104) and event-driven server (OCPP/WebSocket) models:
**SunSpec (9E)**, **Modbus meter (9C)**, **Battery/BMS (9D)**, **OCPP EV charger (9F)**,
**Microgrid IEC-104 (9G-a)** — all verified end-to-end (telemetry → MQTT → ingestor → DB,
command/ack, twin, DERMS, onboarding→certification). INV900, MTR900, BAT900, EVSE900, and
MGC900 are all PRODUCTION_READY. Remaining: IEC 61850 (9G-b), DLMS, DNP3, BACnet — and the
cross-cutting schema extension, security (9J), and HA (9K) work.

## Try it (no field hardware)
```bash
cd drivers
python edge_agent.py --list      # -> bacnet, dlms, dnp3, iec104, iec61850, modbus, ocpp, sunspec
python -m sunspec.selftest       # SunSpec driver e2e against the bundled simulator

# Deploy the SunSpec vertical against the live stack (sim + edge agent in a container):
#   docker compose -f ../docker-compose-sunspec.yml up -d   # publishes diep/solar/INV900
```

## How a real driver plugs in
A driver subclasses `BaseDriver`, sets `domain` + `aliases` + `supported_commands()`, and
implements `connect` / `read_telemetry` / `execute_command`. The shared `Runner` publishes
canonical telemetry to `diep/<domain>/<device_id>` and handles `.../cmd` → `execute_command`
→ `.../ack` — the **exact same MQTT contract the simulators use**, so drivers are drop-in
replacements that work with the existing ingestor, twins, DERMS, and certification suite.
