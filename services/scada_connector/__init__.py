"""SCADA Integration Framework for WP-011-02."""

from .framework import (
    AbstractConnectorSession,
    ConnectorConfig,
    ConnectorHealth,
    ConnectorLifecycle,
    ConnectorRegistry,
    SCADAConnectorError,
    SessionContext,
)
from .ingestion import IngestionClient, IngestionResult, TLSContext
from .metrics import SCADAConnectorMetrics
from .observability import ConnectorHealthServer, start_connector_health_server
from .reliability import (
    ConnectorPipeline,
    DeadLetterQueue,
    DeadLetterRecord,
    EventBuffer,
    ExponentialBackoff,
    PipelineResult,
)
from .translation import (
    AssetIdentityMap,
    SCADAEventTranslator,
    SCADAMessage,
    TranslationResult,
)

__all__ = [
    "AbstractConnectorSession",
    "AssetIdentityMap",
    "ConnectorConfig",
    "ConnectorHealth",
    "ConnectorHealthServer",
    "ConnectorLifecycle",
    "ConnectorPipeline",
    "ConnectorRegistry",
    "DeadLetterQueue",
    "DeadLetterRecord",
    "EventBuffer",
    "ExponentialBackoff",
    "IngestionClient",
    "IngestionResult",
    "PipelineResult",
    "SCADAConnectorError",
    "SCADAConnectorMetrics",
    "SCADAEventTranslator",
    "SCADAMessage",
    "SessionContext",
    "TLSContext",
    "TranslationResult",
    "start_connector_health_server",
]
