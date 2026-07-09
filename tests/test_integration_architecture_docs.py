"""WP-011-01 OA-074 — integration architecture documentation traceability.

Enforces that every objective in the WP-011-01 engineering evidence matrix
maps to an existing, non-empty specification document. Pattern follows
WP-013-01 (tests/test_adms_operational_readiness_docs.py).
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DOCS_BASE = REPO_ROOT / "docs" / "epic-011" / "wp-011-01"
EVIDENCE_FILE = (
    REPO_ROOT
    / "engineering"
    / "governance"
    / "EECR"
    / "wp-011-01"
    / "WP-011-01-ENGINEERING-EVIDENCE.md"
)

OBJECTIVE_DOCUMENTS = {
    "OA-069": "integration-architecture.md",
    "OA-070": "canonical-contracts.md",
    "OA-071": "event-model-extension-rules.md",
    "OA-072": "integration-security-architecture.md",
    "OA-073": "integration-test-harness-specification.md",
    "OA-074": "final-architecture-validation.md",
}


def test_all_objective_documents_exist_and_are_non_empty():
    """Every OA-069..OA-074 objective must have a non-empty specification file."""
    for objective, filename in OBJECTIVE_DOCUMENTS.items():
        path = DOCS_BASE / filename
        assert (
            path.exists()
        ), f"{objective} specification file missing: {path.relative_to(REPO_ROOT)}"
        content = path.read_text(encoding="utf-8").strip()
        assert content, f"{objective} specification file is empty: {path.relative_to(REPO_ROOT)}"
        assert len(content) > 200, (
            f"{objective} specification file appears truncated (< 200 chars): "
            f"{path.relative_to(REPO_ROOT)}"
        )


def test_readme_exists_and_references_all_objectives():
    """README must exist and reference every objective document."""
    readme = DOCS_BASE / "README.md"
    assert readme.exists(), f"README missing: {readme.relative_to(REPO_ROOT)}"
    content = readme.read_text(encoding="utf-8")
    for objective, filename in OBJECTIVE_DOCUMENTS.items():
        assert filename in content, f"README does not reference {objective} document ({filename})"


def test_engineering_evidence_file_exists_and_references_all_objectives():
    """Engineering evidence record must exist and reference all objectives."""
    assert (
        EVIDENCE_FILE.exists()
    ), f"Engineering evidence file missing: {EVIDENCE_FILE.relative_to(REPO_ROOT)}"
    content = EVIDENCE_FILE.read_text(encoding="utf-8")
    for objective in OBJECTIVE_DOCUMENTS:
        assert objective in content, f"Engineering evidence file does not reference {objective}"
