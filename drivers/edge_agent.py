#!/usr/bin/env python3
"""DIEP Edge Agent — config-driven driver host.

Reads a device config, instantiates the right protocol driver via the registry,
and runs it through the shared Runner (telemetry publish + command/ack loop).
This is the process that runs on the edge gateway (see
DIEP_EDGE_GATEWAY_ARCHITECTURE.md). One agent can host multiple drivers.

Usage:
    python edge_agent.py --config devices.json
    python edge_agent.py --list          # list registered protocol drivers

Config (devices.json):
    [
      {"device_id": "INV001", "protocol": "sunspec", "config": {"host": "10.0.0.5", "unit": 1}},
      {"device_id": "SM1001", "protocol": "modbus",  "config": {"host": "10.0.0.6", "port": 502}}
    ]

Importing this module registers all bundled drivers.
"""
from __future__ import annotations

import os
import sys
import json
import logging
import argparse
import threading

# Ensure this directory (the drivers/ root) is importable as the package root,
# so `diep_driver` and each protocol package resolve as top-level packages
# regardless of the caller's working directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Importing the packages registers their drivers via @register(...).
import modbus  # noqa: E402,F401
import modbus_meter  # noqa: E402,F401
import battery_bms  # noqa: E402,F401
import microgrid_iec104  # noqa: E402,F401
import sunspec  # noqa: E402,F401
import dlms  # noqa: E402,F401
import ocpp  # noqa: E402,F401
import ocpp_csms  # noqa: E402,F401
import iec104  # noqa: E402,F401
import iec61850  # noqa: E402,F401
import dnp3  # noqa: E402,F401
import bacnet  # noqa: E402,F401

from diep_driver import Runner
from diep_driver.registry import get_driver, available_drivers
from diep_driver.mqtt_client import MqttTransport

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(name)s %(levelname)s: %(message)s")
logger = logging.getLogger("diep-edge-agent")


def run_device(spec: dict):
    driver_cls = get_driver(spec["protocol"])
    driver = driver_cls(spec["device_id"], spec.get("config", {}))
    transport = MqttTransport(client_id=f"edge-{spec['device_id']}")
    Runner(driver, transport, telemetry_interval=spec.get("interval", 5)).run()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", help="Path to devices JSON config")
    parser.add_argument("--list", action="store_true", help="List registered drivers and exit")
    args = parser.parse_args()

    if args.list:
        print("Registered protocol drivers:", ", ".join(available_drivers()))
        return

    path = args.config or os.getenv("EDGE_CONFIG", "devices.json")
    with open(path) as fh:
        specs = json.load(fh)

    # One thread per device; the Runner loop is blocking.
    threads = []
    for spec in specs:
        t = threading.Thread(target=run_device, args=(spec,), name=spec["device_id"], daemon=True)
        t.start()
        threads.append(t)
        logger.info("Started driver %s (%s)", spec["device_id"], spec["protocol"])
    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
