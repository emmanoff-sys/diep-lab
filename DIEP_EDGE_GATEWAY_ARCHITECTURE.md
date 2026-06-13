# DIEP Edge Gateway Architecture (Phase 9A)

> **Status:** Wave-1 design. No production code changed. Companion to
> `DIEP_PROTOCOL_ADAPTER_FRAMEWORK.md` (the `drivers/` SDK that runs *on* the gateway).

## 1. Role of the edge gateway

Field devices live on site LANs / serial buses / CAN and speak industrial protocols. The
DIEP platform lives centrally and speaks MQTT/Kafka/HTTP. The **edge gateway** bridges the
two: it hosts the protocol adapters (the `drivers/` SDK), normalizes readings, and ships
them to the platform over **MQTT/TLS** — providing local autonomy and store-and-forward when
the backhaul is down.

```
   ┌─────────────── Site / substation LAN ───────────────┐
   │  Meter (DLMS/Modbus)  Inverter (SunSpec)  BMS (CAN)  │
   │  EV charger (OCPP)    Microgrid RTU (IEC-104/61850)  │
   └───────────────┬──────────────────────────────────────┘
                   │ local protocols (LAN/serial/CAN/WS)
            ┌──────▼───────┐
            │ EDGE GATEWAY │  drivers/ SDK + edge_agent.py
            │  • adapters  │  • normalize → canonical schema
            │  • buffer    │  • store-and-forward (offline queue)
            │  • mTLS id   │  • local rules (optional)
            └──────┬───────┘
                   │ MQTT/TLS (mutual) + outbound only :8883
        ┌──────────▼───────────┐
        │     DIEP PLATFORM     │  broker → ingestor → API → twins/DERMS/AI
        └───────────────────────┘
```

## 2. Why edge, not direct-to-cloud

- **Protocol proximity:** Modbus/serial/CAN require LAN/bus adjacency; they don't route over WAN.
- **Resilience:** store-and-forward buffers telemetry during backhaul loss; commands degrade safely.
- **Security:** one hardened, mutually-authenticated egress per site instead of N exposed devices.
- **Scale:** a site presents as one managed gateway; fleet onboarding scales by gateway, not device.
- **Local latency:** safety/fast-loop logic (e.g. frequency response) can run locally if needed.

## 3. Hardware options — comparison

| Platform | CPU / RAM | I/O strengths | Industrial fit | Indicative cost | Best for |
|----------|-----------|---------------|----------------|-----------------|----------|
| **Raspberry Pi 5** | ARM A76 ×4 / 4–8 GB | USB, GPIO, add-on HATs (RS-485/CAN) | Consumer-grade; needs ruggedized enclosure + DIN mount | $ (low) | Pilots, telecom sites, low-cost fleets |
| **Industrial PC (x86)** | x86 ×2–8 / 8–32 GB | Multi-serial, dual NIC, wide-temp | Strong; fanless, DIN/wall mount | $$$ | Substations, demanding multi-protocol sites |
| **NVIDIA Jetson (Orin)** | ARM + GPU / 8–32 GB | USB/CSI, GPIO; **GPU for edge AI** | Moderate; needs enclosure | $$$ | Edge inference (local anomaly/vision) |
| **Siemens IOT2050** | ARM A53 ×2 / 1–2 GB | 2× isolated RS-232/485, dual Ethernet, **industrial-certified** | Excellent; DIN, wide-temp, Siemens ecosystem | $$ | Utility/industrial, IEC environments |
| **Advantech (UNO/ECU)** | x86 or ARM / 2–16 GB | Rich serial/DIO/CAN, isolation, certifications | Excellent; rugged, long lifecycle | $$–$$$ | Utility-grade microgrid/substation gateways |

**Recommendation by tier:**
- **Pilot / low cost / telecom towers:** Raspberry Pi 5 + RS-485/CAN HAT in a DIN enclosure.
- **Utility / substation / IEC 61850/104:** Siemens IOT2050 or Advantech (certified, isolated I/O, lifecycle).
- **Edge-AI sites:** Jetson Orin where local inference adds value; else it's overkill.
- **Heavy multi-protocol aggregation:** fanless Industrial PC (x86) for headroom and dual-NIC segmentation.

All run the same `drivers/` SDK (Python, containerized), so hardware choice is a deployment
decision, not a code fork.

## 4. Gateway software stack

- **Container runtime:** Docker / Podman (or k3s for fleet GitOps).
- **Edge agent:** `drivers/edge_agent.py` — config-driven; one process hosts multiple drivers.
- **Local broker (optional):** a lightweight Mosquitto on the gateway as the store-and-forward
  buffer; bridged to the platform broker so telemetry queues locally during backhaul loss.
- **Identity:** per-gateway (and per-device) X.509 client certificates for mTLS to the platform
  broker (issued by the Phase 9J PKI). No shared passwords.
- **Config & OTA:** device list + register maps delivered as versioned config; remote update
  via GitOps (k3s/Fleet) or signed config pulls.
- **Observability:** node-exporter + a heartbeat topic so the platform sees gateway health.

## 5. Connectivity & store-and-forward

- **Egress only:** the gateway dials **out** to the platform on `:8883` (MQTT/TLS); no inbound
  ports opened on site — commands arrive over the same persistent session.
- **Offline behavior:** telemetry is queued locally (local broker / disk queue) and flushed on
  reconnect; QoS 1 for commands/acks; deduplicate on `command_id`.
- **Backpressure:** cap the local queue; drop oldest non-critical telemetry first; never drop acks.

## 6. Security touchpoints (defer detail to 9J)

- Mutual TLS to the broker; per-device client certs (the SDK's `mqtt_client` already has the
  `MQTT_TLS` / `MQTT_CA_CERTS` / `MQTT_CLIENT_CERT` / `MQTT_CLIENT_KEY` hooks).
- Gateway disk encryption + secure boot where the platform supports it (IOT2050/Advantech).
- Least-privilege ACLs: a gateway may only publish/subscribe its own site's topics.
- Signed config + image provenance for OTA.

## 7. Deployment topology

- **One gateway per site** (default). Multiple gateways per large site segmented by bus/VLAN.
- **Naming:** gateway id = site id; device topics remain `diep/<domain>/<device_id>` so the
  central platform is unchanged whether data originates from a sim or a field gateway.
- **Capacity:** a Pi 5 comfortably hosts tens of Modbus/SunSpec devices; IPC/IOT2050 for
  heavier IEC/61850 or hundreds of points.

## 8. Open decisions for review

- Local broker (store-and-forward) vs. direct client buffering — recommend local broker for
  utility sites, direct buffering for cost-sensitive telecom fleets.
- Orchestration: standalone Docker per gateway vs. k3s fleet (GitOps). Recommend k3s once the
  fleet exceeds ~dozens of sites.
- Reference hardware for the pilot (Phase 9L) — recommend **Raspberry Pi 5 + RS-485/CAN HAT**
  for cost, with an Advantech/IOT2050 unit validated in parallel for the utility path.
