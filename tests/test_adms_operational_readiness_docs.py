"""WP-013-01 operational readiness evidence traceability tests."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
READINESS_DIR = ROOT / "docs" / "adms-operational-readiness" / "wp-013-01"

OBJECTIVE_FILES = {
    "OA-053": "production-deployment-architecture.md",
    "OA-054": "platform-observability-standards.md",
    "OA-055": "operational-runbooks.md",
    "OA-056": "platform-resilience-validation.md",
    "OA-057": "production-security-readiness.md",
    "OA-058": "deployment-rehearsal.md",
    "OA-059": "operational-readiness-assessment.md",
    "OA-060": "final-operational-readiness-validation.md",
}

REQUIRED_TERMS = {
    "OA-053": (
        "Runtime hosting",
        "Service topology",
        "Environment separation",
        "High-Availability",
        "Network Architecture",
        "Infrastructure Assumptions",
    ),
    "OA-054": (
        "Structured Logging",
        "Metrics",
        "Distributed Tracing",
        "Health Endpoints",
        "Alert Definitions",
        "Service Level Objectives",
        "Engineering-Facing Dashboards",
    ),
    "OA-055": (
        "Deployment Runbook",
        "Startup Procedure",
        "Shutdown Procedure",
        "Backup Procedure",
        "Recovery Procedure",
        "Incident Response",
        "Upgrade Procedure",
        "Troubleshooting Guidance",
    ),
    "OA-056": (
        "Backup Verification",
        "Restore Validation",
        "Disaster Recovery Procedure",
        "Operational Persistence Review",
        "Failover Verification",
        "Recovery Objectives",
        "Data Integrity Validation",
    ),
    "OA-057": (
        "Identity Management",
        "Secret Management",
        "Certificate Management",
        "Secure Configuration",
        "Operational Trust Boundaries",
        "Deployment Security Review",
        "Access Control Review",
    ),
    "OA-058": (
        "Environment Preparation",
        "Deployment Validation",
        "Configuration Verification",
        "Operational Smoke Testing",
        "Rollback Rehearsal",
        "Operational Acceptance Checklist",
    ),
    "OA-059": (
        "Readiness Report",
        "Outstanding Risks",
        "Operational Limitations",
        "Deployment Recommendations",
        "Support Readiness Assessment",
        "Operational Acceptance Evidence",
    ),
    "OA-060": (
        "Validation Objective",
        "Required Validation Commands",
        "Validation Evidence Template",
        "Acceptance Position",
    ),
}

PROHIBITED_IMPLEMENTATION_SIGNALS = (
    "operator dashboard implemented",
    "operator console implemented",
    "scada writeback implemented",
    "switching execution implemented",
    "closed-loop automation implemented",
    "device control implemented",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_wp_013_01_index_traces_all_authorised_objectives() -> None:
    index = _read(READINESS_DIR / "README.md")

    assert "PAO-014" in index
    assert "5c28ca3fa2efe37cf5ca364e4650fc9c487c7e34" in index
    for objective, filename in OBJECTIVE_FILES.items():
        assert objective in index
        assert filename in index


def test_each_authorised_objective_has_required_evidence_terms() -> None:
    for objective, filename in OBJECTIVE_FILES.items():
        content = _read(READINESS_DIR / filename)
        normalised = content.lower()

        assert objective in content
        assert "COMPLETE" in content
        for term in REQUIRED_TERMS[objective]:
            assert term.lower() in normalised


def test_readiness_pack_preserves_pao_014_scope_boundaries() -> None:
    corpus = "\n".join(
        _read(READINESS_DIR / filename).lower() for filename in OBJECTIVE_FILES.values()
    )
    corpus += "\n" + _read(READINESS_DIR / "README.md").lower()

    for phrase in PROHIBITED_IMPLEMENTATION_SIGNALS:
        assert phrase not in corpus

    assert "no production deployment is authorised" in corpus
    assert "no scada writeback" in corpus
    assert "no persistence redesign is authorised" in corpus
