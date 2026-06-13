# DIEP API — production image (Phase 10A).
# Multi-stage: build wheels, then a slim non-root runtime. Replaces the lab's
# pip-install-at-runtime container with a reproducible, scannable, signed artifact.

# ---- builder ----
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- runtime ----
FROM python:3.12-slim
# Non-root user (least privilege).
RUN groupadd -r diep && useradd -r -g diep -u 10001 diep
WORKDIR /app
COPY --from=builder /install /usr/local
COPY app.py auth.py ./
USER 10001:10001
EXPOSE 8000

# Container healthcheck hits the liveness probe.
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=2).status==200 else 1)"

# uvicorn workers tuned via env; config comes from env (12-factor / 9J-S0).
ENV UVICORN_WORKERS=2
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS}"]
