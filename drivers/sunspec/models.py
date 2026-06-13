"""SunSpec model layouts + a dependency-free decoder.

SunSpec exposes its data over Modbus holding registers as a self-describing map:

    [ "SunS" marker (2 regs) ] [ model_id, length, <length> data regs ] ... [ 0xFFFF ]

Each model's points sit at fixed offsets inside its data block, with values scaled
by a *scale factor* point ("sunssf") that is a signed power-of-ten exponent
(value = raw * 10**sf). This module captures the subset of the standard models
DIEP needs for a PV inverter and provides:

  - decode_model(): turn a model's raw register block into scaled native points;
  - discover(): walk the register image and locate each model;
  - build_image(): construct a realistic register image for the simulator.

Only the points DIEP maps onto its canonical telemetry are modelled. A production
edge build would use `pysunspec2`'s full SMDX model definitions; the offsets here
follow the SunSpec spec for models 1/103/123 so the decoder is wire-compatible
with a real inverter for those points.
"""
from __future__ import annotations

# SunSpec identity marker: bytes "SunS" -> two 16-bit registers.
SUNS_MARKER = (0x5375, 0x6E53)
END_MODEL_ID = 0xFFFF

# Default Modbus address of the "SunS" marker (the conventional SunSpec base).
DEFAULT_BASE = 40000


# --- model definitions -----------------------------------------------------
# Each point: name -> (offset_in_data_block, type, scale_factor_point|None).
# Types: "uint16", "int16", "acc32"(2 regs), "sunssf"(signed scale exponent),
#        "enum16", "string"(decorative, not decoded to a number).

COMMON_MODEL = {
    "id": 1,
    "length": 66,
    # Decorative identity block; not decoded numerically. Offsets per spec:
    # Mn[0:16] Md[16:32] Opt[32:40] Vr[40:48] SN[48:64] DA[64].
    "points": {},
}

# Model 103 — Inverter, three-phase, integer + scale factor.
INVERTER_MODEL_103 = {
    "id": 103,
    "length": 50,
    "points": {
        "A":      (0,  "uint16", "A_SF"),     # AC total current
        "A_SF":   (4,  "sunssf", None),
        "PhVphA": (8,  "uint16", "V_SF"),     # AC phase-A voltage
        "V_SF":   (11, "sunssf", None),
        "W":      (12, "int16",  "W_SF"),     # AC active power (W)
        "W_SF":   (13, "sunssf", None),
        "Hz":     (14, "uint16", "Hz_SF"),    # line frequency
        "Hz_SF":  (15, "sunssf", None),
        "WH":     (22, "acc32",  "WH_SF"),    # lifetime energy (Wh)
        "WH_SF":  (24, "sunssf", None),
        "DCW":    (29, "int16",  "DCW_SF"),   # DC power (W) — PV array production
        "DCW_SF": (30, "sunssf", None),
        "St":     (36, "enum16", None),       # operating state (4 = MPPT/producing)
    },
}

# Model 123 — Immediate inverter controls (curtailment).
CONTROLS_MODEL_123 = {
    "id": 123,
    "length": 24,
    "points": {
        "WMaxLimPct":    (5,  "uint16", "WMaxLimPct_SF"),  # active-power limit, % of WMax
        "WMaxLim_Ena":   (9,  "enum16", None),             # 0=disabled, 1=enabled
        "WMaxLimPct_SF": (22, "sunssf", None),
    },
}

# Inverter operating states (model 103 St enum).
ST_OFF = 1
ST_SLEEPING = 2
ST_STARTING = 3
ST_MPPT = 4        # normal production
ST_THROTTLED = 5   # producing but power-limited
ST_FAULT = 7


def _to_signed16(v: int) -> int:
    return v - 0x10000 if v & 0x8000 else v


def _read_point(data: list[int], spec) -> int:
    """Read a raw (unscaled) integer value for a point spec from a data block."""
    offset, ptype, _sf = spec
    if ptype == "uint16" or ptype == "enum16":
        return data[offset] & 0xFFFF
    if ptype == "int16" or ptype == "sunssf":
        return _to_signed16(data[offset])
    if ptype == "acc32":
        return ((data[offset] & 0xFFFF) << 16) | (data[offset + 1] & 0xFFFF)
    raise ValueError(f"unknown point type {ptype!r}")


def decode_model(model: dict, data: list[int]) -> dict:
    """Decode a model's raw register block into scaled native point values.

    Scale-factor and sunssf points are consumed (not emitted); every other point
    is returned as raw * 10**sf where sf is its referenced scale factor (0 if none).
    """
    points = model["points"]
    out: dict[str, float] = {}
    for name, spec in points.items():
        ptype = spec[1]
        if ptype == "sunssf":
            continue  # scale factors are applied, not reported
        raw = _read_point(data, spec)
        sf_point = spec[2]
        sf = 0
        if sf_point is not None and sf_point in points:
            sf = _read_point(data, points[sf_point])
        out[name] = raw * (10.0 ** sf) if ptype != "enum16" else raw
    return out


