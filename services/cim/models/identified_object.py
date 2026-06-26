"""CIM IdentifiedObject -- the base every CIM class in this service
extends (per IEC 61970/61968: every modeled object has a stable mRID
identity plus an optional human name/description/aliasName).

Every CIM dataclass in this service uses @dataclass(kw_only=True) so a
required mRID field can coexist with subclasses' own optional fields
without Python's positional-field-ordering constraint forcing every
subclass field to also be required.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(kw_only=True)
class IdentifiedObject:
    mRID: str
    name: str | None = None
    description: str | None = None
    aliasName: str | None = None

    def to_dict(self) -> dict:
        return dict(self.__dict__)
