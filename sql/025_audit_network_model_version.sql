-- Phase 4 (topology importer): stamp network_model_version onto the audit
-- trail tables, mirroring grid_nodes/grid_edges.model_version (sql/013).
--
-- Once a site has more than one published model version (Phase 2's importer
-- is the first writer that can produce that), these audit rows otherwise
-- carry no record of which topology was in effect when they were written —
-- a FLISR run, a control action, an outage case, or an automation event all
-- act on (or react to) a specific network model and should say which one.
--
-- Nullable, no default: existing rows predate versioning (like grid_nodes/
-- grid_edges before sql/013's own backfill) and a DEFAULT expression can't
-- subquery network_model_versions for "whichever is current" — the writing
-- code stamps it explicitly (see common.current_model_version()).
--
-- Additive + idempotent, matching sql/000..024.

ALTER TABLE flisr_events       ADD COLUMN IF NOT EXISTS network_model_version BIGINT REFERENCES network_model_versions(version);
ALTER TABLE control_actions    ADD COLUMN IF NOT EXISTS network_model_version BIGINT REFERENCES network_model_versions(version);
ALTER TABLE control_audit      ADD COLUMN IF NOT EXISTS network_model_version BIGINT REFERENCES network_model_versions(version);
ALTER TABLE outage_cases       ADD COLUMN IF NOT EXISTS network_model_version BIGINT REFERENCES network_model_versions(version);
ALTER TABLE automation_events  ADD COLUMN IF NOT EXISTS network_model_version BIGINT REFERENCES network_model_versions(version);
