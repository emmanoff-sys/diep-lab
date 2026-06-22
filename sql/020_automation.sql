-- DIEP ADMS Phase 4 (P4-1) — closed-loop automation substrate.
--
-- Lets the platform act on its own analysis AUTOMATICALLY, but only ever through
-- the Phase-2/3 governed control plane (control_actions + approvals + flag gate +
-- echo verification + audit). Safe by construction:
--   * a policy is DISABLED by default and runs in mode 'recommend' (human-in-the-
--     loop: it proposes a governed PENDING action, executes nothing);
--   * 'auto' mode is per-policy opt-in and still requires the master automation flag
--     AND the controls flag AND the action to fall within the policy's bounds;
--   * a circuit breaker trips a policy after repeated failures.
-- Additive + idempotent.

CREATE TABLE IF NOT EXISTS automation_policies (
    policy_id     VARCHAR(64) PRIMARY KEY,          -- e.g. flisr_auto | voltvar_auto | noop_auto
    kind          VARCHAR(32) NOT NULL,             -- handler key in the automation registry
    description   TEXT,
    enabled       BOOLEAN NOT NULL DEFAULT FALSE,   -- master per-policy switch (default OFF)
    mode          VARCHAR(16) NOT NULL DEFAULT 'recommend'
        CHECK (mode IN ('recommend','auto')),       -- recommend = propose only; auto = may execute
    params        JSONB NOT NULL DEFAULT '{}'::jsonb,
    bounds        JSONB NOT NULL DEFAULT '{}'::jsonb, -- safety envelope (max_customers, cooldown_s, …)
    consecutive_failures INT NOT NULL DEFAULT 0,
    tripped       BOOLEAN NOT NULL DEFAULT FALSE,    -- circuit breaker open => policy paused
    last_run_at   TIMESTAMPTZ,
    tenant_id     VARCHAR(50) NOT NULL DEFAULT 'default' REFERENCES tenants(tenant_id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS automation_events (
    event_id   BIGSERIAL PRIMARY KEY,
    policy_id  VARCHAR(64) REFERENCES automation_policies(policy_id),
    kind       VARCHAR(32) NOT NULL,
    decision   VARCHAR(16) NOT NULL                 -- proposed|executed|skipped|blocked|failed|tripped|config
        CHECK (decision IN ('proposed','executed','skipped','blocked','failed','tripped','config')),
    trigger    JSONB NOT NULL DEFAULT '{}'::jsonb,  -- what fired the policy (and why)
    action_id  UUID REFERENCES control_actions(action_id),  -- the governed action it created, if any
    detail     JSONB NOT NULL DEFAULT '{}'::jsonb,
    tenant_id  VARCHAR(50) NOT NULL DEFAULT 'default' REFERENCES tenants(tenant_id),
    at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS automation_events_policy_idx ON automation_events (policy_id, at DESC);
CREATE INDEX IF NOT EXISTS automation_events_action_idx ON automation_events (action_id);

-- Seed the policies DISABLED + recommend, with conservative default bounds. Enabling
-- them and/or moving to 'auto' is a deliberate operator action.
INSERT INTO automation_policies (policy_id, kind, description, bounds) VALUES
    ('noop_auto', 'noop',
     'Governance demonstrator: proposes a governed noop each tick (actuates nothing).',
     '{"cooldown_s": 60, "max_per_tick": 1}'::jsonb),
    ('flisr_auto', 'flisr',
     'Auto-FLISR: on a confirmed outage, propose/execute a governed restoration.',
     '{"require_restores_all": true, "max_customers": 25, "cooldown_s": 120, "max_per_tick": 1}'::jsonb),
    ('voltvar_auto', 'voltvar',
     'Continuous Volt/VAR: on a persistent voltage violation, propose/execute a governed dispatch.',
     '{"max_step_kw": 10, "cooldown_s": 120, "max_per_tick": 2}'::jsonb)
ON CONFLICT (policy_id) DO NOTHING;
