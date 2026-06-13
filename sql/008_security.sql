-- DIEP Phase 9J — security: append-only audit trail of state-changing API actions.

CREATE TABLE IF NOT EXISTS audit_events (
    id          BIGSERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
    principal   VARCHAR(100),          -- who (api-key name or JWT subject)
    role        VARCHAR(20),           -- viewer | operator | admin | service
    action      VARCHAR(50) NOT NULL,  -- issue_command | derms_dispatch | register_asset | ...
    resource    VARCHAR(200),          -- device/command/onboarding target
    source_ip   VARCHAR(64),
    result      VARCHAR(20) NOT NULL,  -- ok | denied | error
    detail      JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS audit_events_ts_idx ON audit_events(ts DESC);
CREATE INDEX IF NOT EXISTS audit_events_principal_idx ON audit_events(principal);
CREATE INDEX IF NOT EXISTS audit_events_action_idx ON audit_events(action);
