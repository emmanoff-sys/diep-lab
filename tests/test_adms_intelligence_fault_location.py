"""WP-010 OA-046 — fault location assistance tests."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from _adms_operations_fixtures import (  # noqa: E402
    apply_update,
    fault_on_e1,
    operations_stack,
)

from services.adms_operational_intelligence import (  # noqa: E402
    FaultLocationAssistanceService,
    HistoricalEvent,
)

REGION = ("a", "b", "c")


def test_faulted_segment_ranks_first_with_traceable_evidence():
    view, repository = operations_stack()
    fault_on_e1(repository)
    report = FaultLocationAssistanceService(view).analyze("outage-group:001", REGION)
    top = report.candidates[0]
    assert top.edge_id == "e1"
    assert top.confidence == 0.9
    joined = "\n".join(top.evidence)
    assert "abnormally non-conducting" in joined
    assert "unavailable" in joined
    assert "explains the observed outage exactly" in joined


def test_candidates_are_ranked_deterministically():
    view, repository = operations_stack()
    fault_on_e1(repository)
    report = FaultLocationAssistanceService(view).analyze("outage-group:001", REGION)
    assert [candidate.edge_id for candidate in report.candidates] == ["e1", "e2", "sw1", "tie1"]
    assert all(0.0 <= candidate.confidence <= 1.0 for candidate in report.candidates)


def test_normally_open_tie_is_not_treated_as_abnormal():
    view, repository = operations_stack()
    fault_on_e1(repository)
    report = FaultLocationAssistanceService(view).analyze("outage-group:001", REGION)
    tie = next(candidate for candidate in report.candidates if candidate.edge_id == "tie1")
    assert tie.confidence == 0.2
    assert not any("abnormally" in item for item in tie.evidence)


def test_historical_events_raise_confidence():
    view, repository = operations_stack()
    fault_on_e1(repository)
    history = (
        HistoricalEvent(asset_id="e1", kind="breaker_trip", observed_at="2026-07-01T00:00:00Z"),
        HistoricalEvent(asset_id="e1", kind="breaker_trip", observed_at="2026-07-05T00:00:00Z"),
    )
    report = FaultLocationAssistanceService(view, history=history).analyze(
        "outage-group:001", REGION
    )
    top = report.candidates[0]
    assert top.edge_id == "e1"
    assert top.confidence == 1.0
    assert any("historical events recorded for e1: 2" in item for item in top.evidence)


def test_feeder_impact_analysis():
    view, repository = operations_stack()
    fault_on_e1(repository)
    report = FaultLocationAssistanceService(view).analyze("outage-group:001", REGION)
    assert report.impacted_feeders == ("f1",)
    assert report.correlated_sources == ()


def test_source_correlation_flags_unhealthy_supplying_source():
    view, repository = operations_stack()
    fault_on_e1(repository)
    apply_update(
        repository,
        update_id="u-f1-loss",
        asset_id="f1",
        asset_kind="node",
        sequence=2,
        available=False,
    )
    report = FaultLocationAssistanceService(view).analyze("outage-group:001", REGION)
    assert report.correlated_sources == ("f1",)


def test_analysis_is_repeatable():
    view, repository = operations_stack()
    fault_on_e1(repository)
    service = FaultLocationAssistanceService(view)
    assert service.analyze("outage-group:001", REGION) == service.analyze(
        "outage-group:001", REGION
    )
