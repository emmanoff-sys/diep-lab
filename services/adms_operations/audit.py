"""OA-042 — operational audit trail for decisions and generated plans.

Append-only in-memory trail following the WP-008 repository conventions:
monotonic sequence numbers, caller-supplied timestamps (no wall clock),
content-stable record identifiers, and full recommendation traceability
through `related_record_ids`.
"""

from __future__ import annotations

from typing import Any

from .models import DecisionKind, DecisionRecord, OperationsError


class OperationsAuditTrail:
    def __init__(self) -> None:
        self._records: list[DecisionRecord] = []
        self._by_id: dict[str, DecisionRecord] = {}

    def record(
        self,
        *,
        kind: DecisionKind,
        subject_id: str,
        actor: str,
        recorded_at: str,
        payload: dict[str, Any] | None = None,
        related_record_ids: tuple[str, ...] = (),
    ) -> DecisionRecord:
        for related in related_record_ids:
            if related not in self._by_id:
                raise OperationsError(
                    f"related record {related!r} does not exist in the audit trail"
                )
        sequence = len(self._records) + 1
        record = DecisionRecord(
            record_id=f"decision:{sequence:06d}",
            sequence=sequence,
            recorded_at=recorded_at,
            kind=kind,
            subject_id=subject_id,
            actor=actor,
            related_record_ids=tuple(related_record_ids),
            payload=dict(payload or {}),
        )
        self._records.append(record)
        self._by_id[record.record_id] = record
        return record

    def acknowledge(
        self,
        record_id: str,
        *,
        actor: str,
        recorded_at: str,
        note: str | None = None,
    ) -> DecisionRecord:
        """Operator acknowledgement of an existing decision record."""
        target = self.require(record_id)
        payload: dict[str, Any] = {"acknowledged_record": target.record_id}
        if note:
            payload["note"] = note
        return self.record(
            kind="operator_acknowledgement",
            subject_id=target.subject_id,
            actor=actor,
            recorded_at=recorded_at,
            payload=payload,
            related_record_ids=(target.record_id,),
        )

    def require(self, record_id: str) -> DecisionRecord:
        record = self._by_id.get(record_id)
        if record is None:
            raise OperationsError(f"unknown audit record {record_id!r}")
        return record

    def history(
        self,
        *,
        kind: DecisionKind | None = None,
        subject_id: str | None = None,
    ) -> tuple[DecisionRecord, ...]:
        return tuple(
            record
            for record in self._records
            if (kind is None or record.kind == kind)
            and (subject_id is None or record.subject_id == subject_id)
        )

    def trace(self, record_id: str) -> tuple[DecisionRecord, ...]:
        """Transitive closure over related records, oldest first."""
        seen: set[str] = set()
        stack = [record_id]
        while stack:
            current = self.require(stack.pop())
            if current.record_id in seen:
                continue
            seen.add(current.record_id)
            stack.extend(current.related_record_ids)
            stack.extend(
                record.record_id
                for record in self._records
                if current.record_id in record.related_record_ids
            )
        return tuple(
            sorted(
                (self._by_id[record_id] for record_id in seen),
                key=lambda record: record.sequence,
            )
        )
