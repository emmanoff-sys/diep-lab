# K5 — MQTT High Availability Implementation Plan
## Phase 17 HA Roadmap · Stage 5 of 6

**Date:** 2026-06-16  
**Author:** Phase 17 HA Automation  
**Status:** In progress — validation environment being built  
**Predecessor stages:** K1 (PostgreSQL PITR), K4 (Redis Sentinel), K6 (MinIO HA), K3 (Kafka HA), K2 (PostgreSQL HA)

---

## 1. Objective

Replace the single Mosquitto broker (`diep-mqtt`) with a 3-node EMQX 5 cluster behind an L4
load balancer. The replacement must be transparent to all existing clients: the same device
certificates, the same topic hierarchy, and the same ACL model are preserved without code
changes to any driver, ingestor, or dispatcher.

Production Mosquitto remains untouched throughout. All work occurs in a fully isolated
side-by-side validation environment.

---

## 2. Current State Assessment

### 2.1 Broker

| Property | Value |
|---|---|
| Image | `eclipse-mosquitto` (latest) |
| Container | `diep-mqtt` |
| Port | 8883 (mTLS only — port 1883 retired after Phase 9J-S4) |
| Auth | `allow_anonymous false` · password file + ACL file |
| TLS mode | Mutual TLS: `require_certificate true` · `use_identity_as_username true` |
| CA | `O=DIEP, CN=DIEP-Root-CA` (expires 2036-06-02) |
| Server cert | `CN=diep-mqtt` · SAN: `DNS:diep-mqtt, DNS:localhost, IP:127.0.0.1` |

### 2.2 TLS Certificate Inventory

All device/service certificates are signed by `DIEP-Root-CA` and expire 2028.

| CN | Role | MQTT scope |
|---|---|---|
| `INV001` | SunSpec solar edge driver | `diep/solar/INV001` pub + `/cmd` sub + `/ack` pub |
| `METER001` | Modbus smart-meter edge driver | `diep/smartmeter/METER001` pub + `/cmd` sub + `/ack` pub |
| `BAT001` | Battery BMS edge driver | `diep/battery/BAT001` pub + `/cmd` sub + `/ack` pub |
| `MG001` | Microgrid IEC-104 edge driver | `diep/microgrid/MG001` pub + `/cmd` sub + `/ack` pub |
| `EV001` | EV charger simulator | `diep/charger/EV001` pub + `/cmd` sub + `/ack` pub |
| `csms` | OCPP CSMS bridge | `diep/charger/+` pub/ack + `/cmd` sub (charger domain) |
| `ingestor` | Telemetry ingestor service | `diep/+/+` sub only |
| `dispatcher` | DERMS command dispatcher | `diep/+/+/ack` sub + `diep/+/+/cmd` pub |

### 2.3 Topic Hierarchy

```
diep/<domain>/<deviceId>        ← telemetry (3 levels, devices publish)
diep/<domain>/<deviceId>/cmd   ← command   (4 levels, dispatcher publishes)
diep/<domain>/<deviceId>/ack   ← ack       (4 levels, devices publish)

Domains: solar · smartmeter · battery · microgrid · charger
```

### 2.4 Client Connection Model

All clients use `paho-mqtt` with:
- `loop_start()` / `loop_forever()` — automatic reconnect enabled by paho
- `on_connect` callback re-subscribes all topics — no manual reconnect logic needed
- QoS 0 for telemetry; QoS 1 for commands and acks
- No persistent sessions (paho default: clean session = True)

### 2.5 Session Handling Gap in Current Architecture

Mosquitto single-node: any broker restart drops all in-flight QoS 1 messages and forces
client reconnect. This is the single point of failure being addressed.

---

## 3. HA Solution Evaluation

| Option | Clustering | Session persistence | mTLS | Ops complexity | Selected |
|---|---|---|---|---|---|
| **EMQX 5 cluster** | Native Erlang/Mnesia | Yes — shared across nodes | Native (≥v5 listener config) | Low (same image, static seeds) | **✅** |
| Mosquitto bridge (MQTT bridging) | No — active/passive at best | No — per-broker state | Yes | High (bridge ACL, loop detection) | ✗ |
| VerneMQ cluster | Native (Riak-based) | Yes | Yes | High (Riak ops, old image) | ✗ |
| HiveMQ cluster | Native | Yes | Yes | High (commercial, K8s focus) | ✗ |

