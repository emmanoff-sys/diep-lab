# DAEP / RE-OS — Audit Service multi-stage Docker build (WP-005-04)
# Authority: ENG-SPEC-005-04 §25.1 | LLD v2.0 §7.6

FROM python:3.11-slim AS builder

WORKDIR /build

COPY requirements.txt pyproject.toml ./

RUN pip install --no-cache-dir --upgrade pip build && \
    pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

RUN python -m build --wheel --no-isolation --outdir /build/dist

# ---------------------------------------------------------------------------

FROM python:3.11-slim AS production

RUN groupadd --system reos && \
    useradd --system --gid reos --no-create-home --shell /usr/sbin/nologin reos

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /build/dist/*.whl /tmp/

RUN pip install --no-cache-dir --no-deps /tmp/*.whl && rm -rf /tmp/*.whl

# Vault agent drops AppRole credentials here (ADR-008 / tmpfs mount)
RUN mkdir -p /run/reos/audit-service && \
    chown reos:reos /run/reos/audit-service

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    AUDIT_PORT=8004

EXPOSE 8004

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8004/api/v1/health/ready',timeout=5).status==200 else 1)"

USER reos

CMD ["uvicorn", "audit_service.main:app", "--host", "0.0.0.0", "--port", "8004"]
