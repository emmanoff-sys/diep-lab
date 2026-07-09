"""Shared WP-011-02 SCADA connector test fixtures.

Builds on the two-feeder network canonical dataset and provides a
ready-to-use translator, ingestion client, and pipeline for connector
tests.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from _adms_operations_fixtures import operations_stack  # noqa: E402

from services.adms_operational_state import (  # noqa: E402
    OperationalEventProcessor,
    OperationalStateValidator,
    StateUpdateEngine,
)
from services.scada_connector import (  # noqa: E402
    AssetIdentityMap,
    ConnectorConfig,
    ConnectorLifecycle,
    ConnectorPipeline,
    IngestionClient,
    SCADAEventTranslator,
)
from services.scada_connector.harness.datasets import CANONICAL_ASSET_MAP  # noqa: E402

DEFAULT_CONFIG = ConnectorConfig(
    connector_id="test-scada-01",
    actor="test-scada-connector",
)


def asset_map(extra: dict | None = None) -> AssetIdentityMap:
    mapping = dict(CANONICAL_ASSET_MAP)
    if extra:
        mapping.update(extra)
    return AssetIdentityMap(mapping)


def make_processor(view, repository) -> OperationalEventProcessor:
    validator = OperationalStateValidator(view.topology)
    return OperationalEventProcessor(StateUpdateEngine(repository, validator))


def connector_stack():
    """Returns (view, repository, translator, ingestion_client, lifecycle)."""
    view, repository = operations_stack()
    processor = make_processor(view, repository)
    known = frozenset(
        [node.node_id for node in view.topology.nodes]
        + [edge.edge_id for edge in view.topology.edges]
    )
    identity_map = AssetIdentityMap(CANONICAL_ASSET_MAP, known_asset_ids=known)
    translator = SCADAEventTranslator(identity_map, actor=DEFAULT_CONFIG.actor)
    ingestion = IngestionClient(processor)
    lifecycle = ConnectorLifecycle(DEFAULT_CONFIG)
    return view, repository, translator, ingestion, lifecycle


def full_pipeline():
    """Returns (view, repository, pipeline)."""
    view, repository = operations_stack()
    processor = make_processor(view, repository)
    known = frozenset(
        [node.node_id for node in view.topology.nodes]
        + [edge.edge_id for edge in view.topology.edges]
    )
    identity_map = AssetIdentityMap(CANONICAL_ASSET_MAP, known_asset_ids=known)
    translator = SCADAEventTranslator(identity_map, actor=DEFAULT_CONFIG.actor)
    ingestion = IngestionClient(processor)
    pipeline = ConnectorPipeline(translator, ingestion)
    return view, repository, pipeline
