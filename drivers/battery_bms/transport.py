"""Modbus TCP transport for the battery driver.

Reuses the SunSpec vertical's transport verbatim (Phase 9E) — the same
pymodbus-or-built-in client factory and pure-socket server used by 9E and 9C.
One Modbus transport for the whole edge; no duplication.
"""
from __future__ import annotations

from sunspec.transport import open_modbus, ModbusTcpServer  # noqa: F401

__all__ = ["open_modbus", "ModbusTcpServer"]
