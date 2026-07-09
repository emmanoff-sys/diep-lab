"""OA-041 — operator decision support over the WP-009 analysis services.

Advisory only: composes detection, isolation, switching, and restoration
results into traceable recommendations with plain-language explanations.
Nothing here operates equipment.
"""

from __future__ import annotations

from typing import Literal

from .audit import OperationsAuditTrail
from .detection import OutageDetectionService
from .isolation import IsolationBoundaryService
from .models import (
    IsolationBoundary,
    OperatorRecommendation,
    OutageGroup,
    OutageSummary,
    RestorationCandidate,
    SafetyAdvisory,
    SwitchingPlan,
)
from .restoration import RestorationCandidateService
from .state_view import OperationalNetworkView
from .switching import SwitchingPlanService


class OperatorDecisionSupport:
    def __init__(
        self,
        view: OperationalNetworkView,
        *,
        audit: OperationsAuditTrail | None = None,
    ) -> None:
        self.view = view
        self.detection = OutageDetectionService(view)
        self.isolation = IsolationBoundaryService(view)
        self.switching = SwitchingPlanService(view)
        self.restoration = RestorationCandidateService(view)
        self.audit = audit

    def outage_summary(self, group: OutageGroup) -> OutageSummary:
        causes = tuple(
            sorted({edge for outage in group.outages for edge in outage.candidate_cause_edges})
        )
        return OutageSummary(
            subject_id=group.group_id,
            kinds=tuple(sorted({outage.kind for outage in group.outages})),
            feeder_ids=group.feeder_ids,
            affected_node_count=len(group.affected_nodes),
            customer_count=group.customer_count,
            candidate_cause_edges=causes,
        )

    def recommend(
        self,
        group: OutageGroup,
        *,
        actor: str = "decision-support",
        recorded_at: str | None = None,
    ) -> OperatorRecommendation:
        """Full advisory pipeline for one outage group.

        When an audit trail is attached and `recorded_at` is supplied, the
        recommendation and its inputs are recorded with full traceability.
        """
        summary = self.outage_summary(group)
        boundary = self.isolation.analyze(group.group_id, group.affected_nodes)
        isolation_plan = self.switching.build_isolation_plan(boundary)
        candidates = self.restoration.candidates(group.affected_nodes, boundary)
        restoration_plans = tuple(
            self.switching.build_restoration_plan(candidate, boundary) for candidate in candidates
        )

        advisories = self._advisories(group, boundary, isolation_plan, restoration_plans)
        explanations = self._explanations(
            group, boundary, isolation_plan, candidates, restoration_plans
        )

        recommendation = OperatorRecommendation(
            recommendation_id=f"recommendation:{group.group_id}",
            subject_id=group.group_id,
            summary=summary,
            isolation_plan=isolation_plan,
            restoration_candidates=candidates,
            restoration_plans=restoration_plans,
            advisories=advisories,
            explanations=explanations,
        )

        if self.audit is not None and recorded_at is not None:
            outage_record = self.audit.record(
                kind="outage_detected",
                subject_id=group.group_id,
                actor=actor,
                recorded_at=recorded_at,
                payload={
                    "kinds": list(summary.kinds),
                    "affected_nodes": list(group.affected_nodes),
                    "customer_count": group.customer_count,
                },
            )
            plan_record = self.audit.record(
                kind="plan_generated",
                subject_id=group.group_id,
                actor=actor,
                recorded_at=recorded_at,
                payload={
                    "plan_id": isolation_plan.plan_id,
                    "safe": isolation_plan.safe,
                    "steps": [step.edge_id for step in isolation_plan.steps],
                },
                related_record_ids=(outage_record.record_id,),
            )
            self.audit.record(
                kind="recommendation_issued",
                subject_id=group.group_id,
                actor=actor,
                recorded_at=recorded_at,
                payload={
                    "recommendation_id": recommendation.recommendation_id,
                    "restoration_candidates": [candidate.candidate_id for candidate in candidates],
                },
                related_record_ids=(outage_record.record_id, plan_record.record_id),
            )

        return recommendation

    def _advisories(
        self,
        group: OutageGroup,
        boundary: IsolationBoundary,
        isolation_plan: SwitchingPlan,
        restoration_plans: tuple[SwitchingPlan, ...],
    ) -> tuple[SafetyAdvisory, ...]:
        advisories: list[SafetyAdvisory] = []
        position = 0

        def add(severity: Literal["info", "caution", "warning"], message: str) -> None:
            nonlocal position
            position += 1
            advisories.append(
                SafetyAdvisory(
                    advisory_id=f"advisory:{group.group_id}:{position:02d}",
                    severity=severity,
                    message=message,
                )
            )

        if not boundary.verified:
            add(
                "warning",
                "isolation boundary could not be verified; do not attempt "
                "restoration until the region is confirmed isolated",
            )
        for failure in isolation_plan.safety.failures:
            add("warning", f"isolation plan safety rule {failure.rule_id} failed: {failure.detail}")
        for plan in restoration_plans:
            for failure in plan.safety.failures:
                add(
                    "warning",
                    f"restoration plan {plan.plan_id} safety rule "
                    f"{failure.rule_id} failed: {failure.detail}",
                )
        for diagnostic in boundary.diagnostics:
            add("caution", diagnostic)
        if not restoration_plans:
            add(
                "info",
                "no restoration path is currently available; supply "
                "returns only after fault repair",
            )
        return tuple(advisories)

    def _explanations(
        self,
        group: OutageGroup,
        boundary: IsolationBoundary,
        isolation_plan: SwitchingPlan,
        candidates: tuple[RestorationCandidate, ...],
        restoration_plans: tuple[SwitchingPlan, ...],
    ) -> tuple[str, ...]:
        lines = [
            (
                f"{len(group.affected_nodes)} node(s) across feeder(s) "
                f"{', '.join(group.feeder_ids)} are de-energised, affecting "
                f"{group.customer_count} customer(s)."
            ),
            (
                f"Isolation requires operating {len(isolation_plan.steps)} "
                f"switch(es): "
                + (
                    ", ".join(step.edge_id for step in isolation_plan.steps)
                    or "none (region already electrically isolated)"
                )
                + "."
            ),
        ]
        if boundary.verified:
            lines.append("Simulated isolation confirms the region can be de-energised.")
        else:
            lines.append(
                "Simulated isolation leaves energised nodes: "
                + ", ".join(boundary.unisolated_nodes)
                + "."
            )
        for candidate in candidates:
            capacity = "within path capacity" if candidate.capacity_ok else "EXCEEDS path capacity"
            lines.append(
                f"Restoration option {candidate.candidate_id}: close "
                f"{candidate.tie_edge_id} to supply "
                f"{len(candidate.restored_nodes)} node(s) from "
                f"{candidate.supply_feeder_id} "
                f"({candidate.restored_load_kw:g} kW, {capacity})."
            )
        if not candidates:
            lines.append("No alternative supply path exists in the current state.")
        return tuple(lines)
