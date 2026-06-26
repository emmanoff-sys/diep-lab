"""Pydantic response models, generated dynamically from the CIM
dataclasses in models/ -- one source of truth (the dataclass field
definitions) instead of 12 hand-duplicated field lists. FastAPI uses these
as `response_model` for every route: this is what makes "schema
validation" real rather than aspirational -- a mapping bug that produces a
wrong-shaped object fails response validation here, it doesn't just get
silently serialized.
"""
from __future__ import annotations

import typing

from pydantic import ConfigDict, create_model

from . import models

_CACHE: dict[type, type] = {}


def model_for(dataclass_cls: type) -> type:
    if dataclass_cls not in _CACHE:
        hints = typing.get_type_hints(dataclass_cls)
        fields = {name: (hints[name], None) for name in hints}
        _CACHE[dataclass_cls] = create_model(
            f"{dataclass_cls.__name__}Out",
            __config__=ConfigDict(from_attributes=True),
            **fields,
        )
    return _CACHE[dataclass_cls]


EndDeviceOut = model_for(models.EndDevice)
MeterOut = model_for(models.Meter)
AssetOut = model_for(models.Asset)
CustomerOut = model_for(models.Customer)
ServicePointOut = model_for(models.ServicePoint)
UsagePointOut = model_for(models.UsagePoint)
ConnectivityNodeOut = model_for(models.ConnectivityNode)
TerminalOut = model_for(models.Terminal)
TransformerOut = model_for(models.Transformer)
FeederOut = model_for(models.Feeder)
MeasurementOut = model_for(models.Measurement)
MeasurementValueOut = model_for(models.MeasurementValue)
