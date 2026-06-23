-- Phase 24 — Production Cutover Automation.
--
-- Additive only: persists production-cutover deployment runs and their audit
-- trail without touching any existing operational tables. Builds on the MW2
-- readiness verification (sql/022_platform_readiness.sql); a cutover run links
-- to the readiness assessment captured at pre-cutover time via readiness_run_id.

CREATE TABLE IF NOT EXISTS platform_deployment_runs (
    deployment_id     UUID PRIMARY KEY,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at      TIMESTAMPTZ,
    -- lifecycle: STARTED -> VALIDATED|FAILED|ROLLED_BACK
    status            TEXT NOT NULL DEFAULT 'STARTED'
                      CHECK (status IN ('STARTED', 'VALIDATED', 'FAILED', 'ROLLED_BACK')),
    -- gate posture, derived from the post-cutover validation: GO when every
    -- critical check passes and validation_score >= pass_threshold, else NO-GO.
    deployment_status TEXT NOT NULL DEFAULT 'IN_PROGRESS'
                      CHECK (deployment_status IN ('IN_PROGRESS', 'GO', 'NO_GO')),
    operator          TEXT NOT NULL,
    change_ref        TEXT,
    validation_score  INT CHECK (validation_score IS NULL OR (validation_score >= 0 AND validation_score <= 100)),
    pass_threshold    INT NOT NULL DEFAULT 90 CHECK (pass_threshold >= 0 AND pass_threshold <= 100),
    duration_seconds  DOUBLE PRECISION,
    readiness_run_id  UUID,             -- links to platform_readiness_reports.run_id (best-effort; not FK-enforced)
    baseline          JSONB NOT NULL DEFAULT '{}'::jsonb,  -- captured system baseline snapshot
    pre_cutover       JSONB NOT NULL DEFAULT '{}'::jsonb,  -- pre-cutover validation result
    post_cutover      JSONB NOT NULL DEFAULT '{}'::jsonb,  -- post-cutover validation result
    evidence          JSONB NOT NULL DEFAULT '{}'::jsonb,  -- collected evidence (reports, snapshots, checklist)
    source            TEXT NOT NULL DEFAULT 'api',
    tenant_id         VARCHAR(50) NOT NULL DEFAULT 'default' REFERENCES tenants(tenant_id)
);

CREATE INDEX IF NOT EXISTS platform_deployment_runs_started_at_idx
    ON platform_deployment_runs (started_at DESC);
CREATE INDEX IF NOT EXISTS platform_deployment_runs_status_idx
    ON platform_deployment_runs (status, started_at DESC);
CREATE INDEX IF NOT EXISTS platform_deployment_runs_tenant_idx
    ON platform_deployment_runs (tenant_id, started_at DESC);

-- Immutable, append-only audit trail of every operator action and orchestration
-- step within a deployment (full audit logging requirement).
CREATE TABLE IF NOT EXISTS platform_deployment_events (
    event_id      BIGINT GENERATED ALWAYS AS IDENTITY,
    deployment_id UUID NOT NULL REFERENCES platform_deployment_runs (deployment_id) ON DELETE CASCADE,
    recorded_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- e.g. CUTOVER_STARTED, BASELINE_CAPTURED, CHECKLIST_ITEM, OPERATOR_ACTION,
    --      PRE_CUTOVER_VALIDATED, POST_CUTOVER_VALIDATED, EVIDENCE_RECORDED
    event_type    TEXT NOT NULL,
    actor         TEXT NOT NULL,
    detail        JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (event_id)
);

CREATE INDEX IF NOT EXISTS platform_deployment_events_deployment_idx
    ON platform_deployment_events (deployment_id, recorded_at);
