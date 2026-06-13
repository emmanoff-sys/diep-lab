"""BaseDriver — the 7-operation protocol-adapter interface.

A concrete driver implements the protocol-specific parts (connect, read,
normalize, execute); the shared Runner owns the MQTT publish/subscribe/ack loop
so individual drivers stay small. See DIEP_PROTOCOL_ADAPTER_FRAMEWORK.md §3.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from .normalize import normalize_canonical


@dataclass
class CommandResult:
    status: str            # "ACKED" | "FAILED"
    error: str | None = None


class BaseDriver(ABC):
    # Subclasses set the MQTT domain: meter | battery | solar | charger | microgrid.
    domain: str = "device"
    # Native-key -> canonical-key aliases used by the default normalize().
    aliases: dict[str, str] = {}

    def __init__(self, device_id: str, config: dict | None = None):
        self.device_id = device_id
        self.config = config or {}

    # --- protocol session -------------------------------------------------
    @abstractmethod
    def connect(self) -> None:
        """Open the protocol session (TCP/serial/CAN/WebSocket). Idempotent."""

    def disconnect(self) -> None:
        """Close the session. Override if cleanup is required."""

    # --- telemetry --------------------------------------------------------
    @abstractmethod
    def read_telemetry(self) -> dict:
        """Read a raw/native telemetry dict from the device."""

    def normalize(self, native: dict) -> dict:
        """Map native reading onto the canonical schema. Default uses `aliases`;
        override for non-trivial mappings (e.g. signed power, unit conversion)."""
        return normalize_canonical(native, self.aliases)

    # --- commands ---------------------------------------------------------
    @abstractmethod
    def execute_command(self, command_type: str, params: dict) -> CommandResult:
        """Execute a command against the device and return the result."""

    def supported_commands(self) -> set[str]:
        """Command vocabulary this device accepts (mirror ALLOWED_COMMANDS)."""
        return set()

    # --- topics -----------------------------------------------------------
    @property
    def base_topic(self) -> str:
        return f"diep/{self.domain}/{self.device_id}"

    @property
    def cmd_topic(self) -> str:
        return f"{self.base_topic}/cmd"

    @property
    def ack_topic(self) -> str:
        return f"{self.base_topic}/ack"
