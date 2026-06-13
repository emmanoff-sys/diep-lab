-- DERMS request tracking for Phase 7
CREATE TABLE IF NOT EXISTS derms_requests (
    id BIGSERIAL PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE,
    request_type VARCHAR(50) NOT NULL,
    site_name VARCHAR(100),
    device_id VARCHAR(50) REFERENCES devices(device_id),
    params JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(30) NOT NULL DEFAULT 'CREATED',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    executed_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS derms_requests_request_type_idx ON derms_requests(request_type);
CREATE INDEX IF NOT EXISTS derms_requests_site_name_idx ON derms_requests(site_name);
CREATE INDEX IF NOT EXISTS derms_requests_device_id_idx ON derms_requests(device_id);
