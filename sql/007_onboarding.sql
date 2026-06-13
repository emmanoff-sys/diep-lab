-- DIEP Phase 9H — Device onboarding & certification.
-- Tracks a field device through REGISTERED -> VALIDATED -> CERTIFIED -> PRODUCTION_READY.

CREATE TABLE IF NOT EXISTS device_onboarding (
    id                    BIGSERIAL PRIMARY KEY,
    device_id             VARCHAR(50) NOT NULL UNIQUE REFERENCES devices(device_id),
    site_name             VARCHAR(100),
    protocol              VARCHAR(50),
    vendor                VARCHAR(100),
    -- REGISTERED -> VALIDATED -> CERTIFIED -> PRODUCTION_READY
    status                VARCHAR(30) NOT NULL DEFAULT 'REGISTERED',
    validation            JSONB NOT NULL DEFAULT '{}'::jsonb,  -- last validation results
    notes                 TEXT,
    registered_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    validated_at          TIMESTAMPTZ,
    certified_at          TIMESTAMPTZ,
    production_approved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS device_onboarding_status_idx ON device_onboarding(status);

CREATE TABLE IF NOT EXISTS device_certifications (
    id          BIGSERIAL PRIMARY KEY,
    device_id   VARCHAR(50) NOT NULL REFERENCES devices(device_id),
    test_name   VARCHAR(50) NOT NULL,   -- connectivity|telemetry|command|ack|failover|security
    result      VARCHAR(20) NOT NULL,   -- PASS|FAIL|PENDING|SKIPPED
    details     JSONB NOT NULL DEFAULT '{}'::jsonb,
    run_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS device_certifications_device_idx ON device_certifications(device_id);
CREATE INDEX IF NOT EXISTS device_certifications_run_idx ON device_certifications(run_at DESC);
