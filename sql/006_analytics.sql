-- DIEP AI analytics event tracking for Phase 8
CREATE TABLE IF NOT EXISTS analytics_events (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    device_id VARCHAR(50) REFERENCES devices(device_id),
    site_name VARCHAR(100),
    severity VARCHAR(20) NOT NULL DEFAULT 'INFO',
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS analytics_events_device_idx ON analytics_events(device_id);
CREATE INDEX IF NOT EXISTS analytics_events_site_idx ON analytics_events(site_name);
CREATE INDEX IF NOT EXISTS analytics_events_type_idx ON analytics_events(event_type);
