"""Versioned Operator API facade for WP-013-02 (OA-061).

The v1 contract: every call returns a deterministic envelope
``{"api_version": "v1", "view": <name>, "data": ...}`` where ``data``
is the dataclass view model serialised to plain dicts/lists. Contract
stability is asserted by the WP-013-02 test suites.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from .models import API_VERSION
from .service import OperatorViewService


def _serialise(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, tuple):
        return [_serialise(item) for item in value]
    return value


class OperatorApi:
    """Read-only aggregation facade over the operator view service."""

    api_version = API_VERSION

    def __init__(self, views: OperatorViewService) -> None:
        self.views = views

    def _envelope(self, view: str, data: Any) -> dict[str, Any]:
        return {"api_version": self.api_version, "view": view, "data": _serialise(data)}

    def dashboard(self) -> dict[str, Any]:
        return self._envelope("dashboard", self.views.dashboard())

    def network(self) -> dict[str, Any]:
        return self._envelope("network", self.views.network_workspace())

    def search_assets(self, query: str) -> dict[str, Any]:
        return self._envelope("asset-search", self.views.asset_search(query))

    def asset(self, asset_id: str) -> dict[str, Any]:
        return self._envelope("asset-state", self.views.asset_state_panel(asset_id))

    def topology(self, node_id: str) -> dict[str, Any]:
        return self._envelope("topology-explorer", self.views.topology_explorer(node_id))

    def recommendations(self) -> dict[str, Any]:
        return self._envelope("recommendations", self.views.recommendations())

    def history(
        self,
        *,
        kind: str | None = None,
        subject_id: str | None = None,
        actor: str | None = None,
        text: str | None = None,
    ) -> dict[str, Any]:
        return self._envelope(
            "history",
            self.views.audit_history(kind=kind, subject_id=subject_id, actor=actor, text=text),
        )

    def recommendation_history(self) -> dict[str, Any]:
        return self._envelope("recommendation-history", self.views.recommendation_history())

    def record_trace(self, record_id: str) -> dict[str, Any]:
        return self._envelope("record-trace", self.views.record_trace(record_id))

    def timeline(self, asset_id: str | None = None) -> dict[str, Any]:
        return self._envelope("timeline", self.views.timeline(asset_id))
