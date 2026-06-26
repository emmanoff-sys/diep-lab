"""MDM Quality Engine tests — "never silently overwrite" + estimated/measured
propagation (PLANNING.md §3 cross-layer contract)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from contracts import Measurement, Quality
from services.mdm.quality import QualityAssessor, REASON_NON_FINITE, REASON_OUT_OF_RANGE


def test_good_in_range_value_unchanged():
    m = Measurement(measurement_type="voltage", unit="V", value=230.0, quality=Quality.GOOD)
    new, transition = QualityAssessor().assess(m)
    assert new.quality is Quality.GOOD
    assert transition is None


def test_out_of_range_escalated_from_good():
    m = Measurement(measurement_type="frequency", unit="Hz", value=999.0, quality=Quality.GOOD)
    new, transition = QualityAssessor().assess(m)
    assert new.quality is Quality.OUT_OF_RANGE
    assert transition is not None
    assert transition.reason == REASON_OUT_OF_RANGE
    assert transition.original_quality is Quality.GOOD
    assert transition.new_quality is Quality.OUT_OF_RANGE


def test_non_finite_value_escalated_to_invalid():
    m = Measurement(measurement_type="voltage", unit="V", value=float("nan"), quality=Quality.GOOD)
    new, transition = QualityAssessor().assess(m)
    assert new.quality is Quality.INVALID
    assert transition.reason == REASON_NON_FINITE


@pytest.mark.parametrize("preset_quality", [
    Quality.ESTIMATED, Quality.SUBSTITUTED, Quality.INVALID, Quality.MISSING,
    Quality.COMMUNICATION_FAILURE, Quality.OUT_OF_RANGE, Quality.DUPLICATE,
])
def test_never_silently_overwrites_a_non_good_flag(preset_quality):
    """Even an out-of-range value must NOT be re-flagged if the driver
    already assigned a non-GOOD quality — MDM only ever escalates from GOOD."""
    m = Measurement(measurement_type="frequency", unit="Hz", value=999.0, quality=preset_quality)
    new, transition = QualityAssessor().assess(m)
    assert new.quality is preset_quality
    assert transition is None


def test_estimated_quality_keeps_estimated_flag_true():
    m = Measurement(measurement_type="power_kw", unit="kW", value=1.0, quality=Quality.ESTIMATED)
    new, _ = QualityAssessor().assess(m)
    assert new.estimated is True
    assert new.quality is Quality.ESTIMATED  # untouched, not re-escalated


def test_custom_range_limits_respected():
    assessor = QualityAssessor(range_limits={"custom_field": (0.0, 10.0)})
    m = Measurement(measurement_type="custom_field", unit="x", value=11.0, quality=Quality.GOOD)
    new, transition = assessor.assess(m)
    assert new.quality is Quality.OUT_OF_RANGE
    assert transition is not None
