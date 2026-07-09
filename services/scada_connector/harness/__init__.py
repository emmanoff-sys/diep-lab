"""OA-079 — integration test harness (WP-011-01 OA-073 implementation).

Contract validators, deterministic stubs, canonical datasets, and replay
capability for all EPIC-011 connector test suites.
"""

from .contracts import (
    validate_historical_event,
    validate_mapped_topology,
    validate_operational_event,
)
from .datasets import (
    CANONICAL_FAULT_EVENT,
    TWO_FEEDER_TOPOLOGY,
    make_scada_messages,
)
from .replay import SessionRecorder, SessionReplayer
from .stubs import GisStub, OmsStub, ScadaStub

__all__ = [
    "CANONICAL_FAULT_EVENT",
    "TWO_FEEDER_TOPOLOGY",
    "GisStub",
    "OmsStub",
    "ScadaStub",
    "SessionRecorder",
    "SessionReplayer",
    "make_scada_messages",
    "validate_historical_event",
    "validate_mapped_topology",
    "validate_operational_event",
]
