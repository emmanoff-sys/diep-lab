"""CIM network-domain classes: ConnectivityNode, Terminal, Transformer,
Feeder. See ../../CIM_MAPPING_GUIDE.md for why Terminal/ConnectivityNode
are synthesized rather than schema-backed.
"""
from __future__ import annotations

from dataclasses import dataclass

from .identified_object import IdentifiedObject


@dataclass(kw_only=True)
class ConnectivityNode(IdentifiedObject):
    """The topological identity of any `grid_nodes` row -- independent of
    whatever else that same row also maps to (Feeder/Transformer/etc, by
    node_type)."""
    nodeType: str | None = None
    parentMRID: str | None = None
    siteName: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    nominalKv: float | None = None
    tenantId: str | None = None


@dataclass(kw_only=True)
class Terminal(IdentifiedObject):
    """The connection point of equipment to a ConnectivityNode. No
    dedicated table backs this in the platform's schema -- synthesized two
    per `grid_edges` row (one at from_node, one at to_node) plus one per
    grid_nodes row with no edges referencing it (a leaf DER/meter still
    needs a Terminal). IDs are deterministic (see ../identifiers.py), never
    randomly generated."""
    connected: bool = True
    sequenceNumber: int = 1
    connectivityNodeMRID: str | None = None
    conductingEquipmentRef: str | None = None
    tenantId: str | None = None


@dataclass(kw_only=True)
class Transformer(IdentifiedObject):
    """Maps from `grid_nodes` rows where node_type='transformer'."""
    nominalKv: float | None = None
    siteName: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    parentMRID: str | None = None
    tenantId: str | None = None


@dataclass(kw_only=True)
class Feeder(IdentifiedObject):
    """Maps from `grid_nodes` rows where node_type='feeder'."""
    nominalKv: float | None = None
    siteName: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    tenantId: str | None = None
