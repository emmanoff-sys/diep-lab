"""Battery / BMS Modbus register map + dependency-free decoder (Phase 9D).

A representative vendor-style Modbus map for a battery energy storage system:
float32 measurements + a uint16 state, plus a writable control block (mode,
power setpoint, target SoC, power limit). Maps onto SunSpec storage models
802/803/124 conceptually but is expressed as DATA so swapping a Huawei / BYD /
Sungrow / Victron register map is a config change, not a code change.

Shared with the simulator so both stay wire-compatible.

**Sign convention:** power_kw is signed with **negative = charging** (drawing
power) and **positive = discharging** (delivering power), per the Phase 9D
canonical example. NB this is the opposite of the legacy BAT001 simulator
(+ = charging); see the report's "Remaining Gaps" for the standardization note.
"""
from __future__ import annotations

import struct

DEFAULT_BASE = 4000

# point name -> (modbus_address, type). f32 = 2 regs, u16 = 1 reg.
REGISTER_MAP = {
    # --- measurements (read) ---
    "battery_soc":       (4000, "f32"),  # %
    "voltage":           (4002, "f32"),  # V (DC bus)
    "current":           (4004, "f32"),  # A (magnitude)
    "power_kw":          (4006, "f32"),  # kW signed (- charge / + discharge)
    "temperature":       (4008, "f32"),  # deg C
    "soh":               (4010, "f32"),  # % state of health
    "state":             (4012, "u16"),  # STATE_* enum below
    # --- control (read/write) ---
    "cmd_mode":          (4013, "u16"),  # CMD_* enum below
    "power_setpoint_kw": (4014, "f32"),  # requested power (kW)
    "target_soc":        (4016, "u16"),  # %
    "power_limit_kw":    (4017, "f32"),  # max power (kW)
}

# 4000..4018 inclusive -> 19 registers.
BLOCK_LENGTH = 19

# Operating state (read-back).
STATE_STANDBY = 0
STATE_CHARGING = 1
STATE_DISCHARGING = 2
STATE_FAULT = 3
STATE_NAMES = {
    STATE_STANDBY: "STANDBY",
    STATE_CHARGING: "CHARGING",
    STATE_DISCHARGING: "DISCHARGING",
    STATE_FAULT: "FAULT",
}

# Commanded mode (write).
CMD_STANDBY = 0
CMD_CHARGE = 1
CMD_DISCHARGE = 2

_F32 = ">f"


def _f32_to_regs(value: float) -> list[int]:
    hi, lo = struct.unpack(">HH", struct.pack(_F32, float(value)))
    return [hi, lo]


def _regs_to_f32(hi: int, lo: int) -> float:
    return struct.unpack(_F32, struct.pack(">HH", hi & 0xFFFF, lo & 0xFFFF))[0]


def decode_registers(regs: list[int], base: int = DEFAULT_BASE) -> dict:
    """Decode a raw holding-register block into native battery point values."""
    out: dict[str, float] = {}
    for name, (addr, ptype) in REGISTER_MAP.items():
        off = addr - base
        if ptype == "f32":
            out[name] = round(_regs_to_f32(regs[off], regs[off + 1]), 4)
        elif ptype == "u16":
            out[name] = regs[off] & 0xFFFF
        else:  # pragma: no cover
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
