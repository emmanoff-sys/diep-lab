-- DIEP ADMS M2 — Outage Management System (OMS).
--
-- Outage cases inferred from meter "last gasp" signals, telemetry heartbeat
-- gaps, and manual customer reports (Call Handler). Affected customers/meters
-- are resolved through the M1 network model (grid_nodes / service_points), not
-- duplicated here. Additive + idempotent, matching sql/000..013.

-- An outage case: one de-energized network section over a time window.
CREATE TABLE IF NOT EXISTS outage_cases (
    case_id            VARCHAR(64) PRIMARY KEY,           -- uuid4
    status             VARCHAR(20) NOT NULL DEFAULT 'DETECTED'
        CHECK (status IN ('DETECTED','CONFIRMED','RESTORED','CLOSED')),
    cause              VARCHAR(32) NOT NULL DEFAULT 'unknown'
        CHECK (cause IN ('last_gasp','heartbeat','manual','mixed','unknown')),
    affected_node_id   VARCHAR(64) REFERENCES grid_nodes(node_id),
    customers_affected INT NOT NULL DEFAULT 0,
    detected_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    confirmed_at       TIMESTAMPTZ,
    restored_at        TIMESTAMPTZ,
    closed_at          TIMESTAMPTZ,
    notes              TEXT,
    tenant_id          VARCHAR(50) NOT NULL DEFAULT 'default' REFERENCES tenants(tenant_id),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS outage_cases_status_idx   ON outage_cases(status);
CREATE INDEX IF NOT EXISTS outage_cases_node_idx     ON outage_cases(affected_node_id);
CREATE INDEX IF NOT EXISTS outage_cases_detected_idx ON outage_cases(detected_at DESC);

-- Meters attributed to a case (the devices observed/inferred out).
CREATE TABLE IF NOT EXISTS outage_case_meters (
    case_id         VARCHAR(64) NOT NULL REFERENCES outage_cases(case_id) ON DELETE CASCADE,
    meter_device_id VARCHAR(50) NOT NULL REFERENCES devices(device_id),
    node_id         VARCHAR(64) REFERENCES grid_nodes(node_id),
    added_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (case_id, meter_device_id)
);

-- Customer-reported outages (Call Handler). Linked to a case once correlated.
CREATE TABLE IF NOT EXISTS outage_reports (
    report_id        VARCHAR(64) PRIMARY KEY,            -- uuid4
    customer_id      VARCHAR(64) REFERENCES customers(customer_id),
    meter_device_id  VARCHAR(50) REFERENCES devices(device_id),
    node_id          VARCHAR(64) REFERENCES grid_nodes(node_id),
    caller_name      VARCHAR(128),
    caller_phone     VARCHAR(40),
    description      TEXT,
    status           VARCHAR(20) NOT NULL DEFAULT 'NEW'
        CHECK (status IN ('NEW','LINKED','CLOSED')),
    case_id          VARCHAR(64) REFERENCES outage_cases(case_id),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS outage_reports_status_idx ON outage_reports(status);
CREATE INDEX IF NOT EXISTS outage_reports_case_idx   ON outage_reports(case_id);
CREATE INDEX IF NOT EXISTS outage_reports_created_idx ON outage_reports(created_at DESC);