**Decision rationale:** EMQX 5 provides native Erlang distribution clustering with Mnesia
for shared session state. It supports MQTT 3.1.1 and 5.0, has built-in ACL file authorization
with `{user, "CN"}` term format (exact Mosquitto parity), and `peer_cert_as_username = cn`
on the SSL listener directly mirrors Mosquitto's `use_identity_as_username true`. No code
changes to any existing client are required.

---

## 4. Target Architecture

### 4.1 Topology

```
Devices / Services
(INV001, METER001, BAT001, MG001, EV001, csms, ingestor, dispatcher)
         │
         │  TLS 8883 (client cert = DIEP-Root-CA-signed)
         ▼
┌─────────────────────────────────────────────────────┐
│  HAProxy 2.8  (L4 TCP passthrough, leastconn)      │
│  hostname: emqx-ha-lb  · port 8883                 │
└─────────────┬──────────────┬──────────────┬─────────┘
              │              │              │
              ▼              ▼              ▼
      ┌──────────┐   ┌──────────┐   ┌──────────┐
      │ EMQX 5.8 │   │ EMQX 5.8 │   │ EMQX 5.8 │
      │ emqx-ha-1│   │ emqx-ha-2│   │ emqx-ha-3│
      │ :8883    │   │ :8883    │   │ :8883    │
      └────┬─────┘   └────┬─────┘   └────┬─────┘
           │              │              │
           └──────────────┴──────────────┘
              Erlang distribution :4370
              EMQX cluster RPC    :5369
              Shared Mnesia DB (sessions, subscriptions, retained)
```

### 4.2 EMQX Cluster Properties

