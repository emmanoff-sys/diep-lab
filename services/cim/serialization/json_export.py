"""Platform-native JSON export. This is **not** a claim of conformance to
any official CIM-JSON-LD exchange profile (no access to verify against
one) -- it's a clean, stable JSON shape for the objects this service maps.
See LIMITATIONS.md.
"""
from __future__ import annotations

import json

from ..models.identified_object import IdentifiedObject


def to_json(objects: list[IdentifiedObject], object_type: str) -> str:
    return json.dumps(
        {"objectType": object_type, "count": len(objects), "items": [o.to_dict() for o in objects]},
        default=str,
        indent=2,
    )
