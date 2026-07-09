"""Shared WP-013-02 operator experience test fixtures.

Builds on the WP-009 two-feeder network fixture and adds operator
principals, tokens, and a fully wired operator stack (view service,
API, and FastAPI application) for both healthy and faulted states.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from _adms_operations_fixtures import fault_on_e1, operations_stack  # noqa: E402

from services.adms_operational_intelligence import HistoricalEvent  # noqa: E402
from services.adms_operations import (  # noqa: E402
    OperationsAuditTrail,
    OperatorDecisionSupport,
    OutageDetectionService,
)
from services.adms_operator_api import (  # noqa: E402
    OperatorApi,
    OperatorPrincipal,
    OperatorViewService,
    StaticTokenAuthenticator,
)
from services.adms_operator_ui import create_operator_experience_app  # noqa: E402

OPERATOR_TOKEN = "test-operator-token"  # noqa: S105 - synthetic test credential
VIEWER_TOKEN = "test-viewer-token"  # noqa: S105 - synthetic test credential
NO_ROLE_TOKEN = "test-no-role-token"  # noqa: S105 - synthetic test credential

OPERATOR = OperatorPrincipal(
    operator_id="op-jane", display_name="Jane Operator", roles=("operator",)
)
VIEWER = OperatorPrincipal(operator_id="view-sam", display_name="Sam Viewer", roles=("viewer",))
NO_ROLE = OperatorPrincipal(operator_id="aud-lee", display_name="Lee Auditor", roles=("finance",))

HISTORY = (HistoricalEvent(asset_id="e1", kind="breaker_trip", observed_at="2026-07-01T00:00:00Z"),)


def authenticator() -> StaticTokenAuthenticator:
    return StaticTokenAuthenticator(
        {OPERATOR_TOKEN: OPERATOR, VIEWER_TOKEN: VIEWER, NO_ROLE_TOKEN: NO_ROLE}
    )


def operator_stack(*, faulted: bool = False, seed_audit: bool = False):
    """Returns (views, repository, audit) over the two-feeder network."""
    view, repository = operations_stack()
    audit = OperationsAuditTrail()
    if faulted:
        fault_on_e1(repository)
    if seed_audit:
        group = OutageDetectionService(view).detect_all()[0]
        OperatorDecisionSupport(view, audit=audit).recommend(
            group, recorded_at="2026-07-09T12:00:00Z"
        )
    views = OperatorViewService(view, state_repository=repository, audit=audit, history=HISTORY)
    return views, repository, audit


def operator_api(*, faulted: bool = False, seed_audit: bool = False) -> OperatorApi:
    views, _, _ = operator_stack(faulted=faulted, seed_audit=seed_audit)
    return OperatorApi(views)


def experience_app(*, faulted: bool = False, seed_audit: bool = False):
    views, repository, audit = operator_stack(faulted=faulted, seed_audit=seed_audit)
    return create_operator_experience_app(views, authenticator()), repository, audit


def auth_headers(token: str = OPERATOR_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
