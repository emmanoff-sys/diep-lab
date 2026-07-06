from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/release2/legacy_db_hostname_audit.py"
SPEC = importlib.util.spec_from_file_location("legacy_db_hostname_audit", MODULE_PATH)
assert SPEC is not None
legacy_db_hostname_audit = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = legacy_db_hostname_audit
SPEC.loader.exec_module(legacy_db_hostname_audit)


def test_db_dependent_rows_must_not_route_to_legacy_profile():
    rows = {
        "tests/test_db.py": {
            "validation_profiles": "legacy-platform;database-integration",
            "classification": "Environment-dependent",
            "environment_contract": "database-integration",
            "required_services": "TimescaleDB/PostgreSQL",
        }
    }

    errors = legacy_db_hostname_audit.validate_classification(rows)

    assert "tests/test_db.py: DB-dependent test routed to non-DB profile" in errors


def test_release_gate_db_rows_are_valid():
    rows = {
        "tests/test_smoke.py": {
            "validation_profiles": "release-gate",
            "classification": "System",
            "environment_contract": "release-gate",
            "required_services": "running FastAPI stack;TimescaleDB/PostgreSQL",
        }
    }

    assert legacy_db_hostname_audit.validate_classification(rows) == []


def test_hostname_reference_classification_is_explicit():
    assert legacy_db_hostname_audit.classify_reference("fastapi/common.py") == (
        "environment-derived-legacy-default",
        "Release 2 must provide DB_HOST from DB_DSN",
    )
    assert legacy_db_hostname_audit.classify_reference("docker-compose.yml") == (
        "docker-only-assumption",
        "valid only inside Docker Compose network",
    )
    assert legacy_db_hostname_audit.classify_reference("tests/test_deployment_unit.py") == (
        "fixture-container-name",
        "unit test validates deployment container inventory only",
    )
