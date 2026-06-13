-- DIEP command/control plane — audit & status store
-- Milestone: POST /commands -> Kafka diep.commands -> Node-RED -> device
-- Source of truth for command audit; Redis mirrors live status for fast lookup.

CREATE TABLE IF NOT EXISTS commands (
    id              BIGSERIAL PRIMARY KEY,
    command_id      UUID         NOT NULL UNIQUE,
    device_id       VARCHAR(50)  NOT NULL REFERENCES devices(device_id),
    device_type     VARCHAR(50),
    command_type    VARCHAR(50)  NOT NULL,
    params          JSONB        NOT NULL DEFAULT '{}'::jsonb,
    -- PENDING -> SENT -> ACKED | FAILED
    status          VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
    issued_by       VARCHAR(50)  NOT NULL DEFAULT 'api',
    error_message   TEXT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    dispatched_at   TIMESTAMPTZ,
    acked_at        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS commands_device_id_idx  ON commands (device_id);
CREATE INDEX IF NOT EXISTS commands_status_idx     ON commands (status);
CREATE INDEX IF NOT EXISTS commands_created_at_idx ON commands (created_at DESC);

-- Seed the EV charger used for the end-to-end vertical-slice test.
INSERT INTO devices (device_id, device_type, location, status)
VALUES ('EV001', 'ev_charger', 'Abuja Site A', 'ONLINE')
ON CONFLICT (device_id) DO NOTHING;

INSERT INTO ev_chargers (charger_id, site_name, status, max_power_kw)
VALUES ('EV001', 'Abuja Site A', 'AVAILABLE', 22)
ON CONFLICT (charger_id) DO NOTHING;
