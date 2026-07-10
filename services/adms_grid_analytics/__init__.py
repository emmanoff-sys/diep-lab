"""ADMS Grid Analytics service package (WP-012-01 — Analytics Architecture Foundation).

Canonical home for the DIEP distribution-management analytics engines, migrated
from ``fastapi/dms/`` as part of the EPIC-012 architectural enablement. All
engines are pure Python functions over plain dicts — no DB, no framework, no
external dependencies — making them testable in isolation and reusable across
the platform.

Public API
----------
Service layer (preferred entry point for platform code):

    from services.adms_grid_analytics import GridAnalyticsService
    svc = GridAnalyticsService(topology_repository=..., operational_state=...)
    result = svc.estimate_state()

Engine modules (direct use in tests and one-off scripts):

    from services.adms_grid_analytics import state_estimation, powerflow, contingency

Dependency direction
--------------------
This package depends on no other services/ package at import time. The
``GridAnalyticsService`` accepts platform service objects by constructor
injection; it does not import them at module level.

Package layout
--------------
  linalg.py            — pure linear algebra (foundation for state_estimation)
  state_estimation.py  — WLS distribution state estimator (P5-M2)
  powerflow.py         — three-phase backward/forward sweep (P5-M3)
  reconfiguration.py   — optimal network reconfiguration (P5-M4)
  contingency.py       — N-1 contingency analysis (P5-M5)
  fault_location.py    — impedance + topological fault location (P5-M6)
  outage_inference.py  — AMI last-gasp outage inference (P6-M7)
  outage_validation.py — M7×M5 cross-check (P6-M8)
  crew_dispatch.py     — prioritised crew dispatch recommendation (P6-M9)
  contracts.py                  — TypedDict input/output contracts
  service.py                    — GridAnalyticsService integration adapter
  state_estimation_service.py   — StateEstimationService (WP-012-02)
"""

from __future__ import annotations

from . import (
    contingency,
    contracts,
    crew_dispatch,
    fault_location,
    linalg,
    outage_inference,
    outage_validation,
    powerflow,
    reconfiguration,
    state_estimation,
)
from .service import GridAnalyticsService
from .state_estimation_service import StateEstimationService

__all__ = [
    "GridAnalyticsService",
    "StateEstimationService",
    "contingency",
    "contracts",
    "crew_dispatch",
    "fault_location",
    "linalg",
    "outage_inference",
    "outage_validation",
    "powerflow",
    "reconfiguration",
    "state_estimation",
]
