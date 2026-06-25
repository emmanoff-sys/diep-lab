# DLMS/COSEM driver — VALIDATION CAVEAT (Phase 1)

The Phase-1 DLMS/COSEM driver (`drivers/dlms/`) is a **minimal, self-consistent
DLMS/COSEM wire profile** implemented for testing **without live meters or a
reference DLMS stack**.

## Why minimal
`gurux-dlms` 1.0.200 (the only installable PyPI version) was evaluated and
**dropped**: its server side is broken in multiple compounding ways
(`GXDLMSServer.initialize()` → `append(collection)` rejected; `handleRequest()`
calls a non-existent `GXServerReply.setReply()`; no exposed AARE generator),
and the DLMS spec / Gurux server example were unreachable from the build
environment. Rather than block Phase 1, the driver + simulator were hand-rolled
to a minimal DLMS/COSEM subset (stdlib only, no dependency).

## What is spec-shaped vs simplified
- **Correct / spec-shaped:** PDU *tags* and protocol *structure* — ACSE
  AARQ/AARE association; xDLMS GetRequest/GetResponse; logical-name (LN)
  referencing; OBIS logical names; attribute 2 = value; COSEM "Data" class id 1.
- **Simplified (NOT full BER / A-XDR):** ACSE body encoding and the scalar data
  encoding. The transport frame is a documented length-prefixed envelope, not
  the IEC 62056-46 wrapper header.

## What this means
- The Phase-1 tests/selftest prove the **client ↔ simulator** flow (association,
  OBIS round-trip, error paths) — they do **not** prove conformance to a real
  DLMS meter.
- **This driver is NOT validated against real hardware or a known-good DLMS
  stack.** Before any field or production use, the wire encoding must be
  hardened to full BER/A-XDR and validated against a target meter (or a working
  reference server / DLMS conformance tool). HDLC (SNRM/UA) transport and
  profile-generic block transfer are also still outstanding (Phase 2 / Phase 3).

## Tracking
- Decision context: the planning conversation that produced this branch
  (`feature/dlms-driver`); root cause = gurux-dlms 1.0.200 defective release.
- Follow-up: real-meter validation is a prerequisite before this driver leaves
  the lab — track as a hardening item, not assumed done.
