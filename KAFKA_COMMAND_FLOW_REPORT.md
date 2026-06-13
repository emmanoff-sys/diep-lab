# DIEP Command Flow Validation: Portal -> FastAPI -> Kafka -> Dispatcher -> MQTT -> Device (+ Ack/Audit)

**Scope:** Read-only validation of the command/ack round trip described in
`DIEP_PLATFORM_ASSESSMENT.md` (§A.3 "Commands", §A.5 "Kafka flows"). Platform is
currently down; this report assumes TimescaleDB has been restored and the rest
of the stack (Kafka, FastAPI, dispatcher, MQTT, devices) would be started per
the assessment's recovery sequence.

---

## 1. Kafka topics & broker config

Two Kafka broker definitions exist and are **not equivalent**:

### Root `docker-compose.yml` (lines 14-42) — has the SASL listener
```yaml
KAFKA_LISTENERS: PLAINTEXT://:9092,CONTROLLER://:9093,SASL://:9094
KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://diep-kafka:9092,SASL://diep-kafka:9094
KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT,SASL:SASL_PLAINTEXT
KAFKA_SASL_ENABLED_MECHANISMS: PLAIN
KAFKA_LISTENER_NAME_SASL_PLAIN_SASL_JAAS_CONFIG: '...PlainLoginModule required username="diep" password="diep-kafka-pass-2026" user_diep="diep-kafka-pass-2026";'
KAFKA_AUTO_CREATE_TOPICS_ENABLE: "true"
KAFKA_LOG_DIRS: /var/lib/kafka/data
```
File: `docker-compose.yml:14-43` (network: `diep-net`, ports `9092` only published; `9094`/`9093` are container-internal-only since only `9092` is in `ports:`).

### `docker-compose-kafka.yml` (older split file) — PLAINTEXT only
```yaml
KAFKA_LISTENERS: PLAINTEXT://:9092,CONTROLLER://:9093
KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://diep-kafka:9092
KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT
```
File: `docker-compose-kafka.yml:1-33` — **no SASL/9094 listener at all**, network `diep-net` (external) — note this is *also* the legacy `diep-net`, not `diep-lab_diep-net`.

### Topic
`diep.commands` — single topic, **auto-created** (`KAFKA_AUTO_CREATE_TOPICS_ENABLE: "true"`), so default partitions=1, replication factor=1 (single KRaft broker, `KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1`, `KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR=1`). No explicit topic-creation script found (`grep -r diep.commands` only matches the producer/consumer code).

### What FastAPI and dispatcher expect by default
- `fastapi/app.py:55-59`:
  ```python
  KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "diep-kafka:9094")
  KAFKA_SECURITY_PROTOCOL = os.getenv("KAFKA_SECURITY_PROTOCOL", "SASL_PLAINTEXT")
  KAFKA_SASL_MECHANISM = os.getenv("KAFKA_SASL_MECHANISM", "PLAIN")
  KAFKA_SASL_USERNAME = os.getenv("KAFKA_SASL_USERNAME", "diep")
  KAFKA_SASL_PASSWORD = os.getenv("KAFKA_SASL_PASSWORD", "diep-kafka-pass-2026")
  ```
- `dispatcher/command_dispatcher.py:35-39` — **identical defaults** (`diep-kafka:9094`, `SASL_PLAINTEXT`, user `diep` / `diep-kafka-pass-2026`).
- `docker-compose-fastapi.yml` sets **no `KAFKA_*` env vars at all** — FastAPI will rely entirely on the above hardcoded defaults (`diep-kafka:9094` SASL_PLAINTEXT), i.e. it needs the **root-compose Kafka definition**, not `docker-compose-kafka.yml`.
- `docker-compose.yml` dispatcher service (lines 158-162) **explicitly sets** `KAFKA_BOOTSTRAP=diep-kafka:9094`, `KAFKA_SECURITY_PROTOCOL=SASL_PLAINTEXT`, `KAFKA_SASL_USERNAME=diep`, `KAFKA_SASL_PASSWORD=diep-kafka-pass-2026` — matches the SASL listener in root `docker-compose.yml`'s kafka service exactly.
- `.env` / `.env.example` contain **no `KAFKA_*` overrides** (`grep -iE "KAFKA"` returns nothing) — both services run on hardcoded code defaults pointing at the SASL/9094 listener.

