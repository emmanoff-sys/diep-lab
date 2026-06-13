"""Generic Modbus smart-meter register map + a dependency-free decoder.

Unlike SunSpec (a self-describing standard), a Modbus meter exposes a vendor
register map that the integrator supplies as DATA. This module models a clean,
representative meter profile (IEEE-754 float32 measurements + a uint16 control
relay) and provides decode/encode used by both the driver and the simulator, so
they stay wire-compatible. A real deployment swaps REGISTER_MAP for the vendor
map (Landis+Gyr / Itron / Hexing / EDMI / Schneider) without touching the driver.

Encoding: float32 = two 16-bit holding registers, big-endian, high word first
(the common ">f" / "AB CD" layout). Swap _F32_WORDORDER for word-swapped vendors.
"""
from __future__ import annotations

import struct

# Base Modbus address of the meter register block.
DEFAULT_BASE = 3000

# point name -> (modbus_address, type). Types: "f32" (2 regs), "u16" (1 reg).
REGISTER_MAP = {
    "voltage":            (3000, "f32"),  # V (phase voltage)
    "current":            (3002, "f32"),  # A
    "power_kw":           (3004, "f32"),  # kW active power (signed: + import)
    "frequency":          (3006, "f32"),  # Hz
    "power_factor":       (3008, "f32"),  # 0..1
    "energy_import_kwh":  (3010, "f32"),  # kWh cumulative import
    "energy_export_kwh":  (3012, "f32"),  # kWh cumulative export
    "relay_state":        (3014, "u16"),  # 1 = connected, 0 = disconnected
}

# Total registers spanned by the map (3000..3014 inclusive -> 15 registers).
BLOCK_LENGTH = 15

RELAY_CONNECTED = 1
RELAY_DISCONNECTED = 0

_F32_WORDORDER = ">f"  # big-endian float; high word first


def _f32_to_regs(value: float) -> list[int]:
    hi, lo = struct.unpack(">HH", struct.pack(_F32_WORDORDER, float(value)))
    return [hi, lo]


def _regs_to_f32(hi: int, lo: int) -> float:
    return struct.unpack(_F32_WORDORDER, struct.pack(">HH", hi & 0xFFFF, lo & 0xFFFF))[0]


def decode_registers(regs: list[int], base: int = DEFAULT_BASE) -> dict:
    """Decode a raw holding-register block into native meter point values."""
    out: dict[str, float] = {}
    for name, (addr, ptype) in REGISTER_MAP.items():
        off = addr - base
        if ptype == "f32":
            out[name] = round(_regs_to_f32(regs[off], regs[off + 1]), 4)
        elif ptype == "u16":
            out[name] = regs[off] & 0xFFFF
        else:  # pragma: no cover - guard
            raise ValueError(f"unknown register type {ptype!r}")
    return out


def build_registers(values: dict, base: int = DEFAULT_BASE) -> tuple[int, list[int]]:
    """Build a holding-register image (zero-filled) from native point values."""
    block = [0] * BLOCK_LENGTH
    for name, (addr, ptype) in REGISTER_MAP.items():
        off = addr - base
        value = values.get(name, 0)
        if ptype == "f32":
            block[off], block[off + 1] = _f32_to_regs(value)
        elif ptype == "u16":
            block[off] = int(value) & 0xFFFF
    return base, block
