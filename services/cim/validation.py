"""CIM request-side schema-shape validation -- mirrors
services/mdm/validation.py's explicit-rejection-reason pattern.

FastAPI's own Pydantic response models (see api.py) handle response-shape
validation for free; this module covers what Pydantic doesn't: validating
query-parameter VALUES against this service's own registries (known
profile names, known node_types, ISO date parsing) before a mapping
function ever runs, so a bad request fails with one clear reason rather
than a confusing downstream error.
"""
from __future__ import annotations

from datetime import datetime

KNOWN_PROFILES = ("metering", "network", "measurements", "full")
KNOWN_FORMATS = ("json", "xml")
# Must stay in sync with grid_nodes' CHECK constraint (sql/013_network_model.sql,
# extended by sql/021_network_electrical.sql) -- a living set, not a permanent copy.
KNOWN_NODE_TYPES = (
    "substation", "feeder", "transformer", "switch", "recloser", "bus", "meter", "der", "load",
)


class CimValidationError(ValueError):
    def __init__(self, reason: str, detail: str):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}")


def validate_profile(profile: str) -> str:
    if profile not in KNOWN_PROFILES:
        raise CimValidationError("invalid_profile", f"{profile!r} not in {KNOWN_PROFILES}")
    return profile


def validate_format(fmt: str) -> str:
    if fmt not in KNOWN_FORMATS:
        raise CimValidationError("invalid_format", f"{fmt!r} not in {KNOWN_FORMATS}")
    return fmt


def validate_node_type(node_type: str | None) -> str | None:
    if node_type is not None and node_type not in KNOWN_NODE_TYPES:
        raise CimValidationError(
            "invalid_node_type",
            f"{node_type!r} not in {KNOWN_NODE_TYPES}",
        )
    return node_type


def validate_iso_timestamp(value: str | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise CimValidationError(
            "invalid_timestamp", f"{field_name}={value!r} is not a valid ISO8601 timestamp",
        ) from None


def validate_limit(limit: int, max_limit: int) -> int:
    if limit < 1 or limit > max_limit:
        raise CimValidationError("invalid_limit", f"limit={limit} must be between 1 and {max_limit}")
    return limit