**Conclusion:** FastAPI and the dispatcher both require the **root `docker-compose.yml` Kafka definition** (SASL 9094 + PLAINTEXT 9092). If `docker-compose-kafka.yml` is used instead, both producer (`get_producer()`) and consumer (`_setup_kafka()`) will fail to connect (no listener on 9094, no SASL mechanism configured on the broker) — this matches assessment §A.5/§C.3.

---

## 2. Producer side (FastAPI: `POST /commands`)

Handler chain: `app.py:2040` `create_command()` → `app.py:1931` `_dispatch_command()`.

1. **Auth/validation** (`app.py:2040-2046`): requires `require_role("operator")` (operator or admin), rate-limited 120/60s (`rate_limit("commands", 120, 60)`), and `_assert_tenant_access(principal, cmd.device_id)` (Phase 12 tenant scoping).
2. **Device/command validation** (`app.py:1934-1957`): looks up `device_type, status` from `devices`; rejects unknown device (`COMMANDS_REJECTED.labels("unknown_device")`, 404) or invalid `command_type` for that `device_type` per `ALLOWED_COMMANDS` (`COMMANDS_REJECTED.labels("invalid_command")`, 422).
3. **Persist as PENDING** (`app.py:1959-1973`):
   ```sql
   INSERT INTO commands
       (command_id, device_id, device_type, command_type, params, status, issued_by, created_at)
   VALUES (%s, %s, %s, %s, %s, 'PENDING', %s, %s)
   ```
   `command_id = str(uuid.uuid4())`, `issued_at = now(UTC)`. Commits, mirrors status to Redis (`_mirror_status`, key `command:<command_id>`), increments `COMMANDS_ISSUED.labels(device_type, cmd.command_type)` (metric `diep_commands_issued_total`, `app.py:180-182`).
4. **Produce to Kafka** (`app.py:1975-1998`):
   - Topic: `COMMAND_TOPIC = "diep.commands"` (`app.py:74`).
   - Key: `cmd.device_id` (string, UTF-8 encoded by `key_serializer`, `app.py:220`) — "keyed by device_id for per-device ordering" (comment at `app.py:1975`).
   - Value (JSON, `app.py:1976-1984`):
     ```json
     {
       "command_id": "<uuid4>",
       "device_id": "<device_id>",
       "device_type": "<device_type>",
       "command_type": "<command_type>",
       "params": { ... },
       "issued_by": "<issued_by>",
       "issued_at": "<ISO8601 UTC>"
     }
     ```
   - `get_producer()` (`app.py:214-225`): lazily-constructed `KafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP, acks="all", retries=3, **_kafka_security_kwargs())`.
   - On `KafkaError`: sets `commands.status='FAILED'`, `error_message='kafka publish failed: ...'`, mirrors FAILED to Redis, increments `COMMANDS_REJECTED.labels("kafka_error")`, returns HTTP 502.
5. **Mark dispatched** (`app.py:2000-2028`):
   ```sql
   UPDATE commands
      SET dispatched_at = COALESCE(dispatched_at, now()),
          status = CASE WHEN status IN ('ACKED','FAILED','COMPLETED') THEN status ELSE 'SENT' END
    WHERE command_id=%s
   RETURNING status
   ```
   (Guards against a race where a fast device already ACKed before this UPDATE runs.) Mirrors final status to Redis, persists `last_command_*` fields into `state:<device_id>` (Redis), increments `COMMANDS_SENT.labels(device_type, cmd.command_type)` (`diep_commands_sent_total`), observes `DISPATCH_LATENCY` (`diep_command_dispatch_seconds`).
6. **Audit** (`app.py:2048-2049`, after `_dispatch_command` returns):
   ```python
   auth.audit(principal, "issue_command", f"{cmd.device_id}:{cmd.command_type}", "ok",
              {"command_id": result.get("command_id"), "issued_by": cmd.issued_by})
   ```

**Metrics summary:** `diep_commands_issued_total`, `diep_commands_sent_total`, `diep_commands_rejected_total{reason}`, `diep_command_dispatch_seconds`.

