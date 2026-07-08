"""Shared WP-009 test network fixture helpers.

Two feeders joined by a normally-open tie, mirroring the WP-008 fixture
conventions (MappedTopology rows, adms:* identifiers):

    f1 ──e1── a ──sw1── b ──e2── c(load 100 kW, 40 customers)
                        b ──tie1(open)── d
    f2 ──e3── d ──e4── e(load 50 kW, 10 customers)
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.adms_operational_state import (  # noqa: E402
    InMemoryOperationalStateRepository,
    OperationalStateService,
    StateUpdate,
)
from services.adms_operations import OperationalNetworkView  # noqa: E402
from services.adms_topology_import.mapping import MappedTopology  # noqa: E402
from services.adms_topology_services import InMemoryTopologyRepository  # noqa: E402


def node_row(node_id: str, node_type: str, **attrs) -> dict:
    return {
        "node_id": node_id,
        "node_type": node_type,
        "name": node_id,
        "latitude": 9.0,
        "longitude": 7.0,
        "nominal_kv": 11.0,
        "phases": "ABC",
        "attrs": {"external_id": node_id, "metadata": {}, **attrs},
    }


def edge_row(
    edge_id: str,
    from_node: str,
    to_node: str,
    *,
    edge_type: str = "line",
    switchable: bool = False,
    closed: bool = True,
    rating_kw: float | None = 1000.0,
) -> dict:
    return {
        "edge_id": edge_id,
        "from_node": from_node,
        "to_node": to_node,
        "edge_type": edge_type,
        "is_switchable": switchable,
        "normally_closed": closed,
        "is_closed": closed,
        "rating_kw": rating_kw,
        "phases": "ABC",
        "attrs": {"external_id": edge_id, "metadata": {}},
    }


def two_feeder_topology() -> InMemoryTopologyRepository:
    mapped = MappedTopology(
        source_system="adms-supplier-a",
        external_model_id="model-wp-009",
        external_model_version="2026.07.08",
        nodes=(
            node_row("f1", "feeder"),
            node_row("a", "bus"),
            node_row("b", "bus"),
            node_row("c", "load", base_load_kw=100.0, customer_count=40),
            node_row("f2", "feeder"),
            node_row("d", "bus"),
            node_row("e", "load", base_load_kw=50.0, customer_count=10),
        ),
        edges=(
            edge_row("e1", "f1", "a", rating_kw=1000.0),
            edge_row("sw1", "a", "b", edge_type="switch", switchable=True, rating_kw=800.0),
            edge_row("e2", "b", "c", rating_kw=500.0),
            edge_row(
                "tie1",
                "b",
                "d",
                edge_type="switch",
                switchable=True,
                closed=False,
                rating_kw=300.0,
            ),
            edge_row("e3", "f2", "d", rating_kw=1000.0),
            edge_row("e4", "d", "e", rating_kw=400.0),
        ),
    )
    return InMemoryTopologyRepository.from_mapped_topology(mapped)


def operations_stack() -> tuple[OperationalNetworkView, InMemoryOperationalStateRepository]:
    topology = two_feeder_topology()
    repository = InMemoryOperationalStateRepository()
    service = OperationalStateService(topology, repository)
    return OperationalNetworkView(topology, service), repository


def apply_update(
    repository: InMemoryOperationalStateRepository,
    *,
    update_id: str,
    asset_id: str,
    asset_kind: str,
    sequence: int,
    **fields,
) -> None:
    repository.apply(
        StateUpdate(
            update_id=update_id,
            asset_id=asset_id,
            asset_kind=asset_kind,
            sequence=sequence,
            observed_at=f"2026-07-08T10:{sequence:02d}:00Z",
            actor="scada-sim",
            **fields,
        )
    )


def fault_on_e1(repository: InMemoryOperationalStateRepository) -> None:
    """Line fault upstream of a: e1 becomes non-conducting and unavailable."""
    apply_update(
        repository,
        update_id="u-e1-fault",
        asset_id="e1",
        asset_kind="edge",
        sequence=1,
        switch_status="open",
        available=False,
        energized=False,
    )
