"""DIEP Phase 24 — Production Cutover Automation API.

Read/orchestrate endpoints for executing and validating MW2 production cutovers:

  - GET  /deployment/status            — latest cutover record + (optional) live
                                          pre-cutover posture.
  - POST /deployment/cutover/start     — begin a cutover: capture baseline, run
                                          pre-cutover validation, record the
                                          operator-attested checklist (NO
                                          destructive action).
  - POST /deployment/cutover/validate  — run post-cutover validation against an
                                          in-flight cutover, derive GO/NO-GO,
                                          persist evidence + audit trail.
  - GET  /deployment/history           — past cutovers, newest first.

All infrastructure interaction is read-only. Mutations write only to the additive
evidence tables. Cutover start/validate require admin; reads require
engineer/admin/service.
"""
from __future__ import annotations

import psycopg2
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

import deployment as deployment_service
from auth import require_role

router = APIRouter(prefix="/deployment", tags=["deployment"])

CUTOVER_ROLES = ("admin",)              # attest + execute the cutover workflow
READ_ROLES = ("engineer", "admin", "service")

_STORAGE_HINT = "deployment storage is unavailable; apply sql/023_production_cutover.sql and retry"


class ChecklistItem(BaseModel):
    item: str
    done: bool = False
    note: str | None = None


class CutoverStartRequest(BaseModel):
    change_ref: str | None = Field(default=None, description="Change ticket / window reference")
    checklist: list[ChecklistItem] = Field(default_factory=list)
    notes: str | None = None


class CutoverValidateRequest(BaseModel):
    deployment_id: str | None = Field(
        default=None,
        description="Cutover to validate; defaults to the most recent in-flight (STARTED) cutover",
    )


def _principal_name(principal) -> str:
    return getattr(principal, "name", None) or "unknown"


@router.get("/status", response_model=deployment_service.DeploymentStatusResponse)
def deployment_status(live: bool = False, principal=Depends(require_role(*READ_ROLES))):
    """Latest cutover record. With `?live=true`, also runs a fresh (read-only)
    pre-cutover validation to show current go/no-go posture."""
    try:
        latest = deployment_service.fetch_latest_deployment()
        deployment_service.refresh_prometheus_metrics()
    except psycopg2.Error:
        raise HTTPException(status_code=503, detail=_STORAGE_HINT)
    pre_now = None
    if live:
        config = deployment_service.load_deployment_config()
        pre_now, _ = deployment_service.run_pre_cutover_validation(config)
    return deployment_service.DeploymentStatusResponse(latest=latest, pre_cutover_now=pre_now)


@router.post("/cutover/start", response_model=deployment_service.DeploymentRecord)
def cutover_start(body: CutoverStartRequest, principal=Depends(require_role(*CUTOVER_ROLES))):
    """Begin a production cutover. Captures a read-only baseline, runs pre-cutover
    validation, and records the operator-attested checklist as audit events. Does
    not restart, deploy, or migrate anything."""
    config = deployment_service.load_deployment_config()
    try:
        return deployment_service.start_cutover(
            config,
            operator=_principal_name(principal),
            change_ref=body.change_ref,
            checklist=[c.model_dump() for c in body.checklist],
            notes=body.notes,
        )
    except psycopg2.Error:
        raise HTTPException(status_code=503, detail=_STORAGE_HINT)


@router.post("/cutover/validate", response_model=deployment_service.DeploymentRecord)
def cutover_validate(body: CutoverValidateRequest, principal=Depends(require_role(*CUTOVER_ROLES))):
    """Run post-cutover validation for an in-flight cutover and finalise the
    GO/NO-GO gate, score, duration, and evidence."""
    config = deployment_service.load_deployment_config()
    deployment_id = body.deployment_id
    try:
        if deployment_id is None:
            history = deployment_service.fetch_deployment_history(limit=1, status="STARTED")
            if not history.runs:
                raise HTTPException(status_code=404, detail="no in-flight cutover to validate")
            deployment_id = history.runs[0].deployment_id
        return deployment_service.validate_cutover(config, deployment_id, _principal_name(principal))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"deployment {deployment_id} not found")
    except psycopg2.Error:
        raise HTTPException(status_code=503, detail=_STORAGE_HINT)


@router.get("/history", response_model=deployment_service.DeploymentHistoryResponse)
def deployment_history(limit: int = 50, since_hours: int = 720,
                       status: deployment_service.RunStatus | None = None,
                       principal=Depends(require_role(*READ_ROLES))):
    """Historical cutover runs, newest first."""
    try:
        return deployment_service.fetch_deployment_history(
            limit=limit, since_hours=since_hours, status=status)
    except psycopg2.Error:
        raise HTTPException(status_code=503, detail=_STORAGE_HINT)
