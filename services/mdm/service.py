#!/usr/bin/env python3
"""DIEP MDM — service entrypoint. Wires the health/metrics HTTP server and
the MQTT consumer/republisher loop. See MDM_DESIGN.md.
"""
from __future__ import annotations

import logging

from .config import Settings
from .health import start_health_server
from .mqtt_io import MqttIo

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("diep-mdm")


def main() -> None:
    start_health_server(Settings.HEALTH_PORT)
    MqttIo().run_forever()


if __name__ == "__main__":
    main()
