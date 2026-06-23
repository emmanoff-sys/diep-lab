"""DIEP ADMS P4 — closed-loop automation controller.

Standalone poller (same pattern as oms-detector) that drives the automation engine
on an interval by calling POST /automation/tick on the FastAPI app with the service
token. All policy evaluation + governance lives server-side (fastapi/routers/
automation.py) so it is also callable on demand and from tests; this process just
schedules it.

Safe to run continuously: the engine is inert until OC_AUTOMATION_ENABLED is set, and
even then only enabled policies in 'auto' mode (within bounds, with the controls flag)
actuate — everything else is a recommendation. So this controller can be deployed
disabled-by-default and the flag flipped when operators are ready.
"""
import os
import time
import logging

import requests

logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] [automation-controller] %(levelname)s: %(message)s")
log = logging.getLogger("automation-controller")

FASTAPI_BASE = os.getenv("FASTAPI_BASE", "http://diep-fastapi:8000")
SERVICE_TOKEN = os.getenv("DIEP_SERVICE_TOKEN", "diep-service-dev-token-CHANGE-ME")
INTERVAL = float(os.getenv("AUTOMATION_TICK_INTERVAL", "30"))
HEARTBEAT_FILE = os.getenv("AUTOMATION_HEARTBEAT_FILE", "/tmp/automation-controller.heartbeat")

HEADERS = {"Authorization": f"Bearer {SERVICE_TOKEN}"}


def _heartbeat():
    try:
        with open(HEARTBEAT_FILE, "w") as fh:
            fh.write(str(time.time()))
    except OSError as exc:  # noqa: BLE001
        log.warning("heartbeat write failed: %s", exc)


def main():
    log.info("starting; POST %s/automation/tick every %ss", FASTAPI_BASE, INTERVAL)
    _heartbeat()  # mark alive immediately so health passes within start_period
    while True:
        try:
            res = requests.post(f"{FASTAPI_BASE}/automation/tick", headers=HEADERS, timeout=15)
            if res.status_code == 200:
                d = res.json()
                if d.get("ran") and d.get("results"):
                    acted = [r for r in d["results"] if r.get("decision") in
                             ("proposed", "executed", "blocked", "failed", "tripped")]
                    if acted:
                        log.info("tick: %s", acted)
            else:
                log.warning("tick -> HTTP %s: %s", res.status_code, res.text[:200])
        except Exception as exc:  # noqa: BLE001
            log.warning("tick call failed: %s", exc)
        _heartbeat()
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
