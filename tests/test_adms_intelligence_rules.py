"""WP-010 OA-048 — operational rule engine tests."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.adms_operational_intelligence import (  # noqa: E402
    OperationalIntelligenceError,
    OperationalRule,
    RuleEngine,
    default_operational_rules,
)

HEALTHY_CONTEXT = {
    "plan_safe": True,
    "failed_safety_rules": (),
    "boundary_verified": True,
    "load_kw": 100.0,
    "capacity_kw": 300.0,
    "max_feeder_load_kw": 150.0,
}


def test_default_rule_set_passes_on_healthy_context():
    engine = RuleEngine(default_operational_rules())
    trace = engine.evaluate("strategy:restore:tie1:f2", HEALTHY_CONTEXT)
    assert trace.evaluation_id == "rule-evaluation:strategy:restore:tie1:f2"
    assert trace.passed is True
    assert [outcome.rule_id for outcome in trace.outcomes] == [
        "OI-R-001",
        "OI-R-002",
        "OI-R-003",
        "OI-R-004",
    ]


def test_rules_are_configurable_via_parameters():
    strict = OperationalRule(
        rule_id="OI-R-903",
        category="engineering",
        description="restored load must keep a 70 percent capacity margin",
        evaluator="capacity_margin",
        parameters={"margin_fraction": 0.7},
    )
    trace = RuleEngine((strict,)).evaluate("subject", HEALTHY_CONTEXT)
    assert trace.passed is False
    assert "exceeds capacity limit" in trace.outcomes[0].detail


def test_feeder_load_limit_rule_binds():
    rule = OperationalRule(
        rule_id="OI-R-904",
        category="recommendation",
        description="feeder load cap",
        evaluator="feeder_load_limit",
        parameters={"max_load_kw": 120.0},
    )
    trace = RuleEngine((rule,)).evaluate("subject", HEALTHY_CONTEXT)
    assert trace.passed is False
    assert trace.failures[0].rule_id == "OI-R-904"


def test_capacity_rule_not_binding_without_rating():
    engine = RuleEngine(default_operational_rules())
    context = dict(HEALTHY_CONTEXT, capacity_kw=None)
    trace = engine.evaluate("subject", context)
    outcome = next(item for item in trace.outcomes if item.rule_id == "OI-R-003")
    assert outcome.passed is True
    assert "not binding" in outcome.detail


def test_unknown_evaluator_rejected_at_construction():
    rule = OperationalRule(
        rule_id="OI-R-905",
        category="validation",
        description="broken",
        evaluator="does_not_exist",
    )
    with pytest.raises(OperationalIntelligenceError):
        RuleEngine((rule,))


def test_missing_context_key_raises_deterministically():
    engine = RuleEngine(default_operational_rules())
    with pytest.raises(OperationalIntelligenceError):
        engine.evaluate("subject", {"plan_safe": True})


def test_custom_evaluator_registration():
    def always_caution(parameters, context):
        return False, "custom rule always fails", {"marker": parameters["marker"]}

    rule = OperationalRule(
        rule_id="OI-R-906",
        category="safety",
        description="custom",
        evaluator="always_caution",
        parameters={"marker": "x1"},
    )
    trace = RuleEngine((rule,), evaluators={"always_caution": always_caution}).evaluate(
        "subject", {}
    )
    assert trace.passed is False
    assert trace.outcomes[0].evidence == {"marker": "x1"}


def test_evaluation_trace_records_evidence_inputs():
    engine = RuleEngine(default_operational_rules())
    trace = engine.evaluate("subject", HEALTHY_CONTEXT)
    capacity_outcome = next(item for item in trace.outcomes if item.rule_id == "OI-R-003")
    assert capacity_outcome.evidence["load_kw"] == 100.0
    assert capacity_outcome.evidence["capacity_kw"] == 300.0
    safety_outcome = next(item for item in trace.outcomes if item.rule_id == "OI-R-001")
    assert safety_outcome.evidence["plan_safe"] is True
