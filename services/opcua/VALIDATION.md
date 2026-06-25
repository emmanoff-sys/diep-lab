# OPC UA Connector — VALIDATION CAVEAT (Phases 1–3)

Mirrors `drivers/dlms/VALIDATION.md`'s structure: this is an explicit record
of what is real vs. faked vs. genuinely unverified in this build, so nobody
downstream mistakes "tests pass" for "validated against a real OPC UA
server."

## What is genuinely real (not faked, not mocked)

- **Certificate/trust-store logic (`security.py`)** uses the real
  `cryptography` library, which *is* installed in this dev environment
  (unlike `asyncua`). Self-signed cert generation, PEM loading, expiry
  computation, mtime-based reload detection, and trust-store fingerprint
  matching are all exercised against real X.509 certificates — these tests
  would catch a real bug (and one did get caught: an initial
  `x509.URI(...)` call should have been `x509.UniformResourceIdentifier(...)`
  — `cryptography` has no `URI` attribute; fixed before commit).
- **`mapping.py`** (YAML parsing/validation), **`measurement.py`** (build/
  validate/sink), **`browse_cache.py`** (TTL logic), **`metrics.py`**'s NoOp
  fallback, and **`health.py`**'s stdlib HTTP server are pure
  Python/stdlib/PyYAML — no faking involved, fully real.

## What is real orchestration logic, exercised against a fake asyncua surface

`asyncua` is **not installed** in this dev environment (`ModuleNotFoundError`
on `import asyncua`) — confirmed by attempting `python3 -m pip install
asyncua`, which fails because `pip` itself isn't available here (see
`project_dlms_test_env_gap` memory; same environment gap as the rest of this
branch). Phase 0's discovery pass (`docs/opcua-discovery.md`) *did* install
and validate `asyncua` 2.0 live against its own reference server, in
whatever environment ran that pass — this one does not have it.

So `client.py` and `subscription.py`'s asyncua-facing calls
(`Client.connect()`, `get_node()`, `create_subscription()`,
`subscribe_data_change()`, `get_namespace_array()`,
`connect_and_get_server_endpoints()`, `set_security_string()`, the
`SubHandler.datachange_notification(node, val, data)` callback shape) are
written to the **documented 2.0 API surface** (and to Phase 0's specific
finding that `get_node`/`set_endpoint` are synchronous in 2.0) — they are
**not independently re-verified against the real library here**. Every test
that touches this surface injects a hand-written fake `Client`/
`Subscription`/`Node` shaped to that documented API via the constructor's
`client_factory` parameter, and asserts on `OpcUaConnection`'s/
`SubscriptionManager`'s *own* logic: backoff math, namespace-URI resolution,
reconnect-driven resubscription, security-string construction, DataChange →
`InternalMeasurement` conversion, session-renewal-failure → reconnect wiring.

**One piece is explicitly best-effort, by design:** `_build_filter()` in
`subscription.py` (deadband construction via `ua.DataChangeFilter`) is
wrapped in a try/except that logs and subscribes without a filter on any
mismatch — since asyncua isn't installed, every test run actually exercises
that fallback path (confirmed in the verification run below), not the
real filter construction. If `ua.DataChangeFilter`/`ua.DeadbandType`'s real
shape differs from what's written, deadband silently becomes a no-op rather
than breaking subscriptions — by design, but worth re-checking once asyncua
is installed somewhere.

## Test verification (same constraint as the rest of this branch)

This shell has no `pytest` (confirmed: `ModuleNotFoundError`, and `pip`
itself isn't installed either, so it can't be added). Unlike the MDM phase's
verification (which only ported test *assertions* into a standalone script),
this phase's `tests/test_opcua_*.py` files were **directly executed** — not
reimplemented — via a throwaway runner script (not committed; built for this
verification pass only) that fakes just enough of `pytest` (`raises`,
`monkeypatch`, `tmp_path`) to import and call every `test_*` function in each
file. Result: **60 of 60 test functions passed**, executing the actual test
code, not a parallel reimplementation of its assertions. A second, broader
throwaway smoke script (42 checks) cross-checked the same modules end-to-end
including the real-`cryptography` certificate path.

One real bug was caught and fixed by this run: `security.py`'s
self-signed-cert generation called a nonexistent `cryptography.x509.URI`;
fixed to `x509.UniformResourceIdentifier` before commit.

## What this means going into a real deployment

- **Before pointing this at a real OPC UA server, even an open/unsecured
  one:** re-run against `asyncua`'s own reference server (the same one Phase
  0 used) with `asyncua` actually installed, the way Phase 0 did, to confirm
  the documented API surface this code was written against still matches
  reality across `connect`, `subscribe_data_change`, and the DataChange
  callback shape.
- **Before enabling `Basic256Sha256` against a real secured server:** the
  cert/trust-store mechanics are genuinely tested, but the *handshake itself*
  (asyncua's consumption of `set_security_string()`, and the server's
  acceptance of this connector's self-signed cert) is the one thing Phase 0
  flagged as "real friction" and this phase did not re-exercise live.
- **Deadband filters:** confirm `_build_filter()`'s try path actually
  succeeds (not just its except fallback) once asyncua is installed —
  currently unverified in either direction.

## Tracking

Same branch, same root constraint as `drivers/dlms/VALIDATION.md`: this dev
environment has no working `pip`, so no OPC UA library — real or
reference-server — can be installed here to close this gap directly.
Hardware/live-server validation is a prerequisite before this connector
leaves the lab, not assumed done.
