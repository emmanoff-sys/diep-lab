# DAEP / RE-OS — Identity Service multi-stage Docker build (WP-003-01 / DOCKER_STANDARDS.md)
# Authority: WP-005-01 | LLD v2.0 §2.1.2

FROM python:3.12-slim AS builder

WORKDIR /build

COPY requirements.txt pyproject.toml README.md ./

RUN pip install --no-cache-dir --upgrade pip build && \
    pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

RUN python -m build --wheel --no-isolation --outdir /build/dist

# ---------------------------------------------------------------------------

FROM python:3.12-slim AS production

RUN groupadd --system reos && \
    useradd --system --gid reos --no-create-home --shell /usr/sbin/nologin reos

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /build/dist/*.whl /tmp/

RUN pip install --no-cache-dir --no-deps /tmp/*.whl && rm -rf /tmp/*.whl

# Vault agent drops AppRole credentials here (ADR-008 / tmpfs mount)
RUN mkdir -p /run/reos/identity-service && \
    chown reos:reos /run/reos/identity-service

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    IDENTITY_PORT=8001

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8001/health', timeout=2).status == 200 else 1)"

USER reos

CMD ["uvicorn", "identity_service.main:app", "--host", "0.0.0.0", "--port", "8001"]
