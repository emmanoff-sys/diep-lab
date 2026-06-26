-- Fix: network_model_versions' BIGSERIAL sequence was never advanced.
--
-- sql/013 seeded the only row with an explicit PK (version=1) rather than
-- via nextval(), so the backing sequence stayed at its initial value. This
-- went unnoticed because nothing ever inserted a second row — Phase 2's
-- topology importer (topology/loader.py publish_version(), and the new
-- POST /topology/versions endpoint) is the first code path to ever rely on
-- auto-increment here, and it immediately collided on version=1.
--
-- Idempotent: resyncs the sequence to the current max version. A no-op if
-- the sequence is already ahead (e.g. on a DB that already published a
-- version some other way).
SELECT setval('network_model_versions_version_seq',
              (SELECT COALESCE(MAX(version), 1) FROM network_model_versions));
