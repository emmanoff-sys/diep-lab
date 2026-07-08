"""Governed publish integration for staged ADMS topology imports.

Objective 7 integrates staged imports with the existing governed topology
publish model without adding endpoints or persistence models. The actual
publish operation is dependency-injected so this module remains unit-testable
without importing FastAPI or opening a database connection.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Protocol

from .staging import (
    STATUS_PUBLISHED,
    STATUS_READY_FOR_PUBLISH,
    STATUS_ROLLBACK_REQUESTED,
    StagedTopologyImport,
    StagingEvent,
)
from .validation import validate_topology

ERROR_CATEGORY_PUBLISH = "publish"
ESTABLISHED_CONCURRENCY_MODEL = "topology.publish_version"


@dataclass(frozen=True)
class PublishDiagnostic:
    category: str
    reason_code: str
    description: str
    offending_object: str | None = None
    location: str | None = None


class AdmsTopologyPublishError(ValueError):
    """Deterministic publish integration error."""

    def __init__(
        self,
        *,
        reason_code: str,
        description: str,
        offending_object: str | None = None,
        location: str | None = None,
    ) -> None:
        super().__init__(f"{ERROR_CATEGORY_PUBLISH}:{reason_code}: {description}")
        self.diagnostic = PublishDiagnostic(
            category=ERROR_CATEGORY_PUBLISH,
            reason_code=reason_code,
            description=description,
            offending_object=offending_object,
            location=location,
        )

    @property
    def category(self) -> str:
        return self.diagnostic.category

    @property
    def reason_code(self) -> str:
        return self.diagnostic.reason_code

    @property
    def description(self) -> str:
        return self.diagnostic.description

    @property
    def offending_object(self) -> str | None:
        return self.diagnostic.offending_object

    @property
    def location(self) -> str | None:
        return self.diagnostic.location


@dataclass(frozen=True)
class TopologyPublishPayload:
    label: str
    description: str | None
    site_name: str | None
    nodes: tuple[dict[str, Any], ...]
    edges: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class TopologyPublishResult:
    version: int
    version_row: dict[str, Any]
    nodes_written: int
    edges_written: int


class TopologyPublishGateway(Protocol):
    """Adapter boundary for the existing governed topology publish endpoint."""

    concurrency_model: str
    atomic: bool

    def publish(self, payload: TopologyPublishPayload, *, actor: str) -> TopologyPublishResult:
        """Publish via the existing governed topology publish mechanism."""


@dataclass(frozen=True)
class PublishedTopologyImport:
    staging_id: str
    published_version: int
    staged: StagedTopologyImport
    publish_result: TopologyPublishResult


def publish_staged_import(
    staged: StagedTopologyImport,
    gateway: TopologyPublishGateway,
    *,
    actor: str,
    label: str | None = None,
    description: str | None = None,
    site_name: str | None = None,
) -> PublishedTopologyImport:
    """Publish a ready staged import through the governed publish gateway."""

    _require_ready_for_publish(staged)
    _verify_gateway(gateway)
    validate_topology(staged.topology).raise_if_invalid()

    payload = build_publish_payload(
        staged,
        actor=actor,
        label=label,
        description=description,
        site_name=site_name,
    )
    result = gateway.publish(payload, actor=actor)
    _verify_publish_result(staged, result)
    published = _mark_published(staged, result.version, actor=actor)
    return PublishedTopologyImport(
        staging_id=staged.staging_id,
        published_version=result.version,
        staged=published,
        publish_result=result,
    )


def build_publish_payload(
    staged: StagedTopologyImport,
    *,
    actor: str,
    label: str | None = None,
    description: str | None = None,
    site_name: str | None = None,
) -> TopologyPublishPayload:
    """Build the payload shape consumed by the governed topology publish endpoint."""

    audit_metadata = {
        "adms_staging_id": staged.staging_id,
        "adms_publish_actor": actor,
        "adms_external_model_id": staged.topology.external_model_id,
        "adms_external_model_version": staged.topology.external_model_version,
    }
    nodes = tuple(_with_audit_metadata(node, audit_metadata) for node in staged.topology.nodes)
    edges = tuple(_with_audit_metadata(edge, audit_metadata) for edge in staged.topology.edges)
    resolved_label = label or (
        f"adms-{staged.topology.source_system}-"
        f"{staged.topology.external_model_id}-{staged.topology.external_model_version}"
    )
    return TopologyPublishPayload(
        label=resolved_label,
        description=description or f"ADMS staged import {staged.staging_id}",
        site_name=site_name,
        nodes=nodes,
        edges=edges,
    )


def build_rollback_publish_metadata(staged: StagedTopologyImport, *, actor: str) -> dict[str, Any]:
    """Return rollback coordination metadata for the existing publish mechanism."""

    if staged.status != STATUS_ROLLBACK_REQUESTED:
        _raise(
            "rollback_not_requested",
            "Rollback publish metadata requires rollback_requested staging status",
            offending_object=staged.staging_id,
            location="status",
        )
    return {
        "adms_staging_id": staged.staging_id,
        "adms_rollback_actor": actor,
        "adms_rollback_reason": staged.rollback_reason,
        "adms_rollback_target_version": staged.rollback_target_version,
        "adms_external_model_id": staged.topology.external_model_id,
        "adms_external_model_version": staged.topology.external_model_version,
    }


def _with_audit_metadata(row: dict[str, Any], audit_metadata: dict[str, Any]) -> dict[str, Any]:
    attrs = dict(row.get("attrs") or {})
    attrs.update(audit_metadata)
    return {**row, "attrs": attrs}


def _require_ready_for_publish(staged: StagedTopologyImport) -> None:
    if staged.status != STATUS_READY_FOR_PUBLISH:
        _raise(
            "staging_not_ready_for_publish",
            "Staged topology must be ready_for_publish before governed publish",
            offending_object=staged.staging_id,
            location="status",
        )


def _verify_gateway(gateway: TopologyPublishGateway) -> None:
    if getattr(gateway, "concurrency_model", None) != ESTABLISHED_CONCURRENCY_MODEL:
        _raise(
            "unsupported_concurrency_model",
            "Publish gateway must use the established topology publish advisory-lock model",
            offending_object=str(getattr(gateway, "concurrency_model", None)),
            location="gateway.concurrency_model",
        )
    if getattr(gateway, "atomic", None) is not True:
        _raise(
            "non_atomic_publish_gateway",
            "Publish gateway must provide single-transaction publish semantics",
            offending_object=str(getattr(gateway, "atomic", None)),
            location="gateway.atomic",
        )


def _verify_publish_result(
    staged: StagedTopologyImport,
    result: TopologyPublishResult,
) -> None:
    if result.version < 1:
        _raise(
            "invalid_published_version",
            "Publish gateway returned an invalid topology version",
            offending_object=str(result.version),
            location="publish_result.version",
        )
    if result.nodes_written != len(staged.topology.nodes):
        _raise(
            "node_write_count_mismatch",
            "Publish gateway node write count does not match staged topology",
            offending_object=str(result.nodes_written),
            location="publish_result.nodes_written",
        )
    if result.edges_written != len(staged.topology.edges):
        _raise(
            "edge_write_count_mismatch",
            "Publish gateway edge write count does not match staged topology",
            offending_object=str(result.edges_written),
            location="publish_result.edges_written",
        )
    if result.version_row.get("version") != result.version:
        _raise(
            "version_row_mismatch",
            "Publish gateway version row does not match returned version",
            offending_object=str(result.version_row.get("version")),
            location="publish_result.version_row.version",
        )


def _mark_published(
    staged: StagedTopologyImport,
    version: int,
    *,
    actor: str,
) -> StagedTopologyImport:
    event = StagingEvent(
        from_status=staged.status,
        to_status=STATUS_PUBLISHED,
        reason=f"published_version:{version}",
        actor=actor,
    )
    return replace(staged, status=STATUS_PUBLISHED, lifecycle=(*staged.lifecycle, event))


def _raise(
    reason_code: str,
    description: str,
    *,
    offending_object: str | None = None,
    location: str | None = None,
) -> None:
    raise AdmsTopologyPublishError(
        reason_code=reason_code,
        description=description,
        offending_object=offending_object,
        location=location,
    )