| Property | Value |
|---|---|
| Image | `emqx/emqx:5.8.6` |
| Cluster strategy | `static` (all seeds listed at startup) |
| Session persistence | Mnesia shared across all nodes |
| Quorum requirement | None — any 1 of 3 nodes can serve clients |
| Max tolerated failures | 2 of 3 nodes (cluster degrades to 1 node but remains operational) |
| MQTT listener | Port 8883 (SSL/mTLS only; TCP 1883 disabled) |
| TLS mode | `verify_peer` + `fail_if_no_peer_cert = true` (identical to Mosquitto) |
| Username source | `peer_cert_as_username = cn` (identical to Mosquitto `use_identity_as_username`) |
| Auth model | Empty authn chain (TLS handshake = authentication gate) |
| ACL model | File-based (`/opt/emqx/etc/acl.conf`) — Erlang term format |
| `no_match` action | `deny` (same as Mosquitto's implicit deny) |
| `deny_action` | `disconnect` (stricter than Mosquitto drop; aids misconfiguration detection) |

### 4.3 Load Balancer

| Property | Value |
|---|---|
| Image | `haproxy:2.8` |
| Mode | TCP (L4) — TLS passthrough; EMQX terminates TLS |
| Algorithm | `leastconn` |
| Health check | TCP connect every 5 s; fall after 3 failures; rise after 2 successes |
| Client endpoint change | `diep-mqtt:8883` → `emqx-ha-lb:8883` (hostname only) |

### 4.4 Mosquitto → EMQX Config Mapping

| Mosquitto directive | EMQX 5 equivalent |
|---|---|
| `allow_anonymous false` | `authentication = []` + `fail_if_no_peer_cert = true` |
| `require_certificate true` | `ssl_options.fail_if_no_peer_cert = true` |
| `use_identity_as_username true` | `listeners.ssl.default.peer_cert_as_username = cn` |
| `acl_file /mosquitto/config/acl` | `authorization.sources[{type=file, path=...}]` |
| Implicit ACL deny | `authorization.no_match = deny` |
| Port 8883 | `listeners.ssl.default.bind = "0.0.0.0:8883"` |

### 4.5 Failover Behavior

| Scenario | paho behavior | EMQX cluster behavior | DERMS commands |
|---|---|---|---|
| 1 node fails (2/3 up) | `on_disconnect` fires; `loop_start` reconnects to HAProxy | HAProxy health check removes failed node; routes to healthy nodes | QoS 1 commands re-queued by dispatcher on reconnect |
| 2 nodes fail (1/3 up) | Reconnect to surviving node | Single node serves all clients | Full continuity |
| All 3 nodes fail | Connection refused; paho retries with backoff | N/A | Commands queued in Kafka; dispatched on reconnect |
| Node recovery | Transparent (paho stays connected to HAProxy) | Recovered node re-joins Mnesia cluster; HAProxy adds it back | No operator action |

### 4.6 ACL Migration

The Mosquitto ACL file maps directly to EMQX Erlang term format. Semantics are identical
(username = cert CN; topic wildcard `+` is preserved). Additions for EMQX file that are
redundant in Mosquitto (explicit `{deny, all}.` at end) are included for clarity.

The one behavioral difference: Mosquitto silently drops unauthorized publishes; EMQX with
`deny_action = disconnect` terminates the connection. This is a deliberate security
enhancement — misconfigured clients are surfaced immediately rather than silently ignored.

---

## 5. Implementation Steps

### 5.1 Pre-production (validation only)

1. Generate EMQX cluster server TLS certificate:
   - Sign with existing DIEP CA (`mosquitto/config/certs/ca.crt` / `ca.key`)
   - CN: `emqx-ha-cluster`
   - SAN: `DNS:emqx-ha-1`, `DNS:emqx-ha-2`, `DNS:emqx-ha-3`, `DNS:emqx-ha-lb`,
     `DNS:localhost`, `IP:127.0.0.1`
   - All clients' cert trust anchored to same DIEP CA — no client change

2. Create `emqx-ha-validation/etc/emqx.conf` — shared cluster config:
   - Disable TCP 1883 listener
   - Enable SSL 8883 listener with mTLS + `peer_cert_as_username = cn`
   - `authentication = []` (empty = allow all; TLS handshake is the auth gate)
   - `authorization.sources = [{type = file, path = acl.conf}]`
   - `authorization.no_match = deny`
   - `authorization.deny_action = disconnect`
   - Dashboard on 18083

3. Create `emqx-ha-validation/etc/acl.conf` — ACL migration from Mosquitto format

4. Create `emqx-ha-validation/haproxy/haproxy.cfg` — L4 TCP passthrough

5. Create `docker-compose-emqx-ha-validation.yml` — isolated compose project:
   - Project name: `diep-emqx-ha-val`
   - Dedicated bridge network `emqx-ha-val-net`
   - 3 EMQX nodes (`emqx-ha-1/2/3`) + HAProxy (`emqx-ha-lb`)
   - Named volumes for each node's Mnesia data
   - Production `diep-mqtt` NOT started; NOT referenced

6. Bring up stack and verify cluster formation

7. Run validation scenarios (§6 below)

8. Run failure drills (§7 below)

9. Tear down: `docker compose ... down -v` — all containers and volumes removed

### 5.2 Production rollout (deferred — requires maintenance window)

1. Mirror any retained messages: use `mosquitto_sub --retained-only` → `mosquitto_pub` to
   EMQX cluster before cutover (retained messages not migrated automatically)

2. Add EMQX cluster + HAProxy to `docker-compose-ha.yml` under hostname `emqx-ha-lb`

3. Update all client services (ingestor, dispatcher, edge drivers) to set:
   - `MQTT_BROKER=emqx-ha-lb` (HAProxy hostname)
   - `MQTT_PORT=8883` (unchanged)
   - All cert env vars unchanged — same CA, same device certs

4. Soak period: run both `diep-mqtt` and `emqx-ha-lb` in parallel for ≥48 h,
   observing telemetry ingestion and command ACKs via Grafana/logs

5. Switch production: update DNS alias `diep-mqtt` to resolve to `emqx-ha-lb`
   (or update MQTT_BROKER on all services simultaneously)

6. Decommission `diep-mqtt` after soak period confirmation

---

## 6. Validation Plan

| # | Check | Method | Expected |
|---|---|---|---|
| V1 | Cluster formation | `docker exec emqx-ha-val-1 emqx eval 'mnesia:system_info(running_db_nodes)'` | 3 nodes listed |
| V2 | mTLS: valid cert → connect | paho client with `ingestor.crt` connecting to `emqx-ha-lb:8883` | CONNACK rc=0 |
| V3 | mTLS: no cert → reject | paho client with `verify=CERT_REQUIRED` but no client cert | TLS handshake failure |
| V4 | mTLS: untrusted cert → reject | Self-signed cert not from DIEP CA | TLS handshake failure |
| V5 | ACL: device pub own telemetry | INV001 cert publishes `diep/solar/INV001` | Message delivered |
| V6 | ACL: device pub other device | INV001 cert tries `diep/solar/INV900` | Disconnect |
| V7 | ACL: device pub cmd | INV001 cert tries `diep/solar/INV001/cmd` | Disconnect |
| V8 | ACL: ingestor receives telemetry | ingestor client sub `diep/+/+` receives INV001 pub | Message received |
| V9 | Telemetry flow end-to-end | device → EMQX cluster → ingestor sub | Message intact |
| V10 | DERMS command flow | dispatcher pub `diep/solar/INV001/cmd`, device receives, device pub ack, dispatcher receives ack | Full round-trip ACKED |
| V11 | Single-node failure | Stop `emqx-ha-val-1`; re-run telemetry + command flow | Continuous; reconnect <5 s |
| V12 | Leader/coordinator failure | Stop the first-started node; verify others serve traffic | Continuous |
| V13 | Node recovery | Start stopped node; verify it rejoins cluster and Mnesia | `running_db_nodes` = 3 |
| V14 | Rolling restart | Restart each node with 10 s between; measure continuity | 0 message loss |

---

## 7. Rollback Procedure

1. Production rollback: revert `MQTT_BROKER=diep-mqtt` on all services
   (original Mosquitto, same certs, same port, same ACL — unchanged throughout)
2. Drain EMQX HAProxy connections: `haproxy -sf $(pidof haproxy)` after updating backend
3. Stop EMQX cluster; volumes can be removed (no production data in validation)
4. `diep-mqtt` has been running in parallel throughout the soak period — instant fallback

---

## 8. Resource Requirements

| Component | CPU | Memory | Storage |
|---|---|---|---|
| EMQX node (×3) | 0.5–1 vCPU each | 512 MB each | ~100 MB data per node |
| HAProxy | <0.1 vCPU | 64 MB | nil |
| Total (HA MQTT stack) | ~1.5–3 vCPU | ~1.6 GB | ~300 MB |
| vs. Mosquitto | ~0.1 vCPU | ~32 MB | ~1 MB |
| **Overhead** | +~1.4–2.9 vCPU | +~1.5 GB | +~300 MB |

EMQX is significantly heavier than Mosquitto. The resource increase is justified by full
session replication, message persistence, and HA without data loss. For production, the
3 EMQX nodes can share the same host or be placed on separate hosts for true failure
domain separation.

---

## 9. Availability and Durability Summary

| Failure scenario | Mosquitto (before) | EMQX cluster (after) |
|---|---|---|
| Broker node restart | All clients disconnect; reconnect on restart; in-flight QoS 1 lost | Clients transparently route to other nodes; sessions preserved |
| Single node loss | **Full outage** | Zero impact — 2/3 nodes serve all traffic |
| Two node loss | **Full outage** | Degraded — 1/3 node continues; no data loss |
| All nodes lost | Full outage | Full outage (same) |
| Node recovery | Manual restart needed | Automatic Mnesia re-sync; no operator action |
| Rolling restart (maintenance) | Full outage per restart | Zero-downtime — other nodes absorb load |
| MQTT QoS 1 in-flight during node loss | Lost | Redelivered by cluster on reconnect |
| Session persistence across node fail | None | Full (Mnesia-replicated) |
