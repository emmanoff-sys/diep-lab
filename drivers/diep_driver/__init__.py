"""DIEP protocol-adapter SDK.

Shared framework for turning a field-device protocol into a standard DIEP MQTT
device. See DIEP_PROTOCOL_ADAPTER_FRAMEWORK.md. New code only — does not modify
any running service.
"""
from .base import BaseDriver, CommandResult
from .normalize import CANONICAL_FIELDS, normalize_canonical
from .registry import register, get_driver, available_drivers
from .runner import Runner

__all__ = [
    "BaseDriver",
    "CommandResult",
    "CANONICAL_FIELDS",
    "normalize_canonical",
    "register",
    "get_driver",
    "available_drivers",
    "Runner",
]
