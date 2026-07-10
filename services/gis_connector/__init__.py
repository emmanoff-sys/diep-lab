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
from .metrics import GISConnectorMetrics
from .reconciliation import ReconciliationItem, ReconciliationReport, TopologyReconciler
from .reliability import (
    DeadLetterQueue,
    DeadLetterRecord,
    ExponentialBackoff,
    GISConnectorPipeline,
    GISPipelineResult,
    GISTopologyBuffer,
)
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
    "DeadLetterQueue",
    "DeadLetterRecord",
    "ExponentialBackoff",
    "GISAssetIdentityMap",
    "GISConnectorError",
    "GISConnectorMetrics",
    "GISConnectorPipeline",
    "GISConnectorSession",
    "GISEdgeFeature",
    "GISFeatureRejection",
    "GISNodeFeature",
    "GISPipelineResult",
    "GISTopologyBatch",
    "GISTopologyBuffer",
    "GISTopologyTranslator",
    "GISTranslationResult",
    "ReconciliationItem",
    "ReconciliationReport",
    "SCADAConnectorError",
    "SessionContext",
    "TopologyReconciler",
]
