"""DNP3 transport layer — pluggable link behind the Dnp3Driver (P3-3).

The driver is written against a small transport interface so the *same* governed
path (telemetry readback + island/grid_connect/set_setpoint controls) runs over
either:

  - the in-process **MockDnp3Outstation** (default, no dependency), or
  - a **RealDnp3Master** that speaks DNP3/TCP to field hardware via `pydnp3`
    (the Python binding for opendnp3).

Selection is by config — `transport: "mock" | "tcp"` (or inferred: host "mock"/
empty => mock, otherwise tcp). The mock stays the default so nothing changes for
the lab; pointing a device at real hardware is a config edit, not a code change.

The real master is intentionally lazy: `pydnp3` is imported only when the tcp
transport is actually selected, so the driver image needs the library only where
real outstations are deployed. A clear, actionable error is raised if it is
selected without the binding present.
"""
from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from . import models

logger = logging.getLogger("diep-driver.dnp3.transport")


@runtime_checkable
class Dnp3Transport(Protocol):
    """The link operations the Dnp3Driver needs. Both the mock outstation and the
    real master satisfy this (duck-typed)."""
    def connect(self) -> None: ...
    def close(self) -> None: ...
    def read_analog(self, index: int) -> float: ...
    def read_binary(self, index: int) -> int: ...
    def read_setpoint(self) -> float: ...
    def operate_binary(self, index: int, value: int) -> bool: ...
    def operate_analog(self, index: int, value: float) -> bool: ...


def make_transport(host: str, port: int, config: dict | None = None) -> Dnp3Transport:
    """Build the transport selected by config/host.

    transport: explicit "mock" | "tcp"; if absent, "mock" when host is "mock"/empty,
    else "tcp" (a real outstation address implies a real link).
    """
    config = config or {}
    kind = config.get("transport")
    if kind is None:
        kind = "mock" if host in ("mock", "", None) else "tcp"
    kind = str(kind).lower()

    if kind == "mock":
        from .sim import MockDnp3Outstation
        return MockDnp3Outstation()
    if kind in ("tcp", "real", "dnp3"):
        return RealDnp3Master(host, port, config)
    raise ValueError(f"unknown DNP3 transport '{kind}' (use 'mock' or 'tcp')")


class RealDnp3Master:
    """DNP3/TCP master over `pydnp3` (opendnp3). Talks to a real outstation at
    host:port: integrity-scans its points into a cache for reads, and issues CROB
    (breaker) / AnalogOutput (setpoint) controls with select-before-operate.

    This is the field-hardware integration point. It is exercised against real
    equipment (or a DNP3 outstation simulator), not in CI — the lab default is the
    mock. The pydnp3 object graph below follows the opendnp3 master example.
    """

    # DNP3 link/application addressing (override via config).
    DEFAULT_MASTER_ADDR = 1
    DEFAULT_OUTSTATION_ADDR = 1024

    def __init__(self, host: str, port: int, config: dict | None = None):
        self.host = host
        self.port = int(port)
        self.config = config or {}
        self.master_addr = int(self.config.get("master_addr", self.DEFAULT_MASTER_ADDR))
        self.outstation_addr = int(self.config.get("outstation_addr", self.DEFAULT_OUTSTATION_ADDR))
        self._mgr = None
        self._channel = None
        self._master = None
        self._soe = None  # SOEHandler caching the latest measurements

    # --- lifecycle --------------------------------------------------------
    def connect(self) -> None:
        try:
            from pydnp3 import opendnp3, asiodnp3, asiopal, openpal  # noqa: F401
        except ImportError as exc:  # pragma: no cover - depends on field deployment
            raise RuntimeError(
                "DNP3 'tcp' transport requires the 'pydnp3' binding (opendnp3). "
                "Install it where real outstations are reached (`pip install pydnp3`) "
                "or set the device's config transport to 'mock' for the simulator."
            ) from exc

        from pydnp3 import opendnp3, asiodnp3, asiopal, openpal
        from .real_soe import CachingSOEHandler  # local measurement cache

        self._soe = CachingSOEHandler()
        self._mgr = asiodnp3.DNP3Manager(1, asiodnp3.ConsoleLogger().Create())
        retry = asiopal.ChannelRetry().Default()
        self._channel = self._mgr.AddTCPClient(
            f"{self.host}:{self.port}", openpal.LogFilters(opendnp3.levels.NORMAL),
            retry, self.host, "0.0.0.0", self.port)
        stack = asiodnp3.MasterStackConfig()
        stack.link.LocalAddr = self.master_addr
        stack.link.RemoteAddr = self.outstation_addr
        self._master = self._channel.AddMaster(
            f"master-{self.host}", self._soe,
            asiodnp3.DefaultMasterApplication().Create(), stack)
        # Periodic integrity poll keeps the measurement cache current for reads.
        self._master.AddClassScan(
            opendnp3.ClassField().AllClasses(),
            openpal.TimeDuration().Seconds(int(self.config.get("scan_seconds", 5))),
            self._soe)
        self._master.Enable()
        logger.info("DNP3 master connected to outstation %s:%s (addr %s->%s)",
                    self.host, self.port, self.master_addr, self.outstation_addr)

    def close(self) -> None:  # pragma: no cover - field deployment
        try:
            if self._mgr is not None:
                self._mgr.Shutdown()
        finally:
            self._mgr = self._channel = self._master = self._soe = None

    # --- reads (from the integrity-scan cache) ----------------------------
    def read_analog(self, index: int) -> float:  # pragma: no cover - field deployment
        self._require_link()
        return float(self._soe.analog(index, default=0.0))

    def read_binary(self, index: int) -> int:  # pragma: no cover - field deployment
        self._require_link()
        return 1 if self._soe.binary(index, default=False) else 0

    def read_setpoint(self) -> float:  # pragma: no cover - field deployment
        # Real outstations expose the latched AO as an Analog Input mirror; if the
        # point is absent the readback is unverifiable (treated as a soft skip).
        self._require_link()
        return float(self._soe.analog(models.AI_PCC_KW, default=0.0))

    # --- controls (select-before-operate) ---------------------------------
    def operate_binary(self, index: int, value: int) -> bool:  # pragma: no cover
        from pydnp3 import opendnp3
        self._require_link()
        op = opendnp3.ControlRelayOutputBlock(
            opendnp3.OperationType.LATCH_ON if value else opendnp3.OperationType.LATCH_OFF)
        return self._operate(op, index)

    def operate_analog(self, index: int, value: float) -> bool:  # pragma: no cover
        from pydnp3 import opendnp3
        self._require_link()
        return self._operate(opendnp3.AnalogOutputDouble64(float(value)), index)

    def _operate(self, command, index: int) -> bool:  # pragma: no cover
        from pydnp3 import opendnp3
        # SELECT_AND_OPERATE: the outstation validates the point before actuating.
        result = self._master.SelectAndOperate(
            command, index, opendnp3.TaskConfig().Default())
        # result is a CommandTaskResult; success means the outstation confirmed.
        return "SUCCESS" in str(result).upper()

    def _require_link(self):  # pragma: no cover
        if self._master is None:
            raise RuntimeError("DNP3 master not connected; call connect() first")