# --- discovery -------------------------------------------------------------
class ModelLocation:
    __slots__ = ("model_id", "data_addr", "length")

    def __init__(self, model_id: int, data_addr: int, length: int):
        self.model_id = model_id
        self.data_addr = data_addr   # Modbus address of the first data register
        self.length = length

    def __repr__(self):
        return f"ModelLocation(id={self.model_id}, addr={self.data_addr}, len={self.length})"


def discover(read_holding, base: int = DEFAULT_BASE, max_models: int = 32) -> dict[int, ModelLocation]:
    """Walk the SunSpec map via a `read_holding(addr, count)->list[int]` callable.

    Verifies the SunS marker, then follows [id,len] headers until the end model.
    Returns {model_id: ModelLocation}. Raises ValueError if the marker is absent.
    """
    marker = read_holding(base, 2)
    if tuple(marker[:2]) != SUNS_MARKER:
        raise ValueError(
            f"SunSpec marker not found at {base} (got {marker[:2]!r}); not a SunSpec device"
        )
    found: dict[int, ModelLocation] = {}
    addr = base + 2
    for _ in range(max_models):
        header = read_holding(addr, 2)
        model_id, length = header[0] & 0xFFFF, header[1] & 0xFFFF
        if model_id == END_MODEL_ID:
            break
        found[model_id] = ModelLocation(model_id, addr + 2, length)
        addr += 2 + length
    return found


# --- simulator image builder ----------------------------------------------
def _u16(v: int) -> int:
    return v & 0xFFFF


def _ss(v: int) -> int:
    """Encode a signed scale-factor exponent as a 16-bit register."""
    return v & 0xFFFF


def _pad_model(model: dict, data: dict[int, int]) -> list[int]:
    """Build a length-sized data block (zero-filled) from {offset: value}."""
    block = [0] * model["length"]
    for offset, value in data.items():
        block[offset] = _u16(value)
    return block


def build_image(*, ac_w: int, dc_w: int, voltage_v: float, current_a: float,
                hz: float, state: int, wmax_w: int,
                wmaxlimpct: float = 100.0, wmaxlim_ena: int = 0,
                base: int = DEFAULT_BASE) -> tuple[int, list[int]]:
    """Construct a SunSpec register image (PV inverter: common + 103 + 123).

    Values are encoded with fixed scale factors: W_SF=0 (W in watts),
    V_SF=-1 (0.1 V), A_SF=-2 (0.01 A), Hz_SF=-2 (0.01 Hz), DCW_SF=0,
    WMaxLimPct_SF=0 (whole %). Returns (base_addr, registers).
    """
    regs: list[int] = list(SUNS_MARKER)

    # --- common model (id 1) — identity only ---
    regs += [_u16(COMMON_MODEL["id"]), _u16(COMMON_MODEL["length"])]
    common = _pad_model(COMMON_MODEL, {})
    # "DIEP" manufacturer in the Mn string field for plausibility.
    common[0], common[1] = 0x4449, 0x4550  # "DI", "EP"
    regs += common

    # --- inverter model (id 103) ---
    regs += [_u16(INVERTER_MODEL_103["id"]), _u16(INVERTER_MODEL_103["length"])]
    inv = _pad_model(INVERTER_MODEL_103, {
        0:  _u16(round(current_a * 100)),   # A, A_SF=-2
        4:  _ss(-2),                        # A_SF
        8:  _u16(round(voltage_v * 10)),    # PhVphA, V_SF=-1
        11: _ss(-1),                        # V_SF
        12: _u16(ac_w),                     # W, W_SF=0
        13: _ss(0),                         # W_SF
        14: _u16(round(hz * 100)),          # Hz, Hz_SF=-2
        15: _ss(-2),                        # Hz_SF
        24: _ss(0),                         # WH_SF
        29: _u16(dc_w),                     # DCW, DCW_SF=0
        30: _ss(0),                         # DCW_SF
        36: _u16(state),                    # St
    })
    regs += inv

    # --- controls model (id 123) ---
    regs += [_u16(CONTROLS_MODEL_123["id"]), _u16(CONTROLS_MODEL_123["length"])]
    ctl = _pad_model(CONTROLS_MODEL_123, {
        5:  _u16(round(wmaxlimpct)),  # WMaxLimPct, SF=0
        9:  _u16(wmaxlim_ena),        # WMaxLim_Ena
        22: _ss(0),                   # WMaxLimPct_SF
    })
    regs += ctl

    # --- end model ---
    regs += [_u16(END_MODEL_ID), 0]
    return base, regs
