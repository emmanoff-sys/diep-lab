"""WP-009 OA-037 — outage detection service tests."""

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

from services.adms_operations import OutageDetectionService  # noqa: E402


def test_healthy_network_reports_no_outages():
    view, _ = operations_stack()
    detection = OutageDetectionService(view)
    assert detection.detect_loss_of_supply() == ()
    assert detection.detect_source_loss() == ()
    assert detection.identify_feeder_outages() == ()
    assert detection.detect_all() == ()


def test_loss_of_supply_is_one_outage_per_dark_component():
    view, repository = operations_stack()
    fault_on_e1(repository)
    outages = OutageDetectionService(view).detect_loss_of_supply()
    assert len(outages) == 1
    outage = outages[0]
    assert outage.outage_id == "outage:loss_of_supply:f1:a"
    assert outage.kind == "loss_of_supply"
    assert outage.feeder_id == "f1"
    assert outage.affected_nodes == ("a", "b", "c")
    assert outage.customer_count == 40


def test_open_tie_does_not_attribute_outage_to_backup_feeder():
    view, repository = operations_stack()
    fault_on_e1(repository)
    outages = OutageDetectionService(view).detect_loss_of_supply()
    assert [outage.feeder_id for outage in outages] == ["f1"]


def test_candidate_causes_include_only_non_conducting_edges():
    view, repository = operations_stack()
    fault_on_e1(repository)
    outages = OutageDetectionService(view).detect_loss_of_supply()
    causes = outages[0].candidate_cause_edges
    assert "e1" in causes
    assert "tie1" in causes  # open tie borders the dark region
    assert "sw1" not in causes  # conducting edges are never causes


def test_source_loss_detected_when_feeder_unhealthy():
    view, repository = operations_stack()
    apply_update(
        repository,
        update_id="u-f1-loss",
        asset_id="f1",
        asset_kind="node",
        sequence=1,
        available=False,
    )
    outages = OutageDetectionService(view).detect_source_loss()
    assert len(outages) == 1
    assert outages[0].kind == "source_loss"
    assert outages[0].feeder_id == "f1"
    assert outages[0].outage_id == "outage:source_loss:f1"
    assert outages[0].affected_nodes == ("a", "b", "c", "f1")


def test_feeder_outage_identified_when_all_nodes_dark():
    view, repository = operations_stack()
    fault_on_e1(repository)
    apply_update(
        repository,
        update_id="u-e3-fault",
        asset_id="e3",
        asset_kind="edge",
        sequence=2,
        switch_status="open",
        available=False,
    )
    outages = OutageDetectionService(view).identify_feeder_outages()
    assert {outage.feeder_id for outage in outages} == {"f1", "f2"}
    assert all(outage.kind == "feeder_outage" for outage in outages)


def test_source_loss_groups_with_its_dark_component():
    view, repository = operations_stack()
    apply_update(
        repository,
        update_id="u-f1-loss",
        asset_id="f1",
        asset_kind="node",
        sequence=1,
        available=False,
    )
    groups = OutageDetectionService(view).detect_all()
    assert len(groups) == 1
    group = groups[0]
    assert {outage.kind for outage in group.outages} == {"loss_of_supply", "source_loss"}
    assert group.feeder_ids == ("f1",)
    assert group.affected_nodes == ("a", "b", "c", "f1")


def test_grouping_keeps_disjoint_outages_separate():
    view, repository = operations_stack()
    detection = OutageDetectionService(view)
    fault_on_e1(repository)
    apply_update(
        repository,
        update_id="u-e4-fault",
        asset_id="e4",
        asset_kind="edge",
        sequence=2,
        switch_status="open",
        available=False,
    )
    groups = detection.detect_all()
    regions = sorted(group.affected_nodes for group in groups)
    assert regions == [("a", "b", "c"), ("e",)]
    assert [group.group_id for group in groups] == [
        "outage-group:001",
        "outage-group:002",
    ]
    feeders = sorted(group.feeder_ids for group in groups)
    assert feeders == [("f1",), ("f2",)]


def test_detection_is_deterministic():
    view, repository = operations_stack()
    fault_on_e1(repository)
    detection = OutageDetectionService(view)
    assert detection.detect_all() == detection.detect_all()
