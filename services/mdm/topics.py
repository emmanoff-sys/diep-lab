"""MDM's own topic naming for the trusted output stream.

Deliberately NOT added to contracts/topics.py — that package is frozen this
phase (AMI_INGEST_PHASE4_CONTRACT.md is the AMI Ingest contract; MDM's output
topic is MDM's own concern, layered on top, not a change to the AMI contract
itself). Input-side, MDM subscribes to the existing contracts-defined
telemetry wildcard (config.py:TELEMETRY_TOPIC) — that doesn't need a new
builder, it's already `diep/+/+`.
"""
from __future__ import annotations

from .config import Settings


def build_trusted_topic(domain: str, device_id: str) -> str:
    return f"diep/{domain}/{device_id}/{Settings.TRUSTED_TOPIC_SUFFIX}"
