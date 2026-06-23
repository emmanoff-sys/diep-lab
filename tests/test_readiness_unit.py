import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FASTAPI_DIR = ROOT / "fastapi"
if str(FASTAPI_DIR) not in sys.path:
    sys.path.insert(0, str(FASTAPI_DIR))

import readiness  # noqa: E402


def _config() -> readiness.ReadinessConfig:
    return readiness.ReadinessConfig(
        fastapi_readyz_url="http://127.0.0.1:8000/readyz",
        kafka_exporter_url="http://127.0.0.1:9308/metrics",
        db_host="127.0.0.1",
        db_port=5432,
        db_name="diep",
        db_user="diep",
        db_password="secret",
        redis_host="127.0.0.1",
        redis_port=6379,
        redis_password="redis-secret",
        kafka_container="diep-kafka",
        docker_root_dir="/var/lib/docker",
        disk_max_used_pct=85.0,
        memory_max_used_pct=85.0,
        min_uptime_seconds=86400,
        max_restart_delta=0,
        pass_threshold=90,
        critical_containers=("diep-fastapi", "diep-kafka"),
        source="pytest",
        tenant_id="default",
    )


def _pass(name: str, weight: int) -> readiness.ReadinessCheckResult:
    return readiness.ReadinessCheckResult(
        check_name=name,
        status="PASS",
        weight=weight,
        score=weight,
        message="ok",
        observed={},
        threshold={},
    )


def _fail(name: str, weight: int) -> readiness.ReadinessCheckResult:
    return readiness.ReadinessCheckResult(
        check_name=name,
        status="FAIL",
        weight=weight,
        score=0,
        message="bad",
        observed={},
        threshold={},
    )


def test_parse_docker_timestamp_handles_nanoseconds():
    parsed = readiness.parse_docker_timestamp("2026-06-23T12:56:49.896585898Z")
    assert parsed == datetime(2026, 6, 23, 12, 56, 49, 896585, tzinfo=timezone.utc)


def test_find_metric_value_filters_by_labels():
    text = """
    # HELP kafka_brokers Number of brokers
    # TYPE kafka_brokers gauge
    kafka_brokers 1
    kafka_topic_partitions{topic="diep.commands"} 1
    kafka_topic_partitions{topic="other"} 2
    """
    assert readiness.find_metric_value(text, "kafka_brokers") == 1.0
    assert readiness.find_metric_value(text, "kafka_topic_partitions", {"topic": "diep.commands"}) == 1.0
    assert readiness.find_metric_value(text, "kafka_topic_partitions", {"topic": "missing"}) is None


def test_container_restart_check_uses_previous_run_deltas():
    previous_run = readiness.ReadinessRunResponse(
        run_id="prev",
        checked_at=datetime.now(timezone.utc) - timedelta(hours=1),
        status="FAIL",
        score=80,
        pass_threshold=90,
        recommendation="hold",
        source="pytest",
        tenant_id="default",
        summary={},
        checks=[
            readiness.ReadinessCheckResult(
                check_name="container_restart_counts",
                status="PASS",
                weight=10,
                score=10,
                message="baseline",
                observed={"restart_counts": {"diep-fastapi": 0, "diep-kafka": 1}},
                threshold={"max_restart_delta": 0},
            )
        ],
    )
    container_state = {
        "diep-fastapi": {"restart_count": 0},
        "diep-kafka": {"restart_count": 2},
    }
    result = readiness.check_container_restart_counts(_config(), container_state, previous_run)
    assert result.status == "FAIL"
    assert result.observed["restart_deltas"]["diep-kafka"] == 1


def test_run_readiness_assessment_fails_when_any_critical_check_fails(monkeypatch):
    config = _config()
    now = datetime.now(timezone.utc)
    container_state = {
        "diep-fastapi": {"running": True, "started_at": now - timedelta(hours=25), "restart_count": 0},
        "diep-kafka": {"running": True, "started_at": now - timedelta(hours=25), "restart_count": 0},
    }

    monkeypatch.setattr(readiness, "inspect_containers", lambda names: container_state)
    monkeypatch.setattr(readiness, "check_fastapi_readyz", lambda cfg: _pass("fastapi_readyz", 15))
    monkeypatch.setattr(readiness, "check_postgres_connectivity", lambda cfg: _pass("postgres_connectivity", 10))
    monkeypatch.setattr(readiness, "check_redis_connectivity", lambda cfg: _pass("redis_connectivity", 10))
    monkeypatch.setattr(readiness, "check_kafka_broker_health", lambda cfg: _pass("kafka_broker_health", 15))
    monkeypatch.setattr(readiness, "check_kafka_exporter_metrics", lambda cfg: _pass("kafka_exporter_metrics", 10))
    monkeypatch.setattr(
        readiness,
        "check_container_restart_counts",
        lambda cfg, state, prev: _pass("container_restart_counts", 10),
    )
    monkeypatch.setattr(readiness, "check_disk_utilization", lambda cfg: _pass("disk_utilization", 10))
    monkeypatch.setattr(readiness, "check_memory_utilization", lambda cfg: _pass("memory_utilization", 10))
    monkeypatch.setattr(
        readiness,
        "check_critical_service_uptime",
        lambda cfg, state: _fail("critical_service_uptime", 10),
    )

    run = readiness.run_readiness_assessment(config)
    assert run.status == "FAIL"
    assert run.score == 90
    assert "FAIL" in run.recommendation
