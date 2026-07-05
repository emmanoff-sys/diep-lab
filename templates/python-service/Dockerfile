# DAEP / RE-OS — Multi-stage Docker build standard (WP-003-01)
# Authority: DOCKER_STANDARDS.md | LLD v2.0 §2.1.2 ("Multi-stage: builder → production")
#
# Build:  docker build -t reos/scaffold:local .
# Verify: DOCKER_STANDARDS.md §6

# ---------------------------------------------------------------------------
# Stage 1: builder — installs exact-pinned runtime deps, builds the wheel.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build
ARG PIP_EXTRA_INDEX_URL

# Dependency manifest first — BuildKit layer cache hit on every build that
# only touches application source (DOCKER_STANDARDS.md §2).
COPY requirements.txt pyproject.toml README.md ./

RUN pip install --no-cache-dir --upgrade pip build hatchling && \
    PIP_EXTRA_INDEX_URL="${PIP_EXTRA_INDEX_URL}" pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# hatchling build backend (WP-001-09) — produces the versioned wheel this
# stage's dependencies already satisfy (--no-isolation skips re-resolving).
RUN python -m build --wheel --no-isolation --outdir /build/dist

# ---------------------------------------------------------------------------
# Stage 2: production — runtime-only image, non-root, no build tooling.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS production

# Non-root service user (DOCKER_STANDARDS.md §3) — no login shell, no home dir.
RUN groupadd --system reos && \
    useradd --system --gid reos --no-create-home --shell /usr/sbin/nologin reos

WORKDIR /app

# Runtime dependencies copied verbatim from the builder's resolved
# site-packages — never re-resolved against an index at this stage, so the
# exact pins from requirements.txt (WP-001-08) are what actually ship.
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /build/dist/*.whl /tmp/

# --no-deps: dependencies are already present from the layer above; this
# only registers the service's own package metadata/entry points.
RUN pip install --no-cache-dir --no-deps /tmp/*.whl && rm -rf /tmp/*.whl

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

# Calls the scaffold's own /health endpoint (api/v1/endpoints/health.py).
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=2).status == 200 else 1)"

USER reos

CMD ["uvicorn", "service_name.main:app", "--host", "0.0.0.0", "--port", "8000"]
