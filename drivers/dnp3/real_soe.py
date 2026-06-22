"""Caching SOE handler for the real DNP3 master (P3-3, field-only).

opendnp3 delivers measurements through an ISOEHandler callback as the master scans
the outstation. This handler caches the latest value per (type, index) so the
driver's synchronous read_analog/read_binary can return the most recent scan.

This module imports `pydnp3` at top level and is therefore imported *lazily* —
only from RealDnp3Master.connect(), after the pydnp3 availability check. It is
exercised against real hardware / a DNP3 simulator, not in CI.
"""
from __future__ import annotations  # pragma: no cover

from pydnp3 import opendnp3  # pragma: no cover


class CachingSOEHandler(opendnp3.ISOEHandler):  # pragma: no cover
    def __init__(self):
        super().__init__()
        self._analog: dict[int, float] = {}
        self._binary: dict[int, bool] = {}

    # --- driver-facing accessors -----------------------------------------
    def analog(self, index: int, default: float = 0.0) -> float:
        return self._analog.get(index, default)

    def binary(self, index: int, default: bool = False) -> bool:
        return self._binary.get(index, default)

    # --- ISOEHandler callbacks (opendnp3 invokes these during scans) ------
    def Process(self, info, values):  # noqa: N802 (opendnp3 API name)
        for value, index in values:
            t = type(value).__name__
            if t == "Analog":
                self._analog[index] = float(value.value)
            elif t == "Binary":
                self._binary[index] = bool(value.value)

    def Start(self):  # noqa: N802
        pass

    def End(self):  # noqa: N802
        pass