---

## 3. Consumer side (`dispatcher/command_dispatcher.py`, 244 lines, fully read)

### Kafka consumer config (`command_dispatcher.py:155-184`)
```python
KafkaConsumer(
    "diep.commands",
    bootstrap_servers="diep-kafka:9094",      # KAFKA_BOOTSTRAP env, default
    group_id="diep-command-dispatcher",
    value_deserializer=json.loads,
    auto_offset_reset="earliest",
    enable_auto_commit=True,
    max_poll_records=1,
    consumer_timeout_ms=5000,
    connections_max_idle_ms=540000,
    security_protocol="SASL_PLAINTEXT",
    sasl_mechanism="PLAIN",
    sasl_plain_username="diep",
    sasl_plain_password="diep-kafka-pass-2026",
)
```
Retries up to 30 times with exponential backoff (2s → cap 30s) on connect failure (`command_dispatcher.py:157-183`). Main loop (`run()`, `command_dispatcher.py:207-230`) wraps the consumer iterator in an outer `while True` so idle 5s timeouts don't terminate the process.

### DOMAIN_MAP (`command_dispatcher.py:66-71`)
```python
DOMAIN_MAP = {
    "ev_charger":     "charger",
    "battery":        "battery",
    "solar_inverter": "solar",
    "microgrid":      "microgrid",
}
```
`get_mqtt_domain()` falls back to `device_type` itself if not in the map (e.g. `smartmeter` device_type → domain `smartmeter`, matching `modbus_meter/driver.py:33` comment "domain = smartmeter").

### Command topic construction (`command_dispatcher.py:79-82`, `dispatch_command_to_mqtt` at 186-205)
```python
topic = f"diep/{domain}/{device_id}/cmd"
payload = json.dumps(command)   # the full Kafka message value, unmodified
self.mqtt_client.publish(topic, payload, qos=1)
```
e.g. for `device_type="battery"`, `device_id="BAT001"` → `diep/battery/BAT001/cmd`.

### MQTT connection config (dispatcher) — `docker-compose.yml:158-181`
```yaml
MQTT_BROKER: diep-mqtt
MQTT_PORT: "8883"          # mTLS
MQTT_TLS: "1"
MQTT_CA_CERTS: /certs/ca.crt
MQTT_CLIENT_CERT: /certs/dispatcher.crt
MQTT_CLIENT_KEY: /certs/dispatcher.key
MQTT_USER: ""
MQTT_PASS: ""
```
volume: `./certs/devices:/certs:ro`. Cert files **do exist**: `certs/devices/dispatcher.crt`, `certs/devices/dispatcher.key`, `certs/devices/ca.crt` (verified via `ls`).

`_setup_mqtt()` (`command_dispatcher.py:94-115`): when `MQTT_TLS=1`, calls
```python
self.mqtt_client.tls_set(ca_certs=..., certfile=..., keyfile=...,
                          cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS_CLIENT)
```
then `connect(MQTT_BROKER, MQTT_PORT, keepalive=60)` and `loop_start()`.

**No `docker-compose-dispatcher.yml` exists** — the dispatcher is defined only in root `docker-compose.yml:150-182`, on network `diep-net` (not `diep-lab_diep-net`).

---

## 4. Acknowledgement path

### MQTT subscribe (`command_dispatcher.py:62-63, 117-120`)
```python
ACK_SUBSCRIBE_TOPIC = "diep/+/+/ack"
```
On `_on_mqtt_connect`, subscribes with `qos=1`.

### Ack handling (`command_dispatcher.py:126-153`)
`_on_mqtt_message` parses JSON payload, extracts `command_id`, `status`, `error`, then calls `_post_ack_to_fastapi`:
```python
url = f"{FASTAPI_BASE}/commands/{command_id}/ack"   # FASTAPI_BASE default http://diep-fastapi:8000
payload = {"status": status, "error": error}
requests.post(url, json=payload, headers={"Authorization": f"Bearer {SERVICE_TOKEN}"}, timeout=5)
```
`SERVICE_TOKEN = os.getenv("DIEP_SERVICE_TOKEN", "diep-service-dev-token-CHANGE-ME")` (`command_dispatcher.py:59`). The dispatcher's compose entry does **not** set `DIEP_SERVICE_TOKEN` explicitly (`docker-compose.yml:158-172` has no such key) — so it falls back to the hardcoded default `diep-service-dev-token-CHANGE-ME`, while `.env` defines `DIEP_SERVICE_TOKEN=change-me-service-token` (different value!). **Mismatch risk** — see §7.

