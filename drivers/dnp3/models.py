"""DNP3 point model (mock) for a microgrid/RTU outstation.

A real DNP3 master polls an outstation's points by group/variation; here we model
the minimal point database a distribution RTU would expose, with group/variation
noted for realism. Measurements are Analog Inputs (g30), status is Binary Inputs
(g1); controls are CROB binary outputs (g12) and Analog Outputs (g41).
"""
from __future__ import annotations

# --- Analog Inputs (Group 30) — measurements --------------------------------
AI_VOLTAGE = 0       # V
AI_FREQUENCY = 1     # Hz
AI_PCC_KW = 2        # signed active power at point of common coupling (+import/-export)
AI_LOAD_KW = 3       # site load
AI_SOLAR_KW = 4      # site generation

# --- Binary Inputs (Group 1) — status ---------------------------------------
BI_GRID_CONNECTED = 0  # 1 = grid-connected, 0 = islanded

# --- Controls ----------------------------------------------------------------
BO_BREAKER = 0       # CROB (Group 12): 1 = close (grid-connect), 0 = trip (island)
AO_SETPOINT_KW = 0   # Analog Output (Group 41): PCC exchange setpoint (kW)

NOMINAL_VOLTAGE = 230.0
NOMINAL_HZ = 50.0
