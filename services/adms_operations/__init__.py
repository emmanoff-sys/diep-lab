"""Outage management and switching operations foundation for WP-009."""

from .advisory import OperatorDecisionSupport
from .audit import OperationsAuditTrail
from .detection import OutageDetectionService
from .isolation import IsolationBoundaryService
from .models import (
    DecisionRecord,
    DetectedOutage,
    IsolationBoundary,
    IsolationPoint,
    OperationsError,
    OperatorRecommendation,
    OutageGroup,
    OutageSummary,
    PreconditionResult,
    RestorationCandidate,
    SafetyAdvisory,
    SafetyEvaluation,
    SafetyRuleResult,
    SwitchingPlan,
    SwitchingStep,
)
from .restoration import RestorationCandidateService
from .state_view import OperationalNetworkView
from .switching import SwitchingPlanService

__all__ = [
    "DecisionRecord",
    "DetectedOutage",
    "IsolationBoundary",
    "IsolationBoundaryService",
    "IsolationPoint",
    "OperationalNetworkView",
    "OperationsAuditTrail",
    "OperationsError",
    "OperatorDecisionSupport",
    "OperatorRecommendation",
    "OutageDetectionService",
    "OutageGroup",
    "OutageSummary",
    "PreconditionResult",
    "RestorationCandidate",
    "RestorationCandidateService",
    "SafetyAdvisory",
    "SafetyEvaluation",
    "SafetyRuleResult",
    "SwitchingPlan",
    "SwitchingPlanService",
    "SwitchingStep",
]
