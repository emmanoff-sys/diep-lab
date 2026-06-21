"""DIEP ADMS M2 — OMS outage-detection runner.

Standalone poller (same pattern as ingestor/dispatcher) that drives the OMS
detection sweep on an interval by calling POST /oms/detect on the FastAPI app
with the service token. Detection logic itself lives server-side in
fastapi/routers/oms.py so it is also callable on demand (and from tests); this
process just schedules it.
"""
import os
import time
import logging

import requests

logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] [oms-detector] %(levelname)s: %(message)s")
log = logging.getLogger("oms-detector")

FASTAPI_BASE = os.getenv("FASTAPI_BASE", "http://diep-fastapi:8000")
SERVICE_TOKEN = os.getenv("DIEP_SERVICE_TOKEN", "diep-service-dev-token-CHANGE-ME")
INTERVAL = float(os.getenv("OMS_DETECT_INTERVAL", "30"))
# Liveness signal touched after every sweep so the container HEALTHCHECK can tell
# the poll loop is alive (this process has no HTTP surface of its own). Health =
# "the loop is running", deliberately decoupled from FastAPI reachability — a
# transient API outage is something we retry through, not a reason to flap
# unhealthy. The compose healthcheck asserts this file is fresh. See docker-compose.yml.
HEARTBEAT_FILE = os.getenv("OMS_HEARTBEAT_FILE", "/tmp/oms-detector.heartbeat")

HEADERS = {"Authorization": f"Bearer {SERVICE_TOKEN}"}


def _heartbeat():
    try:
        with open(HEARTBEAT_FILE, "w") as fh:
            fh.write(str(time.time()))
    except OSError as exc:  # noqa: BLE001
        log.warning("heartbeat write failed: %s", exc)


def main():
    log.info("starting; POST %s/oms/detect every %ss", FASTAPI_BASE, INTERVAL)
    _heartbeat()  # mark alive immediately so health passes within start_period
    while True:
        try:
            res = requests.post(f"{FASTAPI_BASE}/oms/detect", headers=HEADERS, timeout=10)
            if res.status_code == 200:
                d = res.json()
                if d.get("created") or d.get("updated") or d.get("restored"):
                    log.info("detection: created=%s updated=%s restored=%s",
                             d.get("created"), d.get("updated"), d.get("restored"))
            else:
                log.warning("detect -> HTTP %s: %s", res.status_code, res.text[:200])
        except Exception as exc:  # noqa: BLE001
            log.warning("detect call failed: %s", exc)
        # Touch after the attempt: the loop completed an iteration, alive either way.
        _heartbeat()
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
