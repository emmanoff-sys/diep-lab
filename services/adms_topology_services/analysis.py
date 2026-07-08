"""Electrical path analysis services."""

from __future__ import annotations

from dataclasses import dataclass

from .graph import ConnectivityGraph, PathResult
from .repository import InMemoryTopologyRepository


@dataclass(frozen=True)
class ElectricalPathAnalysis:
    source_node: str
    target_node: str
    primary_path: PathResult
    alternate_paths: tuple[PathResult, ...]
    loop_detected: bool


class ElectricalPathAnalysisService:
    def __init__(self, repository: InMemoryTopologyRepository) -> None:
        self.repository = repository
        self.graph = ConnectivityGraph(repository)

    def analyze_path(
        self,
        source_node: str,
        target_node: str,
        *,
        max_alternate_paths: int = 3,
    ) -> ElectricalPathAnalysis:
        primary = self.graph.shortest_path(source_node, target_node)
        alternates = self._alternate_paths(
            source_node,
            target_node,
            primary,
            max_alternate_paths=max_alternate_paths,
        )
        return ElectricalPathAnalysis(
            source_node=source_node,
            target_node=target_node,
            primary_path=primary,
            alternate_paths=alternates,
            loop_detected=self.graph.has_cycles(),
        )

    def _alternate_paths(
        self,
        source_node: str,
        target_node: str,
        primary: PathResult,
        *,
        max_alternate_paths: int,
    ) -> tuple[PathResult, ...]:
        alternates: list[PathResult] = []
        seen = {primary.edges} if primary.exists else set()
        for edge_id in primary.edges:
            alternate = self.graph.shortest_path(
                source_node,
                target_node,
                blocked_edges=frozenset({edge_id}),
            )
            if alternate.exists and alternate.edges not in seen:
                alternates.append(alternate)
                seen.add(alternate.edges)
            if len(alternates) >= max_alternate_paths:
                break
        return tuple(alternates)
