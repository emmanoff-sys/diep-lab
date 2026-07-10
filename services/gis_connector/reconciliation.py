"""OA-085 — topology reconciliation.

Produces deterministic reconciliation reports comparing an imported
MappedTopology against the existing known asset inventory. Advisory
only — no automatic correction is performed or authorised.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from services.adms_topology_import.mapping import MappedTopology

ReconciliationKind = Literal[
    "new_asset",
    "missing_asset",
    "attribute_diff",
    "connectivity_issue",
    "duplicate_id",
    "mapping_ambiguity",
    "operator_review",
]


@dataclass(frozen=True)
class ReconciliationItem:
    kind: ReconciliationKind
    asset_id: str
    detail: str


@dataclass(frozen=True)
class ReconciliationReport:
    model_id: str
    model_version: str
    import_count_nodes: int
    import_count_edges: int
    existing_count_nodes: int
    existing_count_edges: int
    items: tuple[ReconciliationItem, ...]

    @property
    def advisory_only(self) -> bool:
        return True

    def by_kind(self, kind: ReconciliationKind) -> tuple[ReconciliationItem, ...]:
        return tuple(item for item in self.items if item.kind == kind)

    @property
    def requires_operator_review(self) -> bool:
        return any(item.kind == "operator_review" for item in self.items)


class TopologyReconciler:
    """Compares imported MappedTopology against the existing asset inventory.

    Every result is advisory only — the reconciliation report is a
    read-only diff produced for operator review. No correction is made
    to either the imported topology or the existing model. Per OA-085.
    """

    def reconcile(
        self,
        imported: MappedTopology,
        existing_nodes: frozenset[str],
        existing_edges: frozenset[str],
    ) -> ReconciliationReport:
        imported_node_ids = [n["node_id"] for n in imported.nodes]
        imported_edge_ids = [e["edge_id"] for e in imported.edges]
        imported_node_set = frozenset(imported_node_ids)
        imported_edge_set = frozenset(imported_edge_ids)

        items: list[ReconciliationItem] = []
        items.extend(self._find_duplicates(imported_node_ids, "node_id"))
        items.extend(self._find_duplicates(imported_edge_ids, "edge_id"))
        items.extend(self._new_assets(imported_node_set, existing_nodes, "node"))
        items.extend(self._new_assets(imported_edge_set, existing_edges, "edge"))
        items.extend(self._missing_assets(existing_nodes, imported_node_set, "node"))
        items.extend(self._missing_assets(existing_edges, imported_edge_set, "edge"))
        items.extend(self._connectivity_issues(imported.edges, imported_node_set | existing_nodes))

        new_count = sum(1 for i in items if i.kind == "new_asset")
        if new_count:
            items.append(
                ReconciliationItem(
                    kind="operator_review",
                    asset_id="",
                    detail=(
                        f"{new_count} new asset(s) require operator review "
                        "before topology promotion"
                    ),
                )
            )

        return ReconciliationReport(
            model_id=imported.external_model_id,
            model_version=imported.external_model_version,
            import_count_nodes=len(imported_node_ids),
            import_count_edges=len(imported_edge_ids),
            existing_count_nodes=len(existing_nodes),
            existing_count_edges=len(existing_edges),
            items=tuple(items),
        )

    @staticmethod
    def _find_duplicates(ids: list[str], label: str) -> list[ReconciliationItem]:
        seen: set[str] = set()
        result: list[ReconciliationItem] = []
        for asset_id in ids:
            if asset_id in seen:
                result.append(
                    ReconciliationItem(
                        kind="duplicate_id",
                        asset_id=asset_id,
                        detail=f"{label} '{asset_id}' appears more than once in import",
                    )
                )
            seen.add(asset_id)
        return result

    @staticmethod
    def _new_assets(
        imported: frozenset[str], existing: frozenset[str], kind: str
    ) -> list[ReconciliationItem]:
        return [
            ReconciliationItem(
                kind="new_asset",
                asset_id=asset_id,
                detail=f"{kind} '{asset_id}' not present in existing topology",
            )
            for asset_id in sorted(imported - existing)
        ]

    @staticmethod
    def _missing_assets(
        existing: frozenset[str], imported: frozenset[str], kind: str
    ) -> list[ReconciliationItem]:
        return [
            ReconciliationItem(
                kind="missing_asset",
                asset_id=asset_id,
                detail=(f"{kind} '{asset_id}' present in existing topology but absent from import"),
            )
            for asset_id in sorted(existing - imported)
        ]

    @staticmethod
    def _connectivity_issues(
        edges: tuple[Any, ...], all_node_ids: frozenset[str]
    ) -> list[ReconciliationItem]:
        result: list[ReconciliationItem] = []
        for edge in edges:
            for endpoint, label in (
                (edge["from_node"], "from_node"),
                (edge["to_node"], "to_node"),
            ):
                if endpoint not in all_node_ids:
                    result.append(
                        ReconciliationItem(
                            kind="connectivity_issue",
                            asset_id=edge["edge_id"],
                            detail=f"{label} '{endpoint}' not found in node inventory",
                        )
                    )
        return result
