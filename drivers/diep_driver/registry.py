"""Driver registry/factory — maps a protocol name to a BaseDriver subclass so an
edge runner can instantiate drivers from config (e.g. {"protocol": "sunspec"}).
"""
from __future__ import annotations

from typing import Type

from .base import BaseDriver

_REGISTRY: dict[str, Type[BaseDriver]] = {}


def register(name: str):
    """Class decorator: @register('sunspec') class SunSpecDriver(BaseDriver): ..."""
    def _wrap(cls: Type[BaseDriver]):
        _REGISTRY[name] = cls
        return cls
    return _wrap


def get_driver(name: str) -> Type[BaseDriver]:
    if name not in _REGISTRY:
        raise KeyError(f"Unknown driver '{name}'. Available: {sorted(_REGISTRY)}")
    return _REGISTRY[name]


def available_drivers() -> list[str]:
    return sorted(_REGISTRY)