### FastAPI `/commands/{command_id}/ack` handler (`app.py:2113-2151`)
- Requires `require_role("service")` — the bearer token must map to the `service` role (likely checked against `DIEP_SERVICE_TOKEN` env in FastAPI's auth module).
- Validates `status.upper()` is `ACKED` or `FAILED` (else 422).
- Updates:
  ```sql
  UPDATE commands
     SET status=%s, error_message=%s, acked_at=now()
   WHERE command_id=%s
  RETURNING device_id, device_type, command_type, created_at
  ```
- 404 if `command_id` unknown.
- Mirrors status to Redis (`_mirror_status`), persists `last_command_*` fields (incl. `last_command_acked_at`) into `state:<device_id>`.
- Metrics: `COMMANDS_ACKED.labels(device_type or "unknown", command_type, status).inc()` → `diep_commands_acked_total{device_type,command_type,result}`; `ACK_LATENCY.labels(status).observe(now - created_at)` → `diep_command_ack_latency_seconds{result}` (`app.py:2148-2150`).

---

## 5. Audit logging (`audit_events`, `sql/008_security.sql`)

Table columns (`sql/008_security.sql:4-13`): `id, ts (default now()), principal, role, action, resource, source_ip, result, detail (jsonb)`.

Write helper: `fastapi/auth.py:194-212`, `audit(principal, action, resource, result, detail)`:
```sql
INSERT INTO audit_events (principal, role, action, resource, source_ip, result, detail)
VALUES (%s, %s, %s, %s, %s, %s, %s)
```
`principal = principal.name if principal else "anonymous"`, `role = principal.role`, `source_ip = principal.source_ip`. Best-effort — wrapped in try/except, only logs a warning on failure (never fails the request).

Call sites (`grep auth.audit`, `app.py`):
| Line | Action | Resource |
|---|---|---|
| 799 | `register_asset` | `asset.device_id` |
| 967 | `onboarding_enroll` | `enrollment.device_id` |
| 1050 | `onboarding_validate` | `device_id` |
| 1207 | `onboarding_certify` | `device_id` |
| 1247 | `onboarding_approve` | `device_id` |
| 1402 | `derms_battery_dispatch` | `device_id`/`site_name` |
| 1446 | `derms_peak_shaving` | `site_name` |
| 1479 | `derms_demand_response` | `site_name` |
| 1518 | `derms_load_optimization` | `site_name` |
| **2048** | **`issue_command`** | `f"{cmd.device_id}:{cmd.command_type}"`, detail `{command_id, issued_by}` |

**Note:** the `/commands/{command_id}/ack` handler (`app.py:2113-2151`) does **not** call `auth.audit()` — only the initial `POST /commands` is audited. The ack/acked_at transition is recorded in `commands.status`/`acked_at` and the Redis mirror, but not as a separate `audit_events` row.

---

## 6. Device-side ack production (per device)

| Seed device | device_type | DOMAIN_MAP domain | Edge/sim compose | Driver `device_id` used on MQTT | cmd subscribe? | ack publish? | Notes |
|---|---|---|---|---|---|---|---|
| **BAT001** | battery | `battery` | `docker-compose-battery-edge.yml` (`drivers/battery_bms`, `edge_agent.py`) | **`BAT900`** (`drivers/battery_bms/devices.json`) | Yes — `Runner.run()` subscribes `cmd_topic` = `diep/battery/<device_id>/cmd` (`drivers/diep_driver/runner.py:63-65`) | Yes — `Runner._on_command` publishes to `ack_topic` (`runner.py:39-58`); `battery_bms/driver.py:88` implements `execute_command` | **Device-ID mismatch**: dispatcher will publish to `diep/battery/BAT001/cmd` (from `commands.device_id=BAT001`), but the running edge driver subscribes to `diep/battery/BAT900/cmd`. Command for `BAT001` would never reach this driver. |
| **INV001** | solar_inverter | `solar` | `docker-compose-sunspec.yml` (`drivers/sunspec`, `edge_agent.py`) | **`INV900`** (`drivers/devices.json`) | Yes — same generic `Runner` (`sunspec/driver.py:33` `domain="solar"`, `execute_command` at `sunspec/driver.py:98`) | Yes — same `Runner` ack path | Same **ID mismatch**: dispatcher topic `diep/solar/INV001/cmd` vs driver subscribed to `diep/solar/INV900/cmd`. |
| **MG001** | microgrid | `microgrid` | `docker-compose-microgrid-edge.yml` (`drivers/microgrid_iec104`, `edge_agent.py`) | **`MGC900`** (`drivers/microgrid_iec104/devices.json`) | Yes — `Runner` (+ `microgrid_iec104/driver.py:119` `execute_command`) | Yes — `Runner` ack path | Same **ID mismatch**: `diep/microgrid/MG001/cmd` vs `diep/microgrid/MGC900/cmd`. |
| **EV001** | ev_charger | `charger` | `docker-compose-ev-charger.yml` (`simulator/ev_charger.py`, legacy) | **`EV001`** (`DEVICE_ID` env, default `EV001`, `docker-compose-ev-charger.yml:17`) | Yes — `ev_charger.py:68` `client.subscribe(CMD_TOPIC)`, `CMD_TOPIC = diep/charger/EV001/cmd` | Yes — `ev_charger.py:89` `client.publish(ACK_TOPIC, ...)` | **IDs match** (`EV001`==`EV001`), but `ev_charger.py:98` does `client.connect(BROKER, 1883, 60)` — **hardcoded plaintext port 1883, no TLS**. Mosquitto only serves mTLS 8883 (per assessment §A.4); this simulator cannot connect to the broker at all in the current config, so it will neither receive `/cmd` nor publish `/ack`. Also no client cert exists for `EV001` under `certs/devices/`. |
| **METER001** | smartmeter | (not in DOMAIN_MAP → falls back to `device_type` = `smartmeter`) | `docker-compose-meter.yml` (`drivers/modbus_meter`, `edge_agent.py`) | **`MTR900`** (`drivers/modbus_meter/devices.json`) | Yes — `Runner` (+ `modbus_meter/driver.py:93` `execute_command`); `modbus_meter/driver.py:33` `domain="smartmeter"` | Yes — `Runner` ack path | Domain matches dispatcher fallback (`diep/smartmeter/.../cmd`), but **ID mismatch**: dispatcher publishes `diep/smartmeter/METER001/cmd`; driver subscribes `diep/smartmeter/MTR900/cmd`. |

**Summary gap:** for **all five seeded devices** (`BAT001, INV001, MG001, EV001, METER001`), a command issued via `POST /commands` and dispatched by `command_dispatcher.py` to `diep/<domain>/<device_id>/cmd` (using the `devices.device_id` from Postgres) will **not be received** by the currently-configured device/edge-driver containers:
- `BAT001/INV001/MG001/METER001`: edge drivers are configured with different device IDs (`BAT900/INV900/MGC900/MTR900`) — topic mismatch.
- `EV001`: IDs match, but the simulator cannot reach the mTLS-only broker (wrong port/no TLS, no cert).

In all five cases, a `POST /commands` would leave the row stuck at **`SENT`** (never reaching `ACKED`/`FAILED`), `diep_commands_acked_total` would never increment for these devices, and `diep_command_ack_latency_seconds` would never be observed.

---

## 7. End-to-end break points

### Kafka reachability
- **If root `docker-compose.yml`'s kafka service is started** (SASL 9094 + PLAINTEXT 9092 + CONTROLLER 9093, network `diep-net`): both FastAPI (`docker-compose-fastapi.yml`, network `diep-net`, no Kafka env overrides → defaults to `diep-kafka:9094` SASL_PLAINTEXT) and the dispatcher (root compose, network `diep-net`, explicit `KAFKA_BOOTSTRAP=diep-kafka:9094` SASL_PLAINTEXT, same creds) **would both be able to connect**, since both default to/are configured for the same SASL listener and are on the same `diep-net` network as `diep-kafka`.
- **If `docker-compose-kafka.yml` is started instead** (PLAINTEXT-only on 9092, network `diep-net`): neither FastAPI's `get_producer()` nor the dispatcher's `KafkaConsumer` would connect — both attempt `SASL_PLAINTEXT` against `diep-kafka:9094`, which doesn't exist on this broker config. `_setup_kafka()` would retry 30× (~total ~10+ minutes with backoff) then raise `RuntimeError("Failed to connect to Kafka after 30 attempts")`, crashing the dispatcher container (Docker would restart-loop it, since `restart: unless-stopped`). FastAPI's `get_producer()` is lazy and would only fail (502, `kafka_error`) on the first `POST /commands`.
- **Network caveat**: `docker-compose-fastapi.yml` and root `docker-compose.yml`'s `kafka`/`dispatcher` all use network `diep-net` (legacy), but the currently-existing Docker network is `diep-lab_diep-net` (per `docker network ls`, confirmed: only `diep-lab_diep-net` and default bridge/host/none exist; `diep-net` does not exist). **Starting any of these `diep-net`-scoped services will either fail ("external network not found" for the split files that mark `diep-net: external: true`, e.g. `docker-compose-kafka.yml:33`) or silently create a brand-new bridge network `diep-net`** that is disconnected from `diep-lab_diep-net` (where `diep-mqtt` and the mTLS edge-driver split files live). This would split FastAPI/Kafka/dispatcher onto a different network than MQTT/edge devices, breaking the MQTT leg even if Kafka itself comes up — a second, independent break point on top of #6.

### MQTT / dispatcher mTLS connectivity
- The dispatcher's MQTT config (`docker-compose.yml:163-170`) is internally consistent with the **active** mosquitto config (mTLS-only 8883, `require_certificate true`, `use_identity_as_username true`): `MQTT_PORT=8883`, `MQTT_TLS=1`, cert/key/CA paths point at `./certs/devices/dispatcher.{crt,key}` and `./certs/devices/ca.crt`, and **all three files exist** on disk (verified via `ls certs/devices/`).
- Assuming the dispatcher container is brought up on the **same network as `diep-mqtt`** (i.e., `diep-lab_diep-net`, which would require fixing the network-name mismatch above, since the dispatcher's own compose entry currently specifies `diep-net`), the dispatcher **should be able to establish the mTLS connection** to `diep-mqtt:8883` and subscribe to `diep/+/+/ack` — its cert material is present and correctly referenced.
- **Net assessment**: dispatcher's MQTT leg is the *one piece that is correctly configured* for the current mTLS-only broker, **provided** the network-name issue is fixed first. Its Kafka leg works only if the root-compose (SASL/9094) Kafka definition is used. The weakest links are (a) network-name reconciliation (affects whether dispatcher can reach either Kafka or MQTT by container name), and (b) the device-ID/topic mismatches and EV001's plaintext-MQTT hardcoding documented in §6, which break the *far* end of the round trip regardless of whether the dispatcher itself connects correctly.

### `DIEP_SERVICE_TOKEN` mismatch (ack auth)
- `.env`: `DIEP_SERVICE_TOKEN=change-me-service-token`.
- Dispatcher's compose env (`docker-compose.yml:158-172`) does **not** set `DIEP_SERVICE_TOKEN`, so `command_dispatcher.py:59` falls back to its own hardcoded default `diep-service-dev-token-CHANGE-ME` — a **different string** than `.env`'s value. If FastAPI's `require_role("service")` check validates the bearer token against `.env`'s `DIEP_SERVICE_TOKEN` (`change-me-service-token`), the dispatcher's `_post_ack_to_fastapi` POST to `/commands/{command_id}/ack` would receive **401/403**, and `commands.status` would never advance from `SENT` to `ACKED`/`FAILED` even for a device that *does* successfully publish an MQTT ack. This should be verified against `fastapi/auth.py`'s service-token check and fixed by setting `DIEP_SERVICE_TOKEN` explicitly in the dispatcher's environment (matching `.env`).

---

## 8. Sequence diagram — full command + ack round trip (happy path, as designed)

```
Portal/API client     FastAPI (8000)        Kafka (diep.commands)   Dispatcher           MQTT (8883 mTLS)        Device/edge-driver
       |                     |                       |                    |                       |                       |
       |--POST /commands---->|                       |                    |                       |                       |
       |  (operator/admin,   |                       |                    |                       |                       |
       |   rate-limited)     |                       |                    |                       |                       |
       |                     |--validate device,---->|                    |                       |                       |
       |                     |  command_type         |                    |                       |                       |
       |                     |--INSERT commands------|                    |                       |                       |
       |                     |  (status=PENDING)     |                    |                       |                       |
       |                     |--mirror Redis---------|                    |                       |                       |
       |                     |  COMMANDS_ISSUED++    |                    |                       |                       |
       |                     |                       |                    |                       |                       |
       |                     |--produce key=device_id, value={command_id, |                       |                       |
       |                     |  device_id, device_type, command_type,     |                       |                       |
       |                     |  params, issued_by, issued_at}------------>|                       |                       |
       |                     |                       |                    |                       |                       |
       |                     |--UPDATE commands------|                    |                       |                       |
       |                     |  status=SENT,         |                    |                       |                       |
       |                     |  dispatched_at=now()  |                    |                       |                       |
       |                     |  COMMANDS_SENT++,     |                    |                       |                       |
       |                     |  DISPATCH_LATENCY     |                    |                       |                       |
       |                     |--audit_events---------|                    |                       |                       |
       |                     |  action=issue_command |                    |                       |                       |
       |<--202 {command_id,--|                       |                    |                       |                       |
       |     status=SENT}    |                       |                    |                       |                       |
       |                     |                       |                    |                       |                       |
       |                     |                       |--consume (group=---|                       |                       |
       |                     |                       |  diep-command-     |                       |                       |
       |                     |                       |  dispatcher)------>|                       |                       |
       |                     |                       |                    |--map device_type----->|                       |
       |                     |                       |                    |  -> domain (DOMAIN_MAP)|                      |
       |                     |                       |                    |--PUBLISH-------------->|                       |
       |                     |                       |                    |  diep/<domain>/<device_id>/cmd                |
       |                     |                       |                    |  qos=1, payload=full   |                       |
       |                     |                       |                    |  Kafka message         |                       |
       |                     |                       |                    |                        |--deliver cmd--------->|
       |                     |                       |                    |                        |  (subscribed cmd_topic)|
       |                     |                       |                    |                        |                       |
       |                     |                       |                    |                        |<--PUBLISH ack---------|
       |                     |                       |                    |                        |  diep/<domain>/<device_id>/ack
       |                     |                       |                    |                        |  {command_id, device_id,
       |                     |                       |                    |                        |   status=ACKED|FAILED, error}
       |                     |                       |                    |<--deliver ack----------|                       |
       |                     |                       |                    |  (subscribed diep/+/+/ack)                    |
       |                     |                       |                    |                        |                       |
       |                     |<--POST /commands/{command_id}/ack----------|                        |                       |
       |                     |  Bearer DIEP_SERVICE_TOKEN, {status, error}|                        |                       |
       |                     |--UPDATE commands------|                    |                        |                       |
       |                     |  status=ACKED|FAILED, |                    |                        |                       |
       |                     |  acked_at=now()       |                    |                        |                       |
       |                     |--mirror Redis---------|                    |                        |                       |
       |                     |  COMMANDS_ACKED++,    |                    |                        |                       |
       |                     |  ACK_LATENCY observe  |                    |                        |                       |
       |                     |-->200 {command_id,----|                    |                        |                       |
       |                     |     status}           |--->(ack to disp.)  |                        |                       |
       |                     |                       |                    |                        |                       |
       |--GET /commands/{id}>|                       |                    |                        |                       |
       |<--{status=ACKED}----|                       |                    |                        |                       |
```

### Where the current configuration breaks this diagram

```
[Portal] --POST /commands--> [FastAPI] --INSERT PENDING, audit_events--> OK (DB-only, no external deps)
                                  |
                                  |--produce diep.commands--> [Kafka]
                                  |     BREAKS IF: docker-compose-kafka.yml (PLAINTEXT-only) used instead of
                                  |     root docker-compose.yml's SASL/9094 broker (§1, §7)
                                  |     ALSO BREAKS IF: diep-net network doesn't exist / is recreated separate
                                  |     from diep-lab_diep-net (§7)
                                  v
                            [Dispatcher] --consume--> map domain --> publish diep/<domain>/<device_id>/cmd
                                  |     (MQTT/mTLS config itself is correct & certs present, IF on
                                  |      diep-lab_diep-net with diep-mqtt — §7)
                                  v
                            [diep-mqtt:8883 mTLS]
                                  |
                                  v
                          [Edge driver / simulator]
                                  BREAKS FOR ALL 5 SEEDED DEVICES (§6):
                                  - BAT001/INV001/MG001/METER001: driver subscribes under a different
                                    device_id (BAT900/INV900/MGC900/MTR900) than the dispatcher publishes to
                                    (BAT001/INV001/MG001/METER001) -> command never received
                                  - EV001: device_id matches, but simulator hardcodes plaintext MQTT 1883
                                    (no TLS, no cert) -> cannot connect to mTLS-only broker at all
                                  =====> no /ack ever published =====> commands.status stuck at SENT forever
                                  =====> diep_commands_acked_total / ack_latency never recorded for these devices

            (even if an ack WERE published, a secondary risk applies:)
                          [Dispatcher] --POST /commands/{id}/ack--> [FastAPI]
                                  POSSIBLE BREAK: dispatcher's DIEP_SERVICE_TOKEN default
                                  ("diep-service-dev-token-CHANGE-ME") differs from .env's
                                  ("change-me-service-token") -> 401/403 on ack POST if
                                  FastAPI validates against .env value (§7)
```

---

## Summary of key findings

1. **Kafka**: FastAPI and dispatcher both hardcode `diep-kafka:9094` / `SASL_PLAINTEXT` / user `diep` (`fastapi/app.py:55-59`, `dispatcher/command_dispatcher.py:35-39`); `.env` has no `KAFKA_*` overrides. Only the **root `docker-compose.yml`** kafka service provides this listener; `docker-compose-kafka.yml` does not (PLAINTEXT-only) and would break both producer and consumer.
2. **No `docker-compose-dispatcher.yml`** — dispatcher is defined only in root `docker-compose.yml:150-182`, network `diep-net` (the network that currently doesn't exist; only `diep-lab_diep-net` exists).
3. **Dispatcher MQTT/mTLS config is correct and certs exist** (`certs/devices/dispatcher.{crt,key}`, `ca.crt`) — this leg should work once the network mismatch is resolved.
4. **All 5 seeded devices have a command-delivery gap**: `BAT001/INV001/MG001/METER001` edge drivers use different device IDs (`BAT900/INV900/MGC900/MTR900`) than the `commands` table / dispatcher topic construction, so `diep/<domain>/<device_id>/cmd` is never subscribed by the running driver. `EV001`'s legacy simulator hardcodes plaintext MQTT port 1883 with no TLS/cert against an mTLS-only broker.
5. **Audit**: `POST /commands` writes an `audit_events` row (`action=issue_command`); the `/commands/{id}/ack` handler does **not** write to `audit_events` (only updates `commands`/Redis/metrics).
6. **Possible service-token mismatch**: dispatcher's ack POST uses `DIEP_SERVICE_TOKEN` default `diep-service-dev-token-CHANGE-ME` (not set in its compose env), while `.env` defines `DIEP_SERVICE_TOKEN=change-me-service-token` — if FastAPI checks against `.env`, the ack POST would be rejected even if MQTT delivery worked.

**Net result**: even with TimescaleDB restored and the rest of the stack started per the assessment's recovery sequence, a `POST /commands` for any of the 5 seeded devices would reach `status=SENT` and then **stay there indefinitely** — the command+ack round trip is not currently end-to-end functional for any seeded device, due to (a) compose-file/network reconciliation issues affecting Kafka/MQTT reachability, and (b) device-ID/topic and MQTT-TLS mismatches at the device layer.
