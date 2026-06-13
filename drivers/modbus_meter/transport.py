"""Modbus TCP transport for the smart-meter driver.

Reuses the SunSpec vertical's transport verbatim (Phase 9E): the pymodbus-or-
built-in client factory `open_modbus()` and the pure-socket `ModbusTcpServer`
used by the simulator. Smart meters and SunSpec inverters both speak Modbus TCP,
so there is one transport for the whole edge — no duplication.
"""
from __future__ import annotations

from sunspec.transport import open_modbus, ModbusTcpServer  # noqa: F401

__all__ = ["open_modbus", "ModbusTcpServer"]
