"""GIS Topology Adapter for WP-011-03."""

from .framework import (
    ConnectorConfig,
    ConnectorHealth,
    ConnectorLifecycle,
    ConnectorRegistry,
    GISConnectorError,
    GISConnectorSession,
    SCADAConnectorError,
    SessionContext,
)
from .identity import GISAssetIdentityMap
from .reconciliation import ReconciliationItem, ReconciliationReport, TopologyReconciler
from .translation import (
    GISEdgeFeature,
    GISFeatureRejection,
    GISNodeFeature,
    GISTopologyBatch,
    GISTopologyTranslator,
    GISTranslationResult,
)

__all__ = [
    "ConnectorConfig",
    "ConnectorHealth",
    "ConnectorLifecycle",
    "ConnectorRegistry",
    "GISAssetIdentityMap",
    "GISConnectorError",
    "GISConnectorSession",
    "GISEdgeFeature",
    "GISFeatureRejection",
    "GISNodeFeature",
    "GISTopologyBatch",
    "GISTopologyTranslator",
    "GISTranslationResult",
    "ReconciliationItem",
    "ReconciliationReport",
    "SCADAConnectorError",
    "SessionContext",
    "TopologyReconciler",
]
