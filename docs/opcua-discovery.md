# OPC UA Bridge — Discovery Findings (scoping pass)

Discovery for the OPC UA bridge (`drivers/opcua/`), run before any build. Scoping
only — no production code was written for this pass. Companion to `PLANNING.md`.

## Library confirmed: `asyncua` 2.0

Installs cleanly (pulls `cryptography` and deps); `Client` + `Server` both import
and work. **No gurux-style defects** — solid foundation. Target `asyncua>=2.0`.

## Simulator used

asyncua's own **reference OPC UA server** (in-process) — a genuine OPC UA endpoint,
so connection/subscription mechanics are validated against a real server, not just
the client API surface. Prosys/open62541 remain options for vendor-realism in
later build phases (they'd need containerizing; the reference server avoids that).

## Connection + subscription mechanics — VALIDATED

Against the reference server:
- `client.connect()` (anonymous / None security) — OK
- Read a node by NodeId (`Breaker1.Status`) — OK
- **Push subscription delivered 5/5 datachanges** as the server toggled the
  breaker status — i.e. the near-real-time status/alarm push path the roadmap
  prioritizes for optimal-switching works.
- Clean unsubscribe / delete / disconnect — OK

## Findings — quirks & friction

1. **API gotcha (the one real surprise).** asyncua **2.0** made
   `Server.set_endpoint()` and `Client.get_node()` **synchronous (not
   awaitable)**. Code following 1.x docs raises
   `TypeError: object NoneType can't be used in 'await' expression`. Everything
   else (`init`, `register_namespace`, `start/stop`, `connect/disconnect`,
   `create_subscription`, `subscribe_data_change`, `read/write_value`) remains
   `async`. **Action:** write to the 2.0 surface; flag in Phase 1.
2. **Security/cert handshake = real friction.** 21 security policies present
   (NoSecurity, Basic256Sha256_Sign/SignAndEncrypt, Aes256Sha256RsaPss…);
   self-signed X.509 cert+key generation via `cryptography` works. With no server
   cert configured the server logged *"Endpoints other than open requested but
   private key and certificate are not set"* / *"No encrypting policy
   available…"* — a secured handshake needs **cert+key + mutual trusted-cert
   setup on both ends**. Dedicated phase (Phase 3), not an afterthought.
3. **Minor:** server caps session timeout (requested 3,600,000 ms → 600,000 ms) —
   reconnect/keepalive logic must account for it.

## Integration decision (recorded)

**Async-runner path chosen (option b):** add an async Runner alongside the
existing sync `Runner`, rather than wrapping asyncua in a sync executor.
Rationale: OPC UA's value here is push-based subscriptions for status/alarm
nodes; wrapping an async library in a sync executor discards native subscription
callbacks and reduces it to polling, defeating the point of choosing OPC UA.

## Build order (proposed, authorized for Phases 1–3)

- **Phase 0:** ✅ done here (asyncua 2.0 validated; `set_endpoint`-sync gotcha
  documented).
- **Phase 1:** `drivers/opcua/` skeleton (async client/driver/nodemap/selftest) +
  integration test vs the asyncua reference server.
- **Phase 2:** subscription manager (push for status/alarm, poll for
  measurements) with reconnect that re-establishes subscriptions.
- **Phase 3:** certificate-based security (X.509 mutual auth + trusted certs).
- **Phase 4 — HARD-GATED** on ami-ingest Phase 4 (pinned MQTT contract). Do not
  start even if Phases 1–3 finish first.

Discipline as ami-ingest: granular per-phase commits, stop-points for review,
flag `requirements.txt`/schema changes before making them, full pytest reporting
per phase, Phase-0 "does the library work here" gate.
