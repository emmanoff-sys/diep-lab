-- ADMS Phase 2 (OC-1) — Operational-controls governance substrate.
--
-- The control plane for *actuation*. Every control action (switch op, FLISR
-- execution, Volt/VAR dispatch — added by OC-2..OC-4) is recorded here and flows
-- through request -> (approve) -> execute -> verify -> audit. This migration adds
-- only the governance tables; no actuation handlers and no behavioural change to
-- existing read-only paths. Additive + idempotent.

-- Lifecycle record for one control action.
CREATE TABLE IF NOT EXISTS control_actions (
    action_id     UUID PRIMARY KEY,
    action_type   TEXT NOT NULL,                 -- noop | switch_op | flisr | voltvar_dispatch
    target        TEXT,                          -- edge_id / node_id / der_id / ...
    params        JSONB NOT NULL DEFAULT '{}'::jsonb,
    mode          TEXT NOT NULL DEFAULT 'dry_run'
                  CHECK (mode IN ('dry_run', 'live')),
    risk          TEXT NOT NULL DEFAULT 'low'
                  CHECK (risk IN ('low', 'high')),
    status        TEXT NOT NULL DEFAULT 'PENDING'
                  CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED',
                                    'EXECUTED', 'FAILED', 'ROLLED_BACK')),
    reason        TEXT,
    requested_by  TEXT NOT NULL,
    approved_by   TEXT,                           -- must differ from requested_by for high-risk
    before_state  JSONB,                          -- captured at plan time (for rollback/audit)
    after_state   JSONB,                          -- captured at execute time
    error         TEXT,
    tenant_id     VARCHAR(50) NOT NULL DEFAULT 'default' REFERENCES tenants(tenant_id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_at   TIMESTAMPTZ,
    executed_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS control_actions_status_idx ON control_actions (status, created_at DESC);
CREATE INDEX IF NOT EXISTS control_actions_tenant_idx ON control_actions (tenant_id, created_at DESC);

-- Append-only audit trail: one row per lifecycle transition. Never updated.
CREATE TABLE IF NOT EXISTS control_audit (
    audit_id   BIGSERIAL PRIMARY KEY,
    action_id  UUID REFERENCES control_actions(action_id),
    event      TEXT NOT NULL,    -- REQUESTED|APPROVED|REJECTED|DRYRUN|EXECUTED|FAILED|ROLLED_BACK|BLOCKED
    actor      TEXT NOT NULL,
    detail     JSONB NOT NULL DEFAULT '{}'::jsonb,
    at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS control_audit_action_idx ON control_audit (action_id, at);
