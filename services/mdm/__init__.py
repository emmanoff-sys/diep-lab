"""DIEP MDM (Meter Data Management) — the canonical quality layer between AMI
acquisition and every downstream consumer (ADMS, OMS, Analytics, OPC UA, CIM).

See MDM_DESIGN.md for the architecture. Consumes contracts.TelemetryEnvelope
read-only (the AMI Ingest Phase 4 contract is frozen — see
AMI_INGEST_PHASE4_CONTRACT.md); never modifies that package.
"""
